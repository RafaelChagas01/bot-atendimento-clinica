import base64
import hashlib
import hmac
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

TOKEN_TTL = 2 * 60 * 60
MAX_TOKEN_LEN = 8000
RETENTION_DAYS = 30


def sign_state(state: dict, secret: str, now: float | None = None) -> str:
    body = {"s": state, "exp": int((now or time.time()) + TOKEN_TTL)}
    payload = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).decode().rstrip("=")
    mac = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{mac}"


def read_state(token: str | None, secret: str, now: float | None = None) -> dict | None:
    """Devolve o estado se a assinatura bater e nao tiver expirado."""
    if not token or len(token) > MAX_TOKEN_LEN or token.count(".") != 1:
        return None
    payload, mac = token.split(".")
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected):
        return None
    try:
        body = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except ValueError:
        return None
    if not isinstance(body, dict) or body.get("exp", 0) < (now or time.time()):
        return None
    state = body.get("s")
    return state if isinstance(state, dict) else None


class ConversationStore:
    """Estado das conversas do WhatsApp em SQLite. O telefone e guardado so como hash."""

    def __init__(self, path: Path, secret: str):
        self.path = path
        self.secret = secret.encode()
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS conversations (key TEXT PRIMARY KEY, state TEXT NOT NULL, updated_at INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS processed (message_id TEXT PRIMARY KEY, created_at INTEGER NOT NULL)")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _key(self, phone: str) -> str:
        return hmac.new(self.secret, phone.encode(), hashlib.sha256).hexdigest()

    def get(self, phone: str) -> dict:
        with self._connect() as db:
            row = db.execute("SELECT state FROM conversations WHERE key = ?", (self._key(phone),)).fetchone()
        return json.loads(row[0]) if row else {}

    def save(self, phone: str, state: dict) -> None:
        now = int(time.time())
        with self._connect() as db:
            db.execute(
                "INSERT INTO conversations (key, state, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at",
                (self._key(phone), json.dumps(state, ensure_ascii=False), now),
            )
            cutoff = now - RETENTION_DAYS * 86400
            db.execute("DELETE FROM conversations WHERE updated_at < ?", (cutoff,))
            db.execute("DELETE FROM processed WHERE created_at < ?", (cutoff,))

    def first_time(self, message_id: str) -> bool:
        """O WhatsApp reenvia webhooks; isso evita responder duas vezes."""
        try:
            with self._connect() as db:
                db.execute("INSERT INTO processed (message_id, created_at) VALUES (?, ?)", (message_id, int(time.time())))
            return True
        except sqlite3.IntegrityError:
            return False
