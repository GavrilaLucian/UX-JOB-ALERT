"""
Loads configuration from config/settings.json and config/companies.json,
and pulls secrets from environment variables (populated from GitHub Secrets
in CI, or from a local .env file for local runs).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_dotenv_if_present() -> None:
    """Lightweight .env loader for local runs (no extra dependency)."""
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class Secrets:
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    google_cse_api_key: str | None = None
    google_cse_engine_id: str | None = None
    anthropic_api_key: str | None = None

    @classmethod
    def from_env(cls) -> "Secrets":
        return cls(
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID"),
            google_cse_api_key=os.environ.get("SEARCH_API_KEY"),
            google_cse_engine_id=os.environ.get("SEARCH_ENGINE_ID"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )


@dataclass
class AppConfig:
    settings: dict[str, Any] = field(default_factory=dict)
    companies: list[dict[str, Any]] = field(default_factory=list)
    secrets: Secrets = field(default_factory=Secrets)

    # convenience accessors -------------------------------------------------
    @property
    def relevance_threshold(self) -> int:
        return int(self.settings.get("relevance_threshold", 60))

    @property
    def timezone(self) -> str:
        return self.settings.get("timezone", "Europe/Bucharest")

    @property
    def max_jobs_per_message(self) -> int:
        return int(self.settings.get("max_jobs_per_telegram_message", 6))

    @property
    def ai_filter_cfg(self) -> dict:
        return self.settings.get("ai_filter", {})

    @property
    def search_cfg(self) -> dict:
        return self.settings.get("search", {})

    @property
    def storage_cfg(self) -> dict:
        return self.settings.get("storage", {"seen_jobs_path": "data/seen_jobs.json"})


def load_config(config_dir: Path = CONFIG_DIR) -> AppConfig:
    _load_dotenv_if_present()
    settings = _load_json(config_dir / "settings.json")
    companies_raw = _load_json(config_dir / "companies.json")
    companies = companies_raw.get("companies", [])
    secrets = Secrets.from_env()
    return AppConfig(settings=settings, companies=companies, secrets=secrets)
