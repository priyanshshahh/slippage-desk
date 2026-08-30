"""Configuration and credential loading."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Credentials:
    api_key: str
    secret_key: str
    paper: bool
    options_feed: str

    @classmethod
    def from_env(cls) -> "Credentials":
        key = os.getenv("ALPACA_API_KEY", "").strip()
        secret = os.getenv("ALPACA_SECRET_KEY", "").strip()
        if not key or not secret:
            raise RuntimeError(
                "ALPACA_API_KEY / ALPACA_SECRET_KEY missing. "
                "Copy .env.example to .env and fill both in."
            )
        return cls(
            api_key=key,
            secret_key=secret,
            paper=os.getenv("ALPACA_PAPER", "true").lower() != "false",
            options_feed=os.getenv("ALPACA_OPTIONS_FEED", "indicative").lower(),
        )


def load_config(path: Path | None = None) -> dict:
    path = path or (ROOT / "config.yaml")
    with open(path) as fh:
        return yaml.safe_load(fh)
