import hmac
import json
import logging
import os
import re

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .answer import build_answerer
from .config import ROOT, settings
from .engine import Engine
from .knowledge import load_sections
from .ratelimit import SlidingWindow
from .state import ConversationStore, read_state, sign_state
from .text import clean_input
from .whatsapp import incoming_texts, send_text, valid_signature

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("bot")

MAX_BODY_BYTES = 64 * 1024
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}

sections = load_sections(settings.knowledge_file)
engine = Engine(build_answerer(sections, settings.anthropic_api_key, settings.model))
demo_limit = SlidingWindow(limit=20, seconds=60)
webhook_limit = SlidingWindow(limit=120, seconds=60)
_store: ConversationStore | None = None

app = FastAPI(title="Bot de atendimento Odonto Prado", docs_url=None, redoc_url=None, openapi_url=None)


def store() -> ConversationStore:
    global _store
    if _store is None:
        _store = ConversationStore(settings.database_file, settings.state_secret)
    return _store


def client_ip(request: Request) -> str:
    # na Vercel o IP real vem nesse header, preenchido pela propria plataforma
    forwarded = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "desconhecido")


@app.middleware("http")
async def guard(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > MAX_BODY_BYTES):
        return JSONResponse({"erro": "requisição grande demais"}, status_code=413)
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


class DemoMessage(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    state: str | None = Field(default=None, max_length=8000)


@app.get("/api/health")
def health():
    return {"ok": True, "ia": settings.ai_enabled, "whatsapp": settings.whatsapp_enabled}


@app.post("/api/demo/message")
def demo_message(body: DemoMessage, request: Request):
    if not demo_limit.allow(client_ip(request)):
        raise HTTPException(status_code=429, detail="Muitas mensagens seguidas. Espera um minuto.")

    text = clean_input(body.text)
    if not text:
        raise HTTPException(status_code=422, detail="Mensagem vazia.")

    previous = read_state(body.state, settings.state_secret)
    reply = engine.handle(text, previous)

    return {
        "messages": reply.messages,
        "state": sign_state(reply.state, settings.state_secret),
        "handoff": reply.handoff,
        "mode": reply.mode,
        "request": reply.request,
    }


@app.get("/webhook/whatsapp")
def whatsapp_verify(request: Request):
    if not settings.whatsapp_enabled:
        raise HTTPException(status_code=404)
    params = request.query_params
    token = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge", "")
    if params.get("hub.mode") == "subscribe" and hmac_equal(token, settings.whatsapp_verify_token) and re.fullmatch(r"\d{1,20}", challenge):
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403)


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    if not settings.whatsapp_enabled:
        raise HTTPException(status_code=404)
    if not webhook_limit.allow(client_ip(request)):
        raise HTTPException(status_code=429)

    raw = await request.body()
    if not valid_signature(raw, request.headers.get("x-hub-signature-256"), settings.whatsapp_app_secret):
        raise HTTPException(status_code=401)

    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400)

    db = store()
    async with httpx.AsyncClient() as client:
        for msg_id, phone, body in incoming_texts(payload):
            if not db.first_time(msg_id):
                continue
            text = clean_input(body)
            if not text:
                continue
            reply = await run_in_threadpool(engine.handle, text, db.get(phone))
            db.save(phone, reply.state)
            if reply.request:
                log.info("pedido para a recepcao: %s", reply.request.get("procedure"))
            for message in reply.messages:
                await send_text(
                    client,
                    token=settings.whatsapp_token,
                    phone_id=settings.whatsapp_phone_id,
                    version=settings.whatsapp_api_version,
                    to=phone,
                    body=message,
                )
    return {"ok": True}


def hmac_equal(a: str, b: str) -> bool:
    return bool(a) and hmac.compare_digest(a.encode(), b.encode())


# na Vercel a pasta public e servida direto pela CDN
if not os.environ.get("VERCEL") and (ROOT / "public").is_dir():
    app.mount("/", StaticFiles(directory=ROOT / "public", html=True), name="public")
