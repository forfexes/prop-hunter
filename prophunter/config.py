"""Central configuration loaded from environment variables."""
from __future__ import annotations

import os
from typing import List


def _csv_env(key: str) -> List[str]:
    return [k.strip() for k in os.environ.get(key, "").split(",") if k.strip()]


# ─── API Keys (rotated) ──────────────────────────────────────────────
ODDS_API_KEYS: List[str] = _csv_env("ODDS_API_KEY")
GEMINI_KEYS: List[str] = _csv_env("GEMINI_API_KEY")
GROQ_KEYS: List[str] = _csv_env("GROQ_API_KEY")
API_SPORTS_KEYS: List[str] = _csv_env("API_SPORTS_KEY")

# ─── Single secrets ──────────────────────────────────────────────────
BALLDONTLIE_KEY: str = os.environ.get("BALLDONTLIE_API_KEY", "")
SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY: str = os.environ.get("SUPABASE_KEY", "")
TG_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN",
