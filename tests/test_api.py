import dataclasses
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.ratelimit import SlidingWindow


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "demo_limit", SlidingWindow(limit=100, seconds=60))
    return TestClient(main.app)


def send(client, text, state=None):
    return client.post("/api/demo/message", json={"text": text, "state": state})


def test_demo_conversation_keeps_state(client):
    first = send(client, "2").json()
    assert "nome completo" in first["messages"][0]
    second = send(client, "Ana Lima", first["state"]).json()
    assert "motivo da consulta" in second["messages"][0]


def test_tampered_state_starts_over(client):
    first = send(client, "2").json()
    reply = send(client, "Ana Lima", first["state"][:-4] + "abcd").json()
    assert "nome completo" not in reply["messages"][0]


def test_input_limits(client):
    assert send(client, "").status_code == 422
    assert send(client, "a" * 501).status_code == 422
    assert client.post("/api/demo/message", content=b"x" * 70000, headers={"content-type": "application/json"}).status_code == 413


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(main, "demo_limit", SlidingWindow(limit=2, seconds=60))
    client = TestClient(main.app)
    codes = [send(client, "oi").status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_security_headers(client):
    headers = send(client, "oi").headers
    assert "script-src 'self'" in headers["content-security-policy"]
    assert headers["x-frame-options"] == "DENY"
    assert client.get("/docs").status_code == 404


def test_webhook_is_off_without_credentials(client):
    assert client.get("/webhook/whatsapp").status_code == 404
    assert client.post("/webhook/whatsapp", json={}).status_code == 404


@pytest.fixture
def whatsapp(monkeypatch, tmp_path):
    configured = dataclasses.replace(
        main.settings,
        whatsapp_token="token",
        whatsapp_phone_id="123",
        whatsapp_verify_token="verifica",
        whatsapp_app_secret="app-secret",
        database_file=tmp_path / "conversas.db",
    )
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(main, "_store", None)
    sent = []

    async def fake_send(client, **kwargs):
        sent.append(kwargs)
        return True

    monkeypatch.setattr(main, "send_text", fake_send)
    return TestClient(main.app), sent


def payload(msg_id="wamid.1", text="tem estacionamento?"):
    return {"entry": [{"changes": [{"value": {"messages": [
        {"id": msg_id, "from": "5531999990000", "type": "text", "text": {"body": text}},
        {"id": "wamid.img", "from": "5531999990000", "type": "image"},
    ]}}]}]}


def signed(body: dict, secret="app-secret"):
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {"x-hub-signature-256": sig, "content-type": "application/json"}


def test_webhook_verification(whatsapp):
    client, _ = whatsapp
    ok = client.get("/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verifica", "hub.challenge": "8812"})
    assert ok.status_code == 200 and ok.text == "8812"
    bad = client.get("/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "errado", "hub.challenge": "8812"})
    assert bad.status_code == 403


def test_webhook_rejects_bad_signature(whatsapp):
    client, sent = whatsapp
    raw, headers = signed(payload(), secret="outro")
    assert client.post("/webhook/whatsapp", content=raw, headers=headers).status_code == 401
    assert sent == []


def test_webhook_answers_once(whatsapp):
    client, sent = whatsapp
    raw, headers = signed(payload())
    assert client.post("/webhook/whatsapp", content=raw, headers=headers).status_code == 200
    assert client.post("/webhook/whatsapp", content=raw, headers=headers).status_code == 200
    assert "estacionamento rotativo" in sent[0]["body"]
    assert all(m["to"] == "5531999990000" for m in sent)
    assert len(sent) == 2  # resposta + "posso ajudar com mais alguma coisa", sem duplicar
