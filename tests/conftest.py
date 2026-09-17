from datetime import date

import pytest

from app.answer import OfflineAnswerer
from app.config import settings
from app.engine import Engine
from app.knowledge import load_sections

TODAY = date(2026, 9, 16)  # quarta-feira


@pytest.fixture(scope="session")
def sections():
    return load_sections(settings.knowledge_file)


@pytest.fixture
def engine(sections):
    return Engine(OfflineAnswerer(sections), today=lambda: TODAY)


def talk(engine, *messages):
    state, reply = None, None
    for text in messages:
        reply = engine.handle(text, state)
        state = reply.state
    return reply
