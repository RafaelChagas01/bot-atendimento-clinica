from dataclasses import dataclass
from pathlib import Path

from .text import normalize, tokens

# sinonimos comuns em mensagem de paciente
SYNONYMS = {
    "valor": "preco", "custa": "preco", "custo": "preco", "quanto": "preco", "precos": "preco",
    "planos": "plano", "convenios": "convenio",
    "aberto": "abre", "funcionamento": "funciona", "horarios": "horario",
    "localizado": "localizacao",
    "doendo": "dor", "doi": "dor", "dores": "dor",
    "parcelado": "parcelar", "parcelamento": "parcelar",
    "criancas": "crianca", "filhos": "filho",
}


@dataclass(frozen=True)
class Section:
    title: str
    tags: tuple[str, ...]
    body: str

    def terms(self) -> set[str]:
        words = set(tokens(self.title))
        for tag in self.tags:
            words.update(tokens(tag))
        return {SYNONYMS.get(w, w) for w in words}


def load_sections(path: Path) -> list[Section]:
    sections: list[Section] = []
    title, tags, body = None, (), []

    def flush():
        if title:
            sections.append(Section(title, tags, " ".join(body).strip()))

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            flush()
            title, tags, body = line[3:].strip(), (), []
        elif title and line.startswith("tags:"):
            tags = tuple(t.strip() for t in line[5:].split(",") if t.strip())
        elif title and line.strip():
            body.append(line.strip())
    flush()
    return sections


def search(sections: list[Section], question: str, limit: int = 3) -> list[tuple[Section, float]]:
    words = {SYNONYMS.get(w, w) for w in tokens(question)}
    if not words:
        return []

    text = normalize(question)
    all_terms = [section.terms() for section in sections]
    # palavra que aparece em muitas secoes pesa menos
    frequency = {w: sum(w in terms for terms in all_terms) for w in words}

    scored = []
    for section, terms in zip(sections, all_terms):
        score = sum(1 / frequency[w] for w in words & terms)
        # frase inteira de tag dentro da pergunta vale mais ("dor de dente", "primeira consulta")
        score += sum(1.5 for tag in section.tags if " " in tag and normalize(tag) in text)
        if score:
            scored.append((section, score / (len(words) ** 0.5)))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]
