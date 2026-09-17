import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Le o .env local sem sobrescrever variaveis que ja existem no ambiente."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    model: str = field(default_factory=lambda: _env("CLAUDE_MODEL", "claude-opus-5"))

    # sem STATE_SECRET os tokens so valem enquanto o processo estiver vivo
    state_secret: str = field(default_factory=lambda: _env("STATE_SECRET") or secrets.token_hex(32))

    whatsapp_token: str = field(default_factory=lambda: _env("WHATSAPP_TOKEN"))
    whatsapp_phone_id: str = field(default_factory=lambda: _env("WHATSAPP_PHONE_NUMBER_ID"))
    whatsapp_verify_token: str = field(default_factory=lambda: _env("WHATSAPP_VERIFY_TOKEN"))
    whatsapp_app_secret: str = field(default_factory=lambda: _env("WHATSAPP_APP_SECRET"))
    whatsapp_api_version: str = field(default_factory=lambda: _env("WHATSAPP_API_VERSION", "v23.0"))

    knowledge_file: Path = ROOT / "knowledge" / "odonto-prado.md"
    database_file: Path = field(default_factory=lambda: Path(_env("DATABASE_FILE", str(ROOT / "conversas.db"))))

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def whatsapp_enabled(self) -> bool:
        return all((self.whatsapp_token, self.whatsapp_phone_id, self.whatsapp_verify_token, self.whatsapp_app_secret))


settings = Settings()
