from datetime import date

from app.answer import Answer
from app.engine import MAX_AI_CALLS, Engine, parse_day

from .conftest import TODAY, talk


def test_greeting_shows_menu(engine):
    reply = talk(engine, "oi")
    assert "1. Tirar uma dúvida" in reply.messages[-1]
    assert reply.state["step"] == "menu"


def test_question_goes_straight_to_answer(engine):
    reply = talk(engine, "vocês aceitam unimed?")
    assert "Unimed Odonto não está credenciado" in reply.messages[0]
    assert reply.mode == "offline"


def test_full_booking(engine):
    reply = talk(engine, "quero marcar", "joão da silva", "limpeza", "sexta", "tarde")
    assert "João da Silva" in reply.messages[0]
    assert "sexta, 18/09, de tarde" in reply.messages[0]

    done = engine.handle("sim", reply.state)
    assert done.handoff is True
    assert done.request == {"name": "João da Silva", "procedure": "Limpeza", "day": "2026-09-18", "period": "tarde"}


def test_booking_validates_input(engine):
    assert "sobrenome" in talk(engine, "2", "joao").messages[0]
    assert "número de 1 a 5" in talk(engine, "2", "Ana Lima", "quero um cafe").messages[0]
    assert "fechada" in talk(engine, "2", "Ana Lima", "1", "domingo").messages[0]
    assert "não consegui entender" in talk(engine, "2", "Ana Lima", "1", "semana que vem").messages[0].lower()
    assert "60 dias" in talk(engine, "2", "Ana Lima", "1", "10/12").messages[0]


def test_saturday_is_morning_only(engine):
    reply = talk(engine, "2", "Ana Lima", "avaliação", "sábado")
    assert reply.state["step"] == "book_confirm"
    assert "de manhã" in reply.messages[0]


def test_urgency_goes_to_human(engine):
    reply = talk(engine, "2", "Ana Lima", "5")
    assert reply.handoff is True
    assert reply.request["urgent"] is True
    assert "pronto-socorro" in reply.messages[1]


def test_saying_no_restarts_booking(engine):
    reply = talk(engine, "2", "Ana Lima", "2", "amanhã", "manhã", "não")
    assert reply.state["step"] == "book_name"


def test_human_and_reset(engine):
    reply = talk(engine, "quero falar com uma pessoa")
    assert reply.handoff is True
    assert "aguardar" in engine.handle("oi?", reply.state).messages[0]
    assert engine.handle("menu", reply.state).state["step"] == "menu"


def test_history_is_capped(engine):
    reply = talk(engine, *["tem estacionamento?"] * 10)
    assert len(reply.state["history"]) == 6
    assert reply.state["history"][0]["role"] == "user"


def test_ai_calls_are_capped():
    class FakeAI:
        mode = "ia"

        def __init__(self):
            self.calls = 0
            self.fallback = type("Off", (), {"mode": "offline", "answer": lambda s, q, h: Answer("local", True, "offline")})()

        def answer(self, question, history):
            self.calls += 1
            return Answer("ia", True, "ia")

    ai = FakeAI()
    engine = Engine(ai, today=lambda: TODAY)
    reply = talk(engine, *["qual o horário?"] * (MAX_AI_CALLS + 3))
    assert ai.calls == MAX_AI_CALLS
    assert reply.mode == "offline"


def test_parse_day():
    assert parse_day("hoje", TODAY) == TODAY
    assert parse_day("amanhã", TODAY) == date(2026, 9, 17)
    assert parse_day("sexta-feira", TODAY) == date(2026, 9, 18)
    assert parse_day("quarta", TODAY) == date(2026, 9, 23)
    assert parse_day("25/09", TODAY) == date(2026, 9, 25)
    assert parse_day("10/01", TODAY) == date(2027, 1, 10)
    assert parse_day("31/02", TODAY) is None
    assert parse_day("qualquer dia", TODAY) is None
