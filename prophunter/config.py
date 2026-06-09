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
TG_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT: str = os.environ.get("TELEGRAM_CHAT_ID", "")

# ─── Endpoints / HTTP ────────────────────────────────────────────────
ODDS_BASE = "https://api.the-odds-api.com/v4"
BOOKMAKERS = "bet365,draftkings,fanduel,betmgm,williamhill,pinnacle"
SHARP_BOOK = "pinnacle"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PropHunter/3.0"
HTTP_HEADERS = {"User-Agent": USER_AGENT}
REQUEST_TIMEOUT = 30

# ─── Tunables ────────────────────────────────────────────────────────
MAX_EVENTS_PER_SPORT = 8
MAX_PROPS_TO_AI = 70
FUZZY_MATCH_THRESHOLD = 85
LINEUP_MATCH_THRESHOLD = 88
KELLY_FRACTION = 0.25
MAX_STAKE_UNITS = 1.5
MIN_STAKE_UNITS = 0.1
ODDS_CACHE_TTL_MAX_SECONDS = 6 * 3600
ODDS_CACHE_FILE = "odds_cache.json"
PICKS_HISTORY_FILE = "picks_history.json"
CLV_HISTORY_FILE = "clv_history.json"
LOOKAHEAD_HOURS = 12
PROPSMADNESS_MAX_PLAYERS = 5
STATCAST_LAST_N_GAMES = 15
NBA_LAST_N_GAMES = 10
NFL_LAST_N_GAMES = 5
AI_MAX_TOKENS = 3000
AI_TEMPERATURE = 0.6
AI_RETRY_ON_INVALID_JSON = 1
GEMINI_MODEL = "gemini-2.0-flash"
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "mixtral-8x7b-32768",
]
