"""Load settings from environment variables. Secrets never live in code."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

OFFICIAL_LINKS = {
    "telegram_group": "https://t.me/ourbitfarsi",
    "telegram_channel": "https://t.me/ourbit_persian",
    "instagram": "https://www.instagram.com/ourbitzh?igsh=bG5tOTEwNmttcHVq",
    "twitter": "https://x.com/ourbit_farsi?s=21",
}

TELEGRAM_CAPTION_LIMIT = 1024
TELEGRAM_MESSAGE_LIMIT = 4096


def _load_env_file() -> None:
    candidates = [
        Path.cwd() / ".env",
        PROJECT_ROOT / ".env",
        Path(__file__).resolve().parent / ".env",
    ]
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=False)
            return
    load_dotenv(override=False)


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(
            f"Missing required environment variable {name}. "
            "Copy .env.example to .env and fill in the values."
        )
    return value


def parse_peer(value: str) -> str | int:
    """Accept @username, username, or numeric channel/user id."""
    raw = value.strip()
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    phone_number: str
    source_channel: str | int
    destination_channel: str | int
    spot_notify_user: str | int | None = None
    session_name: str = "ourbit_session"
    telegram_2fa_password: str | None = None
    translator: str = "groq"
    groq_api_key: str | None = None
    groq_model: str = "qwen/qwen3.6-27b"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    db_path: Path = field(default_factory=lambda: PROJECT_ROOT / "bot.db")
    official_links: dict[str, str] = field(default_factory=lambda: dict(OFFICIAL_LINKS))

    @property
    def session_path(self) -> str:
        return str(PROJECT_ROOT / self.session_name)


def load_config() -> Config:
    _load_env_file()

    api_id_raw = _require("API_ID")
    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise ValueError("API_ID must be an integer.") from exc

    two_fa = os.getenv("TELEGRAM_2FA_PASSWORD", "").strip() or None
    translator = os.getenv("TRANSLATOR", "groq").strip().lower() or "groq"
    groq_key = os.getenv("GROQ_API_KEY", "").strip() or None
    groq_model = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b").strip() or "qwen/qwen3.6-27b"
    openai_key = os.getenv("OPENAI_API_KEY", "").strip() or None
    spot_notify_raw = os.getenv("SPOT_NOTIFY_USER", "").strip()
    spot_notify_user = parse_peer(spot_notify_raw) if spot_notify_raw else None
    db_raw = os.getenv("DB_PATH", "").strip()
    db_path = Path(db_raw) if db_raw else PROJECT_ROOT / "bot.db"
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path

    return Config(
        api_id=api_id,
        api_hash=_require("API_HASH"),
        phone_number=_require("PHONE_NUMBER"),
        source_channel=parse_peer(_require("SOURCE_CHANNEL")),
        destination_channel=parse_peer(_require("DESTINATION_CHANNEL")),
        spot_notify_user=spot_notify_user,
        session_name=os.getenv("SESSION_NAME", "ourbit_session").strip() or "ourbit_session",
        telegram_2fa_password=two_fa,
        translator=translator,
        groq_api_key=groq_key,
        groq_model=groq_model,
        openai_api_key=openai_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        db_path=db_path,
    )
