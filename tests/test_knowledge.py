import pytest

from app.answer import OfflineAnswerer
from app.knowledge import search


@pytest.mark.parametrize("question, title", [
    ("vocês aceitam unimed?", "Convênios aceitos"),
    ("quanto custa a limpeza?", "Limpeza"),
    ("quero remarcar minha consulta", "Remarcar ou cancelar"),
    ("meu filho de 5 anos pode ser atendido?", "Atendimento infantil"),
    ("to com muita dor de dente", "Urgência e dor"),
    ("preciso levar raio x?", "O que levar na consulta"),
    ("abre sábado?", "Horário de funcionamento"),
    ("parcela no cartão?", "Formas de pagamento"),
])
def test_finds_the_right_section(sections, question, title):
    results = search(sections, question, limit=1)
    assert results and results[0][0].title == title


@pytest.mark.parametrize("question", ["qual a capital da frança?", "me conta uma piada", "quanto custa"])
def test_offline_does_not_guess(sections, question):
    assert OfflineAnswerer(sections).answer(question, []).found is False


def test_all_sections_have_tags_and_body(sections):
    assert len(sections) >= 10
    for section in sections:
        assert section.tags and len(section.body) > 30
