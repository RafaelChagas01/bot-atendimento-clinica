import sqlite3

from app.ratelimit import SlidingWindow
from app.state import TOKEN_TTL, ConversationStore, read_state, sign_state

SECRET = "segredo-de-teste"


def test_round_trip():
    token = sign_state({"step": "faq"}, SECRET)
    assert read_state(token, SECRET) == {"step": "faq"}


def test_rejects_tampered_or_foreign_tokens():
    token = sign_state({"step": "faq"}, SECRET)
    payload, mac = token.split(".")
    assert read_state(payload[:-2] + "AA." + mac, SECRET) is None
    assert read_state(token, "outro-segredo") is None
    assert read_state("lixo", SECRET) is None
    assert read_state("a" * 9000, SECRET) is None
    assert read_state(None, SECRET) is None


def test_expired_token():
    token = sign_state({"step": "faq"}, SECRET, now=1000)
    assert read_state(token, SECRET, now=1000 + TOKEN_TTL + 1) is None


def test_store_hashes_phone_and_dedupes(tmp_path):
    db = tmp_path / "conversas.db"
    store = ConversationStore(db, SECRET)
    store.save("5531999990000", {"step": "menu"})
    assert store.get("5531999990000") == {"step": "menu"}
    assert store.get("5531888880000") == {}

    con = sqlite3.connect(db)
    keys = [row[0] for row in con.execute("SELECT key FROM conversations")]
    con.close()
    assert "5531999990000" not in keys[0]

    assert store.first_time("wamid.1") is True
    assert store.first_time("wamid.1") is False


def test_sliding_window():
    limit = SlidingWindow(limit=2, seconds=10)
    assert limit.allow("ip", now=0) and limit.allow("ip", now=1)
    assert not limit.allow("ip", now=2)
    assert limit.allow("outro-ip", now=2)
    assert limit.allow("ip", now=12)
