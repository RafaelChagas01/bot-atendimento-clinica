import hashlib
import hmac
import logging

import httpx

log = logging.getLogger("bot.whatsapp")

MAX_BODY = 4096


def valid_signature(raw_body: bytes, header: str | None, app_secret: str) -> bool:
    """Confere o X-Hub-Signature-256 que a Meta manda em todo webhook."""
    if not header or not header.startswith("sha256=") or not app_secret:
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header[7:], expected)


def incoming_texts(payload: dict) -> list[tuple[str, str, str]]:
    """Extrai (id, telefone, texto) das mensagens de texto. Outros tipos sao ignorados."""
    found = []
    for entry in payload.get("entry", []) if isinstance(payload, dict) else []:
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []) or []:
                if msg.get("type") != "text":
                    continue
                msg_id, phone = msg.get("id"), msg.get("from")
                body = (msg.get("text") or {}).get("body")
                if isinstance(msg_id, str) and isinstance(phone, str) and phone.isdigit() and isinstance(body, str):
                    found.append((msg_id, phone, body))
    return found


async def send_text(client: httpx.AsyncClient, *, token: str, phone_id: str, version: str, to: str, body: str) -> bool:
    url = f"https://graph.facebook.com/{version}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body[:MAX_BODY]},
    }
    try:
        resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=15)
    except httpx.HTTPError as exc:
        log.error("falha ao enviar mensagem: %s", type(exc).__name__)
        return False
    if resp.status_code >= 400:
        # nao loga o corpo: pode ter dado do paciente
        log.error("WhatsApp respondeu %s", resp.status_code)
        return False
    return True
