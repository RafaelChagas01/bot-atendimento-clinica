import re
import unicodedata

STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "de", "da", "do", "das", "dos", "e", "em", "no", "na",
    "nos", "nas", "pra", "para", "por", "com", "que", "qual", "quais", "se", "eu", "voce",
    "vcs", "vc", "voces", "meu", "minha", "tem", "ter", "ou", "me", "gostaria", "queria",
    "saber", "oi", "ola", "bom", "boa", "favor", "pf", "pfv", "ai", "la", "isso", "esse",
    "essa", "ja", "tudo", "bem", "pode", "ser", "posso", "consigo",
}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.lower())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", value)).strip()


def tokens(value: str) -> list[str]:
    return [t for t in normalize(value).split() if t not in STOPWORDS and len(t) > 1]


def clean_input(value: str, max_len: int = 500) -> str:
    """Tira caracteres de controle e corta no limite."""
    value = "".join(c for c in value if c in "\n\t" or unicodedata.category(c)[0] != "C")
    return value.strip()[:max_len]
