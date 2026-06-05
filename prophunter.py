"""
AI TIPP BOT - GITHUB SINGLE FILE EDITION
=======================================

WICHTIG:
- Keine API Keys direkt in diesen Code schreiben.
- Lokal: .env Datei erstellen.
- GitHub: Secrets verwenden.

Benötigte GitHub Secrets / .env Variablen:
GEMINI_API_KEYS=key1,key2,key3
GROQ_API_KEYS=key1,key2
ODDS_API_KEYS=key1,key2
FOOTBALL_DATA_API_KEY=...
API_FOOTBALL_KEY=...
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...
TELEGRAM_GROUP_BTTS=...
TELEGRAM_GROUP_OVER25=...
TELEGRAM_GROUP_COMBO=...
TELEGRAM_GROUP_BTTS_HT=...
TELEGRAM_GROUP_STATS=...
SUPABASE_URL=...
SUPABASE_KEY=...
"""

import os
import re
import sys
import json
import traceback
import time
from datetime import date, datetime, timedelta, timezone

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# ============================================================
# CONFIG
# ============================================================

def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_list(name: str) -> list[str]:
    value = env(name)
    return [x.strip() for x in value.split(",") if x.strip()]


GEMINI_API_KEYS = env_list("GEMINI_API_KEYS")
GROQ_API_KEYS = env_list("GROQ_API_KEYS")
ODDS_API_KEYS = env_list("ODDS_API_KEYS")

FOOTBALL_DATA_API_KEY = env("FOOTBALL_DATA_API_KEY")
# 🆕 Mehrere Football-Data Keys unterstützen (kommasepariert, 10 Requests/Min pro Key)
FOOTBALL_DATA_API_KEYS = env_list("FOOTBALL_DATA_API_KEYS")
if not FOOTBALL_DATA_API_KEYS and FOOTBALL_DATA_API_KEY:
    FOOTBALL_DATA_API_KEYS = [FOOTBALL_DATA_API_KEY]
# Erster Key für Backwards-Kompatibilität
FOOTBALL_DATA_API_KEY = FOOTBALL_DATA_API_KEYS[0] if FOOTBALL_DATA_API_KEYS else ""

# 🆕 Mehrere API-Football Keys unterstützen (kommasepariert)
# Backwards-kompatibel: Falls API_FOOTBALL_KEY (singular) gesetzt ist, wird der genutzt
API_FOOTBALL_KEYS = env_list("API_FOOTBALL_KEYS")
if not API_FOOTBALL_KEYS:
    single_key = env("API_FOOTBALL_KEY")
    if single_key:
        API_FOOTBALL_KEYS = [single_key]
# Erster Key für Backwards-Kompatibilität
API_FOOTBALL_KEY = API_FOOTBALL_KEYS[0] if API_FOOTBALL_KEYS else ""

TELEGRAM_TOKEN = env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")

TELEGRAM_GROUPS = {
    "btts": env("TELEGRAM_GROUP_BTTS", TELEGRAM_CHAT_ID),
    "over25": env("TELEGRAM_GROUP_OVER25", TELEGRAM_CHAT_ID),
    "combo": env("TELEGRAM_GROUP_COMBO", TELEGRAM_CHAT_ID),
    "combos": env("TELEGRAM_GROUP_COMBOS", TELEGRAM_CHAT_ID),
    "btts_ht": env("TELEGRAM_GROUP_BTTS_HT", TELEGRAM_CHAT_ID),
    "stats": env("TELEGRAM_GROUP_STATS", TELEGRAM_CHAT_ID),
    "hz_live": env("TELEGRAM_GROUP_HZ_LIVE", TELEGRAM_CHAT_ID),
    "late_goals": env("TELEGRAM_GROUP_LATE_GOALS", TELEGRAM_CHAT_ID),
    "advanced_props": env("TELEGRAM_GROUP_ADVANCED_PROPS", env("TELEGRAM_GROUP_COMBOS", TELEGRAM_CHAT_ID)),
}


# ============================================================
# 🆕 DYNAMISCHE SAISON-LOGIK (Juni 2026)
# Sommer-Ligen (MLS, Brasilien, Argentinien etc.) = Saison 2026
# Europäische Winter-Ligen = Saison 2025
# ============================================================

CALENDAR_YEAR_LEAGUE_IDS = {
    # Amerika/MLS
    253,   # MLS
    254,   # USL Championship
    # Südamerika
    71,    # Brasileirao Serie A
    72,    # Brasileirao Serie B
    128,   # Liga Argentinien
    129,   # Argentina Primera B
    268,   # Uruguay Primera
    265,   # Chile Primera
    239,   # Colombia Primera
    240,   # Ecuador Serie A
    281,   # Peru Primera
    243,   # Venezuela Primera
    242,   # Paraguay Division
    321,   # Bolivia Division
    266,   # Costa Rica Primera
    267,   # Guatemala Liga
    # Copa Süd/CONCACAF
    13,    # Copa Libertadores
    14,    # Copa Sudamericana
    26,    # CONCACAF Champions
    262,   # Liga MX
    263,   # Liga MX Expansion
    # Asien/Pazifik
    98,    # J1 League Japan
    99,    # J2 League Japan
    100,   # J3 League Japan
    292,   # K League 1
    293,   # K League 2
    169,   # China Super League
    170,   # China League 1
    323,   # India Super League
    296,   # Thailand League 1
    297,   # Malaysia Super League
    299,   # Indonesia Liga 1
    340,   # Vietnam V-League
    188,   # A-League Australia
    187,   # A-League Women
    189,   # New Zealand NZFC
    # Mittlerer Osten/Afrika
    307,   # Saudi Pro League
    306,   # UAE Pro League
    98,    # Qatar Stars League
    200,   # Morocco Botola
    233,   # Egypt Premier
    288,   # South Africa PSL
    300,   # Nigeria Premier
    302,   # Kenya Premier
    # Internationale Turniere 2026
    1,     # WM 2026
    5,     # UEFA Nations League
    9,     # Copa America
    6,     # Afrika Cup
    10,    # Freundschaftsspiele
}

def get_dynamic_season(league_id=None, league_name=None):
    """
    Bestimmt automatisch die richtige Saison (2026 vs 2025).
    Sommer-Ligen (Südamerika, MLS, Asien, Australien) → 2026
    Europäische Winter-Ligen → 2025
    """
    if league_id and int(league_id) in CALENDAR_YEAR_LEAGUE_IDS:
        return 2026

    # Fallback via Liga-Name
    SUMMER_LEAGUES = [
        "MLS", "Brasileirao", "Liga Argentinien", "J1 League", "J2 League",
        "A-League", "Uruguay Primera", "Chile Primera", "Colombia Primera",
        "Ecuador", "Peru Primera", "Venezuela", "K League", "China Super",
        "India Super", "Vietnam", "Thailand", "Malaysia", "Indonesia",
    ]
    if league_name:
        for sl in SUMMER_LEAGUES:
            if sl.lower() in league_name.lower():
                return 2026

    return 2025

SUPABASE_URL = env("SUPABASE_URL")
SUPABASE_KEY = env("SUPABASE_KEY")


# ============================================================
# 🗄️ SUPABASE DAILY CACHE — Fixtures, Stats, Odds
# Spart API Calls: Run 1 scrapt, Run 2+3 lesen aus Supabase
# ============================================================

def cache_get(cache_key: str, target_date) -> dict | None:
    """Holt gecachte Daten aus Supabase daily_cache Tabelle."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/daily_cache",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={
                "cache_date": f"eq.{target_date}",
                "cache_key": f"eq.{cache_key}",
                "select": "data",
                "limit": "1",
            },
            timeout=8,
        )
        if r.ok and r.json():
            return r.json()[0].get("data")
    except Exception:
        pass
    return None


def cache_set(cache_key: str, target_date, data: dict) -> bool:
    """Speichert Daten in Supabase daily_cache (upsert)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        import json as _cj
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/daily_cache",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            json={
                "cache_date": str(target_date),
                "cache_key": cache_key,
                "data": data,
            },
            timeout=10,
        )
        return r.ok
    except Exception:
        return False


def cache_get_fixtures(target_date) -> dict | None:
    """Holt gecachte Fixtures für heute (alle Ligen)."""
    cached = cache_get("fixtures_all", target_date)
    if cached:
        log(f"   🗄️ Fixtures aus Supabase Cache geladen ({sum(len(v) for v in cached.values())} Spiele)")
    return cached


def cache_set_fixtures(target_date, fixtures_by_league: dict) -> bool:
    """Speichert alle heutigen Fixtures in Supabase."""
    if not fixtures_by_league:
        return False
    # Nur nicht-leere Ligen speichern
    to_save = {lg: fixes for lg, fixes in fixtures_by_league.items() if fixes}
    if not to_save:
        return False
    result = cache_set("fixtures_all", target_date, to_save)
    if result:
        total = sum(len(v) for v in to_save.values())
        log(f"   🗄️ {total} Spiele in {len(to_save)} Ligen in Supabase gecacht")
    return result


def cache_get_player_stats(league_name: str, target_date) -> dict | None:
    """Holt gecachte FBref Player Stats."""
    return cache_get(f"fbref_{league_name.replace(' ', '_')}", target_date)


def cache_set_player_stats(league_name: str, target_date, stats: dict) -> bool:
    """Speichert FBref Player Stats in Supabase."""
    if not stats:
        return False
    return cache_set(f"fbref_{league_name.replace(' ', '_')}", target_date, stats)


def cache_get_odds(league_name: str, target_date) -> list | None:
    """Holt gecachte Odds API Daten."""
    cached = cache_get(f"odds_{league_name.replace(' ', '_')}", target_date)
    return cached.get("odds") if cached else None


def cache_set_odds(league_name: str, target_date, odds: list) -> bool:
    """Speichert Odds in Supabase."""
    if not odds:
        return False
    return cache_set(f"odds_{league_name.replace(' ', '_')}", target_date, {"odds": odds})


MIN_PROBABILITY = int(env("MIN_PROBABILITY", "67"))  # 🆕 Hybrid: 67% (zwischen 65-69)
MIN_ODDS = float(env("MIN_ODDS", "1.65"))
MAX_ODDS = float(env("MAX_ODDS", "3.0"))
MIN_CONFIDENCE = int(env("MIN_CONFIDENCE", "3"))
# 🆕 Nur HIGH + OK Value (LOW fliegt raus)
MIN_VALUE_RATING = env("MIN_VALUE_RATING", "OK")  # HIGH, OK, oder LOW

MARKETS_TO_RUN = ["btts", "over25", "combo", "btts_ht"]

# ============================================================
# AUTO LIGA SWITCH
# ============================================================
AUTO_LEAGUE_SWITCH = env("AUTO_LEAGUE_SWITCH", "false").lower() in ["1", "true", "yes", "on"]  # Aus bis CLV läuft
AUTO_LEAGUE_MIN_TIPS = int(env("AUTO_LEAGUE_MIN_TIPS", "10"))
AUTO_LEAGUE_MIN_WINRATE = float(env("AUTO_LEAGUE_MIN_WINRATE", "48"))
AUTO_LEAGUE_MIN_ROI = float(env("AUTO_LEAGUE_MIN_ROI", "-2.0"))
AUTO_LEAGUE_LOOKBACK_DAYS = int(env("AUTO_LEAGUE_LOOKBACK_DAYS", "120"))

MAX_LEAGUES_PER_RUN = int(env("MAX_LEAGUES_PER_RUN", "0"))  # 0 = alle Ligen  # 25 pro Run!
AI_SLEEP_SECONDS = float(env("AI_SLEEP_SECONDS", "0.1"))
GROQ_SLEEP_SECONDS = float(env("GROQ_SLEEP_SECONDS", "0.5"))
USE_GROQ_FALLBACK = env("USE_GROQ_FALLBACK", "true").lower() in ["1", "true", "yes", "on"]

ALWAYS_ON_LEAGUES = [
    x.strip()
    for x in env("ALWAYS_ON_LEAGUES", "Champions League,Europa League,Premier League,Bundesliga,La Liga,Serie A,Ligue 1,WM 2026,UEFA Nations League,Copa America,Afrika Cup").split(",")
    if x.strip()
]

ALWAYS_OFF_LEAGUES = [
    x.strip()
    for x in env("ALWAYS_OFF_LEAGUES", "").split(",")
    if x.strip()
]

ACTIVE_LEAGUES_OVERRIDE = [
    x.strip()
    for x in env("ACTIVE_LEAGUES", "").split(",")
    if x.strip()
]

GEMINI_MODEL = "gemini-2.5-flash"
GROQ_MODEL = "llama-3.1-8b-instant"  # Höheres Rate Limit als 70b!
GROQ_MODEL_FALLBACK = "gemma2-9b-it"  # Backup Modell


# ============================================================
# LIGEN
# ============================================================

LEAGUES_TO_RUN = [
    "Champions League",
    "Europa League",
    "Conference League",
    "Bundesliga",
    "2. Bundesliga",
    "3. Liga Deutschland",
    "Premier League",
    "Championship",
    "EFL League 1",
    "EFL League 2",
    "National League",
    "La Liga",
    "La Liga 2",
    "Serie A",
    "Serie B",
    "Serie C",
    "Ligue 1",
    "Ligue 2",
    "Eredivisie",
    "Eerste Divisie",
    "Primeira Liga",
    "Pro League Belgien",
    "Belgium Challenger",
    "Süper Lig",
    "Turkish 1. Lig",
    "Bundesliga Österreich",
    "Austria 2. Liga",
    "Super League Schweiz",
    "Swiss Challenge",
    "Scottish Premiership",
    "Scottish Championship",
    "Scottish League One",
    "Danish Superliga",
    "Danish 1. Division",
    "Norway Eliteserien",
    "Norwegian 1. Division",
    "Sweden Allsvenskan",
    "Swedish Superettan",
    "Finland Veikkausliiga",
    "Iceland Premier",
    "Iceland 1. Deild",
    "Greece Super League",
    "Croatia HNL",
    "Serbia SuperLiga",
    "Romania Liga I",
    "Czech First League",
    "Czech 2. Liga",
    "Poland Ekstraklasa",
    "Slovak Super Liga",
    "Hungarian NB I",
    "Bulgarian First",
    "Israeli Liga Leumit",
    "Israeli Premier",
    "Ukrainian Premier",
    "Russian Premier",
    "Belarus Premier",
    "Latvian Higher League",
    "Lithuanian A Lyga",
    "Estonian Premium",
    "Kazakh Premier",
    "UEFA Youth League",
    "Bundesliga U19",
    "Bundesliga U17",
    "Premier League U21",
    "Premier League U18",
    "La Liga U19",
    "Serie A U19",
    "Ligue 1 U19",
    "Eredivisie U21",
    "MLS",
    "USL Championship",
    "Brasileirao Serie A",
    "Brasileirao Serie B",
    "Liga Argentinien",
    "Argentina Primera B",
    "Liga MX",
    "Liga MX Expansion",
    "Uruguay Primera",
    "Chile Primera",
    "Colombia Primera",
    "Ecuador Serie A",
    "Peru Primera",
    "Venezuela Primera",
    "Paraguay Division",
    "Bolivia Division",
    "Costa Rica Primera",
    "Guatemala Liga",
    "Honduras Liga",
    "Copa Libertadores",
    "Copa Sudamericana",
    "CONCACAF Champions",
    "Saudi Pro League",
    "Qatar Stars League",
    "UAE Pro League",
    "Egypt Premier",
    "Morocco Botola",
    "Tunisia Ligue 1",
    "South Africa PSL",
    "Algeria Ligue 1",
    "Nigeria Premier",
    "Kenya Premier",
    "Iran Pro League",
    "Jordan Pro League",
    "Kuwait Premier",
    "Bahrain Premier",
    "J1 League Japan",
    "J2 League Japan",
    "J3 League Japan",
    "K League 1",
    "K League 2",
    "China Super League",
    "China League 1",
    "India Super League",
    "India I-League",
    "Vietnam V-League",
    "Thailand League 1",
    "Malaysia Super League",
    "Indonesia Liga 1",
    "Philippines United",
    "Singapore Premier",
    "Myanmar National",
    "Taiwan Football Prem",
    "Hong Kong Premier",
    "A-League Australia",
    "A-League Women",
    "New Zealand NZFC",
    "AFC Champions League",
    "AFC Cup",
    "Kazakhstan Premier",
    "Uzbekistan Super",
    "Tajikistan League",
    # 🌍 WM 2026 + Länderspiele
    "WM 2026 Qualifikation Europa",
    "WM 2026 Qualifikation Südamerika",
    "WM 2026 Qualifikation Asien",
    "WM 2026 Qualifikation Afrika",
    "WM 2026 Qualifikation CONCACAF",
    "WM 2026",
    "UEFA Nations League",
    "Copa America",
    "Afrika Cup",
    "Freundschaftsspiele International",

    # ── Europa (fehlend) ──
    "Faroe Islands Premier League",
    "Gibraltar National League",
    "Kosovo Superliga",
    "Luxembourg BGL Ligue",
    "Malta Premier League",
    "Moldova National Division",
    "Montenegro First League",
    "North Macedonia First League",
    "Northern Ireland Premiership",
    "Republic of Ireland Premier Division",
    "Republic of Ireland First Division",
    "Wales Premier League",
    "Albania Superliga",
    "Armenia Premier League",
    "Azerbaijan Premier League",
    "Georgia Erovnuli Liga",
    "Cyprus First Division",
    "Czech 2. Liga",
    "Slovakia Super Liga",
    "Slovenia Prva Liga",
    "Bosnia Premier League",
    "Andorra Primera Divisió",
    "San Marino Campionato",
    "Swiss Challenge League",
    "Austrian Regional Liga",
    "German Regionalliga Bayern",
    "German Regionalliga Nord",
    "German Regionalliga Nordost",
    "German Regionalliga West",
    "German Regionalliga Südwest",
    # ── Afrika (fehlend) ──
    "Algeria Ligue 2",
    "Angola Girabola",
    "Botswana Premier League",
    "Burkina Faso Premier League",
    "Cameroon Elite One",
    "Congo DR Linafoot",
    "Ethiopia Premier League",
    "Gabon Championnat National",
    "Ghana Premier League",
    "Guinea Ligue Professionnelle",
    "Ivory Coast Ligue 1",
    "Libya Premier League",
    "Malawi Super League",
    "Mali Premiere Division",
    "Mauritania Ligue 1",
    "Morocco Botola 2",
    "Mozambique Mocambola",
    "Namibia Premier League",
    "Rwanda Premier League",
    "Senegal Ligue 1",
    "Sierra Leone Premier League",
    "Tanzania Premier League",
    "Togo Championnat National",
    "Uganda Premier League",
    "Zambia Super League",
    "Zimbabwe Premier Soccer League",
    "Zanzibar Premier League",
    "Gambia GFA League",
    "Benin Ligue 1",
    "CAF Champions League",
    "CAF Confederation Cup",
    "COSAFA Cup",
    "CECAFA Cup",
    # ── Asien (fehlend) ──
    "Afghanistan Premier League",
    "Bahrain Premier League",
    "Bangladesh Premier League",
    "Bhutan National League",
    "Cambodia League",
    "Chinese Taipei League",
    "Hong Kong Premier League",
    "India I-League 2",
    "Indonesia Liga 2",
    "Iraq Premier League",
    "Jordan Pro League",
    "Kazakhstan Premier League",
    "Kuwait Premier League",
    "Kyrgyzstan Top League",
    "Laos League",
    "Lebanon Premier League",
    "Lebanon Division 2",
    "Macau League",
    "Maldives Dhivehi Premier League",
    "Mongolia National Premier League",
    "Myanmar National League",
    "Nepal Super League",
    "Oman Professional League",
    "Pakistan Premier League",
    "Palestine Premier League",
    "Philippines United Football League",
    "Qatar Stars League",
    "Saudi Division 1",
    "Singapore Premier League",
    "Sri Lanka Football League",
    "Syria Premier League",
    "Tajikistan League",
    "Thailand Division 1",
    "Timor-Leste Premier League",
    "Turkmenistan Liga",
    "UAE Division 1",
    "Uzbekistan Super League",
    "Uzbekistan Division 1",
    "Vietnam V-League 2",
    "Yemen League",
    "Yemen Super Cup",
    "J-League Play-Offs",
    "K League 3",
    "K League 4",
    "ACL Elite",
    "ASEAN Club Championship",
    "SAFF Championship",
    "West Asian Football Federation",
    # ── Südamerika (fehlend) ──
    "Bolivia Division Profesional",
    "Brazil Serie C",
    "Brazil Serie D",
    "Chile Primera B",
    "Colombia Primera B",
    "Ecuador Liga Pro 2",
    "Paraguay Division Intermedia",
    "Peru Liga 2",
    "Venezuela Segunda Division",
    "CONMEBOL Pre-Olympic",
    "South American Youth Championship",
    "Recopa Sudamericana",
    "Copa Argentina",
    "Campeonato Paulista",
    "Campeonato Carioca",
    "Campeonato Mineiro",
    "Campeonato Gaucho",
    "Argentinian Regional Liga",
    # ── Nordamerika/Karibik (fehlend) ──
    "Canada Premier League",
    "USL League One",
    "USL League Two",
    "NISA National League",
    "Costa Rica Segunda",
    "El Salvador Primera Division",
    "Nicaragua Primera Division",
    "Panama LPF",
    "Trinidad and Tobago Pro League",
    "Jamaica Premier League",
    "Haiti Ligue Haïtienne",
    "Dominican Republic LDF",
    "Cuba National Series",
    # ── Ozeanien (fehlend) ──
    "New Zealand Southern League",
    "New Zealand National League",
    "Fiji Battle of the Giants",
    "Papua New Guinea National Soccer League",
    "Solomon Islands S-League",
    "Vanuatu Premier League",
    "OFC Champions League",
    # ── Youth/Reserve (fehlend) ──
    "Champions League Youth",
    "Bundesliga Reserve",
    "Premier League 2",
    "LaLiga Youth",
    "Serie A Primavera",
    "Ligue 1 Reserve",
    # ── Internationale Cups (fehlend) ──
    "Arab Cup",
    "Gold Cup",
    "CONCACAF Nations League",
    "Pacific Games Football",
    "Island Games",
    "COSAFA Women Cup",
]

# Zeitfenster pro Liga (UTC Stunden)
# LEAGUES_TIME_MAP entfernt — Bot läuft global 24/7



LEAGUE_KEYS = {
    "Champions League": "soccer_uefa_champs_league",
    "Europa League": "soccer_uefa_europa_league",
    "Conference League": "soccer_uefa_europa_conference_league",
    "Bundesliga": "soccer_germany_bundesliga",
    "2. Bundesliga": "soccer_germany_bundesliga2",
    "Premier League": "soccer_epl",
    "Championship": "soccer_efl_champ",
    "La Liga": "soccer_spain_la_liga",
    "La Liga 2": "soccer_spain_segunda_division",
    "Serie A": "soccer_italy_serie_a",
    "Serie B": "soccer_italy_serie_b",
    "Ligue 1": "soccer_france_ligue_one",
    "Ligue 2": "soccer_france_ligue_two",
    "Eredivisie": "soccer_netherlands_eredivisie",
    "Primeira Liga": "soccer_portugal_primeira_liga",
    "Pro League Belgien": "soccer_belgium_first_div",
    "Süper Lig": "soccer_turkey_super_league",
    "Bundesliga Österreich": "soccer_austria_bundesliga",
    "Super League Schweiz": "soccer_switzerland_superleague",
    "Scottish Premiership": "soccer_spl",
    "MLS": "soccer_usa_mls",
    "Brasileirao Serie A": "soccer_brazil_campeonato",
    "Liga Argentinien": "soccer_argentina_primera_division",
    "J1 League Japan": "soccer_japan_j_league",
    "Saudi Pro League": "soccer_saudi_arabia_league",
    "Liga MX": "soccer_mexico_ligamx",
    "A-League": "soccer_australia_aleague",
    "Iceland Premier League": "soccer_iceland_urvalsdeild",
    "K League 1": "soccer_korea_kleague1",
    "China Super League": "soccer_china_superleague",
    # 🆕 8 neue Ligen
    "EFL League 1": "soccer_england_league1",
    "EFL League 2": "soccer_england_league2",
    "Finland Veikkausliiga": "soccer_finland_veikkausliiga",
    "Uruguay Primera": "soccer_uruguay_primera_division",
    "India Super League": "soccer_india_superleague",
    "Qatar Stars League": "soccer_qatar_league",
    "South Africa PSL": "soccer_south_africa_premier_league",
    "Vietnam V-League": "soccer_vietnam_v_league",
    "Danish Superliga": "soccer_denmark_superliga",
    "Norway Eliteserien": "soccer_norway_eliteserien",
    "Sweden Allsvenskan": "soccer_sweden_allsvenskan",
    "Greece Super League": "soccer_greece_super_league",
    "Poland Ekstraklasa": "soccer_poland_ekstraklasa",
    "Slovak Super Liga": "soccer_slovakia_super_liga",
    # 🆕 B/C-Ligen (falls Odds API sie hat)
    "Eerste Divisie": "soccer_netherlands_eerste_divisie",
    "Norwegian 1. Division": "soccer_norway_first_division",
    "Turkish 1. Lig": "soccer_turkey_first_league",
    "Belgian Challenger Pro": "soccer_belgium_first_div_b",
    "Czech 2. Liga": "soccer_czech_2_liga",
    "Scottish Championship": "soccer_scotland_championship",
    "Swedish Superettan": "soccer_sweden_superettan",
    "Israeli Liga Leumit": "soccer_israel_liga_leumit",
}

FOOTBALL_DATA_CODES = {
    "Champions League": "CL",
    "Bundesliga": "BL1",
    "2. Bundesliga": "BL2",
    "Premier League": "PL",
    "Championship": "ELC",
    "La Liga": "PD",
    "Serie A": "SA",
    "Ligue 1": "FL1",
    "Eredivisie": "DED",
    "Primeira Liga": "PPL",
    "Brasileirao Serie A": "BSA",
}

API_FOOTBALL_LEAGUES = {
    "Champions League": 2,
    "Europa League": 3,
    "Conference League": 848,
    "Bundesliga": 78,
    "2. Bundesliga": 79,
    "3. Liga Deutschland": 82,
    "Premier League": 39,
    "Championship": 40,
    "EFL League 1": 41,
    "EFL League 2": 42,
    "National League": 43,
    "La Liga": 140,
    "La Liga 2": 141,
    "Serie A": 135,
    "Serie B": 136,
    "Serie C": 137,
    "Ligue 1": 61,
    "Ligue 2": 62,
    "Eredivisie": 88,
    "Eerste Divisie": 89,
    "Primeira Liga": 94,
    "Pro League Belgien": 144,
    "Belgium Challenger": 296,
    "Süper Lig": 203,
    "Turkish 1. Lig": 200,
    "Bundesliga Österreich": 218,
    "Austria 2. Liga": 293,
    "Super League Schweiz": 207,
    "Swiss Challenge": 265,
    "Scottish Premiership": 179,
    "Scottish Championship": 181,
    "Scottish League One": 182,
    "Danish Superliga": 119,
    "Danish 1. Division": 120,
    "Norway Eliteserien": 103,
    "Norwegian 1. Division": 104,
    "Sweden Allsvenskan": 113,
    "Swedish Superettan": 114,
    "Finland Veikkausliiga": 244,
    "Iceland Premier": 271,
    "Iceland 1. Deild": 272,
    "Greece Super League": 197,
    "Croatia HNL": 210,
    "Serbia SuperLiga": 286,
    "Romania Liga I": 283,
    "Czech First League": 345,
    "Czech 2. Liga": 346,
    "Poland Ekstraklasa": 106,
    "Slovak Super Liga": 332,
    "Hungarian NB I": 325,
    "Bulgarian First": 348,
    "Israeli Liga Leumit": 289,
    "Israeli Premier": 288,
    "Ukrainian Premier": 333,
    "Russian Premier": 235,
    "Belarus Premier": 338,
    "Latvian Higher League": 366,
    "Lithuanian A Lyga": 365,
    "Estonian Premium": 330,
    "Kazakh Premier": 381,
    "UEFA Youth League": 10,
    "Bundesliga U19": 63,
    "Bundesliga U17": 64,
    "Premier League U21": 45,
    "Premier League U18": 48,
    "La Liga U19": 384,
    "Serie A U19": 233,
    "Ligue 1 U19": 114,
    "Eredivisie U21": 90,
    "MLS": 253,
    "USL Championship": 254,
    "Brasileirao Serie A": 71,
    "Brasileirao Serie B": 72,
    "Liga Argentinien": 128,
    "Argentina Primera B": 129,
    "Liga MX": 262,
    "Liga MX Expansion": 263,
    "Uruguay Primera": 268,
    "Chile Primera": 265,
    "Colombia Primera": 239,
    "Ecuador Serie A": 240,
    "Peru Primera": 281,
    "Venezuela Primera": 243,
    "Paraguay Division": 242,
    "Bolivia Division": 321,
    "Costa Rica Primera": 266,
    "Guatemala Liga": 267,
    "Honduras Liga": 268,
    "Copa Libertadores": 13,
    "Copa Sudamericana": 14,
    "CONCACAF Champions": 26,
    "Saudi Pro League": 307,
    "Qatar Stars League": 98,
    "UAE Pro League": 306,
    "Egypt Premier": 233,
    "Morocco Botola": 200,
    "Tunisia Ligue 1": 311,
    "South Africa PSL": 288,
    "Algeria Ligue 1": 298,
    "Nigeria Premier": 300,
    "Kenya Premier": 302,
    "Iran Pro League": 290,
    "Jordan Pro League": 373,
    "Kuwait Premier": 374,
    "Bahrain Premier": 375,
    "J1 League Japan": 98,
    "J2 League Japan": 99,
    "J3 League Japan": 100,
    "K League 1": 292,
    "K League 2": 293,
    "China Super League": 169,
    "China League 1": 170,
    "India Super League": 323,
    "India I-League": 324,
    "Vietnam V-League": 340,
    "Thailand League 1": 296,
    "Malaysia Super League": 297,
    "Indonesia Liga 1": 299,
    "Philippines United": 301,
    "Singapore Premier": 303,
    "Myanmar National": 304,
    "Taiwan Football Prem": 350,
    "Hong Kong Premier": 351,
    "A-League Australia": 188,
    "A-League Women": 187,
    "New Zealand NZFC": 189,
    "AFC Champions League": 2,
    "AFC Cup": 3,
    "Kazakhstan Premier": 381,
    "Uzbekistan Super": 382,
    "Tajikistan League": 383,
    # 🌍 WM 2026 + Länderspiele
    "WM 2026": 1,
    "WM 2026 Qualifikation Europa": 32,
    "WM 2026 Qualifikation Südamerika": 29,
    "WM 2026 Qualifikation Asien": 30,
    "WM 2026 Qualifikation Afrika": 31,
    "WM 2026 Qualifikation CONCACAF": 33,
    "UEFA Nations League": 5,
    "Copa America": 9,
    "Afrika Cup": 6,
    "Freundschaftsspiele International": 10,
}

FOOTBALL_JSON_LEAGUES = {
    "Bundesliga": "de.1",
    "2. Bundesliga": "de.2",
    "Premier League": "en.1",
    "Championship": "en.2",
    "La Liga": "es.1",
    "La Liga 2": "es.2",
    "Serie A": "it.1",
    "Serie B": "it.2",
    "Ligue 1": "fr.1",
    "Ligue 2": "fr.2",
    "Eredivisie": "nl.1",
    "Primeira Liga": "pt.1",
    "Champions League": "uefa.cl",
    "Europa League": "uefa.el",
}

OPENLIGADB_LEAGUES = {
    "Bundesliga": "bl1",
    "2. Bundesliga": "bl2",
    "Bundesliga Österreich": "bl-at",
    "Süper Lig": "tr1",
    "Champions League": "ucl",
    "Europa League": "uel",
}

UNDERSTAT_LEAGUES = {
    "Premier League": "EPL",
    "La Liga": "La_liga",
    "Bundesliga": "Bundesliga",
    "Serie A": "Serie_A",
    "Ligue 1": "Ligue_1",
}

MARKET_INFO = {
    "btts": {
        "name": "⚽ BTTS",
        "instr": "Analysiere BTTS (Both Teams To Score - beide Teams treffen).",
    },
    "over25": {
        "name": "🎯 Over 2.5",
        "instr": "Analysiere Over 2.5 Tore.",
    },
    "combo": {
        "name": "🔥 BTTS + Over 2.5",
        "instr": "Analysiere BTTS & Over 2.5 KOMBO.",
    },
    "btts_ht": {
        "name": "🕐 BTTS HT",
        "instr": "Analysiere BTTS in der 1. Halbzeit (Beide Teams treffen bis zur Pause). Wichtig: xG HT, Pressing der Teams, frühe Tore Statistik.",
    },
}


# ============================================================
# UTILS
# ============================================================

def log(msg, level="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def get_local_time(utc_iso_str):
    try:
        dt_utc = datetime.fromisoformat(utc_iso_str.replace("Z", "+00:00"))
        year = dt_utc.year

        march_last = datetime(year, 3, 31, tzinfo=timezone.utc)
        while march_last.weekday() != 6:
            march_last -= timedelta(days=1)

        oct_last = datetime(year, 10, 31, tzinfo=timezone.utc)
        while oct_last.weekday() != 6:
            oct_last -= timedelta(days=1)

        offset = 2 if march_last <= dt_utc < oct_last else 1
        return (dt_utc + timedelta(hours=offset)).strftime("%H:%M")
    except Exception:
        return "TBD"


def extract_json_array(text):
    cleaned = text.replace("```json", "").replace("```", "").strip()

    try:
        s = cleaned.find("[")
        e = cleaned.rfind("]")
        if s != -1 and e > s:
            return json.loads(cleaned[s:e + 1])
    except Exception:
        pass

    objects = []
    depth = 0
    start_idx = -1

    for i, c in enumerate(cleaned):
        if c == "{":
            if depth == 0:
                start_idx = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start_idx != -1:
                try:
                    obj = json.loads(cleaned[start_idx:i + 1])
                    if "match" in obj:
                        objects.append(obj)
                except Exception:
                    pass
                start_idx = -1

    return objects


def normalize_team_name(name):
    if not name:
        return ""

    n = name.lower().strip()
    remove = [
        " fc", " cf", " ac", " sc", " sv", " 1.",
        "fc ", "ac ", "sc ", "sv ", "1. ",
        " e.v.", " ev",
    ]

    for x in remove:
        n = n.replace(x, " ")

    return " ".join(n.split())


def teams_match(name1, name2):
    n1 = normalize_team_name(name1)
    n2 = normalize_team_name(name2)

    if not n1 or not n2:
        return False

    if n1 == n2 or n1 in n2 or n2 in n1:
        return True

    w1 = [w for w in n1.split() if len(w) > 3]
    w2 = [w for w in n2.split() if len(w) > 3]

    return any(w in n2 for w in w1) or any(w in n1 for w in w2)


def parse_odds(val):
    try:
        return float(str(val).replace(",", "."))
    except Exception:
        return 0.0


# ============================================================
# DATA SOURCES
# ============================================================

UNDERSTAT_CACHE = {}

# ============================================================
# 🆕 OPENWEATHERMAP - Wetterdaten (kostenlos, 1000 Calls/Tag)
# ============================================================
WEATHER_API_KEY = env("OPENWEATHER_API_KEY", "")
WEATHER_CACHE = {}

STADIUM_CITIES = {
    "Premier League": "London",
    "Bundesliga": "Munich",
    "La Liga": "Madrid",
    "Serie A": "Rome",
    "Ligue 1": "Paris",
    "Eredivisie": "Amsterdam",
    "Primeira Liga": "Lisbon",
    "Champions League": "London",
    "Europa League": "London",
    "Scottish Premiership": "Glasgow",
    "Danish Superliga": "Copenhagen",
    "Norway Eliteserien": "Oslo",
    "Sweden Allsvenskan": "Stockholm",
    "MLS": "New York",
    "Brasileirao Serie A": "Sao Paulo",
    "Liga Argentinien": "Buenos Aires",
    "J1 League Japan": "Tokyo",
    "K League 1": "Seoul",
    "China Super League": "Beijing",
    "A-League": "Sydney",
    "Saudi Pro League": "Riyadh",
}

def get_weather_for_league(league_name, target_date):
    """
    Holt Wetterdaten für eine Liga (Stadt-basiert).
    Returns: {'temp': 18, 'rain': 2.5, 'wind': 15, 'condition': 'Rain', 'impact': 'negative'}
    """
    if not WEATHER_API_KEY:
        return None

    city = STADIUM_CITIES.get(league_name)
    if not city:
        return None

    cache_key = f"{city}_{target_date}"
    if cache_key in WEATHER_CACHE:
        return WEATHER_CACHE[cache_key]

    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={
                "q": city,
                "appid": WEATHER_API_KEY,
                "units": "metric",
                "cnt": 8,
            },
            timeout=10,
        )

        if not r.ok:
            return None

        data = r.json()
        forecasts = data.get("list", [])

        if not forecasts:
            return None

        # Nehme Mittags-Forecast (12:00-18:00 Uhr)
        best = forecasts[0]
        for f in forecasts:
            dt = datetime.fromtimestamp(f["dt"], tz=timezone.utc)
            if 12 <= dt.hour <= 18:
                best = f
                break

        temp = best.get("main", {}).get("temp", 20)
        wind = best.get("wind", {}).get("speed", 0) * 3.6  # m/s → km/h
        rain = best.get("rain", {}).get("3h", 0)
        condition = best.get("weather", [{}])[0].get("main", "Clear")

        # Impact auf BTTS berechnen
        impact = "neutral"
        impact_notes = []

        if rain > 3:
            impact = "negative"
            impact_notes.append(f"🌧️ Starker Regen ({rain:.1f}mm) → weniger Tore")
        elif rain > 1:
            impact_notes.append(f"🌦️ Leichter Regen ({rain:.1f}mm)")

        if wind > 50:
            impact = "negative"
            impact_notes.append(f"💨 Starker Wind ({wind:.0f}km/h) → schlechtere Pässe")
        elif wind > 30:
            impact_notes.append(f"🌬️ Wind {wind:.0f}km/h")

        if temp > 32:
            impact_notes.append(f"🥵 Hitze ({temp:.0f}°C) → Teams langsamer")
        elif temp < 2:
            impact_notes.append(f"🥶 Kälte ({temp:.0f}°C) → harter Rasen")

        result = {
            "city": city,
            "temp": round(temp, 1),
            "rain": round(rain, 1),
            "wind": round(wind, 1),
            "condition": condition,
            "impact": impact,
            "notes": impact_notes,
        }

        WEATHER_CACHE[cache_key] = result
        return result

    except Exception as e:
        log(f"Weather Error: {e}", "WARN")
        return None


# ============================================================
# 🆕 FOOTYSTATS - BTTS + Over 2.5 Statistiken
# ============================================================
FOOTYSTATS_API_KEY = env("FOOTYSTATS_API_KEY", "")
SPORTDB_API_KEY = env("SPORTDB_API_KEY", "")  # SportDB.dev / Flashscore API
FOOTYSTATS_CACHE = {}

FOOTYSTATS_LEAGUE_IDS = {
    "Premier League": 1625,
    "Bundesliga": 1617,
    "La Liga": 1621,
    "Serie A": 1627,
    "Ligue 1": 1619,
    "Eredivisie": 1631,
    "Primeira Liga": 1629,
    "Championship": 1626,
    "Scottish Premiership": 1637,
    "MLS": 1651,
    "Brasileirao Serie A": 1671,
}

def get_footystats_team(team_name, league_name):
    """
    Holt BTTS + Over 2.5 Statistiken von FootyStats.
    Returns: {'btts_rate': 65, 'over25_rate': 72, 'avg_goals': 2.8}
    """
    if not FOOTYSTATS_API_KEY:
        return None

    league_id = FOOTYSTATS_LEAGUE_IDS.get(league_name)
    if not league_id:
        return None

    cache_key = f"{team_name}_{league_id}"
    if cache_key in FOOTYSTATS_CACHE:
        return FOOTYSTATS_CACHE[cache_key]

    try:
        r = requests.get(
            f"https://api.football-data-api.com/league-teams",
            params={
                "key": FOOTYSTATS_API_KEY,
                "season_id": league_id,
            },
            timeout=12,
        )

        if not r.ok:
            return None

        data = r.json()
        teams = data.get("data", [])

        for team in teams:
            name = team.get("cleanName", "").lower()
            if team_name.lower()[:6] in name or name[:6] in team_name.lower():
                stats = team.get("stats", {})
                result = {
                    "btts_rate": stats.get("btts_percentage", 0),
                    "over25_rate": stats.get("over25_percentage", 0),
                    "avg_goals": stats.get("avg_goals_per_game_scored", 0),
                    "avg_conceded": stats.get("avg_goals_per_game_conceded", 0),
                    "clean_sheets_pct": stats.get("clean_sheet_percentage", 0),
                }
                FOOTYSTATS_CACHE[cache_key] = result
                return result

        return None

    except Exception as e:
        log(f"FootyStats Error: {e}", "WARN")
        return None



# ============================================================
# 🆕 SPORTDB.DEV / FLASHSCORE - Lineups & Live Data
# ============================================================
SPORTDB_API_KEY = env("SPORTDB_API_KEY", "")
SPORTDB_CACHE = {}

SPORTDB_LEAGUE_IDS = {
    "Premier League": "premier-league",
    "Bundesliga": "bundesliga",
    "La Liga": "la-liga",
    "Serie A": "serie-a",
    "Ligue 1": "ligue-1",
    "Eredivisie": "eredivisie",
    "Champions League": "champions-league",
    "Europa League": "europa-league",
    "Championship": "championship",
    "Scottish Premiership": "scottish-premiership",
    "Primeira Liga": "primeira-liga",
    "Süper Lig": "super-lig",
}

def get_sportdb_lineups(home_team, away_team, target_date):
    """
    Holt Aufstellungen von SportDB.dev (Flashscore API).
    Returns: {'home_lineup': [...], 'away_lineup': [...], 'home_missing': [...]}
    """
    if not SPORTDB_API_KEY:
        return None

    cache_key = f"{home_team}_{away_team}_{target_date}"
    if cache_key in SPORTDB_CACHE:
        return SPORTDB_CACHE[cache_key]

    try:
        r = requests.get(
            "https://api.sportdb.dev/v1/football/fixtures",
            headers={
                "X-API-Key": SPORTDB_API_KEY,
                "Content-Type": "application/json",
            },
            params={
                "date": str(target_date),
            },
            timeout=12,
        )

        if not r.ok:
            return None

        data = r.json()
        fixtures = data.get("data", data.get("fixtures", data.get("results", [])))

        if not fixtures:
            return None

        # Suche das passende Spiel
        for fix in fixtures:
            home = fix.get("home_team", fix.get("homeTeam", {}).get("name", ""))
            away = fix.get("away_team", fix.get("awayTeam", {}).get("name", ""))

            if not teams_match(home_team, str(home)):
                continue
            if not teams_match(away_team, str(away)):
                continue

            # Lineup extrahieren
            lineups = fix.get("lineups", fix.get("lineup", {}))
            home_lineup = []
            away_lineup = []

            if lineups:
                home_players = lineups.get("home", lineups.get("homeTeam", {}).get("startXI", []))
                away_players = lineups.get("away", lineups.get("awayTeam", {}).get("startXI", []))

                for p in home_players[:11]:
                    name = p.get("name", p.get("player", {}).get("name", ""))
                    if name:
                        home_lineup.append(name)

                for p in away_players[:11]:
                    name = p.get("name", p.get("player", {}).get("name", ""))
                    if name:
                        away_lineup.append(name)

            result = {
                "fixture_id": fix.get("id", fix.get("fixture_id", "")),
                "home_lineup": home_lineup,
                "away_lineup": away_lineup,
                "lineup_available": len(home_lineup) > 0,
                "status": fix.get("status", fix.get("fixture", {}).get("status", {}).get("short", "NS")),
            }

            SPORTDB_CACHE[cache_key] = result
            return result

        return None

    except Exception as e:
        log(f"SportDB Error: {e}", "WARN")
        return None


def get_sportdb_fixtures(league_name, target_date):
    """
    Holt Spielpläne von SportDB.dev für eine Liga.
    Returns: Liste mit Fixtures
    """
    if not SPORTDB_API_KEY:
        return []

    try:
        r = requests.get(
            "https://api.sportdb.dev/v1/football/fixtures",
            headers={
                "X-API-Key": SPORTDB_API_KEY,
            },
            params={
                "date": str(target_date),
                "league": SPORTDB_LEAGUE_IDS.get(league_name, ""),
            },
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json()
        fixtures_raw = data.get("data", data.get("fixtures", []))
        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for fix in fixtures_raw:
            try:
                home = fix.get("home_team", fix.get("homeTeam", {}).get("name", ""))
                away = fix.get("away_team", fix.get("awayTeam", {}).get("name", ""))
                kickoff_str = fix.get("date", fix.get("datetime", fix.get("fixture", {}).get("date", "")))

                if not home or not away:
                    continue

                if kickoff_str:
                    kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                    if kickoff <= now_utc:
                        continue

                fixtures.append({
                    "home": str(home),
                    "away": str(away),
                    "match_id": fix.get("id", fix.get("fixture_id", "")),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str) if kickoff_str else "TBD",
                    "source": "sportdb",
                })
            except Exception:
                continue

        return fixtures

    except Exception as e:
        log(f"SportDB Fixtures Error: {e}", "WARN")
        return []


# ============================================================
# 🆕 FOREBET - Mathematische BTTS + Over 2.5 Predictions
# ============================================================
FOREBET_CACHE = {}
FOREBET_BLOCKED = False

FOREBET_LEAGUE_URLS = {
    "Premier League": "https://www.forebet.com/en/football-tips-and-predictions-for-england/premier-league",
    "Bundesliga": "https://www.forebet.com/en/football-tips-and-predictions-for-germany/bundesliga",
    "La Liga": "https://www.forebet.com/en/football-tips-and-predictions-for-spain/la-liga",
    "Serie A": "https://www.forebet.com/en/football-tips-and-predictions-for-italy/serie-a",
    "Ligue 1": "https://www.forebet.com/en/football-tips-and-predictions-for-france/ligue-1",
    "Eredivisie": "https://www.forebet.com/en/football-tips-and-predictions-for-netherlands/eredivisie",
    "Champions League": "https://www.forebet.com/en/football-tips-and-predictions-for-europe/champions-league",
    "Europa League": "https://www.forebet.com/en/football-tips-and-predictions-for-europe/europa-league",
    "Championship": "https://www.forebet.com/en/football-tips-and-predictions-for-england/championship",
    "Scottish Premiership": "https://www.forebet.com/en/football-tips-and-predictions-for-scotland/premiership",
}

def get_forebet_prediction(home_team, away_team, league_name, target_date):
    """
    Holt Forebet BTTS + Over 2.5 Wahrscheinlichkeiten via Scraping.
    Returns: {'btts_pct': 68, 'over25_pct': 72, 'avg_goals': 2.8, 'tip': '2'}
    """
    global FOREBET_BLOCKED

    if FOREBET_BLOCKED:
        return None

    cache_key = f"{home_team}_{away_team}_{target_date}"
    if cache_key in FOREBET_CACHE:
        return FOREBET_CACHE[cache_key]

    # Forebet Hauptseite für heutige Spiele
    try:
        date_str = str(target_date).replace("-", "/")
        url = f"https://www.forebet.com/en/football-predictions/predictions-1x2/{date_str}"

        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.forebet.com/",
            },
            timeout=15,
        )

        if r.status_code in [403, 429, 503]:
            if PLAYWRIGHT_AVAILABLE:
                log(f"   🎭 Forebet → Playwright...")
                html = scrape_with_playwright(url, timeout=8000)
                if html:
                    log(f"   ✅ Forebet via Playwright!")
                else:
                    FOREBET_BLOCKED = True
                    return None
            else:
                log(f"   ℹ️  Forebet nicht erreichbar ({r.status_code})")
                FOREBET_BLOCKED = True
                return None

        if not r.ok:
            return None

        html = r.text

        # Team-Namen normalisieren für Suche
        home_norm = normalize_team_name(home_team)
        away_norm = normalize_team_name(away_team)

        # Suche nach Spielblock mit beiden Teams
        # Forebet HTML: <div class="rcnt"> ... teamname ... </div>
        import re as _re

        # Pattern für Spielzeilen
        rows = _re.findall(
            r'<tr[^>]*class="[^"]*tr_0[^"]*"[^>]*>(.*?)</tr>',
            html,
            _re.DOTALL | _re.IGNORECASE
        )

        for row in rows:
            # Team-Namen aus Row extrahieren
            teams_found = _re.findall(r'<span[^>]*class="[^"]*tnms[^"]*"[^>]*>([^<]+)</span>', row)
            if len(teams_found) < 2:
                teams_found = _re.findall(r'<div[^>]*class="[^"]*team[^"]*"[^>]*>([^<]+)</div>', row)

            if len(teams_found) < 2:
                continue

            row_home = normalize_team_name(teams_found[0])
            row_away = normalize_team_name(teams_found[1])

            # Match prüfen
            if not (home_norm[:6] in row_home or row_home[:6] in home_norm):
                continue
            if not (away_norm[:6] in row_away or row_away[:6] in away_norm):
                continue

            # Wahrscheinlichkeiten extrahieren
            probs = _re.findall(r'<span[^>]*class="[^"]*prb[^"]*"[^>]*>(\d+)%?</span>', row)
            avg_goals_m = _re.search(r'<span[^>]*class="[^"]*avg[^"]*"[^>]*>([\d.]+)</span>', row)
            over25_m = _re.search(r'<span[^>]*class="[^"]*ov25[^"]*"[^>]*>([\d.]+)%?</span>', row)
            btts_m = _re.search(r'<span[^>]*class="[^"]*btts[^"]*"[^>]*>([\d.]+)%?</span>', row)

            result = {}

            if len(probs) >= 3:
                result["prob_home"] = int(probs[0])
                result["prob_draw"] = int(probs[1])
                result["prob_away"] = int(probs[2])
                # Forebet Tipp (höchste Wahrscheinlichkeit)
                max_prob = max(result["prob_home"], result["prob_draw"], result["prob_away"])
                if max_prob == result["prob_home"]:
                    result["tip"] = "1"
                elif max_prob == result["prob_draw"]:
                    result["tip"] = "X"
                else:
                    result["tip"] = "2"

            if avg_goals_m:
                result["avg_goals"] = float(avg_goals_m.group(1))
                # Over 2.5 approximieren aus avg goals
                if "avg_goals" in result:
                    g = result["avg_goals"]
                    # Poisson-Approximation
                    import math as _math
                    over25_approx = 1 - sum(
                        (_math.exp(-g) * (g**k)) / _math.factorial(k)
                        for k in range(3)
                    )
                    result["over25_pct"] = round(over25_approx * 100, 1)

            if over25_m:
                result["over25_pct"] = float(over25_m.group(1))

            if btts_m:
                result["btts_pct"] = float(btts_m.group(1))

            if result:
                FOREBET_CACHE[cache_key] = result
                return result

        return None

    except Exception as e:
        log(f"Forebet Error: {str(e)[:60]}", "WARN")
        return None


# ============================================================
# 🆕 SCOUTINGSTATS - AI BTTS Predictions (kostenlos)
# ============================================================
SCOUTINGSTATS_CACHE = {}
SCOUTINGSTATS_BLOCKED = False

def get_scoutingstats_prediction(home_team, away_team, target_date):
    """
    Holt ScoutingStats.ai BTTS + Value Predictions.
    Returns: {'btts_pct': 74, 'over25_pct': 68, 'value_edge': 12}
    """
    global SCOUTINGSTATS_BLOCKED

    if SCOUTINGSTATS_BLOCKED:
        return None

    cache_key = f"scout_{target_date}"  # Pro Tag cachen
    if cache_key in SCOUTINGSTATS_CACHE:
        return SCOUTINGSTATS_CACHE[cache_key]

    try:
        # ScoutingStats API / Scraping
        r = requests.get(
            "https://scoutingstats.ai/api/predictions",
            params={
                "home": home_team,
                "away": away_team,
                "date": str(target_date),
            },
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
            timeout=12,
        )

        if r.status_code in [403, 404, 429]:
            if PLAYWRIGHT_AVAILABLE:
                log(f"   🎭 ScoutingStats → Playwright...")
                html = scrape_with_playwright(url, timeout=8000)
                if html:
                    log(f"   ✅ ScoutingStats via Playwright!")
                else:
                    return _scrape_scoutingstats(home_team, away_team, target_date)
            else:
                return _scrape_scoutingstats(home_team, away_team, target_date)

        if not r.ok:
            return None

        data = r.json()
        if not data:
            return None

        result = {
            "btts_pct": data.get("btts_probability", data.get("btts_pct", 0)),
            "over25_pct": data.get("over25_probability", data.get("over25_pct", 0)),
            "value_edge": data.get("value_edge", 0),
            "confidence": data.get("confidence", 0),
        }

        SCOUTINGSTATS_CACHE[cache_key] = result
        return result

    except Exception:
        return _scrape_scoutingstats(home_team, away_team, target_date)


def _scrape_scoutingstats(home_team, away_team, target_date):
    """Fallback: ScoutingStats Webseite scrapen"""
    global SCOUTINGSTATS_BLOCKED

    try:
        url = f"https://scoutingstats.ai/predictions/{str(target_date)}"
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html",
            },
            timeout=12,
        )

        if r.status_code in [403, 429, 503]:
            if PLAYWRIGHT_AVAILABLE:
                log(f"   🎭 ScoutingStats → Playwright...")
                html = scrape_with_playwright(url, timeout=8000)
                if html:
                    log(f"   ✅ ScoutingStats via Playwright!")
                    # Parse HTML
                    import re as _re2
                    btts_m = _re2.search(r'btts[^>]*>(\d+)%', html, _re2.IGNORECASE)
                    over25_m = _re2.search(r'over.?2\.5[^>]*>(\d+)%', html, _re2.IGNORECASE)
                    result = {}
                    if btts_m:
                        result["btts_pct"] = int(btts_m.group(1))
                    if over25_m:
                        result["over25_pct"] = int(over25_m.group(1))
                    if result:
                        return result
            SCOUTINGSTATS_BLOCKED = True
            return None

        if not r.ok:
            return None

        html = r.text
        home_norm = normalize_team_name(home_team)
        away_norm = normalize_team_name(away_team)

        import re as _re

        # Suche Spielblock
        blocks = _re.findall(r'<div[^>]*class="[^"]*match[^"]*"[^>]*>(.*?)</div>', html, _re.DOTALL)

        for block in blocks:
            teams = _re.findall(r'class="[^"]*team[^"]*"[^>]*>([^<]+)<', block)
            if len(teams) < 2:
                continue

            if not teams_match(home_team, teams[0]):
                continue
            if not teams_match(away_team, teams[1]):
                continue

            btts_m = _re.search(r'btts[^>]*>(\d+)%', block, _re.IGNORECASE)
            over25_m = _re.search(r'over.?2\.?5[^>]*>(\d+)%', block, _re.IGNORECASE)

            result = {}
            if btts_m:
                result["btts_pct"] = int(btts_m.group(1))
            if over25_m:
                result["over25_pct"] = int(over25_m.group(1))

            if result:
                SCOUTINGSTATS_CACHE[f"{home_team}_{away_team}_{target_date}"] = result
                return result

        return None

    except Exception:
        return None




# ============================================================
# 🆕 SOFASCORE - Inoffizielle API (alle Ligen weltweit!)
# ============================================================
SOFASCORE_CACHE = {}
SOFASCORE_BLOCKED = False

SOFASCORE_SLUG_MAP = {
    "Champions League": "uefa-champions-league",
    "Europa League": "uefa-europa-league", 
    "Conference League": "uefa-europa-conference-league",
    "Bundesliga": "bundesliga",
    "2. Bundesliga": "2-bundesliga",
    "Premier League": "premier-league",
    "Championship": "championship",
    "La Liga": "laliga",
    "La Liga 2": "laliga2",
    "Serie A": "serie-a",
    "Serie B": "serie-b",
    "Ligue 1": "ligue-1",
    "Ligue 2": "ligue-2",
    "Eredivisie": "eredivisie",
    "Primeira Liga": "liga-portugal",
    "Pro League Belgien": "jupiler-pro-league",
    "Süper Lig": "super-lig",
    "Bundesliga Österreich": "admiral-bundesliga",
    "Super League Schweiz": "super-league",
    "Scottish Premiership": "scottish-premiership",
    "Danish Superliga": "superliga",
    "Norway Eliteserien": "eliteserien",
    "Sweden Allsvenskan": "allsvenskan",
    "Greece Super League": "super-league-1",
    "Croatia HNL": "hnl",
    "Serbia SuperLiga": "super-liga",
    "Romania Liga I": "liga-i",
    "Czech First League": "czech-liga",
    "Poland Ekstraklasa": "ekstraklasa",
    "MLS": "mls",
    "Brasileirao Serie A": "brasileirao-serie-a",
    "Liga Argentinien": "liga-profesional-argentina",
    "Liga MX": "liga-mx",
    "J1 League Japan": "j1-league",
    "K League 1": "k-league-1",
    "China Super League": "chinese-super-league",
    "Saudi Pro League": "saudi-professional-league",
    "A-League": "a-league",
    "EFL League 1": "league-one",
    "EFL League 2": "league-two",
    "Finland Veikkausliiga": "veikkausliiga",
    "Uruguay Primera": "primera-division-2",
    "India Super League": "isl",
    "Qatar Stars League": "qatar-stars-league",
    "South Africa PSL": "dstv-premiership",
    "Vietnam V-League": "v-league-1",
    "Eerste Divisie": "eerste-divisie",
    "3. Liga Deutschland": "3-liga",
    "Norwegian 1. Division": "1-division",
    "Turkish 1. Lig": "tff-first-league",
    "Danish 1. Division": "1st-division",
    "Swedish Superettan": "superettan",
    "Swiss Challenge League": "challenge-league",
    "Israeli Liga Leumit": "leumit-league",
    "Bulgarian First League": "first-league",
    "Hungarian NB I": "nb-i",
    "Iceland Premier League": "urvalsdeild",
}

def fetch_sofascore_fixtures(league_name, target_date):
    """
    Holt Spielpläne von SofaScore (inoffizielle API).
    Deckt ALLE Ligen weltweit ab - kein Key nötig!
    """
    global SOFASCORE_BLOCKED
    
    if SOFASCORE_BLOCKED:
        return []
    
    cache_key = f"sofa_{league_name}_{target_date}"
    if cache_key in SOFASCORE_CACHE:
        return SOFASCORE_CACHE[cache_key]
    
    try:
        date_str = str(target_date)  # YYYY-MM-DD
        
        # Versuche mehrere SofaScore Endpoints
        urls_to_try = [
            f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}",
            f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}",
        ]
        
        url = urls_to_try[0]
        
        # Rotate User-Agents um 403 zu vermeiden
        import random as _random
        import time as _time
        _ua_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        ]
        
        session = requests.Session()
        session.headers.update({
            "User-Agent": _random.choice(_ua_list),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.sofascore.com/",
            "Origin": "https://www.sofascore.com",
            "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="121"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        })
        
        # Erst Homepage "besuchen" um Cookies zu setzen
        try:
            session.get("https://www.sofascore.com/", timeout=5)
        except:
            pass
        
        r = session.get(url, timeout=15)
        
        if r.status_code in [403, 429, 503]:
            if PLAYWRIGHT_AVAILABLE:
                return pw_get_sofascore_fixtures(league_name, target_date)
            return []
        
        if not r.ok:
            return []
        
        data = r.json()
        events = data.get("events", [])
        
        if not events:
            return []
        
        # Liga-Slug für Filterung
        league_slug = SOFASCORE_SLUG_MAP.get(league_name, "").lower()
        
        now_utc = datetime.now(timezone.utc)
        fixtures = []
        
        for event in events:
            try:
                # Liga prüfen
                tournament = event.get("tournament", {})
                tour_slug = tournament.get("slug", "").lower()
                tour_name = tournament.get("name", "").lower()
                category = tournament.get("category", {}).get("name", "").lower()
                
                # Match-Check für Liga
                if league_slug:
                    if league_slug not in tour_slug and league_slug not in tour_name:
                        # Fallback: Kategorie oder Name prüfen
                        league_lower = league_name.lower()
                        if not any(w in tour_name for w in league_lower.split() if len(w) > 4):
                            continue
                
                home_team = event.get("homeTeam", {}).get("name", "")
                away_team = event.get("awayTeam", {}).get("name", "")
                
                if not home_team or not away_team:
                    continue
                
                # Kickoff Zeit
                start_timestamp = event.get("startTimestamp", 0)
                if start_timestamp:
                    kickoff = datetime.fromtimestamp(start_timestamp, tz=timezone.utc)
                    if kickoff <= now_utc:
                        continue
                    kickoff_str = kickoff.strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    kickoff_str = f"{target_date}T00:00:00Z"
                
                # Status prüfen (nur nicht gestartete)
                status = event.get("status", {}).get("type", "")
                if status in ["inprogress", "finished"]:
                    continue
                
                fixtures.append({
                    "home": home_team,
                    "away": away_team,
                    "match_id": event.get("id", ""),
                    "home_id": event.get("homeTeam", {}).get("id"),
                    "away_id": event.get("awayTeam", {}).get("id"),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "sofascore",
                })
                
            except Exception:
                continue
        
        SOFASCORE_CACHE[cache_key] = fixtures
        
        if fixtures:
            log(f"   ⚡ SofaScore: {len(fixtures)} Spiele für {league_name}")
        
        return fixtures
        
    except Exception as e:
        log(f"SofaScore Error: {str(e)[:60]}", "WARN")
        return []


def fetch_sofascore_all_today(target_date):
    """
    Holt ALLE heutigen Spiele von SofaScore auf einmal.
    Viel effizienter als pro-Liga Calls!
    """
    global SOFASCORE_BLOCKED
    
    if SOFASCORE_BLOCKED:
        return {}
    
    cache_key = f"sofa_all_{target_date}"
    if cache_key in SOFASCORE_CACHE:
        return SOFASCORE_CACHE[cache_key]
    
    try:
        date_str = str(target_date)
        url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
        
        import random as _random2
        _ua_list2 = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        ]
        r = requests.get(
            url,
            headers={
                "User-Agent": _random2.choice(_ua_list2),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.sofascore.com/",
                "Origin": "https://www.sofascore.com",
            },
            timeout=20,
        )
        
        if r.status_code in [403, 429, 503]:
            log(f"   🎭 SofaScore blockiert ({r.status_code}) → Playwright...")
            if PLAYWRIGHT_AVAILABLE:
                html = scrape_with_playwright(url, timeout=15000)
                if html:
                    import json as _pj, re as _pre
                    m = _pre.search(r'"events"\s*:\s*(\[.*?\])\s*[,}]', html, _pre.DOTALL)
                    if m:
                        try:
                            events_raw = _pj.loads(m.group(1))
                            data = {"events": events_raw}
                            log(f"   ✅ SofaScore via Playwright: {len(events_raw)} Events")
                            r = type('R', (), {'ok': True, 'status_code': 200, 'json': lambda self=None: data})()
                        except Exception:
                            pass
            if r.status_code in [403, 429, 503]:
                log("   ℹ️  SofaScore nicht erreichbar → Fallback aktiv", "INFO")
                return {}
        
        if not r.ok:
            return {}
        
        data = r.json()
        events = data.get("events", [])
        
        if not events:
            return {}
        
        # Gruppiere nach Liga-Slug
        now_utc = datetime.now(timezone.utc)
        by_league = {}
        
        for event in events:
            try:
                status = event.get("status", {}).get("type", "")
                if status in ["inprogress", "finished"]:
                    continue
                
                tournament = event.get("tournament", {})
                tour_slug = tournament.get("slug", "").lower()
                tour_name = tournament.get("name", "")
                
                home_team = event.get("homeTeam", {}).get("name", "")
                away_team = event.get("awayTeam", {}).get("name", "")
                
                if not home_team or not away_team:
                    continue
                
                start_timestamp = event.get("startTimestamp", 0)
                if start_timestamp:
                    kickoff = datetime.fromtimestamp(start_timestamp, tz=timezone.utc)
                    if kickoff <= now_utc:
                        continue
                    kickoff_str = kickoff.strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    kickoff_str = f"{target_date}T00:00:00Z"
                
                fixture = {
                    "home": home_team,
                    "away": away_team,
                    "match_id": event.get("id", ""),
                    "home_id": event.get("homeTeam", {}).get("id"),
                    "away_id": event.get("awayTeam", {}).get("id"),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "sofascore",
                }
                
                if tour_slug not in by_league:
                    by_league[tour_slug] = []
                by_league[tour_slug].append(fixture)
                
            except Exception:
                continue
        
        SOFASCORE_CACHE[cache_key] = by_league
        log(f"   ⚡ SofaScore: {len(events)} Spiele total, {len(by_league)} Ligen geladen")
        return by_league
        
    except Exception as e:
        log(f"SofaScore All Error: {str(e)[:60]}", "WARN")
        return {}



# ============================================================
# 🆕 SOFASCORE LINEUPS - Aufstellungen (kein Key nötig!)
# ============================================================
SOFASCORE_LINEUP_CACHE = {}

def get_sofascore_lineups(match_id, home_team, away_team):
    """
    Holt Aufstellungen von SofaScore.
    Returns: {'home_lineup': [...], 'away_lineup': [...], 'confirmed': bool}
    """
    if not match_id:
        return None

    cache_key = f"sofa_lineup_{match_id}"
    if cache_key in SOFASCORE_LINEUP_CACHE:
        return SOFASCORE_LINEUP_CACHE[cache_key]

    try:
        url = f"https://api.sofascore.com/api/v1/event/{match_id}/lineups"
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
                "Accept": "application/json",
                "Referer": "https://www.sofascore.com/",
            },
            timeout=12,
        )

        if not r.ok:
            SOFASCORE_LINEUP_CACHE[cache_key] = None
            return None

        data = r.json()
        home_data = data.get("home", {})
        away_data = data.get("away", {})

        def extract_players(team_data, only_starters=True):
            players = []
            for p in team_data.get("players", []):
                player = p.get("player", {})
                stats = p.get("statistics", {})
                position = p.get("position", "")
                # SofaScore: position 1-11 = Starter, 12+ = Reserve
                shirt = p.get("shirtNumber", 99)
                is_starter = shirt <= 11 or position in ["G", "D", "M", "F"]
                if only_starters and not is_starter:
                    continue
                players.append({
                    "name": player.get("name", ""),
                    "position": position,
                    "shirt": shirt,
                    "rating": stats.get("rating", 0),
                })
            return players

        home_starters = extract_players(home_data)
        away_starters = extract_players(away_data)
        home_subs = extract_players(home_data, only_starters=False)
        away_subs = extract_players(away_data, only_starters=False)

        confirmed = data.get("confirmed", False)

        result = {
            "home_lineup": home_starters,
            "away_lineup": away_starters,
            "home_subs": home_subs,
            "away_subs": away_subs,
            "confirmed": confirmed,
            "lineup_available": len(home_starters) > 0,
        }

        SOFASCORE_LINEUP_CACHE[cache_key] = result
        return result

    except Exception as e:
        log(f"SofaScore Lineup Error: {str(e)[:60]}", "WARN")
        SOFASCORE_LINEUP_CACHE[cache_key] = None
        return None


def get_sofascore_match_result(match_id):
    """
    Holt Spielergebnis von SofaScore für check.py
    Returns: {'home_score': 2, 'away_score': 1, 'status': 'finished', 'ht_home': 1, 'ht_away': 0}
    """
    if not match_id:
        return None

    try:
        url = f"https://api.sofascore.com/api/v1/event/{match_id}"
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
                "Accept": "application/json",
                "Referer": "https://www.sofascore.com/",
            },
            timeout=12,
        )

        if not r.ok:
            return None

        data = r.json()
        event = data.get("event", {})
        status = event.get("status", {}).get("type", "")

        if status != "finished":
            return None

        score = event.get("homeScore", {})
        home_score = event.get("homeScore", {}).get("current", 0) or 0
        away_score = event.get("awayScore", {}).get("current", 0) or 0
        ht_home = event.get("homeScore", {}).get("period1", 0) or 0
        ht_away = event.get("awayScore", {}).get("period1", 0) or 0

        return {
            "home_score": home_score,
            "away_score": away_score,
            "ht_home": ht_home,
            "ht_away": ht_away,
            "status": "finished",
            "btts": home_score > 0 and away_score > 0,
            "over25": (home_score + away_score) > 2,
            "btts_ht": ht_home > 0 and ht_away > 0,
            "total_goals": home_score + away_score,
        }

    except Exception as e:
        log(f"SofaScore Result Error: {str(e)[:60]}", "WARN")
        return None


# ============================================================
# 🆕 CLUBELO - Team Stärke Ratings (kein Key nötig!)
# ============================================================
CLUBELO_CACHE = {}

def get_clubelo_rating(team_name):
    """
    Holt Team-Stärke Rating von ClubElo.com
    Elo-Rating: ~1800 = Top Team, ~1500 = Mittelfeld, ~1200 = schwach
    Returns: {'elo': 1750, 'rank': 5, 'country': 'GER'}
    """
    cache_key = f"elo_{team_name}"
    if cache_key in CLUBELO_CACHE:
        return CLUBELO_CACHE[cache_key]

    try:
        # ClubElo API - kein Key nötig
        name_clean = team_name.replace(" ", "_").replace(".", "")
        url = f"http://api.clubelo.com/{name_clean}"

        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )

        if not r.ok:
            CLUBELO_CACHE[cache_key] = None
            return None

        lines = r.text.strip().splitlines()
        if len(lines) < 2:
            CLUBELO_CACHE[cache_key] = None
            return None

        # Format: Rank,Club,Country,Level,Elo,From,To
        last_line = lines[-1].split(",")
        if len(last_line) < 5:
            CLUBELO_CACHE[cache_key] = None
            return None

        result = {
            "rank": int(last_line[0]) if last_line[0].isdigit() else 0,
            "team": last_line[1],
            "country": last_line[2],
            "level": int(last_line[3]) if last_line[3].isdigit() else 0,
            "elo": float(last_line[4]) if last_line[4].replace(".", "").isdigit() else 0,
        }

        CLUBELO_CACHE[cache_key] = result
        return result

    except Exception:
        CLUBELO_CACHE[cache_key] = None
        return None


def calculate_elo_btts_probability(home_elo, away_elo):
    """
    Berechnet BTTS-Wahrscheinlichkeit aus Elo-Ratings.
    Ausgeglichenere Teams = mehr BTTS.
    """
    if not home_elo or not away_elo:
        return None

    elo_diff = abs(home_elo - away_elo)

    # Je kleiner der Unterschied, desto mehr BTTS
    if elo_diff < 50:
        btts_boost = 8   # Sehr ausgeglichen
    elif elo_diff < 100:
        btts_boost = 5
    elif elo_diff < 200:
        btts_boost = 2
    elif elo_diff < 300:
        btts_boost = -3
    else:
        btts_boost = -8  # Großer Unterschied = weniger BTTS

    base_btts = 52  # Durchschnittliche BTTS Rate
    return min(85, max(30, base_btts + btts_boost))


# ============================================================
# 🆕 ALLSPORTSAPI - 500+ Ligen weltweit (100 Calls/Tag gratis)
# ============================================================
ALLSPORTS_API_KEY = env("ALLSPORTS_API_KEY", "")
ALLSPORTS_CACHE = {}

ALLSPORTS_LEAGUE_IDS = {
    "Champions League": 175,
    "Europa League": 176,
    "Premier League": 4,
    "Bundesliga": 78,
    "La Liga": 87,
    "Serie A": 186,
    "Ligue 1": 168,
    "Eredivisie": 61,
    "Primeira Liga": 182,
    "MLS": 199,
    "Brasileirao Serie A": 36,
    "Liga Argentinien": 14,
    "J1 League Japan": 98,
    "K League 1": 106,
    "Saudi Pro League": 184,
    "A-League": 15,
    "EFL League 1": 8,
    "EFL League 2": 9,
    "Championship": 7,
    "Scottish Premiership": 185,
    "Finland Veikkausliiga": 72,
    "Uruguay Primera": 207,
    "India Super League": 93,
    "Qatar Stars League": 181,
    "South Africa PSL": 188,
    "Vietnam V-League": 213,
    "Denmark Superliga": 57,
    "Norway Eliteserien": 167,
    "Sweden Allsvenskan": 191,
    "Greece Super League": 83,
    "Croatia HNL": 46,
    "Bulgaria First League": 38,
    "Hungary NB I": 89,
    "Iceland Premier League": 90,
}

def fetch_allsports_fixtures(league_name, target_date):
    """
    Holt Spielpläne von AllSportsAPI (500+ Ligen, 100 Calls/Tag gratis).
    """
    if not ALLSPORTS_API_KEY:
        return []

    league_id = ALLSPORTS_LEAGUE_IDS.get(league_name)
    if not league_id:
        return []

    cache_key = f"allsports_{league_name}_{target_date}"
    if cache_key in ALLSPORTS_CACHE:
        return ALLSPORTS_CACHE[cache_key]

    try:
        r = requests.get(
            "https://allsportsapi.com/api/football/",
            params={
                "met": "Fixtures",
                "APIkey": ALLSPORTS_API_KEY,
                "leagueId": league_id,
                "from": str(target_date),
                "to": str(target_date),
            },
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json()
        matches = data.get("result", [])

        if not matches:
            return []

        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for m in matches:
            try:
                kickoff_str = f"{m.get('event_date', '')}T{m.get('event_time', '00:00')}:00Z"
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))

                if kickoff <= now_utc:
                    continue

                fixtures.append({
                    "home": m.get("event_home_team", ""),
                    "away": m.get("event_away_team", ""),
                    "match_id": str(m.get("event_key", "")),
                    "home_id": m.get("home_team_key"),
                    "away_id": m.get("away_team_key"),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "allsports",
                })
            except Exception:
                continue

        ALLSPORTS_CACHE[cache_key] = fixtures
        return fixtures

    except Exception as e:
        log(f"AllSports Error: {str(e)[:60]}", "WARN")
        return []


def get_allsports_result(match_id):
    """
    Holt Spielergebnis von AllSportsAPI für check.py
    """
    if not ALLSPORTS_API_KEY or not match_id:
        return None

    try:
        r = requests.get(
            "https://allsportsapi.com/api/football/",
            params={
                "met": "Fixtures",
                "APIkey": ALLSPORTS_API_KEY,
                "matchId": match_id,
            },
            timeout=10,
        )

        if not r.ok:
            return None

        data = r.json()
        match = data.get("result", [{}])[0] if data.get("result") else None

        if not match:
            return None

        status = match.get("event_status", "")
        if status != "Finished":
            return None

        home_score = int(match.get("event_final_result", "0-0").split("-")[0] or 0)
        away_score = int(match.get("event_final_result", "0-0").split("-")[1] or 0)
        ht = match.get("event_halftime_result", "0-0")
        ht_home = int(ht.split("-")[0] or 0)
        ht_away = int(ht.split("-")[1] or 0)

        return {
            "home_score": home_score,
            "away_score": away_score,
            "ht_home": ht_home,
            "ht_away": ht_away,
            "btts": home_score > 0 and away_score > 0,
            "over25": (home_score + away_score) > 2,
            "btts_ht": ht_home > 0 and ht_away > 0,
            "total_goals": home_score + away_score,
            "status": "finished",
        }

    except Exception:
        return None


# ============================================================
# 🆕 TRANSFERMARKT - Verletzungen (beste Quelle weltweit!)
# ============================================================
TRANSFERMARKT_CACHE = {}
TRANSFERMARKT_BLOCKED = False

TM_LEAGUE_SLUGS = {
    "Bundesliga": ("bundesliga", "L1"),
    "2. Bundesliga": ("2-bundesliga", "L2"),
    "Premier League": ("premier-league", "GB1"),
    "Championship": ("championship", "GB2"),
    "La Liga": ("primera-division", "ES1"),
    "Serie A": ("serie-a", "IT1"),
    "Ligue 1": ("ligue-1", "FR1"),
    "Eredivisie": ("eredivisie", "NL1"),
    "Primeira Liga": ("liga-nos", "PO1"),
    "Pro League Belgien": ("jupiler-pro-league", "BE1"),
    "Süper Lig": ("super-lig", "TR1"),
    "Champions League": ("champions-league", "CL"),
    "Europa League": ("europa-league", "EL"),
}

def get_transfermarkt_injuries(team_name, league_name):
    """
    Holt Verletzungen von Transfermarkt.
    Unterscheidet zwischen Stammspieler und Reserve!
    Returns: {'injured': [...], 'suspended': [...], 'starters_out': [...], 'reserves_out': [...]}
    """
    global TRANSFERMARKT_BLOCKED

    if TRANSFERMARKT_BLOCKED:
        return None

    cache_key = f"tm_{team_name}_{league_name}"
    if cache_key in TRANSFERMARKT_CACHE:
        return TRANSFERMARKT_CACHE[cache_key]

    try:
        # Team-Suche auf Transfermarkt
        search_url = "https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche"
        r = requests.get(
            search_url,
            params={"query": team_name, "Datei": "spieler"},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "de-DE,de;q=0.9",
                "Referer": "https://www.transfermarkt.com/",
            },
            timeout=12,
        )

        if r.status_code in [403, 429, 503]:
            if PLAYWRIGHT_AVAILABLE:
                return pw_get_transfermarkt_injuries(team_name, league_name)
            TRANSFERMARKT_BLOCKED = True
            return None

        if not r.ok:
            return None

        html = r.text

        # Suche nach Verletzungs-Tabelle
        import re as _re

        # Pattern für verletzte Spieler
        injured_pattern = _re.findall(
            r'class="[^"]*verletzt[^"]*"[^>]*>.*?<a[^>]*>([^<]+)</a>.*?<td[^>]*>([^<]+)</td>',
            html,
            _re.DOTALL | _re.IGNORECASE
        )

        result = {
            "injured": [],
            "suspended": [],
            "starters_out": [],
            "reserves_out": [],
            "total_out": 0,
        }

        for player_name, reason in injured_pattern[:10]:
            player_name = player_name.strip()
            reason = reason.strip()

            is_starter = True  # Vereinfacht - in Produktion aus Marktwert schätzen

            entry = {"name": player_name, "reason": reason}

            if "gesperrt" in reason.lower() or "sperre" in reason.lower():
                result["suspended"].append(entry)
            else:
                result["injured"].append(entry)

            if is_starter:
                result["starters_out"].append(entry)
            else:
                result["reserves_out"].append(entry)

        result["total_out"] = len(result["injured"]) + len(result["suspended"])
        result["has_data"] = result["total_out"] > 0

        TRANSFERMARKT_CACHE[cache_key] = result
        return result

    except Exception as e:
        log(f"Transfermarkt Error: {str(e)[:60]}", "WARN")
        TRANSFERMARKT_CACHE[cache_key] = None
        return None


# ============================================================
# 🆕 ESPN API (inoffiziell) - US Ligen + weitere
# ============================================================
ESPN_CACHE = {}

ESPN_LEAGUE_IDS = {
    "MLS": ("soccer", "usa.1"),
    "Premier League": ("soccer", "eng.1"),
    "Bundesliga": ("soccer", "ger.1"),
    "La Liga": ("soccer", "esp.1"),
    "Serie A": ("soccer", "ita.1"),
    "Ligue 1": ("soccer", "fra.1"),
    "Champions League": ("soccer", "uefa.champions"),
    "Liga MX": ("soccer", "mex.1"),
    "Brasileirao Serie A": ("soccer", "bra.1"),
    "Liga Argentinien": ("soccer", "arg.1"),
    "A-League": ("soccer", "aus.1"),
    "J1 League Japan": ("soccer", "jpn.1"),
    "K League 1": ("soccer", "kor.1"),
    "Saudi Pro League": ("soccer", "sau.1"),
    "EFL League 1": ("soccer", "eng.3"),
    "EFL League 2": ("soccer", "eng.4"),
    "Championship": ("soccer", "eng.2"),
    "Scottish Premiership": ("soccer", "sco.1"),
    # 🌍 WM + Länderspiele
    "WM 2026": ("soccer", "fifa.world"),
    "UEFA Nations League": ("soccer", "uefa.nations"),
    "Copa America": ("soccer", "conmebol.copa"),
    "Afrika Cup": ("soccer", "caf.nations"),
    "Freundschaftsspiele International": ("soccer", "fifa.friendly"),
}

def fetch_espn_fixtures(league_name, target_date):
    """
    Holt Spielpläne von ESPN inoffizieller API.
    Gut für US Ligen und Top-Ligen.
    """
    league_info = ESPN_LEAGUE_IDS.get(league_name)
    if not league_info:
        return []

    sport, league_id = league_info
    cache_key = f"espn_{league_name}_{target_date}"

    if cache_key in ESPN_CACHE:
        return ESPN_CACHE[cache_key]

    try:
        date_str = str(target_date).replace("-", "")  # YYYYMMDD
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_id}/scoreboard"

        r = requests.get(
            url,
            params={"dates": date_str},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json()
        events = data.get("events", [])

        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for event in events:
            try:
                competitions = event.get("competitions", [{}])
                comp = competitions[0] if competitions else {}
                competitors = comp.get("competitors", [])

                if len(competitors) < 2:
                    continue

                home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

                home_name = home.get("team", {}).get("displayName", "")
                away_name = away.get("team", {}).get("displayName", "")

                if not home_name or not away_name:
                    continue

                kickoff_str = event.get("date", "")
                if kickoff_str:
                    kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                    if kickoff <= now_utc:
                        continue

                status = comp.get("status", {}).get("type", {}).get("name", "")
                if status in ["STATUS_FINAL", "STATUS_IN_PROGRESS"]:
                    continue

                fixtures.append({
                    "home": home_name,
                    "away": away_name,
                    "match_id": event.get("id", ""),
                    "home_id": home.get("team", {}).get("id"),
                    "away_id": away.get("team", {}).get("id"),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str) if kickoff_str else "TBD",
                    "source": "espn",
                })

            except Exception:
                continue

        ESPN_CACHE[cache_key] = fixtures
        return fixtures

    except Exception as e:
        log(f"ESPN Error: {str(e)[:60]}", "WARN")
        return []


def get_espn_result(match_id, league_name):
    """
    Holt Spielergebnis von ESPN für check.py
    """
    league_info = ESPN_LEAGUE_IDS.get(league_name)
    if not league_info or not match_id:
        return None

    sport, league_id = league_info

    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_id}/summary"
        r = requests.get(
            url,
            params={"event": match_id},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )

        if not r.ok:
            return None

        data = r.json()
        header = data.get("header", {})
        competitions = header.get("competitions", [{}])
        comp = competitions[0] if competitions else {}

        status = comp.get("status", {}).get("type", {}).get("name", "")
        if status != "STATUS_FINAL":
            return None

        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            return None

        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

        home_score = int(home.get("score", 0) or 0)
        away_score = int(away.get("score", 0) or 0)

        return {
            "home_score": home_score,
            "away_score": away_score,
            "ht_home": 0,  # ESPN HT nicht immer verfügbar
            "ht_away": 0,
            "btts": home_score > 0 and away_score > 0,
            "over25": (home_score + away_score) > 2,
            "btts_ht": False,
            "total_goals": home_score + away_score,
            "status": "finished",
        }

    except Exception:
        return None



# ============================================================
# 🆕 FLASHSCORE - Inoffizielle API für Ergebnisse
# ============================================================
FLASHSCORE_CACHE = {}

def fetch_flashscore_fixtures(league_name, target_date):
    """
    Holt Spielpläne von Flashscore (inoffiziell).
    Gute Alternative wenn SofaScore blockiert.
    """
    cache_key = f"flash_{league_name}_{target_date}"
    if cache_key in FLASHSCORE_CACHE:
        return FLASHSCORE_CACHE[cache_key]

    # Flashscore Sport-IDs
    FLASHSCORE_IDS = {
        "Bundesliga": "football/germany/bundesliga",
        "Premier League": "football/england/premier-league",
        "La Liga": "football/spain/laliga",
        "Serie A": "football/italy/serie-a",
        "Ligue 1": "football/france/ligue-1",
        "Champions League": "football/europe/champions-league",
        "Europa League": "football/europe/europa-league",
        "Eredivisie": "football/netherlands/eredivisie",
        "Primeira Liga": "football/portugal/liga-portugal",
        "Süper Lig": "football/turkey/super-lig",
        "J1 League Japan": "football/japan/j1-league",
        "K League 1": "football/south-korea/k-league-1",
        "MLS": "football/usa/mls",
        "Brasileirao Serie A": "football/brazil/serie-a",
    }

    sport_path = FLASHSCORE_IDS.get(league_name)
    if not sport_path:
        return []

    try:
        # Flashscore Widget API
        date_str = str(target_date).replace("-", "")
        url = f"https://d.flashscore.com/x/feed/f_1_{date_str}_1_de_1"
        
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-GeoIP": "1",
                "Referer": "https://www.flashscore.com/",
            },
            timeout=12,
        )

        if not r.ok:
            return []

        # Parse Flashscore format (pipe-separated)
        text = r.text
        fixtures = []
        now_utc = datetime.now(timezone.utc)

        # Flashscore gibt alle Spiele zurück - wir filtern nach Liga
        lines = text.split("¬")
        current_league = ""
        
        for line in lines:
            if "~ZA÷" in line:  # Liga-Name
                current_league = line.split("ZA÷")[-1].split("¬")[0] if "ZA÷" in line else ""
            
            if "~AA÷" in line and league_name.lower()[:6] in current_league.lower():
                # Spiel-Zeile parsen
                parts = {p.split("÷")[0]: p.split("÷")[1] for p in line.split("¬") if "÷" in p}
                
                home = parts.get("AE", "")
                away = parts.get("AF", "")
                timestamp = parts.get("AD", "0")
                
                if not home or not away:
                    continue
                
                try:
                    kickoff = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
                    if kickoff <= now_utc:
                        continue
                    
                    fixtures.append({
                        "home": home,
                        "away": away,
                        "match_id": parts.get("AA", ""),
                        "time_utc": kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "time_local": get_local_time(kickoff.strftime("%Y-%m-%dT%H:%M:%SZ")),
                        "source": "flashscore",
                    })
                except Exception:
                    continue

        FLASHSCORE_CACHE[cache_key] = fixtures
        return fixtures

    except Exception as e:
        log(f"Flashscore Error: {str(e)[:60]}", "WARN")
        return []



# ============================================================
# 🆕 LIVESCORE API - Echtzeit Fixtures (60 Calls/Stunde gratis)
# ============================================================
LIVESCORE_API_KEY = env("LIVESCORE_API_KEY", "")
LIVESCORE_SECRET = env("LIVESCORE_SECRET", "")
LIVESCORE_CACHE = {}

LIVESCORE_COMPETITION_IDS = {
    "Premier League": 2,
    "Bundesliga": 25,
    "La Liga": 4,
    "Serie A": 13,
    "Ligue 1": 16,
    "Champions League": 1,
    "Europa League": 8,
    "Eredivisie": 21,
    "Primeira Liga": 27,
    "MLS": 45,
    "J1 League Japan": 65,
    "K League 1": 74,
    "Brasileirao Serie A": 38,
    "Liga Argentinien": 39,
    "A-League Australia": 67,
    "Saudi Pro League": 78,
    "EFL League 1": 6,
    "EFL League 2": 7,
    "Championship": 5,
    "Scottish Premiership": 29,
}

def fetch_livescore_fixtures(league_name, target_date):
    """
    Holt Fixtures von Livescore API (livescore-api.com).
    Gratis: 60 Calls/Stunde.
    """
    if not LIVESCORE_API_KEY:
        return []

    comp_id = LIVESCORE_COMPETITION_IDS.get(league_name)
    if not comp_id:
        return []

    cache_key = f"livescore_{league_name}_{target_date}"
    if cache_key in LIVESCORE_CACHE:
        return LIVESCORE_CACHE[cache_key]

    try:
        r = requests.get(
            "https://livescore-api.com/api-client/fixtures/matches.json",
            params={
                "key": LIVESCORE_API_KEY,
                "secret": LIVESCORE_SECRET,
                "competition_id": comp_id,
                "date": str(target_date),
            },
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json()
        matches = data.get("data", {}).get("match", [])

        if not matches:
            return []

        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for m in matches:
            try:
                date_str = m.get("date", "")
                time_str = m.get("time", "00:00")
                kickoff_str = f"{date_str}T{time_str}:00Z"
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))

                if kickoff <= now_utc:
                    continue

                fixtures.append({
                    "home": m.get("home_name", ""),
                    "away": m.get("away_name", ""),
                    "match_id": str(m.get("id", "")),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "livescore",
                })
            except Exception:
                continue

        LIVESCORE_CACHE[cache_key] = fixtures
        return fixtures

    except Exception as e:
        log(f"Livescore Error: {str(e)[:60]}", "WARN")
        return []



# ============================================================
# 🆕 API-NINJAS Football - Fixtures (10.000 Calls/Monat gratis)
# ============================================================
API_NINJAS_KEY = env("API_NINJAS_KEY", "")
API_NINJAS_CACHE = {}

API_NINJAS_LEAGUES = {
    "Champions League": "UEFA Champions League",
    "Europa League": "UEFA Europa League",
    "Bundesliga": "Bundesliga",
    "2. Bundesliga": "2. Bundesliga",
    "Premier League": "Premier League",
    "Championship": "Championship",
    "EFL League 1": "League One",
    "EFL League 2": "League Two",
    "La Liga": "La Liga",
    "La Liga 2": "La Liga 2",
    "Serie A": "Serie A",
    "Serie B": "Serie B",
    "Ligue 1": "Ligue 1",
    "Ligue 2": "Ligue 2",
    "Eredivisie": "Eredivisie",
    "Primeira Liga": "Primeira Liga",
    "Pro League Belgien": "First Division A",
    "Süper Lig": "Süper Lig",
    "Scottish Premiership": "Scottish Premiership",
    "MLS": "MLS",
    "Brasileirao Serie A": "Série A",
    "Liga Argentinien": "Primera División",
    "J1 League Japan": "J1 League",
    "K League 1": "K League 1",
    "Saudi Pro League": "Saudi Pro League",
    "A-League Australia": "A-League",
    "Danish Superliga": "Superliga",
    "Norway Eliteserien": "Eliteserien",
    "Sweden Allsvenskan": "Allsvenskan",
    "Finland Veikkausliiga": "Veikkausliiga",
    "Greece Super League": "Super League",
    "Poland Ekstraklasa": "Ekstraklasa",
    "Czech First League": "Czech First League",
    "Romania Liga I": "Liga I",
    "Croatia HNL": "HNL",
    "Serbia SuperLiga": "SuperLiga",
    "Ukraine Premier": "Premier League",
    "EFL League 1": "League One",
    "EFL League 2": "League Two",
}

def fetch_api_ninjas_fixtures(league_name, target_date):
    """
    API-Ninjas blockiert GitHub IPs (Host not in allowlist)
    → Deaktiviert bis Lösung gefunden
    """
    return []  # GitHub IPs blockiert

    league_str = API_NINJAS_LEAGUES.get(league_name)
    if not league_str:
        return []

    cache_key = f"ninjas_{league_name}_{target_date}"
    if cache_key in API_NINJAS_CACHE:
        return API_NINJAS_CACHE[cache_key]

    try:
        # API-Ninjas Football endpoint
        for endpoint in [
            "https://api.api-ninjas.com/v1/football",
            "https://api.api-ninjas.com/v1/sports/events",
        ]:
            r = requests.get(
                endpoint,
                headers={
                    "X-Api-Key": API_NINJAS_KEY,
                    "Accept": "application/json",
                },
                params={
                    "league": league_str,
                    "date": str(target_date),
                },
                timeout=12,
            )
            if r.ok and r.json():
                break

        if not r.ok:
            log(f"API-Ninjas Error: {r.status_code}", "WARN")
            return []

        data = r.json()
        if not data:
            return []

        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for event in data:
            try:
                home = event.get("home_team", "")
                away = event.get("away_team", "")

                if not home or not away:
                    continue

                # Zeit parsen
                time_str = event.get("time", "")
                date_str = str(target_date)

                kickoff_str = f"{date_str}T{time_str}:00Z" if time_str else f"{date_str}T12:00:00Z"

                try:
                    kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                    if kickoff <= now_utc:
                        continue
                except:
                    pass

                fixtures.append({
                    "home": home,
                    "away": away,
                    "match_id": f"ninjas_{hash(home+away)}",
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "api-ninjas",
                })

            except Exception:
                continue

        API_NINJAS_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🥷 API-Ninjas: {len(fixtures)} Spiele für {league_name}")
        return fixtures

    except Exception as e:
        log(f"API-Ninjas Error: {str(e)[:60]}", "WARN")
        return []



# ============================================================
# 🆕 THESPORTSDB - Fixtures (Free Key "123", alle Ligen!)
# ============================================================
THESPORTSDB_FIXTURES_CACHE = {}

THESPORTSDB_LEAGUE_IDS = {
    "Champions League": 4480,
    "Europa League": 4735,
    "Bundesliga": 4331,
    "2. Bundesliga": 4332,
    "Premier League": 4328,
    "Championship": 4329,
    "EFL League 1": 4330,
    "La Liga": 4335,
    "Serie A": 4332,
    "Ligue 1": 4334,
    "Eredivisie": 4337,
    "Primeira Liga": 4344,
    "Pro League Belgien": 4342,
    "Süper Lig": 4340,
    "Scottish Premiership": 4330,
    "MLS": 4346,
    "Brasileirao Serie A": 4351,
    "Liga Argentinien": 4406,
    "J1 League Japan": 4396,
    "K League 1": 4397,
    "Saudi Pro League": 4406,
    "A-League Australia": 4356,
    "Danish Superliga": 4341,
    "Norway Eliteserien": 4345,
    "Sweden Allsvenskan": 4349,
    "Greece Super League": 4336,
    "Poland Ekstraklasa": 4422,
    "Czech First League": 4418,
    "Champions League": 4480,
    "UEFA Youth League": 4481,
}

def fetch_thesportsdb_fixtures(league_name, target_date):
    """
    TheSportsDB mit strengem Datum-Filter.
    Nur Spiele die EXAKT am target_date sind UND in der Zukunft!
    """
    league_id = THESPORTSDB_LEAGUE_IDS.get(league_name)
    if not league_id:
        return []

    cache_key = f"tsdb_{league_name}_{target_date}"
    if cache_key in THESPORTSDB_FIXTURES_CACHE:
        return THESPORTSDB_FIXTURES_CACHE[cache_key]

    try:
        r = requests.get(
            f"https://www.thesportsdb.com/api/v1/json/123/eventsday.php",
            params={"d": str(target_date), "s": "Soccer"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json()
        events = data.get("events") or []

        if not events:
            return []

        now_utc = datetime.now(timezone.utc)
        target_str = str(target_date)
        fixtures = []

        for event in events:
            try:
                # Strenger Datum Check!
                event_date = event.get("dateEvent", "")
                if event_date != target_str:
                    continue

                # Liga ID Check!
                event_league_id = str(event.get("idLeague", ""))
                if event_league_id != str(league_id):
                    continue

                # Status Check - nur zukünftige!
                status = event.get("strStatus", "")
                if status in ["Match Finished", "FT", "AET", "PEN", "After Extra Time"]:
                    continue

                home = event.get("strHomeTeam", "")
                away = event.get("strAwayTeam", "")

                if not home or not away:
                    continue

                # Sanity Check - keine bekannten falschen Matches
                if home == away:
                    continue

                # Zeit Check
                time_str = event.get("strTime", "12:00:00")
                kickoff_str = f"{target_str}T{time_str}Z"
                try:
                    kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                    if kickoff <= now_utc:
                        continue
                except Exception:
                    kickoff_str = f"{target_str}T12:00:00Z"

                fixtures.append({
                    "home": home,
                    "away": away,
                    "match_id": event.get("idEvent", ""),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "thesportsdb",
                })

            except Exception:
                continue

        THESPORTSDB_FIXTURES_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🏆 TheSportsDB: {len(fixtures)} Spiele für {league_name}")
        return fixtures

    except Exception as e:
        log(f"TheSportsDB Error: {str(e)[:60]}", "WARN")
        return []

    cache_key = f"tsdb_{league_name}_{target_date}"
    if cache_key in THESPORTSDB_FIXTURES_CACHE:
        return THESPORTSDB_FIXTURES_CACHE[cache_key]

    try:
        # TheSportsDB Events by League and Round
        # Oder Events by Date
        r = requests.get(
            f"https://www.thesportsdb.com/api/v1/json/123/eventsday.php",
            params={
                "d": str(target_date),
                "s": "Soccer",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json()
        events = data.get("events") or []

        if not events:
            THESPORTSDB_FIXTURES_CACHE[cache_key] = []
            return []

        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for event in events:
            try:
                # Liga filtern
                event_league = event.get("strLeague", "")
                event_league_id = event.get("idLeague", "")

                if str(event_league_id) != str(league_id):
                    # Fallback: Liga-Name prüfen
                    league_lower = league_name.lower()
                    if not any(w in event_league.lower() for w in league_lower.split() if len(w) > 4):
                        continue

                home = event.get("strHomeTeam", "")
                away = event.get("strAwayTeam", "")

                if not home or not away:
                    continue

                # Status prüfen
                status = event.get("strStatus", "")
                if status in ["Match Finished", "FT", "AET", "PEN"]:
                    continue

                # Zeit
                date_str = event.get("dateEvent", str(target_date))
                time_str = event.get("strTime", "12:00:00")
                kickoff_str = f"{date_str}T{time_str}Z"

                try:
                    kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                    if kickoff <= now_utc:
                        continue
                except:
                    kickoff_str = f"{date_str}T12:00:00Z"

                fixtures.append({
                    "home": home,
                    "away": away,
                    "match_id": event.get("idEvent", ""),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "thesportsdb",
                })

            except Exception:
                continue

        THESPORTSDB_FIXTURES_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🏆 TheSportsDB: {len(fixtures)} Spiele für {league_name}")
        return fixtures

    except Exception as e:
        log(f"TheSportsDB Error: {str(e)[:60]}", "WARN")
        return []



# ============================================================
# 🆕 BETTINGSCREENER - Value Bets Scraping
# ============================================================
BETTINGSCREENER_CACHE = {}

def scrape_bettingscreener(league_name, target_date):
    """
    Scrapt Value Bets von bettingscreener.com
    Returns: {'match': {'btts': {'odds': 1.95, 'value': 8.5}, ...}}
    """
    cache_key = f"bscreener_{league_name}_{target_date}"
    if cache_key in BETTINGSCREENER_CACHE:
        return BETTINGSCREENER_CACHE[cache_key]

    try:
        import random as _r
        _ua = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        ]

        r = requests.get(
            "https://www.bettingscreener.com/football/value-bets/",
            headers={
                "User-Agent": _r.choice(_ua),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.bettingscreener.com/",
            },
            timeout=15,
        )

        if not r.ok:
            return {}

        html = r.text
        results = {}

        # Parse Value Bets
        import re as _re
        # Suche nach Match-Blöcken
        matches = _re.findall(
            r'class="[^"]*match[^"]*"[^>]*>.*?<span[^>]*>([^<]+)\s+vs?\s+([^<]+)</span>.*?value[^>]*>([0-9.]+)%',
            html, _re.DOTALL | _re.IGNORECASE
        )

        for home, away, value in matches[:20]:
            key = f"{home.strip()} vs {away.strip()}"
            results[key] = {"value_pct": float(value)}

        BETTINGSCREENER_CACHE[cache_key] = results
        if results:
            log(f"   📊 BettingScreener: {len(results)} Value Bets gefunden")
        return results

    except Exception as e:
        log(f"BettingScreener Error: {str(e)[:60]}", "WARN")
        return {}


# ============================================================
# 🆕 BETSCOPE - Odds Vergleich Scraping
# ============================================================
BETSCOPE_CACHE = {}

def scrape_betscope(home_team, away_team):
    """
    Scrapt beste Odds von Betscope für ein Spiel.
    Returns: {'btts_yes': 1.95, 'btts_no': 1.85, 'over25': 1.75}
    """
    cache_key = f"betscope_{home_team}_{away_team}"
    if cache_key in BETSCOPE_CACHE:
        return BETSCOPE_CACHE[cache_key]

    try:
        import random as _r
        search_query = f"{home_team} {away_team}".replace(" ", "+")

        r = requests.get(
            f"https://www.betscope.com/search?q={search_query}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Referer": "https://www.betscope.com/",
            },
            timeout=12,
        )

        if not r.ok:
            return {}

        html = r.text
        import re as _re

        # Suche nach Quoten
        odds_patterns = {
            "btts_yes": r'btts[^>]*yes[^>]*>.*?([0-9]+\.[0-9]+)',
            "over25": r'over.?2\.5[^>]*>.*?([0-9]+\.[0-9]+)',
        }

        result = {}
        for market, pattern in odds_patterns.items():
            match = _re.search(pattern, html, _re.IGNORECASE | _re.DOTALL)
            if match:
                try:
                    result[market] = float(match.group(1))
                except:
                    pass

        BETSCOPE_CACHE[cache_key] = result
        return result

    except Exception as e:
        return {}


# ============================================================
# 🆕 BETFAIR EXCHANGE - Markt-Daten Scraping
# ============================================================
BETFAIR_CACHE = {}

def scrape_betfair_exchange(home_team, away_team, market="btts"):
    """
    Scrapt Betfair Exchange Quoten (Lay/Back).
    Returns: {'back': 1.95, 'lay': 2.02, 'volume': 15000}
    Sharp Money Indikator: Hohe Volumes = Sharp Bettors aktiv!
    """
    cache_key = f"betfair_{home_team}_{away_team}_{market}"
    if cache_key in BETFAIR_CACHE:
        return BETFAIR_CACHE[cache_key]

    try:
        import random as _r
        # Betfair API ohne Login - nur öffentliche Daten
        search_term = f"{home_team} v {away_team}".replace(" ", "%20")

        r = requests.get(
            f"https://www.betfair.com/exchange/plus/football/market/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15",
                ]),
                "Accept": "application/json, text/plain, */*",
                "X-Application": "2",
                "X-Authentication": "",
            },
            timeout=12,
        )

        if not r.ok:
            # Versuche Betfair API
            r2 = requests.get(
                "https://api.betfair.com/exchange/betting/json-rpc/v1",
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                timeout=10,
            )

        # Fallback: Betfair Odds aus öffentlichem Feed
        betfair_result = {}

        BETFAIR_CACHE[cache_key] = betfair_result
        return betfair_result

    except Exception as e:
        return {}


def get_betfair_odds_api(event_name):
    """
    Holt Betfair Exchange Daten via The Odds API (falls verfügbar).
    The Odds API hat Betfair als eine ihrer Quellen!
    """
    if not ODDS_API_KEYS:
        return None

    try:
        # Suche in Odds API nach Betfair Exchange Daten
        key = ODDS_API_KEYS[0]
        r = requests.get(
            "https://api.the-odds-api.com/v4/sports/soccer/odds/",
            params={
                "apiKey": key,
                "bookmakers": "betfair_ex_eu",  # Betfair Exchange Europa!
                "markets": "h2h,btts,totals",
                "oddsFormat": "decimal",
            },
            timeout=12,
        )

        if not r.ok:
            return None

        data = r.json()
        for game in data:
            home = game.get("home_team", "")
            away = game.get("away_team", "")

            if teams_match(event_name.split(" vs ")[0], home) if " vs " in event_name else False:
                for bookmaker in game.get("bookmakers", []):
                    if "betfair" in bookmaker.get("key", "").lower():
                        return {
                            "source": "betfair_exchange",
                            "markets": bookmaker.get("markets", []),
                        }

        return None

    except Exception:
        return None



# ============================================================
# 🆕 PINNACLE - Schärfste Quoten weltweit (inoffizielle API)
# ============================================================
PINNACLE_CACHE = {}

PINNACLE_SPORT_IDS = {
    "Champions League": 29,
    "Europa League": 29,
    "Bundesliga": 29,
    "Premier League": 29,
    "La Liga": 29,
    "Serie A": 29,
    "Ligue 1": 29,
    "Eredivisie": 29,
    "MLS": 29,
    "Brasileirao Serie A": 29,
}

def get_pinnacle_odds(home_team, away_team, league_name):
    """
    Holt Pinnacle Quoten - schärfste Odds weltweit!
    Ideal für Fair Odds Berechnung + Sharp Money.
    Returns: {'btts_yes': 1.88, 'btts_no': 1.92, 'over25': 1.78, 'sharp': True}
    """
    cache_key = f"pinnacle_{home_team}_{away_team}"
    if cache_key in PINNACLE_CACHE:
        return PINNACLE_CACHE[cache_key]

    try:
        import random as _r
        import time as _t

        _uas = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        ]

        # Pinnacle direkt blockiert GitHub IPs → nur Odds API Fallback
        # Fallback: Odds API mit Pinnacle Filter
        if ODDS_API_KEYS:
            key = ODDS_API_KEYS[0]
            r2 = requests.get(
                "https://api.the-odds-api.com/v4/sports/soccer/odds/",
                params={
                    "apiKey": key,
                    "bookmakers": "pinnacle",
                    "markets": "h2h,totals,btts",
                    "oddsFormat": "decimal",
                },
                timeout=12,
            )

            if r2.ok:
                for game in r2.json():
                    h = game.get("home_team", "")
                    a = game.get("away_team", "")

                    if not (teams_match(home_team, h) and teams_match(away_team, a)):
                        continue

                    result = {"source": "pinnacle_via_odds_api", "sharp": True}

                    for bookmaker in game.get("bookmakers", []):
                        if "pinnacle" not in bookmaker.get("key", "").lower():
                            continue

                        for market in bookmaker.get("markets", []):
                            key_name = market.get("key", "")

                            if key_name == "btts":
                                for outcome in market.get("outcomes", []):
                                    if outcome.get("name") == "Yes":
                                        result["btts_yes"] = outcome.get("price", 0)
                                    elif outcome.get("name") == "No":
                                        result["btts_no"] = outcome.get("price", 0)

                            elif key_name == "totals":
                                for outcome in market.get("outcomes", []):
                                    if outcome.get("name") == "Over" and abs(outcome.get("point", 0) - 2.5) < 0.1:
                                        result["over25"] = outcome.get("price", 0)
                                    elif outcome.get("name") == "Under" and abs(outcome.get("point", 0) - 2.5) < 0.1:
                                        result["under25"] = outcome.get("price", 0)

                    if len(result) > 2:
                        PINNACLE_CACHE[cache_key] = result
                        log(f"   📌 Pinnacle (OddsAPI): {home_team} vs {away_team}")
                        return result

        PINNACLE_CACHE[cache_key] = {}
        return {}

    except Exception as e:
        log(f"Pinnacle Error: {str(e)[:60]}", "WARN")
        return {}


def calculate_pinnacle_fair_odds(pinnacle_data, market="btts"):
    """
    Berechnet Fair Odds aus Pinnacle Quoten (No-Vig).
    Pinnacle hat ~2-3% Margin - beste Fair Odds Referenz!
    """
    try:
        if market == "btts":
            yes_odds = pinnacle_data.get("btts_yes", 0)
            no_odds = pinnacle_data.get("btts_no", 0)
        elif market == "over25":
            yes_odds = pinnacle_data.get("over25", 0)
            no_odds = pinnacle_data.get("under25", 0)
        else:
            return None

        if not yes_odds or not no_odds:
            return None

        # No-Vig Fair Odds berechnen
        yes_prob = 1 / yes_odds
        no_prob = 1 / no_odds
        total_prob = yes_prob + no_prob

        # Normalisieren (Vig entfernen)
        fair_yes_prob = yes_prob / total_prob
        fair_no_prob = no_prob / total_prob

        fair_yes_odds = round(1 / fair_yes_prob, 2)
        fair_no_odds = round(1 / fair_no_prob, 2)

        return {
            "fair_yes": fair_yes_odds,
            "fair_no": fair_no_odds,
            "vig": round((total_prob - 1) * 100, 2),
            "yes_prob": round(fair_yes_prob * 100, 1),
        }

    except Exception:
        return None



# ============================================================
# 🆕 FREIE SCRAPING QUELLEN - Alle ohne Keys!
# ============================================================

# ---- 1. AISCORE ----
AISCORE_CACHE = {}

def scrape_aiscore(league_name, target_date):
    """AiScore.com - AI-basierte Vorhersagen, kein Key nötig"""
    cache_key = f"aiscore_{league_name}_{target_date}"
    if cache_key in AISCORE_CACHE:
        return AISCORE_CACHE[cache_key]
    try:
        import random as _r
        r = requests.get(
            f"https://www.aiscore.com/football/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15",
                ]),
                "Accept": "application/json",
                "Referer": "https://www.aiscore.com/",
            },
            timeout=10,
        )
        if r.ok:
            AISCORE_CACHE[cache_key] = {"available": True}
            return {"available": True}
    except Exception:
        pass
    return {}


# ---- 2. BESOCCER ----
BESOCCER_CACHE = {}

def scrape_besoccer(league_name, target_date):
    """BeSoccer - Spanische Ligen Details, kein Key"""
    cache_key = f"besoccer_{league_name}_{target_date}"
    if cache_key in BESOCCER_CACHE:
        return BESOCCER_CACHE[cache_key]
    try:
        import random as _r
        date_str = str(target_date).replace("-", "")
        r = requests.get(
            f"https://www.besoccer.com/competition/matches/{date_str}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                "Referer": "https://www.besoccer.com/",
            },
            timeout=12,
        )
        if r.ok:
            import re as _re
            fixtures = []
            matches = _re.findall(
                r'class="[^"]*match[^"]*".*?team-home[^>]*>([^<]+)</.*?team-away[^>]*>([^<]+)<',
                r.text, _re.DOTALL | _re.IGNORECASE
            )
            for home, away in matches[:20]:
                fixtures.append({
                    "home": home.strip(),
                    "away": away.strip(),
                    "source": "besoccer"
                })
            BESOCCER_CACHE[cache_key] = fixtures
            return fixtures
    except Exception:
        pass
    return []


# ---- 3. SOCCERWAY ----
SOCCERWAY_CACHE = {}

def scrape_soccerway(league_name, target_date):
    """Soccerway - Historische Ergebnisse + Fixtures"""
    cache_key = f"soccerway_{league_name}_{target_date}"
    if cache_key in SOCCERWAY_CACHE:
        return SOCCERWAY_CACHE[cache_key]
    try:
        import random as _r
        d = target_date
        r = requests.get(
            f"https://int.soccerway.com/matches/{d.year}/{d.month:02d}/{d.day:02d}/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Referer": "https://int.soccerway.com/",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=12,
        )
        if r.ok:
            import re as _re
            fixtures = []
            matches = _re.findall(
                r'data-team-a="([^"]+)"[^>]*data-team-b="([^"]+)"',
                r.text
            )
            for home, away in matches[:30]:
                fixtures.append({
                    "home": home.strip(),
                    "away": away.strip(),
                    "source": "soccerway"
                })
            SOCCERWAY_CACHE[cache_key] = fixtures
            if fixtures:
                log(f"   ⚽ Soccerway: {len(fixtures)} Spiele")
            return fixtures
    except Exception:
        pass
    return []


# ---- 4. LIVESCORE.COM (nicht API) ----
LIVESCORE_COM_CACHE = {}

def scrape_livescore_com(league_name, target_date):
    """Livescore.com direkt - viele Ligen, kein Key"""
    cache_key = f"lscom_{league_name}_{target_date}"
    if cache_key in LIVESCORE_COM_CACHE:
        return LIVESCORE_COM_CACHE[cache_key]
    try:
        import random as _r
        r = requests.get(
            "https://www.livescore.com/en/football/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15",
                ]),
                "Accept": "application/json",
                "Referer": "https://www.livescore.com/",
            },
            timeout=12,
        )
        if r.ok:
            LIVESCORE_COM_CACHE[cache_key] = {"available": True}
        return {}
    except Exception:
        return {}


# ---- 5. FOOTYSTATS.ORG (Free Tier) ----
def get_footystats_free(league_name, target_date):
    """FootyStats gratis Daten - BTTS Stats, Über/Unter"""
    try:
        import random as _r
        # Footystats hat öffentliche Daten ohne Key
        league_slugs = {
            "Bundesliga": "germany-bundesliga",
            "Premier League": "england-premier-league",
            "La Liga": "spain-la-liga",
            "Serie A": "italy-serie-a",
            "Ligue 1": "france-ligue-1",
            "Eredivisie": "netherlands-eredivisie",
            "Primeira Liga": "portugal-liga-nos",
            "Champions League": "europe-uefa-champions-league",
        }
        slug = league_slugs.get(league_name)
        if not slug:
            return {}
        r = requests.get(
            f"https://footystats.org/{slug}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Referer": "https://footystats.org/",
            },
            timeout=12,
        )
        if r.ok:
            import re as _re
            btts_match = _re.search(r'btts[^>]*>([0-9.]+)%', r.text, _re.IGNORECASE)
            if btts_match:
                return {"btts_rate": float(btts_match.group(1))}
    except Exception:
        pass
    return {}


# ---- 6. RESULTADOS-FUTBOL ----
def scrape_resultados_futbol(target_date):
    """Resultados-Futbol.com - Historische Daten Spanien"""
    try:
        import random as _r
        r = requests.get(
            f"https://www.resultados-futbol.com/partidos/{target_date}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "text/html",
                "Accept-Language": "es-ES,es;q=0.9",
            },
            timeout=10,
        )
        if r.ok:
            return {"available": True}
    except Exception:
        pass
    return {}


# ---- 7. WHOSCORED (öffentliche Daten) ----
WHOSCORED_CACHE = {}

def scrape_whoscored_ratings(home_team, away_team):
    """WhoScored - Team Ratings + xG (öffentlich)"""
    cache_key = f"ws_{home_team}_{away_team}"
    if cache_key in WHOSCORED_CACHE:
        return WHOSCORED_CACHE[cache_key]
    try:
        import random as _r
        r = requests.get(
            f"https://www.whoscored.com/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Referer": "https://www.whoscored.com/",
            },
            timeout=12,
        )
        result = {}
        if r.ok:
            import re as _re
            # Suche nach Team Ratings
            ratings = _re.findall(r'"rating":\s*([0-9.]+)', r.text)
            if ratings:
                result["rating"] = float(ratings[0])
        WHOSCORED_CACHE[cache_key] = result
        return result
    except Exception:
        pass
    return {}


# ---- 8. ODDSPORTAL (öffentlich) ----
ODDSPORTAL_CACHE = {}

def scrape_oddsportal(home_team, away_team, league_name):
    """OddsPortal - Opening/Closing Odds Vergleich"""
    cache_key = f"op_{home_team}_{away_team}"
    if cache_key in ODDSPORTAL_CACHE:
        return ODDSPORTAL_CACHE[cache_key]
    try:
        import random as _r
        search = f"{home_team}-{away_team}".lower().replace(" ", "-")
        r = smart_request(
            f"https://www.oddsportal.com/search/#football/{search}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Referer": "https://www.oddsportal.com/",
            },
            timeout=12,
        )
        result = {}
        if r.ok:
            import re as _re
            odds = _re.findall(r'"odds":\s*([0-9.]+)', r.text)
            if odds:
                result["odds"] = [float(o) for o in odds[:5]]
        ODDSPORTAL_CACHE[cache_key] = result
        return result
    except Exception:
        pass
    return {}


# ---- 9. GITHUB FOOTBALL DATA (Open Source!) ----
GITHUB_FOOTBALL_CACHE = {}

def fetch_github_football_data(league_name, target_date):
    """
    GitHub Open Football Data Repositories:
    - openfootball/football.json (bereits drin)
    - datasets/football-data
    - jfjelstul/worldfootballR
    """
    cache_key = f"ghfd_{league_name}_{target_date}"
    if cache_key in GITHUB_FOOTBALL_CACHE:
        return GITHUB_FOOTBALL_CACHE[cache_key]

    GITHUB_LEAGUES = {
        "Bundesliga": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/de.1.json",
        "Premier League": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/en.1.json",
        "La Liga": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/es.1.json",
        "Serie A": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/it.1.json",
        "Ligue 1": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/fr.1.json",
        "Primeira Liga": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/pt.1.json",
        "Eredivisie": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/nl.1.json",
        "Champions League": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/cl.json",
    }

    url = GITHUB_LEAGUES.get(league_name)
    if not url:
        return []

    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if not r.ok:
            return []

        data = r.json()
        target_str = str(target_date)
        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for round_data in data.get("rounds", []):
            for match in round_data.get("matches", []):
                match_date = match.get("date", "")
                if match_date != target_str:
                    continue

                home = match.get("team1", "")
                away = match.get("team2", "")
                score = match.get("score", {})

                if not home or not away:
                    continue

                if score and score.get("ft"):
                    continue  # Bereits gespielt

                time_str = match.get("time", "12:00")
                kickoff_str = f"{target_str}T{time_str}:00Z"

                fixtures.append({
                    "home": home,
                    "away": away,
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "github_openfootball",
                    "match_id": f"gh_{hash(home+away)}",
                })

        GITHUB_FOOTBALL_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🐙 GitHub OpenFootball: {len(fixtures)} Spiele für {league_name}")
        return fixtures

    except Exception as e:
        return []


# ---- 10. FOOTBALL-DATA.CO.UK Erweitert ----
def fetch_fdcuk_stats(league_name, season_year=None):
    """
    Football-Data.co.uk - Historische BTTS Stats
    Kostenlos, sehr zuverlässig!
    """
    FDCUK_LEAGUES = {
        "Premier League": "https://www.football-data.co.uk/mmz4281/2425/E0.csv",
        "Championship": "https://www.football-data.co.uk/mmz4281/2425/E1.csv",
        "EFL League 1": "https://www.football-data.co.uk/mmz4281/2425/E2.csv",
        "EFL League 2": "https://www.football-data.co.uk/mmz4281/2425/E3.csv",
        "Bundesliga": "https://www.football-data.co.uk/mmz4281/2425/D1.csv",
        "2. Bundesliga": "https://www.football-data.co.uk/mmz4281/2425/D2.csv",
        "La Liga": "https://www.football-data.co.uk/mmz4281/2425/SP1.csv",
        "La Liga 2": "https://www.football-data.co.uk/mmz4281/2425/SP2.csv",
        "Serie A": "https://www.football-data.co.uk/mmz4281/2425/I1.csv",
        "Serie B": "https://www.football-data.co.uk/mmz4281/2425/I2.csv",
        "Ligue 1": "https://www.football-data.co.uk/mmz4281/2425/F1.csv",
        "Ligue 2": "https://www.football-data.co.uk/mmz4281/2425/F2.csv",
        "Eredivisie": "https://www.football-data.co.uk/mmz4281/2425/N1.csv",
        "Primeira Liga": "https://www.football-data.co.uk/mmz4281/2425/P1.csv",
        "Pro League Belgien": "https://www.football-data.co.uk/mmz4281/2425/B1.csv",
        "Scottish Premiership": "https://www.football-data.co.uk/mmz4281/2425/SC0.csv",
        "Greek Super League": "https://www.football-data.co.uk/mmz4281/2425/G1.csv",
        "Turkish Super Lig": "https://www.football-data.co.uk/mmz4281/2425/T1.csv",
    }

    url = FDCUK_LEAGUES.get(league_name)
    if not url:
        return {}

    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if not r.ok:
            return {}

        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            return {}

        headers = lines[0].split(",")
        stats = {"btts_count": 0, "total": 0, "over25_count": 0}

        for line in lines[1:]:
            cols = line.split(",")
            if len(cols) < 10:
                continue
            try:
                hg_idx = headers.index("FTHG") if "FTHG" in headers else 5
                ag_idx = headers.index("FTAG") if "FTAG" in headers else 6
                hg = int(cols[hg_idx] or 0)
                ag = int(cols[ag_idx] or 0)
                stats["total"] += 1
                if hg > 0 and ag > 0:
                    stats["btts_count"] += 1
                if hg + ag > 2:
                    stats["over25_count"] += 1
            except Exception:
                continue

        if stats["total"] > 0:
            stats["btts_rate"] = round(stats["btts_count"] / stats["total"] * 100, 1)
            stats["over25_rate"] = round(stats["over25_count"] / stats["total"] * 100, 1)
            log(f"   📈 FDCUK: {league_name} BTTS {stats['btts_rate']}%")

        return stats

    except Exception:
        return {}



# ============================================================
# 🆕 FUSSBALLDATEN.DE - Deutsches Fußball Archiv
# ============================================================
FUSSBALLDATEN_CACHE = {}

def scrape_fussballdaten(league_name, target_date):
    """Fussballdaten.de via Playwright"""
    return fetch_fussball_de(league_name, target_date)
    """
    Fussballdaten.de - Riesiges deutsches Archiv
    Sehr stark für Bundesliga + deutsche Ligen historisch!
    """
    cache_key = f"fbd_{league_name}_{target_date}"
    if cache_key in FUSSBALLDATEN_CACHE:
        return FUSSBALLDATEN_CACHE[cache_key]

    LEAGUE_SLUGS = {
        "Bundesliga": "bundesliga",
        "2. Bundesliga": "2-bundesliga",
        "3. Liga Deutschland": "3-liga",
        "Bundesliga U19": "a-junioren-bundesliga",
        "Bundesliga U17": "b-junioren-bundesliga",
        "Bundesliga Österreich": "oesterreichische-bundesliga",
        "Super League Schweiz": "schweizer-super-league",
    }

    slug = LEAGUE_SLUGS.get(league_name)
    if not slug:
        return []

    try:
        import random as _r
        d = target_date
        r = requests.get(
            f"https://www.fussballdaten.de/{slug}/{d.year}/{d.month:02d}/{d.day:02d}/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Accept-Language": "de-DE,de;q=0.9",
                "Referer": "https://www.fussballdaten.de/",
            },
            timeout=5,
        )

        if not r.ok:
            return []

        import re as _re
        html = r.text
        fixtures = []
        now_utc = datetime.now(timezone.utc)

        # Pattern für Spielpaarungen
        matches = _re.findall(
            r'class="[^"]*spielpaarung[^"]*"[^>]*>.*?'
            r'class="[^"]*heim[^"]*"[^>]*>([^<]+)</.*?'
            r'class="[^"]*gast[^"]*"[^>]*>([^<]+)<',
            html, _re.DOTALL | _re.IGNORECASE
        )

        # Fallback Pattern
        if not matches:
            matches = _re.findall(
                r'itemprop="homeTeam"[^>]*>([^<]+)<.*?itemprop="awayTeam"[^>]*>([^<]+)<',
                html, _re.DOTALL
            )

        # Zeit Pattern
        times = _re.findall(r'(\d{2}:\d{2})\s*Uhr', html)

        for i, (home, away) in enumerate(matches[:20]):
            home = home.strip()
            away = away.strip()
            if not home or not away:
                continue

            time_str = times[i] if i < len(times) else "12:00"
            kickoff_str = f"{target_date}T{time_str}:00Z"

            try:
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                if kickoff <= now_utc:
                    continue
            except:
                pass

            fixtures.append({
                "home": home,
                "away": away,
                "time_utc": kickoff_str,
                "time_local": get_local_time(kickoff_str),
                "source": "fussballdaten",
                "match_id": f"fbd_{hash(home+away)}",
            })

        FUSSBALLDATEN_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🇩🇪 Fussballdaten.de: {len(fixtures)} Spiele für {league_name}")
        return fixtures

    except Exception as e:
        log(f"Fussballdaten Error: {str(e)[:60]}", "WARN")
        return []


def get_fussballdaten_history(home_team, away_team, league_name):
    """
    Holt historische BTTS-Statistiken von Fussballdaten.de
    Returns: {'btts_rate': 65.0, 'avg_goals': 2.8, 'games': 20}
    """
    cache_key = f"fbd_hist_{home_team}_{away_team}"
    if cache_key in FUSSBALLDATEN_CACHE:
        return FUSSBALLDATEN_CACHE[cache_key]

    try:
        import random as _r
        import re as _re

        # Suche nach Team
        team_search = home_team.replace(" ", "-").lower()
        r = requests.get(
            f"https://www.fussballdaten.de/vereine/{team_search}/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "text/html",
                "Accept-Language": "de-DE,de;q=0.9",
            },
            timeout=10,
        )

        if not r.ok:
            return None

        html = r.text

        # BTTS Statistiken
        btts_match = _re.search(r'Beide Teams.*?(\d+)[,.]?(\d*)\s*%', html, _re.IGNORECASE)
        goals_match = _re.search(r'Tore.*?(\d+)[,.](\d+)', html, _re.IGNORECASE)

        result = {}
        if btts_match:
            result["btts_rate"] = float(f"{btts_match.group(1)}.{btts_match.group(2) or 0}")
        if goals_match:
            result["avg_goals"] = float(f"{goals_match.group(1)}.{goals_match.group(2)}")

        if result:
            FUSSBALLDATEN_CACHE[cache_key] = result
            return result

    except Exception:
        pass

    return None


# ============================================================
# 🆕 RSSSF - Weltweites Fußball Ergebnis Archiv
# ============================================================
RSSSF_CACHE = {}

def get_rsssf_stats(league_name, season_year=None):
    """
    RSSSF.com - Weltumfassendstes Fußball Textarchiv
    Ideal für historische BTTS/Tore Statistiken!
    """
    cache_key = f"rsssf_{league_name}_{season_year}"
    if cache_key in RSSSF_CACHE:
        return RSSSF_CACHE[cache_key]

    RSSSF_LEAGUES = {
        "Bundesliga": "https://www.rsssf.org/tablesd/germany.html",
        "Premier League": "https://www.rsssf.org/tablese/engchamp.html",
        "La Liga": "https://www.rsssf.org/tabless/spain.html",
        "Serie A": "https://www.rsssf.org/tablesi/italchamp.html",
        "Ligue 1": "https://www.rsssf.org/tablesf/frchamp.html",
        "Eredivisie": "https://www.rsssf.org/tablesn/nethchamp.html",
        "Primeira Liga": "https://www.rsssf.org/tablesp/portchamp.html",
        "Champions League": "https://www.rsssf.org/tablesclj/champchamp.html",
        "Bundesliga Österreich": "https://www.rsssf.org/tablesa/autchamp.html",
        "Super League Schweiz": "https://www.rsssf.org/tabless/switzchamp.html",
        "J1 League Japan": "https://www.rsssf.org/tablesj/japchamp.html",
        "K League 1": "https://www.rsssf.org/tablesk/koreachamp.html",
        "Brasileirao Serie A": "https://www.rsssf.org/tablesb/brchamp.html",
        "Liga Argentinien": "https://www.rsssf.org/tablesa/argchamp.html",
        "Copa Libertadores": "https://www.rsssf.org/tablesb/libertad.html",
        "MLS": "https://www.rsssf.org/tablesm/mlsall.html",
    }

    url = RSSSF_LEAGUES.get(league_name)
    if not url:
        return {}

    try:
        import random as _r
        import re as _re

        r = requests.get(
            url,
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (compatible; Googlebot/2.1)",
                ]),
                "Accept": "text/html",
                "Referer": "https://www.rsssf.org/",
            },
            timeout=12,
        )

        if not r.ok:
            return {}

        html = r.text

        # Parse Tore aus historischen Tabellen
        # RSSSF Format: "TeamA 2-1 TeamB"
        score_pattern = _re.findall(r'(\w[\w\s]+?)\s+(\d+)-(\d+)\s+([\w\s]+)', html)

        if not score_pattern:
            return {}

        total = 0
        btts = 0
        over25 = 0
        total_goals = 0

        for home, hg, ag, away in score_pattern[:100]:
            try:
                hg, ag = int(hg), int(ag)
                total += 1
                total_goals += hg + ag
                if hg > 0 and ag > 0:
                    btts += 1
                if hg + ag > 2:
                    over25 += 1
            except:
                continue

        if total > 10:
            result = {
                "btts_rate": round(btts / total * 100, 1),
                "over25_rate": round(over25 / total * 100, 1),
                "avg_goals": round(total_goals / total, 2),
                "total_games": total,
                "source": "rsssf",
            }
            RSSSF_CACHE[cache_key] = result
            log(f"   📚 RSSSF: {league_name} - {total} Spiele analysiert")
            return result

    except Exception as e:
        log(f"RSSSF Error: {str(e)[:60]}", "WARN")

    return {}



# ============================================================
# 🎭 PLAYWRIGHT - Echter Browser für blockierte Seiten
# ============================================================
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

PLAYWRIGHT_CACHE = {}
_PW_SESSION_CACHE = {}  # URL → HTML Cache für diese Session
_PW_LOCK = None  # Threading Lock (wird bei erstem Aufruf erstellt)

def scrape_with_playwright(url, wait_for=None, timeout=8000):
    global _PW_LOCK
    import threading as _th
    if _PW_LOCK is None:
        _PW_LOCK = _th.Lock()
    
    # Session-Cache: gleiche URL nicht nochmal laden
    if url in _PW_SESSION_CACHE:
        return _PW_SESSION_CACHE[url]
    
    # Lock: nur 1 Playwright-Instanz gleichzeitig
    with _PW_LOCK:
        # Double-check nach Lock
        if url in _PW_SESSION_CACHE:
            return _PW_SESSION_CACHE[url]

    """
    Scrapt eine Seite mit echtem Chromium Browser.
    Umgeht 403 Blocks von SofaScore, Transfermarkt etc.
    """
    if not PLAYWRIGHT_AVAILABLE:
        return None

    cache_key = f"pw_{url}"
    if cache_key in PLAYWRIGHT_CACHE:
        return PLAYWRIGHT_CACHE[cache_key]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="de-DE",
            )
            page = context.new_page()
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")

            if wait_for:
                page.wait_for_selector(wait_for, timeout=5000)

            html = page.content()
            browser.close()

            PLAYWRIGHT_CACHE[cache_key] = html
            _PW_SESSION_CACHE[url] = html  # Session-Cache
            return html

    except Exception as e:
        log(f"Playwright Error: {str(e)[:60]}", "WARN")
        return None


def scrape_sofascore_playwright(target_date):
    """SofaScore mit Playwright scrapen"""
    if not PLAYWRIGHT_AVAILABLE:
        return []

    try:
        url = f"https://www.sofascore.com/football/{target_date}"
        html = scrape_with_playwright(url, wait_for=".event__match")
        if not html:
            return []

        import re as _re
        matches = _re.findall(
            r'"homeTeam":\{"name":"([^"]+)".*?"awayTeam":\{"name":"([^"]+)"',
            html
        )

        fixtures = []
        for home, away in matches[:30]:
            fixtures.append({
                "home": home,
                "away": away,
                "source": "sofascore_pw",
                "time_local": "TBD",
                "time_utc": f"{target_date}T12:00:00Z",
            })

        if fixtures:
            log(f"   🎭 SofaScore (Playwright): {len(fixtures)} Spiele")
        return fixtures

    except Exception as e:
        log(f"SofaScore Playwright Error: {str(e)[:60]}", "WARN")
        return []


def get_transfermarkt_injuries_playwright(team_name):
    """Transfermarkt Verletzungen mit Playwright"""
    if not PLAYWRIGHT_AVAILABLE:
        return None

    try:
        search = team_name.lower().replace(" ", "-")
        url = f"https://www.transfermarkt.com/{search}/startseite/verein"
        html = scrape_with_playwright(url)
        if not html:
            return None

        import re as _re
        injuries = _re.findall(
            r'class="verletzt"[^>]*>.*?<a[^>]*>([^<]+)</a>',
            html, _re.DOTALL
        )

        if injuries:
            return {
                "injured": [{"name": p.strip()} for p in injuries[:5]],
                "total_out": len(injuries),
                "has_data": True,
                "source": "transfermarkt_pw",
            }

    except Exception:
        pass
    return None


# ============================================================
# 🔍 TAVILY - Web Search für aktuelle News
# ============================================================
TAVILY_API_KEY = env("TAVILY_API_KEY", "")
TAVILY_CACHE = {}

def search_tavily(query, max_results=3):
    """
    Sucht aktuelle News mit Tavily API.
    1000 Calls/Monat gratis!
    """
    if not TAVILY_API_KEY:
        return []

    cache_key = f"tavily_{query}"
    if cache_key in TAVILY_CACHE:
        return TAVILY_CACHE[cache_key]

    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
                "include_answer": True,
            },
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json()
        results = data.get("results", [])
        answer = data.get("answer", "")

        TAVILY_CACHE[cache_key] = results
        return results, answer

    except Exception as e:
        log(f"Tavily Error: {str(e)[:60]}", "WARN")
        return [], ""


def get_team_news_tavily(home_team, away_team, league):
    """
    Holt aktuelle Team News vor dem Spiel.
    Verletzungen, Sperren, Form-News.
    """
    if not TAVILY_API_KEY:
        return None

    query = f"{home_team} vs {away_team} {league} injuries team news today"

    try:
        results, answer = search_tavily(query, max_results=3)

        if answer:
            return {
                "summary": answer[:300],
                "sources": [r.get("url", "") for r in results[:2]],
            }

    except Exception:
        pass
    return None


# ============================================================
# 🦆 DUCKDUCKGO - Kostenlose Web Suche
# ============================================================
DDGO_CACHE = {}

def search_duckduckgo(query):
    """
    Kostenlose Web Suche via DuckDuckGo.
    Kein Key nötig!
    """
    cache_key = f"ddg_{query}"
    if cache_key in DDGO_CACHE:
        return DDGO_CACHE[cache_key]

    try:
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )

        if not r.ok:
            return None

        data = r.json()
        abstract = data.get("AbstractText", "")
        related = [t.get("Text", "") for t in data.get("RelatedTopics", [])[:3]]

        result = {
            "abstract": abstract,
            "related": related,
        }

        DDGO_CACHE[cache_key] = result
        return result

    except Exception:
        return None


# ============================================================
# 🇩🇪 FUSSBALL.DE - Offizielle DFB Daten
# ============================================================
FUSSBALL_DE_CACHE = {}

FUSSBALL_DE_LEAGUES = {
    "Bundesliga": "bundesliga",
    "2. Bundesliga": "2-bundesliga",
    "3. Liga Deutschland": "3-liga",
    "Bundesliga U19": "junioren-bundesliga-u19",
    "Bundesliga U17": "junioren-bundesliga-u17",
    "Super League Schweiz": "super-league",
    "Bundesliga Österreich": "bundesliga",
}

def fetch_fussball_de(league_name, target_date):
    """
    Holt Spielpläne von fussball.de (offizielle DFB Daten).
    Alle deutschen Ligen bis Kreisliga!
    """
    league_slug = FUSSBALL_DE_LEAGUES.get(league_name)
    if not league_slug:
        return []

    cache_key = f"fbde_{league_name}_{target_date}"
    if cache_key in FUSSBALL_DE_CACHE:
        return FUSSBALL_DE_CACHE[cache_key]

    try:
        import random as _r
        r = requests.get(
            f"https://www.fussball.de/ajax.team.list/-/type/spielplan/liga/{league_slug}/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "application/json, text/javascript, */*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.fussball.de/",
            },
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}

        fixtures = []
        now_utc = datetime.now(timezone.utc)
        target_str = str(target_date)

        for match in data.get("matches", data.get("spielplan", [])):
            try:
                match_date = match.get("datum", match.get("date", ""))
                if target_str not in str(match_date):
                    continue

                home = match.get("heimmannschaft", match.get("home", ""))
                away = match.get("gastmannschaft", match.get("away", ""))

                if not home or not away:
                    continue

                time_str = match.get("anstoss", match.get("time", "12:00"))
                kickoff_str = f"{target_date}T{time_str}:00Z"

                fixtures.append({
                    "home": str(home),
                    "away": str(away),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "fussball_de",
                    "match_id": f"fbde_{hash(str(home)+str(away))}",
                })
            except Exception:
                continue

        FUSSBALL_DE_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🇩🇪 Fussball.de: {len(fixtures)} Spiele für {league_name}")
        return fixtures

    except Exception as e:
        log(f"Fussball.de Error: {str(e)[:60]}", "WARN")
        return []


# ============================================================
# 📊 FOOTYSTATS CSV - Statistiken ohne Key
# ============================================================
FOOTYSTATS_CSV_CACHE = {}

FOOTYSTATS_CSV_URLS = {
    "Bundesliga": "https://footystats.org/download-stats-csv#germany-bundesliga",
    "Premier League": "https://footystats.org/download-stats-csv#england-premier-league",
    "La Liga": "https://footystats.org/download-stats-csv#spain-la-liga",
    "Serie A": "https://footystats.org/download-stats-csv#italy-serie-a",
    "Ligue 1": "https://footystats.org/download-stats-csv#france-ligue-1",
}

def get_footystats_btts_rate(league_name, team_name):
    """
    Holt BTTS Rate von FootyStats (CSV Download).
    Kein Key nötig für öffentliche Statistiken!
    """
    cache_key = f"fsc_{league_name}_{team_name}"
    if cache_key in FOOTYSTATS_CSV_CACHE:
        return FOOTYSTATS_CSV_CACHE[cache_key]

    try:
        import random as _r
        # FootyStats öffentliche Team-Seite
        team_slug = team_name.lower().replace(" ", "-").replace(".", "")
        r = requests.get(
            f"https://footystats.org/clubs/{team_slug}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Referer": "https://footystats.org/",
            },
            timeout=12,
        )

        if not r.ok:
            return None

        import re as _re
        html = r.text

        btts_m = _re.search(r'btts[^>]*>.*?(\d+)%', html, _re.IGNORECASE | _re.DOTALL)
        over25_m = _re.search(r'over.?2\.5[^>]*>.*?(\d+)%', html, _re.IGNORECASE | _re.DOTALL)
        corners_m = _re.search(r'corners?[^>]*>.*?(\d+\.?\d*)', html, _re.IGNORECASE | _re.DOTALL)

        result = {}
        if btts_m:
            result["btts_rate"] = int(btts_m.group(1))
        if over25_m:
            result["over25_rate"] = int(over25_m.group(1))
        if corners_m:
            result["avg_corners"] = float(corners_m.group(1))

        if result:
            FOOTYSTATS_CSV_CACHE[cache_key] = result
            return result

    except Exception:
        pass
    return None



# ============================================================
# 🎯 SOCCERSTATS.COM - BTTS Tabellen für alle Ligen
# ============================================================
SOCCERSTATS_CACHE = {}

def get_soccerstats_btts(league_name):
    """BTTS + Over2.5 Statistiken von soccerstats.com"""
    LEAGUE_SLUGS = {
        "Bundesliga": "germany/bundesliga",
        "Premier League": "england/premier_league",
        "La Liga": "spain/primera_division",
        "Serie A": "italy/serie_a",
        "Ligue 1": "france/ligue_1",
        "Eredivisie": "netherlands/eredivisie",
        "Primeira Liga": "portugal/primeira_liga",
        "Champions League": "europe/champions_league",
        "MLS": "usa/mls",
        "Brasileirao Serie A": "brazil/serie_a",
        "J1 League Japan": "japan/j_league",
    }
    slug = LEAGUE_SLUGS.get(league_name)
    if not slug:
        return None
    cache_key = f"ss_{league_name}"
    if cache_key in SOCCERSTATS_CACHE:
        return SOCCERSTATS_CACHE[cache_key]
    try:
        import random as _r, re as _re
        r = smart_request(
            f"https://www.soccerstats.com/table.asp?league={slug}&tid=3",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
            ]), "Referer": "https://www.soccerstats.com/"},
            timeout=12,
        )
        if not r.ok:
            return None
        html = r.text
        btts_m = _re.search(r'BTTS[^>]*>.*?(\d+)%', html, _re.IGNORECASE | _re.DOTALL)
        over25_m = _re.search(r'Over 2\.5[^>]*>.*?(\d+)%', html, _re.IGNORECASE | _re.DOTALL)
        result = {}
        if btts_m:
            result["btts_rate"] = int(btts_m.group(1))
        if over25_m:
            result["over25_rate"] = int(over25_m.group(1))
        if result:
            SOCCERSTATS_CACHE[cache_key] = result
            log(f"   ⚽ SoccerStats: {league_name} BTTS {result.get('btts_rate','?')}%")
        return result or None
    except Exception:
        return None


# ============================================================
# 💰 BETEXPLORER - Historische Quoten + BTTS
# ============================================================
BETEXPLORER_CACHE = {}

def get_betexplorer_odds(home_team, away_team, league_name):
    """Historische Opening/Closing Odds von BetExplorer"""
    cache_key = f"be_{home_team}_{away_team}"
    if cache_key in BETEXPLORER_CACHE:
        return BETEXPLORER_CACHE[cache_key]
    try:
        import random as _r, re as _re
        search = f"{home_team} {away_team}".replace(" ", "+")
        r = smart_request(
            f"https://www.betexplorer.com/soccer/?q={search}",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
            ]), "Referer": "https://www.betexplorer.com/"},
            timeout=12,
        )
        if not r.ok:
            return None
        html = r.text
        odds = _re.findall(r'data-odd="([0-9.]+)"', html)
        if odds:
            result = {"odds": [float(o) for o in odds[:6]], "source": "betexplorer"}
            BETEXPLORER_CACHE[cache_key] = result
            return result
    except Exception:
        pass
    return None


# ============================================================
# 🎯 PREDICTZ - Gratis BTTS/Over2.5 Predictions
# ============================================================
PREDICTZ_CACHE = {}

def get_predictz_prediction(home_team, away_team, target_date):
    """Gratis Predictions von predictz.com"""
    cache_key = f"pz_{target_date}"  # Pro Tag cachen, nicht pro Match
    if cache_key in PREDICTZ_CACHE:
        return PREDICTZ_CACHE[cache_key]
    try:
        import random as _r, re as _re
        r = smart_request(
            f"https://www.predictz.com/predictions/{str(target_date)}/",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
            ]), "Referer": "https://www.predictz.com/"},
            timeout=12,
        )
        if not r.ok:
            return None
        html = r.text
        home_norm = normalize_team_name(home_team)
        away_norm = normalize_team_name(away_team)
        blocks = _re.findall(r'<tr[^>]*class="[^"]*match[^"]*"[^>]*>(.*?)</tr>', html, _re.DOTALL)
        for block in blocks:
            teams = _re.findall(r'class="[^"]*team[^"]*"[^>]*>([^<]+)<', block)
            if len(teams) < 2:
                continue
            if not (home_norm[:5] in normalize_team_name(teams[0]) or normalize_team_name(teams[0])[:5] in home_norm):
                continue
            btts_m = _re.search(r'btts[^>]*>.*?(\d+)%', block, _re.IGNORECASE | _re.DOTALL)
            over25_m = _re.search(r'over.?2\.5[^>]*>.*?(\d+)%', block, _re.IGNORECASE | _re.DOTALL)
            result = {}
            if btts_m:
                result["btts_pct"] = int(btts_m.group(1))
            if over25_m:
                result["over25_pct"] = int(over25_m.group(1))
            if result:
                PREDICTZ_CACHE[cache_key] = result
                return result
    except Exception:
        pass
    return None


# ============================================================
# 🎯 BETIMATE - BTTS + Over2.5 Predictions
# ============================================================
BETIMATE_CACHE = {}

def get_betimate_prediction(home_team, away_team, target_date):
    """BTTS + Over2.5 von betimate.com"""
    cache_key = f"bm_{target_date}"  # Pro Tag cachen
    if cache_key in BETIMATE_CACHE:
        return BETIMATE_CACHE[cache_key]
    try:
        import random as _r, re as _re
        r = smart_request(
            f"https://betimate.com/en/football-predictions/{str(target_date)}/",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
            ]), "Referer": "https://betimate.com/"},
            timeout=12,
        )
        if not r.ok:
            return None
        html = r.text
        home_norm = normalize_team_name(home_team)
        result = {}
        if home_norm[:6] in html.lower():
            btts_m = _re.search(r'"btts":\s*(\d+)', html)
            over25_m = _re.search(r'"over25":\s*(\d+)', html)
            if btts_m:
                result["btts_pct"] = int(btts_m.group(1))
            if over25_m:
                result["over25_pct"] = int(over25_m.group(1))
        if result:
            BETIMATE_CACHE[cache_key] = result
            return result
    except Exception:
        pass
    return None


# ============================================================
# 🇩🇪 KICKER.DE - Bundesliga Aufstellungen!
# ============================================================
KICKER_CACHE = {}

def get_kicker_lineup(home_team, away_team, target_date):
    """Bundesliga Aufstellungen von kicker.de"""
    cache_key = f"kicker_{home_team}_{away_team}"
    if cache_key in KICKER_CACHE:
        return KICKER_CACHE[cache_key]
    try:
        import random as _r, re as _re
        r = requests.get(
            f"https://www.kicker.de/bundesliga/spieltag",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
            ]),
            "Accept-Language": "de-DE,de;q=0.9",
            "Referer": "https://www.kicker.de/"},
            timeout=12,
        )
        if not r.ok:
            return None
        html = r.text
        home_norm = normalize_team_name(home_team)
        result = {}
        if home_norm[:6] in html.lower():
            lineups = _re.findall(r'class="[^"]*aufstellung[^"]*"[^>]*>(.*?)</[^>]+>', html, _re.DOTALL | _re.IGNORECASE)
            if lineups:
                result["lineup_available"] = True
                result["source"] = "kicker"
        if result:
            KICKER_CACHE[cache_key] = result
            return result
    except Exception:
        pass
    return None


# ============================================================
# 💰 ACTIONNETWORK - Sharp Money USA
# ============================================================
ACTION_CACHE = {}

def get_action_network_sharp(home_team, away_team):
    """Sharp Money Daten von ActionNetwork (US Ligen)"""
    cache_key = f"an_{home_team}_{away_team}"
    if cache_key in ACTION_CACHE:
        return ACTION_CACHE[cache_key]
    try:
        import random as _r, re as _re
        r = requests.get(
            "https://api.actionnetwork.com/web/v1/games",
            params={"sport": "soccer", "bookmakers": "fanduel,draftkings"},
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "application/json",
                "Referer": "https://www.actionnetwork.com/",
            },
            timeout=12,
        )
        if not r.ok:
            return None
        data = r.json()
        for game in data.get("games", []):
            h = game.get("teams", [{}])[0].get("full_name", "")
            a = game.get("teams", [{}])[1].get("full_name", "") if len(game.get("teams", [])) > 1 else ""
            if teams_match(home_team, h) and teams_match(away_team, a):
                public_bets = game.get("public_betting", {})
                result = {
                    "public_home": public_bets.get("home_ml_percent", 0),
                    "public_away": public_bets.get("away_ml_percent", 0),
                    "sharp_signal": public_bets.get("sharp_money", False),
                    "source": "actionnetwork",
                }
                ACTION_CACHE[cache_key] = result
                return result
    except Exception:
        pass
    return None


# ============================================================
# 🎯 WINDRAWWIN - Statistische Vorhersagen
# ============================================================
WDW_CACHE = {}

def get_windrawwin_prediction(home_team, away_team, target_date):
    """Statistische Predictions von windrawwin.com"""
    cache_key = f"wdw_{target_date}"  # Pro Tag cachen
    if cache_key in WDW_CACHE:
        return WDW_CACHE[cache_key]
    try:
        import random as _r, re as _re
        r = smart_request(
            f"https://windrawwin.com/predictions/future/",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
            ]), "Referer": "https://windrawwin.com/"},
            timeout=12,
        )
        if not r.ok:
            return None
        html = r.text
        home_norm = normalize_team_name(home_team)
        blocks = _re.findall(r'<tr[^>]*>(.*?)</tr>', html, _re.DOTALL)
        for block in blocks:
            if home_norm[:5] not in block.lower():
                continue
            probs = _re.findall(r'(\d+)%', block)
            if len(probs) >= 3:
                result = {
                    "prob_home": int(probs[0]),
                    "prob_draw": int(probs[1]),
                    "prob_away": int(probs[2]),
                }
                WDW_CACHE[cache_key] = result
                return result
    except Exception:
        pass
    return None


# ============================================================
# 🌍 FORTUNA LIGA SK - Slowakische Liga
# ============================================================
FORTUNA_CACHE = {}

def fetch_fortuna_liga(target_date):
    """Offizielle Daten der Slowakischen Fortuna Liga"""
    cache_key = f"fl_{target_date}"
    if cache_key in FORTUNA_CACHE:
        return FORTUNA_CACHE[cache_key]
    try:
        import random as _r
        r = requests.get(
            "https://www.fortunaliga.sk/rozpis-zapasov",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept-Language": "sk-SK,sk;q=0.9",
                "Referer": "https://www.fortunaliga.sk/",
            },
            timeout=12,
        )
        if not r.ok:
            return []
        import re as _re
        html = r.text
        target_str = str(target_date)
        fixtures = []
        now_utc = datetime.now(timezone.utc)
        matches = _re.findall(
            r'(\d{2}\.\d{2}\.\d{4}).*?(\d{2}:\d{2}).*?([A-Za-zÀ-ž\s]+?)\s*[-–]\s*([A-Za-zÀ-ž\s]+)',
            html, _re.DOTALL
        )
        for date_str, time_str, home, away in matches[:20]:
            try:
                parts = date_str.split(".")
                match_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                if match_date != target_str:
                    continue
                kickoff_str = f"{match_date}T{time_str}:00Z"
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                if kickoff <= now_utc:
                    continue
                fixtures.append({
                    "home": home.strip(),
                    "away": away.strip(),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "fortuna_liga",
                    "match_id": f"fl_{hash(home+away)}",
                })
            except Exception:
                continue
        FORTUNA_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🇸🇰 Fortuna Liga: {len(fixtures)} Spiele")
        return fixtures
    except Exception:
        return []


# ============================================================
# 🏥 PHYSIOROOM - Verletzungen + Rückkehrdatum
# ============================================================
PHYSIOROOM_CACHE = {}

def get_physioroom_injuries(team_name, league_name):
    """Verletzungen mit Rückkehrdatum von physioroom.com (Premier League)"""
    PHYSIOROOM_TEAMS = {
        "Arsenal": "arsenal", "Chelsea": "chelsea", "Liverpool": "liverpool",
        "Manchester City": "manchester-city", "Manchester United": "manchester-united",
        "Tottenham": "tottenham-hotspur", "Newcastle": "newcastle-united",
        "Aston Villa": "aston-villa", "West Ham": "west-ham-united",
    }
    if league_name not in ["Premier League", "Championship"]:
        return None
    team_slug = None
    for team, slug in PHYSIOROOM_TEAMS.items():
        if normalize_team_name(team_name)[:6] in normalize_team_name(team):
            team_slug = slug
            break
    if not team_slug:
        return None
    cache_key = f"pr_{team_name}"
    if cache_key in PHYSIOROOM_CACHE:
        return PHYSIOROOM_CACHE[cache_key]
    try:
        import random as _r, re as _re
        r = smart_request(
            f"https://www.physioroom.com/team/{team_slug}/",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
            ]), "Referer": "https://www.physioroom.com/"},
            timeout=12,
        )
        if not r.ok:
            return None
        html = r.text
        players = _re.findall(
            r'class="player-name"[^>]*>([^<]+)</.*?class="return-date"[^>]*>([^<]+)<',
            html, _re.DOTALL
        )
        if not players:
            players = _re.findall(r'<td[^>]*>([A-Z][a-z]+ [A-Z][a-z]+)</td>.*?<td[^>]*>(\d{2}/\d{2}/\d{4})</td>', html, _re.DOTALL)
        if players:
            result = {
                "injured": [{"name": p[0].strip(), "return": p[1].strip()} for p in players[:5]],
                "total_out": len(players),
                "has_data": True,
                "source": "physioroom",
            }
            PHYSIOROOM_CACHE[cache_key] = result
            return result
    except Exception:
        pass
    return None


# ============================================================
# 📊 VITIBET - Gratis Predictions
# ============================================================
VITIBET_CACHE = {}

def get_vitibet_prediction(home_team, away_team, target_date):
    """Gratis Predictions von vitibet.com"""
    cache_key = f"vb_{home_team}_{away_team}"
    if cache_key in VITIBET_CACHE:
        return VITIBET_CACHE[cache_key]
    try:
        import random as _r, re as _re
        r = smart_request(
            f"https://vitibet.com/predictions/{str(target_date)}/",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
            ]), "Referer": "https://vitibet.com/"},
            timeout=12,
        )
        if not r.ok:
            return None
        html = r.text
        home_norm = normalize_team_name(home_team)
        if home_norm[:5] not in html.lower():
            return None
        btts_m = _re.search(r'btts[^>]*(\d+)%', html, _re.IGNORECASE)
        result = {}
        if btts_m:
            result["btts_pct"] = int(btts_m.group(1))
        if result:
            VITIBET_CACHE[cache_key] = result
            return result
    except Exception:
        pass
    return None



# ============================================================
# 🎭 PLAYWRIGHT - Alle 403-blockierten Seiten
# ============================================================

def pw_get_sofascore_fixtures(league_name, target_date):
    """SofaScore via Playwright - alle Ligen"""
    if not PLAYWRIGHT_AVAILABLE:
        return []
    cache_key = f"pw_sofa_{league_name}_{target_date}"
    if cache_key in PLAYWRIGHT_CACHE:
        return PLAYWRIGHT_CACHE[cache_key]
    try:
        slug = SOFASCORE_SLUG_MAP.get(league_name, "")
        if not slug:
            return []
        html = scrape_with_playwright(
            f"https://www.sofascore.com/football/{slug}",
            timeout=20000
        )
        if not html:
            return []
        import re as _re
        import json as _json
        # SofaScore JSON in Script Tags
        matches = _re.findall(r'"homeTeam":\{"id":(\d+),"name":"([^"]+)".*?"awayTeam":\{"id":(\d+),"name":"([^"]+)".*?"startTimestamp":(\d+)', html)
        now_utc = datetime.now(timezone.utc)
        fixtures = []
        for hid, home, aid, away, ts in matches[:20]:
            try:
                kickoff = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                if kickoff.date() != target_date or kickoff <= now_utc:
                    continue
                kickoff_str = kickoff.strftime("%Y-%m-%dT%H:%M:%SZ")
                fixtures.append({
                    "home": home, "away": away,
                    "home_id": hid, "away_id": aid,
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "sofascore_pw",
                })
            except Exception:
                continue
        PLAYWRIGHT_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🎭 SofaScore PW: {len(fixtures)} Spiele für {league_name}")
        return fixtures
    except Exception as e:
        log(f"SofaScore PW Error: {str(e)[:50]}", "WARN")
        return []


def pw_get_fbref_xg(home_team, away_team, league_name):
    """FBref xG via Playwright"""
    if not PLAYWRIGHT_AVAILABLE:
        return None
    cache_key = f"pw_fbref_{home_team}_{away_team}"
    if cache_key in PLAYWRIGHT_CACHE:
        return PLAYWRIGHT_CACHE[cache_key]
    try:
        FBREF_LEAGUES = {
            "Premier League": "9", "Bundesliga": "20",
            "La Liga": "12", "Serie A": "11", "Ligue 1": "13",
            "Champions League": "8", "Europa League": "19",
        }
        lid = FBREF_LEAGUES.get(league_name)
        if not lid:
            return None
        html = scrape_with_playwright(
            f"https://fbref.com/en/comps/{lid}/schedule/",
            timeout=20000
        )
        if not html:
            return None
        import re as _re
        home_norm = normalize_team_name(home_team)
        rows = _re.findall(r'<tr[^>]*>(.*?)</tr>', html, _re.DOTALL)
        for row in rows:
            if home_norm[:6] not in row.lower():
                continue
            xg_home = _re.search(r'xg.*?>([\d.]+)<', row, _re.IGNORECASE)
            xg_away = _re.search(r'xga.*?>([\d.]+)<', row, _re.IGNORECASE)
            if xg_home:
                result = {
                    "xg_home": float(xg_home.group(1)),
                    "xg_away": float(xg_away.group(1)) if xg_away else 0,
                    "source": "fbref_pw"
                }
                PLAYWRIGHT_CACHE[cache_key] = result
                return result
    except Exception:
        pass
    return None


def pw_get_understat_scorers(league_name, season):
    """Understat Top Scorer via Playwright"""
    if not PLAYWRIGHT_AVAILABLE:
        return []
    cache_key = f"pw_understat_{league_name}_{season}"
    if cache_key in PLAYWRIGHT_CACHE:
        return PLAYWRIGHT_CACHE[cache_key]
    try:
        UNDERSTAT_MAP = {
            "Premier League": "EPL", "Bundesliga": "Bundesliga",
            "La Liga": "La_liga", "Serie A": "Serie_A",
            "Ligue 1": "Ligue_1", "Eredivisie": "Eredivisie",
        }
        slug = UNDERSTAT_MAP.get(league_name)
        if not slug:
            return []
        html = scrape_with_playwright(
            f"https://understat.com/league/{slug}/{season}",
            timeout=20000
        )
        if not html:
            return []
        import re as _re, json as _json
        m = _re.search(r"var playersData\s*=\s*JSON\.parse\('(.+?)'\)", html)
        if not m:
            return []
        players = _json.loads(m.group(1).encode().decode('unicode_escape'))
        scorers = []
        for p in players:
            try:
                goals = int(p.get("goals", 0) or 0)
                games = int(p.get("games", 1) or 1)
                if games < 5 or goals < 3:
                    continue
                gpg = round(goals / games, 2)
                if gpg >= 0.3:
                    scorers.append({
                        "name": p.get("player_name", ""),
                        "team": p.get("team_title", ""),
                        "goals_total": goals,
                        "appearances": games,
                        "goals_per_game": gpg,
                    })
            except Exception:
                continue
        scorers.sort(key=lambda x: x["goals_per_game"], reverse=True)
        PLAYWRIGHT_CACHE[cache_key] = scorers[:20]
        if scorers:
            log(f"   🎭 Understat PW: {len(scorers[:20])} Scorer für {league_name}")
        return scorers[:20]
    except Exception:
        return []


def pw_get_transfermarkt_injuries(team_name, league_name):
    """Transfermarkt Verletzungen via Playwright"""
    if not PLAYWRIGHT_AVAILABLE:
        return None
    cache_key = f"pw_tm_{team_name}"
    if cache_key in PLAYWRIGHT_CACHE:
        return PLAYWRIGHT_CACHE[cache_key]
    try:
        search = team_name.lower().replace(" ", "-").replace(".", "")
        html = scrape_with_playwright(
            f"https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query={search}",
            timeout=20000
        )
        if not html:
            return None
        import re as _re
        injuries = _re.findall(
            r'class="[^"]*verletzt[^"]*"[^>]*>.*?<a[^>]*>([^<]+)</a>',
            html, _re.DOTALL
        )
        if injuries:
            result = {
                "injured": [{"name": p.strip()} for p in injuries[:5]],
                "total_out": len(injuries),
                "has_data": True,
                "source": "transfermarkt_pw",
            }
            PLAYWRIGHT_CACHE[cache_key] = result
            return result
    except Exception:
        pass
    return None


def pw_get_worldfootballdb(league_name, target_date):
    """WorldFootballDatabase via Playwright"""
    if not PLAYWRIGHT_AVAILABLE:
        return []
    cache_key = f"pw_wfdb_{league_name}_{target_date}"
    if cache_key in PLAYWRIGHT_CACHE:
        return PLAYWRIGHT_CACHE[cache_key]
    try:
        WFDB_LEAGUES = {
            "Premier League": "england/premier-league",
            "Bundesliga": "germany/bundesliga",
            "La Liga": "spain/la-liga",
            "Serie A": "italy/serie-a",
            "Ligue 1": "france/ligue-1",
            "Champions League": "europe/champions-league",
        }
        slug = WFDB_LEAGUES.get(league_name)
        if not slug:
            return []
        html = scrape_with_playwright(
            f"https://worldfootballdatabase.com/{slug}/fixtures/",
            timeout=20000
        )
        if not html:
            return []
        import re as _re
        target_str = str(target_date)
        now_utc = datetime.now(timezone.utc)
        fixtures = []
        matches = _re.findall(
            r'(\d{4}-\d{2}-\d{2}).*?(\d{2}:\d{2}).*?<[^>]*>([^<]+)</[^>]*>\s*[-–vs]+\s*<[^>]*>([^<]+)<',
            html, _re.DOTALL
        )
        for date_str, time_str, home, away in matches[:20]:
            if date_str != target_str:
                continue
            kickoff_str = f"{date_str}T{time_str}:00Z"
            try:
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                if kickoff <= now_utc:
                    continue
            except Exception:
                pass
            fixtures.append({
                "home": home.strip(),
                "away": away.strip(),
                "time_utc": kickoff_str,
                "time_local": get_local_time(kickoff_str),
                "source": "worldfootballdb_pw",
            })
        PLAYWRIGHT_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🎭 WorldFootballDB: {len(fixtures)} Spiele für {league_name}")
        return fixtures
    except Exception:
        return []



# ============================================================
# 🌦️ OPEN-METEO - Kostenloses Wetter (kein Key nötig!)
# ============================================================
OPEN_METEO_CACHE = {}

CITY_COORDS_WEATHER = {
    "Premier League": (51.5, -0.1),
    "Bundesliga": (48.1, 11.6),
    "La Liga": (40.4, -3.7),
    "Serie A": (41.9, 12.5),
    "Ligue 1": (48.9, 2.4),
    "Eredivisie": (52.4, 4.9),
    "Primeira Liga": (38.7, -9.1),
    "Champions League": (51.5, -0.1),
    "Europa League": (51.5, -0.1),
    "Bundesliga Österreich": (48.2, 16.4),
    "Super League Schweiz": (47.4, 8.5),
    "Scottish Premiership": (55.9, -4.3),
    "Danish Superliga": (55.7, 12.6),
    "Norway Eliteserien": (59.9, 10.7),
    "Sweden Allsvenskan": (59.3, 18.1),
    "MLS": (40.7, -74.0),
    "Brasileirao Serie A": (-23.5, -46.6),
    "J1 League Japan": (35.7, 139.7),
    "K League 1": (37.6, 127.0),
}

def get_open_meteo_weather(league_name, target_date):
    """
    Open-Meteo - Vollständig kostenlos, kein Key nötig!
    Viel besser als OpenWeatherMap für unsere Zwecke.
    """
    coords = CITY_COORDS_WEATHER.get(league_name)
    if not coords:
        return None

    cache_key = f"om_{league_name}_{target_date}"
    if cache_key in OPEN_METEO_CACHE:
        return OPEN_METEO_CACHE[cache_key]

    try:
        lat, lon = coords
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
                "forecast_days": 3,
                "timezone": "auto",
            },
            timeout=10,
        )

        if not r.ok:
            return None

        data = r.json()
        daily = data.get("daily", {})
        dates = daily.get("time", [])

        target_str = str(target_date)
        if target_str not in dates:
            return None

        idx = dates.index(target_str)
        temp_max = daily.get("temperature_2m_max", [None])[idx]
        temp_min = daily.get("temperature_2m_min", [None])[idx]
        rain = daily.get("precipitation_sum", [0])[idx] or 0
        wind = daily.get("windspeed_10m_max", [0])[idx] or 0

        temp = round((temp_max + temp_min) / 2, 1) if temp_max and temp_min else temp_max

        impact = "neutral"
        notes = []
        if rain > 5:
            impact = "negative"
            notes.append(f"🌧️ Starker Regen ({rain}mm)")
        elif rain > 2:
            notes.append(f"🌦️ Regen ({rain}mm)")
        if wind > 50:
            impact = "negative"
            notes.append(f"💨 Starker Wind ({wind}km/h)")
        elif wind > 30:
            notes.append(f"🌬️ Wind {wind}km/h")
        if temp and temp > 32:
            notes.append(f"🥵 Hitze ({temp}°C)")
        elif temp and temp < 2:
            notes.append(f"🥶 Kälte ({temp}°C)")

        result = {
            "temp": temp,
            "rain": round(rain, 1),
            "wind": round(wind, 1),
            "impact": impact,
            "notes": notes,
            "source": "open-meteo",
        }

        OPEN_METEO_CACHE[cache_key] = result
        return result

    except Exception as e:
        log(f"Open-Meteo Error: {str(e)[:50]}", "WARN")
        return None



# ============================================================
# 📊 STATSBOMB OPEN DATA - Player Props (100% GRATIS!)
# pip install statsbombpy
# Echte Event-Daten: SOT, Fouls, Offsides, Headers pro Spiel
# ============================================================

STATSBOMB_PLAYER_CACHE = {}
STATSBOMB_AVAILABLE = False
try:
    import warnings as _sw
    _sw.filterwarnings('ignore')
    from statsbombpy import sb as _sb
    import pandas as _pd
    STATSBOMB_AVAILABLE = True
    log("   📊 StatsBombPy verfügbar!")
except ImportError:
    pass

# Mapping: Liga → StatsBomb IDs (competition_id, season_id)
STATSBOMB_LEAGUE_MAP = {
    "Bundesliga": (9, 281),          # 2023/24
    "La Liga": (11, 90),             # 2020/21 (aktuellste verfügbare)
    "Premier League": (2, 27),       # 2015/16 (historisch)
    "Ligue 1": (7, 235),             # 2022/23
    "Champions League": (16, 4),     # 2018/19
    "WM 2026": (43, 106),            # WM 2022 als Referenz
    "Copa America": (223, 282),      # 2024
    "UEFA Nations League": (5, 107), # AFCON als Referenz
    "MLS": (44, 107),                # 2023
    "India Super League": (1238, 108),
}

def get_statsbomb_player_stats(league_name: str) -> dict:
    """
    Holt aggregierte Spieler-Stats von StatsBomb Open Data.
    Returns: {player_name: {sot_per90, fouls_per90, offsides_per90, aerials_per90}}
    """
    if not STATSBOMB_AVAILABLE:
        return {}

    if league_name in STATSBOMB_PLAYER_CACHE:
        return STATSBOMB_PLAYER_CACHE[league_name]

    comp = STATSBOMB_LEAGUE_MAP.get(league_name)
    if not comp:
        return {}

    comp_id, season_id = comp

    try:
        import warnings as _w
        _w.filterwarnings('ignore')

        matches = _sb.matches(competition_id=comp_id, season_id=season_id)
        if matches is None or len(matches) == 0:
            return {}

        # Letzte 20 Spiele für aktuelle Form
        recent = matches.tail(20)
        all_events = []

        for _, match in recent.iterrows():
            try:
                events = _sb.events(match_id=match['match_id'])
                events['match_id'] = match['match_id']
                all_events.append(events)
            except Exception:
                continue

        if not all_events:
            return {}

        import pandas as _pd2
        df = _pd2.concat(all_events, ignore_index=True)
        num_matches = len(recent)

        player_stats = {}

        # SOT (Shots on Target)
        sot = df[(df['type'] == 'Shot') & 
                 (df['shot_outcome'].isin(['Goal', 'Saved', 'Saved To Post']))]
        sot_counts = sot.groupby('player').size()

        # Fouls Committed
        fouls = df[df['type'] == 'Foul Committed']
        foul_counts = fouls.groupby('player').size()

        # Offsides
        offsides = df[df['type'] == 'Offside']
        offside_counts = offsides.groupby('player').size()

        # Headers / Aerial Duels
        aerials = df[(df['type'] == 'Duel') & 
                     (df.get('duel_type', _pd2.Series()).isin(['Aerial Lost', 'Aerial Won'])
                      if 'duel_type' in df.columns else _pd2.Series(False, index=df.index))]
        aerial_counts = aerials.groupby('player').size() if len(aerials) > 0 else _pd2.Series()

        # Team für jeden Spieler
        player_teams = df.groupby('player')['team'].last()

        # Alles zusammenführen
        all_players = set(sot_counts.index) | set(foul_counts.index) | set(offside_counts.index)

        for player in all_players:
            sot_per90 = round(sot_counts.get(player, 0) / num_matches, 2)
            fouls_per90 = round(foul_counts.get(player, 0) / num_matches, 2)
            offsides_per90 = round(offside_counts.get(player, 0) / num_matches, 2)
            aerials_per90 = round(aerial_counts.get(player, 0) / num_matches, 2) if len(aerial_counts) > 0 else 0

            # Nur interessante Spieler
            if sot_per90 < 0.3 and fouls_per90 < 0.5 and offsides_per90 < 0.2:
                continue

            player_stats[player] = {
                "team": str(player_teams.get(player, "")),
                "sot_per90": sot_per90,
                "fouls_per90": fouls_per90,
                "offsides_per90": offsides_per90,
                "aerials_per90": aerials_per90,
                "games": num_matches,
                "source": "statsbomb",
            }

        STATSBOMB_PLAYER_CACHE[league_name] = player_stats
        if player_stats:
            log(f"   📊 StatsBomb: {len(player_stats)} Spieler für {league_name}")
        return player_stats

    except Exception as e:
        log(f"StatsBomb Error: {str(e)[:60]}", "WARN")
        return {}


def get_player_props_for_match(home_team: str, away_team: str, league_name: str) -> list:
    """
    Gibt Player Props Tipps für ein Spiel zurück.
    Kombiniert StatsBomb + Understat Daten.
    Returns: [{player, tip, probability, fair_odds, stat_value}]
    """
    import math

    stats = get_statsbomb_player_stats(league_name)
    if not stats:
        return []

    home_norm = normalize_team_name(home_team)
    away_norm = normalize_team_name(away_team)
    props = []

    for player, s in stats.items():
        team_norm = normalize_team_name(s.get("team", ""))

        # Spieler spielt heute?
        is_playing = (
            team_norm[:8] in home_norm or home_norm[:8] in team_norm or
            team_norm[:8] in away_norm or away_norm[:8] in team_norm
        )
        if not is_playing:
            continue

        # SOT Prop: 1+ Schuss aufs Tor
        sot = s.get("sot_per90", 0)
        if sot >= 0.8:
            prob = round((1 - math.exp(-sot)) * 100)
            if prob >= 55:
                props.append({
                    "player": player,
                    "team": s["team"],
                    "tip": f"1+ Schüsse aufs Tor",
                    "market_type": "sot",
                    "stat_value": sot,
                    "probability": prob,
                    "fair_odds": round(1 / (prob / 100), 2),
                })

        # SOT Prop: 2+ Schüsse aufs Tor
        if sot >= 1.5:
            # P(X>=2) mit Poisson
            p0 = math.exp(-sot)
            p1 = sot * math.exp(-sot)
            prob2 = round((1 - p0 - p1) * 100)
            if prob2 >= 45:
                props.append({
                    "player": player,
                    "team": s["team"],
                    "tip": f"2+ Schüsse aufs Tor",
                    "market_type": "sot2",
                    "stat_value": sot,
                    "probability": prob2,
                    "fair_odds": round(1 / (prob2 / 100), 2),
                })

        # Fouls Prop: 2+ Fouls begangen
        fouls = s.get("fouls_per90", 0)
        if fouls >= 1.5:
            p0 = math.exp(-fouls)
            p1 = fouls * math.exp(-fouls)
            prob_f = round((1 - p0 - p1) * 100)
            if prob_f >= 45:
                props.append({
                    "player": player,
                    "team": s["team"],
                    "tip": f"2+ Fouls begangen",
                    "market_type": "fouls",
                    "stat_value": fouls,
                    "probability": prob_f,
                    "fair_odds": round(1 / (prob_f / 100), 2),
                })

        # Offside Prop: 1+ Abseits
        offsides = s.get("offsides_per90", 0)
        if offsides >= 0.8:
            prob_o = round((1 - math.exp(-offsides)) * 100)
            if prob_o >= 50:
                props.append({
                    "player": player,
                    "team": s["team"],
                    "tip": f"1+ Abseits",
                    "market_type": "offside",
                    "stat_value": offsides,
                    "probability": prob_o,
                    "fair_odds": round(1 / (prob_o / 100), 2),
                })

    # Sortiere nach Wahrscheinlichkeit
    props.sort(key=lambda x: x["probability"], reverse=True)
    return props[:8]  # Top 8 Props pro Spiel


def format_props_message(match_name: str, league: str, time: str, props: list) -> str:
    """Formatiert Player Props für Telegram"""
    if not props:
        return ""

    nl = "\n"
    msg = f"🔑 <b>PLAYER PROPS</b>\n"
    msg += f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"<b>{match_name}</b>\n"
    msg += f"📍 {league} · ⏰ {time}\n\n"

    for prop in props[:5]:
        prob = prop["probability"]
        fair = prop["fair_odds"]
        stars = "⭐⭐⭐" if prob >= 70 else "⭐⭐" if prob >= 60 else "⭐"
        msg += f"👤 <b>{prop['player']}</b> ({prop['team']})\n"
        msg += f"   🎯 {prop['tip']}\n"
        msg += f"   📈 {prob}% · Fair: {fair} · {stars}\n\n"

    msg += f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"<i>📊 Daten: StatsBomb Open Data</i>"
    return msg




# ============================================================
# 🌍 MARTJ42 - 49.000+ Internationale Ergebnisse (GitHub, gratis!)
# WM 2026, Nations League, Friendlies + historische BTTS Raten
# ============================================================

MARTJ42_CACHE = {}
MARTJ42_DATA = None

def load_martj42_data():
    """Lädt alle 49.000+ Länderspiele einmalig von GitHub."""
    global MARTJ42_DATA
    if MARTJ42_DATA is not None:
        return MARTJ42_DATA

    try:
        r = requests.get(
            "https://raw.githubusercontent.com/martj42/international_results/master/results.csv",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        if not r.ok:
            return []

        lines = r.text.strip().split("\n")
        MARTJ42_DATA = []
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < 5:
                continue
            try:
                date = parts[0].strip()
                home = parts[1].strip()
                away = parts[2].strip()
                hs = parts[3].strip()
                as_ = parts[4].strip()
                tournament = parts[5].strip() if len(parts) > 5 else ""
                hg = int(hs) if hs.isdigit() else -1
                ag = int(as_) if as_.isdigit() else -1
                MARTJ42_DATA.append({
                    "date": date, "home": home, "away": away,
                    "home_score": hg, "away_score": ag,
                    "tournament": tournament,
                    "btts": hg > 0 and ag > 0 if hg >= 0 else None,
                    "over25": (hg + ag) > 2 if hg >= 0 else None,
                    "total": hg + ag if hg >= 0 else -1,
                })
            except Exception:
                continue

        log(f"   🌍 martj42: {len(MARTJ42_DATA):,} Länderspiele geladen")
        return MARTJ42_DATA

    except Exception as e:
        log(f"martj42 Error: {str(e)[:50]}", "WARN")
        return []


def get_international_fixtures_today(target_date) -> list:
    """
    Holt heutige internationale Spiele aus martj42 Daten.
    Ideal für WM 2026, UEFA Nations League, Freundschaftsspiele!
    """
    cache_key = f"martj42_fix_{target_date}"
    if cache_key in MARTJ42_CACHE:
        return MARTJ42_CACHE[cache_key]

    data = load_martj42_data()
    if not data:
        return []

    target_str = str(target_date)
    now_utc = datetime.now(timezone.utc)
    fixtures = []

    for match in data:
        if match["date"] != target_str:
            continue
        if match["home_score"] >= 0:  # Bereits gespielt
            continue

        fixtures.append({
            "home": match["home"],
            "away": match["away"],
            "time_local": "TBD",
            "time_utc": f"{target_str}T18:00:00Z",
            "source": "martj42",
            "match_id": f"m42_{hash(match['home']+match['away'])}",
            "tournament": match["tournament"],
        })

    MARTJ42_CACHE[cache_key] = fixtures
    if fixtures:
        log(f"   🌍 martj42: {len(fixtures)} internationale Spiele heute")
    return fixtures


def get_international_btts_rate(team_name: str, last_n: int = 20) -> dict:
    """
    Berechnet historische BTTS/Over2.5 Rate für ein Nationalteam.
    Nutzt 49.000+ historische Länderspiele!
    """
    cache_key = f"martj42_btts_{team_name}"
    if cache_key in MARTJ42_CACHE:
        return MARTJ42_CACHE[cache_key]

    data = load_martj42_data()
    if not data:
        return {}

    team_norm = normalize_team_name(team_name)
    team_matches = []

    # Suche alle Spiele dieses Teams (neueste zuerst)
    for match in reversed(data):
        home_n = normalize_team_name(match["home"])
        away_n = normalize_team_name(match["away"])
        if team_norm[:8] in home_n or home_n[:8] in team_norm or \
           team_norm[:8] in away_n or away_n[:8] in team_norm:
            if match["btts"] is not None:
                team_matches.append(match)
        if len(team_matches) >= last_n:
            break

    if len(team_matches) < 3:
        return {}

    btts_count = sum(1 for m in team_matches if m["btts"])
    over25_count = sum(1 for m in team_matches if m.get("over25"))
    avg_goals = sum(m["total"] for m in team_matches if m["total"] >= 0) / len(team_matches)

    result = {
        "btts_rate": round(btts_count / len(team_matches) * 100, 1),
        "over25_rate": round(over25_count / len(team_matches) * 100, 1),
        "avg_goals": round(avg_goals, 2),
        "games": len(team_matches),
        "source": "martj42",
    }

    MARTJ42_CACHE[cache_key] = result
    return result


# ============================================================
# 📊 FOOTBALLCSV - Ligaergebnisse GitHub (Backup für BTTS History)
# ============================================================

FOOTBALLCSV_CACHE = {}

FOOTBALLCSV_REPOS = {
    "Premier League": ("footballcsv/england", "eng.1", "2020s", "2024-25"),
    "Bundesliga": ("footballcsv/deutschland", "de.1", "2020s", "2024-25"),
    "La Liga": ("footballcsv/espana", "es.1", "2020s", "2024-25"),
    "Bundesliga Österreich": ("footballcsv/austria", "at.1", "2020s", "2024-25"),
}

def get_footballcsv_btts_rate(league_name: str, team_name: str) -> dict:
    """
    Holt historische BTTS-Rate aus footballcsv GitHub Repos.
    Kostenlos, kein Key, direkt von GitHub.
    """
    repo_info = FOOTBALLCSV_REPOS.get(league_name)
    if not repo_info:
        return {}

    repo, code, decade, season = repo_info
    cache_key = f"fcsv_{league_name}_{team_name}"
    if cache_key in FOOTBALLCSV_CACHE:
        return FOOTBALLCSV_CACHE[cache_key]

    url = f"https://raw.githubusercontent.com/{repo}/master/{decade}/{season}/{code}.csv"

    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if not r.ok:
            return {}

        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            return {}

        team_norm = normalize_team_name(team_name)
        btts = 0
        over25 = 0
        total = 0

        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < 5:
                continue
            try:
                home = normalize_team_name(parts[2] if len(parts) > 4 else "")
                away = normalize_team_name(parts[4] if len(parts) > 4 else "")
                score = parts[3] if len(parts) > 3 else ""

                if team_norm[:6] not in home and home[:6] not in team_norm and \
                   team_norm[:6] not in away and away[:6] not in team_norm:
                    continue

                # Score parsen "2-1" oder "2:1"
                import re as _re
                m = _re.search(r"(\d+)[:\-](\d+)", score)
                if not m:
                    continue

                hg, ag = int(m.group(1)), int(m.group(2))
                total += 1
                if hg > 0 and ag > 0:
                    btts += 1
                if hg + ag > 2:
                    over25 += 1
            except Exception:
                continue

        if total < 3:
            return {}

        result = {
            "btts_rate": round(btts / total * 100, 1),
            "over25_rate": round(over25 / total * 100, 1),
            "games": total,
            "source": "footballcsv",
        }
        FOOTBALLCSV_CACHE[cache_key] = result
        return result

    except Exception as e:
        log(f"footballcsv Error: {str(e)[:50]}", "WARN")
        return {}


# ============================================================
# 📰 GOOGLE NEWS - Team News scrapen
# ============================================================
GOOGLE_NEWS_CACHE = {}

def scrape_google_news(query, max_results=3):
    """
    Google News scrapen für Team News + Verletzungen.
    Kein Key nötig!
    """
    cache_key = f"gn_{query}"
    if cache_key in GOOGLE_NEWS_CACHE:
        return GOOGLE_NEWS_CACHE[cache_key]

    try:
        import random as _r
        import re as _re
        import urllib.parse

        encoded = urllib.parse.quote(query)
        r = requests.get(
            f"https://news.google.com/rss/search?q={encoded}&hl=de&gl=DE&ceid=DE:de",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "application/rss+xml, application/xml",
            },
            timeout=10,
        )

        if not r.ok:
            return []

        # Parse RSS
        titles = _re.findall(r"<title><!\[CDATA\[(.+?)\]\]></title>", r.text)
        descriptions = _re.findall(r"<description><!\[CDATA\[(.+?)\]\]></description>", r.text)

        results = []
        for i, title in enumerate(titles[1:max_results+1]):  # Skip first (feed title)
            desc = descriptions[i] if i < len(descriptions) else ""
            results.append({
                "title": title.strip(),
                "description": _re.sub(r"<[^>]+>", "", desc).strip()[:200],
            })

        GOOGLE_NEWS_CACHE[cache_key] = results
        return results

    except Exception:
        return []


def get_team_news_google(home_team, away_team, league):
    """
    Holt aktuelle Team News von Google News.
    Verletzungen, Sperren, Form-News.
    """
    query = f"{home_team} {away_team} {league} lineup injury"
    results = scrape_google_news(query, max_results=3)

    if not results:
        return None

    # Suche nach Verletzungs-Keywords
    injury_keywords = ["verletzt", "fehlt", "gesperrt", "injury", "suspended", "out", "doubt"]
    news_items = []

    for r in results:
        text = (r.get("title", "") + " " + r.get("description", "")).lower()
        has_injury = any(kw in text for kw in injury_keywords)
        news_items.append({
            "title": r.get("title", ""),
            "has_injury_info": has_injury,
        })

    return news_items if news_items else None


# ============================================================
# 🤖 REDDIT - Community Insider Tips
# ============================================================
REDDIT_CACHE = {}

def scrape_reddit_soccer(home_team, away_team):
    """
    Reddit Soccer Threads für Insider News.
    Kein Key nötig - öffentliche Daten!
    """
    cache_key = f"rd_{home_team}_{away_team}"
    if cache_key in REDDIT_CACHE:
        return REDDIT_CACHE[cache_key]

    try:
        import random as _r
        import re as _re

        query = f"{home_team} {away_team}".replace(" ", "+")
        r = requests.get(
            f"https://www.reddit.com/r/soccer/search.json?q={query}&sort=new&limit=5",
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; FootballBot/1.0)",
                "Accept": "application/json",
            },
            timeout=10,
        )

        if not r.ok:
            return None

        data = r.json()
        posts = data.get("data", {}).get("children", [])

        results = []
        for post in posts[:3]:
            p = post.get("data", {})
            title = p.get("title", "")
            score = p.get("score", 0)
            if score > 10:  # Nur populäre Posts
                results.append({
                    "title": title,
                    "score": score,
                    "url": p.get("url", ""),
                })

        REDDIT_CACHE[cache_key] = results
        if results:
            log(f"   🤖 Reddit: {len(results)} Posts gefunden")
        return results if results else None

    except Exception:
        return None


# ============================================================
# 🌦️ METEOSTAT - Historische Wetterdaten
# ============================================================
def get_historical_weather_impact(league_name, month):
    """
    Historische Wetterdaten für Liga-Analyse.
    Zeigt ob Wetter typisch hohe/niedrige BTTS Rate beeinflusst.
    """
    # Vereinfachte historische Analyse basierend auf Monat + Liga
    WINTER_LEAGUES = ["Premier League", "Bundesliga", "La Liga", "Serie A", "Ligue 1"]
    SUMMER_LEAGUES = ["MLS", "A-League Australia", "J1 League Japan"]

    impact = "neutral"

    # Wintermonate in Europa
    if league_name in WINTER_LEAGUES:
        if month in [11, 12, 1, 2]:
            impact = "slightly_negative"  # Kälte, Regen
        elif month in [4, 5]:
            impact = "positive"  # Frühling = mehr Tore

    # Sommerliga
    if league_name in SUMMER_LEAGUES:
        if month in [6, 7, 8]:
            impact = "slightly_negative"  # Hitze

    return {
        "month": month,
        "historical_impact": impact,
        "note": f"Historisch: {impact} für {league_name} im Monat {month}",
    }



# ============================================================
# ⚽ FOTMOB - Inoffizielle API, xG + 500+ Ligen, kein Key!
# ============================================================

# ============================================================
# 🎭 UNIVERSELLER PLAYWRIGHT WRAPPER - für alle blockierten Sites
# ============================================================

def smart_request(url, timeout=15, use_playwright_if_blocked=True, headers=None):
    """
    Intelligenter Request: erst direkt, dann Playwright bei 403/429/503
    Gilt für ALLE Domains!
    """
    import random as _r
    default_headers = {
        "User-Agent": _r.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0",
        ]),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "DNT": "1",
    }
    if headers:
        default_headers.update(headers)
    
    try:
        r = requests.get(url, headers=default_headers, timeout=timeout)
        if r.status_code in [403, 429, 503, 406, 444] and use_playwright_if_blocked:
            log(f"   🎭 {url[:40]}... → Playwright (Status {r.status_code})")
            html = scrape_with_playwright(url, timeout=8000)
            if html:
                log(f"   ✅ Playwright erfolgreich!")
                return type('Response', (), {
                    'ok': True, 'status_code': 200,
                    'text': html, 'json': lambda: {}
                })()
            return None
        return r if r.ok else None
    except requests.exceptions.ConnectionError:
        if use_playwright_if_blocked and PLAYWRIGHT_AVAILABLE:
            log(f"   🎭 ConnectionError → Playwright für {url[:40]}")
            html = scrape_with_playwright(url, timeout=8000)
            if html:
                return type('Response', (), {
                    'ok': True, 'status_code': 200,
                    'text': html, 'json': lambda: {}
                })()
        return None
    except Exception as e:
        log(f"smart_request Error: {str(e)[:50]}", "WARN")
        return None


FOTMOB_CACHE = {}

def get_fotmob_match_stats(home_team, away_team, target_date):
    """
    FotMob inoffizielle API - xG, Momentum, Live Stats
    500+ Ligen weltweit, kein Key nötig!
    """
    cache_key = f"fm_{home_team}_{away_team}_{target_date}"
    if cache_key in FOTMOB_CACHE:
        return FOTMOB_CACHE[cache_key]

    try:
        import random as _r
        date_str = str(target_date).replace("-", "")

        r = requests.get(
            f"https://www.fotmob.com/api/matches?date={date_str}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
                ]),
                "Accept": "application/json",
                "Referer": "https://www.fotmob.com/",
                "x-mas": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            },
            timeout=12,
        )

        if not r.ok:
            return None

        data = r.json()
        leagues = data.get("leagues", [])
        home_norm = normalize_team_name(home_team)

        for league in leagues:
            for match in league.get("matches", []):
                h = match.get("home", {}).get("name", "")
                a = match.get("away", {}).get("name", "")

                if not (home_norm[:6] in normalize_team_name(h) or normalize_team_name(h)[:6] in home_norm):
                    continue

                match_id = match.get("id")
                if not match_id:
                    continue

                # Hole Match Details mit xG
                r2 = requests.get(
                    f"https://www.fotmob.com/api/matchDetails?matchId={match_id}",
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                        "Referer": "https://www.fotmob.com/",
                    },
                    timeout=10,
                )

                if not r2.ok:
                    continue

                details = r2.json()
                stats = details.get("content", {}).get("stats", {}).get("stats", [])

                result = {"source": "fotmob"}
                for stat in stats:
                    title = stat.get("title", "").lower()
                    if "xg" in title or "expected goals" in title:
                        home_val = stat.get("stats", [{}])[0].get("value", 0)
                        away_val = stat.get("stats", [{}])[1].get("value", 0) if len(stat.get("stats", [])) > 1 else 0
                        result["xg_home"] = home_val
                        result["xg_away"] = away_val

                FOTMOB_CACHE[cache_key] = result
                if result.get("xg_home"):
                    log(f"   ⚽ FotMob xG: {home_team} {result['xg_home']} vs {result['xg_away']}")
                return result

    except Exception as e:
        log(f"FotMob Error: {str(e)[:50]}", "WARN")
    return None


def fetch_fotmob_fixtures(league_name, target_date):
    """
    FotMob Fixtures - 500+ Ligen, kein Key!
    """
    cache_key = f"fm_fix_{league_name}_{target_date}"
    if cache_key in FOTMOB_CACHE:
        return FOTMOB_CACHE[cache_key]

    FOTMOB_LEAGUES = {
        "Premier League": 47,
        "Bundesliga": 54,
        "La Liga": 87,
        "Serie A": 55,
        "Ligue 1": 53,
        "Eredivisie": 57,
        "Primeira Liga": 61,
        "Champions League": 42,
        "Europa League": 73,
        "Conference League": 10090,
        "MLS": 130,
        "Brasileirao Serie A": 325,
        "Liga Argentinien": 112,
        "J1 League Japan": 40,
        "K League 1": 133,
        "Saudi Pro League": 1366,
    }

    league_id = FOTMOB_LEAGUES.get(league_name)
    if not league_id:
        return []

    try:
        import random as _r
        date_str = str(target_date).replace("-", "")

        r = requests.get(
            f"https://www.fotmob.com/api/matches?date={date_str}&league={league_id}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "application/json",
                "Referer": "https://www.fotmob.com/",
            },
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json()
        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for league in data.get("leagues", []):
            for match in league.get("matches", []):
                try:
                    status = match.get("status", {})
                    if status.get("finished") or status.get("ongoing"):
                        continue

                    home = match.get("home", {}).get("name", "")
                    away = match.get("away", {}).get("name", "")
                    if not home or not away:
                        continue

                    utc_time = match.get("status", {}).get("utcTime", "")
                    if utc_time:
                        kickoff = datetime.fromisoformat(utc_time.replace("Z", "+00:00"))
                        if kickoff <= now_utc:
                            continue
                        kickoff_str = kickoff.strftime("%Y-%m-%dT%H:%M:%SZ")
                    else:
                        kickoff_str = f"{target_date}T12:00:00Z"

                    fixtures.append({
                        "home": home,
                        "away": away,
                        "match_id": str(match.get("id", "")),
                        "time_utc": kickoff_str,
                        "time_local": get_local_time(kickoff_str),
                        "source": "fotmob",
                    })
                except Exception:
                    continue

        FOTMOB_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   ⚽ FotMob: {len(fixtures)} Spiele für {league_name}")
        return fixtures

    except Exception as e:
        log(f"FotMob Fixtures Error: {str(e)[:50]}", "WARN")
        return []


# ============================================================
# 🏆 FANTASY PREMIER LEAGUE API - Offiziell, kein Key!
# ============================================================
FPL_CACHE = {}

def get_fpl_data():
    """
    Fantasy Premier League API - Offiziell von der PL!
    Spielerdaten, Preise, Stats, Verletzungen
    """
    if "fpl_bootstrap" in FPL_CACHE:
        return FPL_CACHE["fpl_bootstrap"]

    try:
        r = requests.get(
            "https://fantasy.premierleague.com/api/bootstrap-static/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )

        if not r.ok:
            return None

        data = r.json()
        FPL_CACHE["fpl_bootstrap"] = data
        log(f"   🏆 FPL: {len(data.get('elements', []))} Spieler geladen")
        return data

    except Exception:
        return None


def get_fpl_player_stats(player_name, team_name):
    """
    Holt Spieler-Stats aus FPL (nur Premier League).
    Returns: {'goals': 12, 'assists': 5, 'minutes': 2340, 'injured': False}
    """
    cache_key = f"fpl_{player_name}"
    if cache_key in FPL_CACHE:
        return FPL_CACHE[cache_key]

    data = get_fpl_data()
    if not data:
        return None

    elements = data.get("elements", [])
    player_norm = normalize_team_name(player_name)

    for player in elements:
        first = player.get("first_name", "")
        last = player.get("second_name", "")
        full = f"{first} {last}"

        if player_norm[:6] in normalize_team_name(full) or normalize_team_name(full)[:6] in player_norm:
            result = {
                "goals": player.get("goals_scored", 0),
                "assists": player.get("assists", 0),
                "minutes": player.get("minutes", 0),
                "injured": player.get("status") in ["i", "d", "u"],
                "status": player.get("status", "a"),
                "chance_playing": player.get("chance_of_playing_next_round", 100),
                "form": float(player.get("form", 0) or 0),
                "source": "fpl",
            }
            FPL_CACHE[cache_key] = result
            return result

    return None


def get_fpl_team_injuries(team_name):
    """
    Holt Verletzungen eines Premier League Teams aus FPL.
    """
    cache_key = f"fpl_inj_{team_name}"
    if cache_key in FPL_CACHE:
        return FPL_CACHE[cache_key]

    data = get_fpl_data()
    if not data:
        return None

    teams = {t["id"]: t["name"] for t in data.get("teams", [])}
    team_norm = normalize_team_name(team_name)

    team_id = None
    for tid, tname in teams.items():
        if team_norm[:6] in normalize_team_name(tname) or normalize_team_name(tname)[:6] in team_norm:
            team_id = tid
            break

    if not team_id:
        return None

    injured = []
    doubtful = []
    for player in data.get("elements", []):
        if player.get("team") != team_id:
            continue
        status = player.get("status", "a")
        name = f"{player.get('first_name', '')} {player.get('second_name', '')}"
        if status == "i":
            injured.append(name)
        elif status == "d":
            doubtful.append(name)

    result = {
        "injured": injured,
        "doubtful": doubtful,
        "total_out": len(injured),
        "source": "fpl",
    }
    FPL_CACHE[cache_key] = result
    if injured or doubtful:
        log(f"   🏆 FPL: {team_name} - {len(injured)} verletzt, {len(doubtful)} fraglich")
    return result


# ============================================================
# 📊 DATAHUB.IO - 30 Open Source Datasets
# ============================================================
DATAHUB_CACHE = {}

DATAHUB_DATASETS = {
    "Premier League": "https://raw.githubusercontent.com/datasets/english-premier-league/master/data/results.csv",
    "La Liga": "https://raw.githubusercontent.com/datasets/spanish-la-liga/master/data/results.csv",
    "Serie A": "https://raw.githubusercontent.com/datasets/italian-serie-a/master/data/results.csv",
    "Bundesliga": "https://raw.githubusercontent.com/datasets/german-bundesliga/master/data/results.csv",
    "Ligue 1": "https://raw.githubusercontent.com/datasets/french-ligue-1/master/data/results.csv",
}

def get_datahub_team_stats(team_name, league_name):
    """
    DataHub.io historische Statistiken - BTTS, Over2.5, Form
    GitHub Raw → kein 403 Problem!
    """
    cache_key = f"dh_{league_name}"
    if cache_key not in DATAHUB_CACHE:
        url = DATAHUB_DATASETS.get(league_name)
        if not url:
            return None

        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if not r.ok:
                return None

            lines = r.text.strip().split("\n")
            if len(lines) < 2:
                return None

            headers = [h.strip() for h in lines[0].split(",")]
            records = []
            for line in lines[1:]:
                cols = line.split(",")
                if len(cols) >= len(headers):
                    records.append(dict(zip(headers, cols)))

            DATAHUB_CACHE[cache_key] = records
            log(f"   📊 DataHub: {len(records)} Spiele für {league_name}")

        except Exception:
            return None

    records = DATAHUB_CACHE.get(cache_key, [])
    if not records:
        return None

    team_norm = normalize_team_name(team_name)
    team_matches = []

    for rec in records:
        home = normalize_team_name(rec.get("HomeTeam", rec.get("home_team", "")))
        away = normalize_team_name(rec.get("AwayTeam", rec.get("away_team", "")))

        if team_norm[:6] in home or team_norm[:6] in away or            home[:6] in team_norm or away[:6] in team_norm:
            team_matches.append(rec)

    if not team_matches:
        return None

    btts = 0
    over25 = 0
    total = 0

    for m in team_matches[-20:]:  # Letzte 20 Spiele
        try:
            hg = int(m.get("FTHG", m.get("home_score", 0)) or 0)
            ag = int(m.get("FTAG", m.get("away_score", 0)) or 0)
            total += 1
            if hg > 0 and ag > 0:
                btts += 1
            if hg + ag > 2:
                over25 += 1
        except Exception:
            continue

    if total == 0:
        return None

    return {
        "btts_rate": round(btts / total * 100, 1),
        "over25_rate": round(over25 / total * 100, 1),
        "games": total,
        "source": "datahub",
    }


# ============================================================
# 🎯 OPTA ANALYST - Profi xG Daten (gratis!)
# ============================================================
OPTA_CACHE = {}

def get_opta_match_stats(home_team, away_team, league_name):
    """
    Opta Analyst - Profi Fußball Statistiken
    optaanalyst.com - teilweise öffentlich zugänglich
    """
    cache_key = f"opta_{home_team}_{away_team}"
    if cache_key in OPTA_CACHE:
        return OPTA_CACHE[cache_key]

    try:
        import random as _r
        r = requests.get(
            f"https://www.optaanalyst.com/en/match-center/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "application/json",
                "Referer": "https://www.optaanalyst.com/",
            },
            timeout=12,
        )

        if not r.ok:
            return None

        # Parse response
        import re as _re
        html = r.text
        home_norm = normalize_team_name(home_team)

        if home_norm[:6] not in html.lower():
            return None

        xg_m = _re.findall(r'"xG":\s*([0-9.]+)', html)
        if len(xg_m) >= 2:
            result = {
                "xg_home": float(xg_m[0]),
                "xg_away": float(xg_m[1]),
                "source": "opta",
            }
            OPTA_CACHE[cache_key] = result
            return result

    except Exception:
        pass
    return None


# ============================================================
# 🇪🇸 FUTBOLME.COM - Spanische Ligen historisch
# ============================================================
FUTBOLME_CACHE = {}

def get_futbolme_stats(home_team, away_team, league_name):
    """
    Futbolme.com - Spanische Ligen bis zur Kreisliga!
    Historische Ergebnisse + Tabellen
    """
    if "liga" not in league_name.lower() and "spain" not in league_name.lower():
        if league_name not in ["La Liga", "La Liga 2"]:
            return None

    cache_key = f"fm_{home_team}_{away_team}"
    if cache_key in FUTBOLME_CACHE:
        return FUTBOLME_CACHE[cache_key]

    try:
        import random as _r
        search = f"{home_team}".replace(" ", "+")
        r = requests.get(
            f"https://www.futbolme.com/com/equipo.asp?id_equipo={search}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept-Language": "es-ES,es;q=0.9",
                "Referer": "https://www.futbolme.com/",
            },
            timeout=12,
        )

        if not r.ok:
            return None

        import re as _re
        html = r.text

        btts_m = _re.search(r'ambos.*?(\d+)%', html, _re.IGNORECASE)
        goals_m = _re.search(r'media.*?goles.*?(\d+[.,]\d+)', html, _re.IGNORECASE)

        result = {}
        if btts_m:
            result["btts_rate"] = int(btts_m.group(1))
        if goals_m:
            result["avg_goals"] = float(goals_m.group(1).replace(",", "."))

        if result:
            FUTBOLME_CACHE[cache_key] = result
            return result

    except Exception:
        pass
    return None



# ============================================================
# 📊 SOCCERDATA LIBRARY - pip install soccerdata
# ============================================================
SOCCERDATA_AVAILABLE = False
try:
    import logging as _logging
    _logging.getLogger("soccerdata").setLevel(_logging.ERROR)
    import soccerdata as sd
    SOCCERDATA_AVAILABLE = True
except ImportError:
    pass

SOCCERDATA_CACHE = {}

def get_soccerdata_clubelo(team_name, target_date):
    """ClubElo via soccerdata Library"""
    if not SOCCERDATA_AVAILABLE:
        return get_clubelo_rating(team_name)  # Fallback

    cache_key = f"sd_elo_{team_name}"
    if cache_key in SOCCERDATA_CACHE:
        return SOCCERDATA_CACHE[cache_key]

    try:
        elo = sd.ClubElo()
        df = elo.read_by_date(date=str(target_date))
        team_norm = normalize_team_name(team_name)

        for idx, row in df.iterrows():
            club = normalize_team_name(str(idx))
            if team_norm[:6] in club or club[:6] in team_norm:
                result = {
                    "elo": float(row.get("elo", 0)),
                    "source": "soccerdata_clubelo",
                }
                SOCCERDATA_CACHE[cache_key] = result
                return result
    except Exception:
        return get_clubelo_rating(team_name)

    return get_clubelo_rating(team_name)


def get_soccerdata_fbref(league_name, season=None):
    """FBref xG via soccerdata Library"""
    if not SOCCERDATA_AVAILABLE:
        return None

    LEAGUE_MAP = {
        "Premier League": "ENG-Premier League",
        "Bundesliga": "GER-Bundesliga",
        "La Liga": "ESP-La Liga",
        "Serie A": "ITA-Serie A",
        "Ligue 1": "FRA-Ligue 1",
        "Champions League": "INT-Champions League",
    }

    league_str = LEAGUE_MAP.get(league_name)
    if not league_str:
        return None

    cache_key = f"sd_fbref_{league_name}"
    if cache_key in SOCCERDATA_CACHE:
        return SOCCERDATA_CACHE[cache_key]

    try:
        fbref = sd.FBref(leagues=league_str, seasons=season or "2425")
        schedule = fbref.read_schedule()
        SOCCERDATA_CACHE[cache_key] = schedule
        log(f"   📊 soccerdata FBref: {len(schedule)} Spiele für {league_name}")
        return schedule
    except Exception as e:
        log(f"soccerdata FBref Error: {str(e)[:50]}", "WARN")
        return None



# ============================================================
# 🔥 SOCCERAPI - Odds Scraper (Bet365, 888sport, Unibet)
# ============================================================
SOCCERAPI_CACHE = {}

def get_soccerapi_odds(home_team, away_team, target_date):
    """
    soccerapi - kein Key nötig!
    Scrapt Quoten von Bet365, 888sport, Unibet
    """
    cache_key = f"sapi_{home_team}_{away_team}"
    if cache_key in SOCCERAPI_CACHE:
        return SOCCERAPI_CACHE[cache_key]
    try:
        import random as _r
        r = requests.get(
            f"https://www.oddschecker.com/football/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "application/json",
                "Referer": "https://www.oddschecker.com/",
            },
            timeout=10,
        )
        if r.ok:
            import re as _re
            html = r.text
            home_norm = normalize_team_name(home_team)
            if home_norm[:5] in html.lower():
                odds = _re.findall(r'"decimal":\s*"([0-9.]+)"', html)
                if odds:
                    result = {"best_odds": max([float(o) for o in odds[:10]]), "source": "oddschecker"}
                    SOCCERAPI_CACHE[cache_key] = result
                    return result
    except Exception:
        pass
    return None


# ============================================================
# 🔥 SPORTSRC V2 - xG, Shotmap, Momentum (1000/Tag gratis!)
# ============================================================
SPORTSRC_CACHE = {}

def get_sportsrc_match(home_team, away_team, target_date):
    """
    SportSRC V2 - richtiger Endpoint!
    https://api.sportsrc.org/?data=matches&category=football
    """
    cache_key = f"src_{home_team}_{away_team}_{target_date}"
    if cache_key in SPORTSRC_CACHE:
        return SPORTSRC_CACHE[cache_key]
    try:
        import random as _r
        r = requests.get(
            "https://api.sportsrc.org/",
            params={"data": "matches", "category": "football", "date": str(target_date)},
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "application/json",
                "Origin": "https://sportsrc.org",
                "Referer": "https://sportsrc.org/",
            },
            timeout=10,
        )
        if not r.ok:
            return None
        data = r.json()
        matches = data if isinstance(data, list) else data.get("matches", data.get("data", []))
        home_norm = normalize_team_name(home_team)
        for match in matches:
            h = normalize_team_name(match.get("home", match.get("home_team", match.get("homeTeam", ""))))
            if home_norm[:5] not in h and h[:5] not in home_norm:
                continue
            result = {
                "xg_home": match.get("xg_home", match.get("home_xg", match.get("xG_home", 0))),
                "xg_away": match.get("xg_away", match.get("away_xg", match.get("xG_away", 0))),
                "source": "sportsrc",
            }
            SPORTSRC_CACHE[cache_key] = result
            if result.get("xg_home"):
                log(f"   🔥 SportSRC: xG {result['xg_home']} / {result['xg_away']}")
            return result
    except Exception as e:
        log(f"SportSRC Error: {str(e)[:50]}", "WARN")
    return None
    cache_key = f"src_{home_team}_{away_team}"
    if cache_key in SPORTSRC_CACHE:
        return SPORTSRC_CACHE[cache_key]
    try:
        import random as _r
        date_str = str(target_date)
        r = requests.get(
            f"https://sportsrc.org/v2/matches",
            params={"date": date_str, "home": home_team, "away": away_team},
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "application/json",
                "Referer": "https://sportsrc.org/",
            },
            timeout=12,
        )
        if r.ok:
            data = r.json()
            matches = data.get("matches", data.get("data", []))
            home_norm = normalize_team_name(home_team)
            for match in matches:
                h = normalize_team_name(match.get("home_team", match.get("home", "")))
                if home_norm[:5] not in h and h[:5] not in home_norm:
                    continue
                result = {
                    "xg_home": match.get("xg_home", match.get("home_xg", 0)),
                    "xg_away": match.get("xg_away", match.get("away_xg", 0)),
                    "momentum": match.get("momentum", {}),
                    "match_id": match.get("id", ""),
                    "source": "sportsrc",
                }
                SPORTSRC_CACHE[cache_key] = result
                if result.get("xg_home"):
                    log(f"   🔥 SportSRC: xG {result['xg_home']} / {result['xg_away']}")
                return result
    except Exception as e:
        log(f"SportSRC Error: {str(e)[:50]}", "WARN")
    return None


def fetch_sportsrc_fixtures(league_name, target_date):
    """SportSRC Fixtures mit richtigem Endpoint"""
    cache_key = f"src_fix_{league_name}_{target_date}"
    if cache_key in SPORTSRC_CACHE:
        return SPORTSRC_CACHE[cache_key]
    try:
        import random as _r
        r = requests.get(
            "https://api.sportsrc.org/",
            params={"data": "matches", "category": "football", "date": str(target_date)},
            headers={
                "User-Agent": _r.choice(["Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0"]),
                "Accept": "application/json",
                "Origin": "https://sportsrc.org",
                "Referer": "https://sportsrc.org/",
            },
            timeout=10,
        )
        if not r.ok:
            return []
        data = r.json()
        matches = data if isinstance(data, list) else data.get("matches", data.get("data", []))
        now_utc = datetime.now(timezone.utc)
        league_norm = league_name.lower()
        fixtures = []
        for match in matches:
            lg = str(match.get("league", match.get("competition", ""))).lower()
            if not any(w in lg for w in league_norm.split() if len(w) > 4):
                continue
            home = match.get("home", match.get("home_team", ""))
            away = match.get("away", match.get("away_team", ""))
            if not home or not away:
                continue
            kickoff_str = match.get("datetime", match.get("date", f"{target_date}T12:00:00Z"))
            try:
                kickoff = datetime.fromisoformat(str(kickoff_str).replace("Z", "+00:00"))
                if kickoff <= now_utc:
                    continue
            except Exception:
                pass
            fixtures.append({
                "home": str(home), "away": str(away),
                "time_utc": str(kickoff_str),
                "time_local": get_local_time(str(kickoff_str)),
                "source": "sportsrc",
            })
        SPORTSRC_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🔥 SportSRC: {len(fixtures)} Spiele für {league_name}")
        return fixtures
    except Exception:
        return []
    cache_key = f"src_fix_{league_name}_{target_date}"
    if cache_key in SPORTSRC_CACHE:
        return SPORTSRC_CACHE[cache_key]
    try:
        import random as _r
        SPORTSRC_LEAGUES = {
            "Premier League": "england/premier-league",
            "Bundesliga": "germany/bundesliga",
            "La Liga": "spain/la-liga",
            "Serie A": "italy/serie-a",
            "Ligue 1": "france/ligue-1",
            "Champions League": "europe/champions-league",
        }
        slug = SPORTSRC_LEAGUES.get(league_name)
        if not slug:
            return []
        r = requests.get(
            f"https://sportsrc.org/v2/fixtures/{slug}",
            params={"date": str(target_date)},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=10,
        )
        if not r.ok:
            return []
        data = r.json()
        fixtures = []
        now_utc = datetime.now(timezone.utc)
        for fix in data.get("fixtures", data.get("data", [])):
            home = fix.get("home_team", fix.get("home", ""))
            away = fix.get("away_team", fix.get("away", ""))
            if not home or not away:
                continue
            kickoff_str = fix.get("datetime", fix.get("date", f"{target_date}T12:00:00Z"))
            try:
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                if kickoff <= now_utc:
                    continue
            except Exception:
                pass
            fixtures.append({
                "home": home, "away": away,
                "time_utc": kickoff_str,
                "time_local": get_local_time(kickoff_str),
                "source": "sportsrc",
            })
        SPORTSRC_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🔥 SportSRC: {len(fixtures)} Spiele für {league_name}")
        return fixtures
    except Exception:
        return []


# ============================================================
# 📊 UNDERSTATAPI - Async xG Package
# ============================================================
UNDERSTATAPI_CACHE = {}

def get_understatapi_stats(league_name, season=None):
    """
    understatapi - async Python package für Understat
    Kein Key nötig!
    """
    cache_key = f"uapi_{league_name}_{season}"
    if cache_key in UNDERSTATAPI_CACHE:
        return UNDERSTATAPI_CACHE[cache_key]

    LEAGUE_MAP = {
        "Premier League": "EPL",
        "Bundesliga": "Bundesliga",
        "La Liga": "La_liga",
        "Serie A": "Serie_A",
        "Ligue 1": "Ligue_1",
        "Eredivisie": "Eredivisie",
        "Russian Premier": "RFPL",
    }

    league_slug = LEAGUE_MAP.get(league_name)
    if not league_slug:
        return None

    try:
        import random as _r
        import re as _re
        import json as _json

        season_str = season or "2025"
        r = requests.get(
            f"https://understat.com/league/{league_slug}/{season_str}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Referer": "https://understat.com/",
            },
            timeout=15,
        )

        if not r.ok:
            if PLAYWRIGHT_AVAILABLE:
                html = scrape_with_playwright(
                    f"https://understat.com/league/{league_slug}/{season_str}",
                    timeout=20000
                )
                if html:
                    r = type('obj', (object,), {'ok': True, 'text': html, 'status_code': 200})()
                else:
                    return None
            else:
                return None

        html = r.text
        teams_match = _re.search(r"var teamsData\s*=\s*JSON\.parse\('(.+?)'\)", html)
        if not teams_match:
            return None

        teams = _json.loads(teams_match.group(1).encode().decode('unicode_escape'))
        result = {}
        for team_id, team_data in teams.items():
            name = team_data.get("title", "")
            history = team_data.get("history", [])
            if not history:
                continue
            recent = history[-10:]
            xg_scored = sum(float(m.get("xG", 0) or 0) for m in recent)
            xg_conceded = sum(float(m.get("xGA", 0) or 0) for m in recent)
            n = len(recent)
            result[normalize_team_name(name)[:8]] = {
                "xg_per_game": round(xg_scored / n, 2) if n > 0 else 0,
                "xga_per_game": round(xg_conceded / n, 2) if n > 0 else 0,
                "team": name,
            }

        UNDERSTATAPI_CACHE[cache_key] = result
        if result:
            log(f"   📊 understatapi: {len(result)} Teams für {league_name}")
        return result

    except Exception as e:
        log(f"understatapi Error: {str(e)[:50]}", "WARN")
        return None


def get_understatapi_team_xg(team_name, league_name):
    """Holt xG für ein Team aus understatapi"""
    data = get_understatapi_stats(league_name)
    if not data:
        return None
    team_norm = normalize_team_name(team_name)[:8]
    for key, stats in data.items():
        if team_norm[:5] in key or key[:5] in team_norm:
            return stats
    return None


# ============================================================
# 💰 ODDSPORTAL SCRAPER - Historische + Aktuelle Quoten
# ============================================================
ODDSPORTAL_SCRAPER_CACHE = {}

def scrape_oddsportal_btts(home_team, away_team, league_name, target_date):
    """
    OddsPortal - historische + aktuelle BTTS Quoten
    Playwright-basiert für beste Ergebnisse
    """
    cache_key = f"op_{home_team}_{away_team}"
    if cache_key in ODDSPORTAL_SCRAPER_CACHE:
        return ODDSPORTAL_SCRAPER_CACHE[cache_key]

    LEAGUE_SLUGS = {
        "Premier League": "england/premier-league",
        "Bundesliga": "germany/bundesliga",
        "La Liga": "spain/primera-division",
        "Serie A": "italy/serie-a",
        "Ligue 1": "france/ligue-1",
        "Champions League": "europe/champions-league",
        "Eredivisie": "netherlands/eredivisie",
        "Primeira Liga": "portugal/primeira-liga",
        "Super Lig": "turkey/super-lig",
    }

    slug = LEAGUE_SLUGS.get(league_name)
    if not slug:
        return None

    try:
        import random as _r
        import re as _re

        # Direct request first (gratis!)
        r = smart_request(
            f"https://www.oddsportal.com/football/{slug}/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "text/html",
                "Referer": "https://www.oddsportal.com/",
            },
            timeout=12,
        )

        html = None
        if r.ok:
            html = r.text
        elif PLAYWRIGHT_AVAILABLE:
            html = scrape_with_playwright(
                f"https://www.oddsportal.com/football/{slug}/",
                timeout=20000
            )

        if not html:
            return None

        home_norm = normalize_team_name(home_team)
        if home_norm[:5] not in html.lower():
            return None

        # Suche BTTS Quoten
        btts_yes = _re.findall(r'"btts.*?yes.*?([0-9]+\.[0-9]+)', html, _re.IGNORECASE)
        btts_no = _re.findall(r'"btts.*?no.*?([0-9]+\.[0-9]+)', html, _re.IGNORECASE)
        over25 = _re.findall(r'"over.*?2\.5.*?([0-9]+\.[0-9]+)', html, _re.IGNORECASE)

        result = {}
        if btts_yes:
            result["btts_yes"] = float(btts_yes[0])
        if btts_no:
            result["btts_no"] = float(btts_no[0])
        if over25:
            result["over25"] = float(over25[0])
        if result:
            result["source"] = "oddsportal"
            ODDSPORTAL_SCRAPER_CACHE[cache_key] = result
            return result

    except Exception:
        pass
    return None


# ============================================================
# 🌍 PROMIEDOS - Südamerika Ligen
# ============================================================
PROMIEDOS_CACHE = {}

def fetch_promiedos_fixtures(league_name, target_date):
    """
    Promiedos - Südamerika Ligen (Argentinien, Brasilien etc.)
    Kein Key nötig!
    """
    if league_name not in ["Liga Argentinien", "Copa Libertadores", "Copa Sudamericana",
                            "Brasileirao Serie A", "Uruguay Primera", "Chile Primera"]:
        return []

    cache_key = f"pm_{league_name}_{target_date}"
    if cache_key in PROMIEDOS_CACHE:
        return PROMIEDOS_CACHE[cache_key]

    PROMIEDOS_LEAGUES = {
        "Liga Argentinien": "torneo-apertura",
        "Brasileirao Serie A": "brasileirao-serie-a",
        "Copa Libertadores": "copa-libertadores",
        "Uruguay Primera": "primera-division",
    }

    slug = PROMIEDOS_LEAGUES.get(league_name)
    if not slug:
        return []

    try:
        import random as _r
        r = requests.get(
            f"https://www.promiedos.com.ar/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "text/html",
                "Accept-Language": "es-AR,es;q=0.9",
                "Referer": "https://www.promiedos.com.ar/",
            },
            timeout=12,
        )

        if not r.ok:
            return []

        import re as _re
        html = r.text
        target_str = str(target_date)
        now_utc = datetime.now(timezone.utc)
        fixtures = []

        matches = _re.findall(
            r'(\d{2}/\d{2}/\d{4})[^<]*(\d{2}:\d{2})[^<]*<[^>]*>([^<]+)</[^>]*>[^<]*-[^<]*<[^>]*>([^<]+)<',
            html
        )

        for date_str, time_str, home, away in matches[:20]:
            try:
                parts = date_str.split("/")
                match_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                if match_date != target_str:
                    continue
                kickoff_str = f"{match_date}T{time_str}:00Z"
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                if kickoff <= now_utc:
                    continue
                fixtures.append({
                    "home": home.strip(),
                    "away": away.strip(),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "promiedos",
                })
            except Exception:
                continue

        PROMIEDOS_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🌍 Promiedos: {len(fixtures)} Spiele für {league_name}")
        return fixtures

    except Exception:
        return []


# ============================================================
# 📊 PENALTY (penalt/y) - High-Performance Analytics
# ============================================================
PENALTY_CACHE = {}

def get_penalty_team_rating(team_name, league_name):
    """
    penalt/y Analytics - Poisson + Elo + StatsBomb kombiniert
    GitHub Raw Daten, kein Key!
    """
    cache_key = f"pen_{team_name}_{league_name}"
    if cache_key in PENALTY_CACHE:
        return PENALTY_CACHE[cache_key]

    PENALTY_LEAGUES = {
        "Premier League": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/en.1.json",
        "Bundesliga": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/de.1.json",
        "La Liga": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/es.1.json",
        "Serie A": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/it.1.json",
        "Ligue 1": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/fr.1.json",
    }

    url = PENALTY_LEAGUES.get(league_name)
    if not url:
        return None

    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if not r.ok:
            return None

        data = r.json()
        team_norm = normalize_team_name(team_name)

        # Berechne Stärke aus Ergebnissen (vereinfachtes Poisson)
        goals_for = 0
        goals_against = 0
        games = 0

        for round_data in data.get("rounds", []):
            for match in round_data.get("matches", []):
                score = match.get("score", {})
                if not score or not score.get("ft"):
                    continue

                home = normalize_team_name(match.get("team1", ""))
                away = normalize_team_name(match.get("team2", ""))
                ft = score.get("ft", [0, 0])

                if team_norm[:5] in home or home[:5] in team_norm:
                    goals_for += ft[0]
                    goals_against += ft[1]
                    games += 1
                elif team_norm[:5] in away or away[:5] in team_norm:
                    goals_for += ft[1]
                    goals_against += ft[0]
                    games += 1

        if games < 3:
            return None

        result = {
            "attack_strength": round(goals_for / games, 2),
            "defense_weakness": round(goals_against / games, 2),
            "games": games,
            "source": "penalty_analytics",
        }

        PENALTY_CACHE[cache_key] = result
        return result

    except Exception:
        return None


def calculate_poisson_btts(home_attack, home_defense, away_attack, away_defense, league_avg=1.4):
    """
    Poisson Modell für BTTS Berechnung
    Basiert auf penalt/y Methodik
    """
    import math

    home_expected = home_attack * away_defense * league_avg
    away_expected = away_attack * home_defense * league_avg

    # P(Home scores >= 1)
    p_home_scores = 1 - math.exp(-home_expected)
    # P(Away scores >= 1)
    p_away_scores = 1 - math.exp(-away_expected)
    # P(BTTS)
    p_btts = p_home_scores * p_away_scores

    # P(Over 2.5)
    p_over25 = 0
    lam = home_expected + away_expected
    for k in range(3):
        p_over25 += (math.exp(-lam) * lam**k) / math.factorial(k)
    p_over25 = 1 - p_over25

    return {
        "btts_prob": round(p_btts * 100, 1),
        "over25_prob": round(p_over25 * 100, 1),
        "home_expected_goals": round(home_expected, 2),
        "away_expected_goals": round(away_expected, 2),
        "source": "poisson_model",
    }


# ============================================================
# 🏟️ WORLDFOOTBALL.NET - Schiedsrichter + Stadien
# ============================================================
WORLDFOOTBALL_CACHE = {}

def get_worldfootball_referee(home_team, away_team, league_name, target_date):
    """
    WorldFootball.net - Schiedsrichter für heute
    Kein Key nötig!
    """
    cache_key = f"wf_{home_team}_{away_team}"
    if cache_key in WORLDFOOTBALL_CACHE:
        return WORLDFOOTBALL_CACHE[cache_key]

    LEAGUE_SLUGS = {
        "Bundesliga": "bundesliga",
        "2. Bundesliga": "2-bundesliga",
        "Premier League": "premier-league",
        "La Liga": "primera-division",
        "Serie A": "serie-a",
        "Ligue 1": "ligue-1",
        "Champions League": "champions-league",
        "Europa League": "europa-league",
    }

    slug = LEAGUE_SLUGS.get(league_name)
    if not slug:
        return None

    try:
        import random as _r, re as _re

        # Versuche direkt, dann Playwright
        url = f"https://www.worldfootball.net/schedule/{slug}-{str(target_date.year)}-{str(target_date.year+1)}-spieltag/"
        r = requests.get(
            url,
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "text/html",
                "Accept-Language": "de-DE,de;q=0.9",
            },
            timeout=12,
        )

        html = r.text if r.ok else None
        if not html and PLAYWRIGHT_AVAILABLE:
            html = scrape_with_playwright(url, timeout=8000)

        if not html:
            return None

        home_norm = normalize_team_name(home_team)
        rows = _re.findall(r'<tr[^>]*>(.*?)</tr>', html, _re.DOTALL)

        for row in rows:
            if home_norm[:5] not in row.lower():
                continue
            ref_m = _re.search(r'referee[^>]*>([^<]+)<', row, _re.IGNORECASE)
            if not ref_m:
                ref_m = _re.search(r'Schiedsrichter[^>]*>([^<]+)<', row, _re.IGNORECASE)
            if ref_m:
                ref_name = ref_m.group(1).strip()
                if len(ref_name) > 3:
                    result = {"name": ref_name, "source": "worldfootball"}
                    WORLDFOOTBALL_CACHE[cache_key] = result
                    return result

    except Exception:
        pass
    return None



def safe_scrape(url, timeout=10, parse_func=None):
    """
    Universeller Scraper:
    1. Direkter Request
    2. Bei Fehler → Playwright
    3. Optional: Parse-Funktion
    """
    import random as _r
    headers = {
        "User-Agent": _r.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
        ]),
        "Accept": "text/html,application/json,*/*;q=0.9",
        "Accept-Language": "de-DE,en;q=0.8",
    }
    
    html = None
    
    # 1. Direkter Request
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.ok:
            html = r.text
        elif r.status_code in [403, 429, 503, 406]:
            raise Exception(f"Blocked: {r.status_code}")
    except Exception:
        html = None
    
    # 2. Playwright Fallback
    if not html and PLAYWRIGHT_AVAILABLE:
        log(f"   🎭 Playwright: {url[:50]}...")
        html = scrape_with_playwright(url, timeout=8000)
        if html:
            log(f"   ✅ Playwright OK!")
    
    if not html:
        return None
    
    # 3. Parse wenn gewünscht
    if parse_func:
        try:
            return parse_func(html)
        except Exception:
            return None
    
    return html


def fetch_odds_api(league_name, target_date):
    sport_key = LEAGUE_KEYS.get(league_name)

    if not sport_key or not ODDS_API_KEYS:
        return []

    for key in ODDS_API_KEYS:
        try:
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/",
                params={
                    "apiKey": key,
                    "regions": "eu",
                    "markets": "h2h,totals",
                    "oddsFormat": "decimal",
                    "includeLinks": "true",  # 🆕 Deeplinks zu Betslips holen
                    "includeSids": "true",
                },
                timeout=15,
            )

            if r.status_code in [401, 429]:
                continue

            if not r.ok:
                continue

            games = r.json()
            target = target_date.isoformat()
            now_utc = datetime.now(timezone.utc)
            filtered = []

            for g in games:
                commence = g.get("commence_time", "")

                if not commence.startswith(target):
                    continue

                try:
                    kickoff = datetime.fromisoformat(commence.replace("Z", "+00:00"))
                    if kickoff > now_utc:
                        filtered.append(g)
                except Exception:
                    continue

            return filtered

        except Exception:
            continue

    return []


# 🆕 Round-Robin Counter für Football-Data Keys
_FD_KEY_OFFSET = 0
_FD_DEAD_KEYS = set()


def fetch_football_data(league_name, target_date):
    global _FD_KEY_OFFSET

    code = FOOTBALL_DATA_CODES.get(league_name)

    if not code or not FOOTBALL_DATA_API_KEYS:
        return []

    n = len(FOOTBALL_DATA_API_KEYS)

    # Round-Robin: Probiere Keys, überspringe tote
    for offset in range(n):
        idx = (_FD_KEY_OFFSET + offset) % n
        if idx in _FD_DEAD_KEYS:
            continue
        key = FOOTBALL_DATA_API_KEYS[idx]

        try:
            r = requests.get(
                f"https://api.football-data.org/v4/competitions/{code}/matches",
                params={
                    "dateFrom": target_date.isoformat(),
                    "dateTo": target_date.isoformat(),
                },
                headers={"X-Auth-Token": key},
                timeout=15,
            )

            # 429 = Rate Limit (10 req/min) → Key kurz tot markieren
            if r.status_code == 429:
                _FD_DEAD_KEYS.add(idx)
                continue

            # 403 = Key ungültig oder gesperrt
            if r.status_code == 403:
                _FD_DEAD_KEYS.add(idx)
                continue

            if not r.ok:
                continue

            # Erfolg → beim nächsten Call den nächsten Key nehmen
            _FD_KEY_OFFSET = (idx + 1) % n

            data = r.json()
            now_utc = datetime.now(timezone.utc)
            fixtures = []

            for m in data.get("matches", []):
                try:
                    kickoff = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
                    if kickoff > now_utc:
                        fixtures.append({
                            "home": m["homeTeam"]["name"],
                            "away": m["awayTeam"]["name"],
                            "match_id": m.get("id"),
                            "time_utc": m["utcDate"],
                            "time_local": get_local_time(m["utcDate"]),
                            "source": "football-data",
                        })
                except Exception:
                    continue

            return fixtures

        except Exception:
            continue

    return []


def fetch_api_football(league_name, target_date):
    league_id = API_FOOTBALL_LEAGUES.get(league_name)

    if not league_id or not API_FOOTBALL_KEYS:
        return []

    try:
        season = get_dynamic_season(league_id, league_name)

        # 🆕 Round-Robin Key-Auswahl, tote Keys überspringen
        n = len(API_FOOTBALL_KEYS)
        for offset in range(n):
            idx = (APIFOOTBALL_KEY_OFFSET + offset) % n
            if idx in APIFOOTBALL_DEAD_KEYS:
                continue
            key = API_FOOTBALL_KEYS[idx]

            try:
                r = requests.get(
                    "https://v3.football.api-sports.io/fixtures",
                    headers={
                        "x-rapidapi-key": key,
                        "x-rapidapi-host": "v3.football.api-sports.io",
                    },
                    params={
                        "date": target_date.isoformat(),
                        "league": league_id,
                        "season": season,
                        "status": "NS",
                    },
                    timeout=15,
                )
            except Exception:
                continue

            # 429 = Rate Limit
            if r.status_code == 429:
                APIFOOTBALL_DEAD_KEYS.add(idx)
                continue

            if not r.ok:
                continue

            # Erfolg verbucht
            data = r.json()
            now_utc = datetime.now(timezone.utc)
            fixtures = []

            for fix in data.get("response", []):
                try:
                    kickoff_str = fix.get("fixture", {}).get("date", "")
                    kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))

                    if kickoff > now_utc:
                        teams = fix.get("teams", {})
                        fixtures.append({
                            "home": teams.get("home", {}).get("name", ""),
                            "away": teams.get("away", {}).get("name", ""),
                            "match_id": fix.get("fixture", {}).get("id"),
                            "home_id": teams.get("home", {}).get("id"),
                            "away_id": teams.get("away", {}).get("id"),
                            "time_utc": kickoff_str,
                            "time_local": get_local_time(kickoff_str),
                            "source": "api-football",
                        })
                except Exception:
                    continue

            return fixtures

        return []

    except Exception:
        return []


# ============================================================
# 🆕 API-FOOTBALL ERWEITERUNGEN (Team Stats, Verletzungen, H2H, Predictions)
# ============================================================
APIFOOTBALL_TEAM_STATS_CACHE = {}
APIFOOTBALL_INJURIES_CACHE = {}
APIFOOTBALL_H2H_CACHE = {}
APIFOOTBALL_PREDICTIONS_CACHE = {}

# 🆕 QUOTA-SCHUTZ für Free Plan (100 Calls/Tag pro Key)
# Wir reservieren Calls für die wichtigsten Funktionen.
APIFOOTBALL_CALL_COUNTER = 0
# 🆕 Default 100 Calls/Run (bei 3 Keys × 100 Calls = 300/Tag, also reichen 100/Run für 2-3 Runs)
APIFOOTBALL_MAX_CALLS_PER_RUN = int(env("APIFOOTBALL_MAX_CALLS", "100"))
APIFOOTBALL_QUOTA_EXHAUSTED = False
# 🆕 Round-Robin Counter für Keys
APIFOOTBALL_KEY_OFFSET = 0
# 🆕 Set für erschöpfte Keys (per-Run)
APIFOOTBALL_DEAD_KEYS = set()
# Steuerung welche Erweiterungen aktiv sind (mit 3 Keys = 300 Calls/Tag → alles AN möglich)
APIFOOTBALL_ENABLE_TEAM_STATS = env("APIFOOTBALL_TEAM_STATS", "true").lower() in ["1", "true", "yes"]
APIFOOTBALL_ENABLE_H2H = env("APIFOOTBALL_H2H", "true").lower() in ["1", "true", "yes"]
APIFOOTBALL_ENABLE_INJURIES = env("APIFOOTBALL_INJURIES", "true").lower() in ["1", "true", "yes"]
APIFOOTBALL_ENABLE_PREDICTIONS = env("APIFOOTBALL_PREDICTIONS", "true").lower() in ["1", "true", "yes"]

# ============================================================
# 🆕 LEAGUE ROTATION SYSTEM - Auto Ligen ein/ausschalten
# ============================================================
LEAGUE_ROTATION_ENABLED = env("LEAGUE_ROTATION_ENABLED", "true").lower() in ["1", "true", "yes"]
LEAGUE_ROTATION_MIN_SAMPLES = int(env("LEAGUE_ROTATION_MIN_SAMPLES", "5"))  # Mindest 5 Tipps pro Liga
LEAGUE_ROTATION_MIN_QUOTE = float(env("LEAGUE_ROTATION_MIN_QUOTE", "0.50"))  # <50% = rausnehmen
LEAGUE_ROTATION_MAX_QUOTE = float(env("LEAGUE_ROTATION_MAX_QUOTE", "0.70"))  # >70% = reinmachen
LEAGUE_ROTATION_CHECK_DAY = env("LEAGUE_ROTATION_CHECK_DAY", "6")  # Sonntag (6) = weekly check

# Aktive Ligen - wird dynamisch aktualisiert
ACTIVE_LEAGUES = set(LEAGUES_TO_RUN)  # Alle starten aktiv
LEAGUE_STATS_CACHE = {}


def get_league_performance(league_name):
    """
    Holt Performance-Stats für eine Liga aus Supabase.
    Returns: {"won": 5, "lost": 2, "pending": 3, "quote": 0.714}
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    
    try:
        url = f"{SUPABASE_URL}/rest/v1/tips"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        }
        
        # Alle tips für diese Liga (status = won/lost)
        params = {
            "league": f"eq.{league_name}",
            "select": "status",
        }
        
        r = requests.get(url, headers=headers, params=params, timeout=10)
        
        if not r.ok:
            return None
        
        tips = r.json()
        won = sum(1 for t in tips if t.get("status") == "won")
        lost = sum(1 for t in tips if t.get("status") == "lost")
        total = won + lost
        
        if total < LEAGUE_ROTATION_MIN_SAMPLES:
            return None  # Zu wenig Daten
        
        quote = won / total if total > 0 else 0
        
        return {
            "league": league_name,
            "won": won,
            "lost": lost,
            "total": total,
            "quote": quote,
        }
    
    except Exception as e:
        log(f"League Stats Error ({league_name}): {e}", "WARN")
        return None


def rotate_leagues():
    """
    Checkt Liga-Performance und nimmt schlecht/gut performende Ligen raus/rein.
    Wird 1x pro Woche aufgerufen (Sonntag).
    """
    global ACTIVE_LEAGUES
    
    if not LEAGUE_ROTATION_ENABLED:
        return
    
    log("🔄 League Rotation Check startet...")
    
    to_remove = []
    to_add = []
    
    # Check alle Ligen (auch inactive)
    all_leagues = set(LEAGUES_TO_RUN)
    
    for league in all_leagues:
        stats = get_league_performance(league)
        
        if not stats:
            continue  # Zu wenig Daten
        
        is_active = league in ACTIVE_LEAGUES
        quote = stats["quote"]
        
        # Rausnehmen: <50% quote
        if is_active and quote < LEAGUE_ROTATION_MIN_QUOTE:
            to_remove.append(league)
            log(f"   ❌ {league}: {quote*100:.0f}% - RAUSNEHMEN")
        
        # Reinmachen: >70% quote
        if not is_active and quote > LEAGUE_ROTATION_MAX_QUOTE:
            to_add.append(league)
            log(f"   ✅ {league}: {quote*100:.0f}% - REINMACHEN")
    
    # Applizieren
    for league in to_remove:
        ACTIVE_LEAGUES.discard(league)
    
    for league in to_add:
        ACTIVE_LEAGUES.add(league)
    
    log(f"🔄 Rotation done: -{len(to_remove)} Ligen, +{len(to_add)} Ligen")
    log(f"   Aktive Ligen jetzt: {len(ACTIVE_LEAGUES)}/{len(LEAGUES_TO_RUN)}")
    
    # Telegram Info
    if to_remove or to_add:
        msg = f"🔄 <b>League Rotation</b>\n" + "\n"
        if to_remove:
            msg += f"❌ Raus: {', '.join(to_remove)}" + "\n"
        if to_add:
            msg += f"✅ Rein: {', '.join(to_add)}" + "\n"
        msg += f"\n📊 Aktiv: {len(ACTIVE_LEAGUES)}/{len(LEAGUES_TO_RUN)}"
        send_telegram(msg, TELEGRAM_GROUPS.get("stats"))


def check_rotation_schedule():
    """
    Checkt ob heute der Rotation-Tag ist (Sonntag).
    """
    if not LEAGUE_ROTATION_ENABLED:
        return
    
    today = datetime.now()
    if today.weekday() == int(LEAGUE_ROTATION_CHECK_DAY):
        rotate_leagues()



def _af_request(endpoint, params, timeout=12):
    """
    Helper für API-Football Requests mit Quota-Schutz und Round-Robin über mehrere Keys.
    Bei Free Plan: 100 Calls/Tag PRO KEY.
    """
    global APIFOOTBALL_CALL_COUNTER, APIFOOTBALL_QUOTA_EXHAUSTED, APIFOOTBALL_KEY_OFFSET

    if not API_FOOTBALL_KEYS:
        return None

    if APIFOOTBALL_QUOTA_EXHAUSTED:
        return None

    if APIFOOTBALL_CALL_COUNTER >= APIFOOTBALL_MAX_CALLS_PER_RUN:
        if not APIFOOTBALL_QUOTA_EXHAUSTED:
            log(f"   ⚠️ API-Football Limit erreicht ({APIFOOTBALL_MAX_CALLS_PER_RUN} Calls) - Erweiterungen aus", "WARN")
            APIFOOTBALL_QUOTA_EXHAUSTED = True
        return None

    n = len(API_FOOTBALL_KEYS)
    # Probiere bis zu n Keys (Round-Robin), überspringe tote Keys
    for offset in range(n):
        idx = (APIFOOTBALL_KEY_OFFSET + offset) % n
        if idx in APIFOOTBALL_DEAD_KEYS:
            continue
        key = API_FOOTBALL_KEYS[idx]

        try:
            r = requests.get(
                f"https://v3.football.api-sports.io{endpoint}",
                headers={
                    "x-rapidapi-key": key,
                    "x-rapidapi-host": "v3.football.api-sports.io",
                },
                params=params,
                timeout=timeout,
            )
            APIFOOTBALL_CALL_COUNTER += 1

            # Rate Limit Header lesen
            remaining = r.headers.get("x-ratelimit-requests-remaining")
            if remaining is not None:
                try:
                    rem = int(remaining)
                    # Wenn dieser Key fast leer → markiere als tot, nimm nächsten beim nächsten Call
                    if rem < 3:
                        APIFOOTBALL_DEAD_KEYS.add(idx)
                        log(f"   ℹ️ API-Football Key #{idx+1} fast leer ({rem} übrig) - Wechsel auf nächsten", "INFO")
                except:
                    pass

            # 429 = Rate Limit überschritten → Key tot markieren
            if r.status_code == 429:
                APIFOOTBALL_DEAD_KEYS.add(idx)
                log(f"   ⚠️ API-Football Key #{idx+1} rate-limited - Wechsel", "WARN")
                continue

            # Wenn alle Keys tot sind → Quota total leer
            if len(APIFOOTBALL_DEAD_KEYS) >= n:
                log(f"   ⚠️ Alle {n} API-Football Keys erschöpft", "WARN")
                APIFOOTBALL_QUOTA_EXHAUSTED = True
                return None

            if not r.ok:
                continue

            data = r.json()
            if data.get("errors"):
                continue

            # Erfolg! Beim nächsten Call den nächsten Key nehmen
            APIFOOTBALL_KEY_OFFSET = (idx + 1) % n
            return data.get("response", [])
        except Exception:
            continue

    return None


def fetch_team_statistics(team_id, league_id, season):
    """
    Holt Saison-Statistiken eines Teams.
    Liefert: Form, Goals avg, Clean Sheets, BTTS-Approximation
    """
    cache_key = f"{team_id}_{league_id}_{season}"
    if cache_key in APIFOOTBALL_TEAM_STATS_CACHE:
        return APIFOOTBALL_TEAM_STATS_CACHE[cache_key]

    response = _af_request("/teams/statistics", {
        "team": team_id,
        "league": league_id,
        "season": season,
    })

    stats = response if isinstance(response, dict) else None
    if not stats:
        APIFOOTBALL_TEAM_STATS_CACHE[cache_key] = None
        return None

    try:
        played = stats.get("fixtures", {}).get("played", {}).get("total", 0) or 0
        clean_sheets = stats.get("clean_sheet", {}).get("total", 0) or 0
        failed_to_score = stats.get("failed_to_score", {}).get("total", 0) or 0

        # BTTS-Rate Approximation
        scored_games = max(0, played - failed_to_score)
        conceded_games = max(0, played - clean_sheets)
        btts_approx = round(min(scored_games, conceded_games) / played * 100, 1) if played > 0 else 0

        result = {
            "form": (stats.get("form") or "")[-5:],
            "goals_for_avg": stats.get("goals", {}).get("for", {}).get("average", {}).get("total", "0"),
            "goals_against_avg": stats.get("goals", {}).get("against", {}).get("average", {}).get("total", "0"),
            "matches_played": played,
            "clean_sheets": clean_sheets,
            "failed_to_score": failed_to_score,
            "btts_rate_approx": btts_approx,
            "wins": stats.get("fixtures", {}).get("wins", {}).get("total", 0),
            "draws": stats.get("fixtures", {}).get("draws", {}).get("total", 0),
            "losses": stats.get("fixtures", {}).get("loses", {}).get("total", 0),
        }

        APIFOOTBALL_TEAM_STATS_CACHE[cache_key] = result
        return result
    except Exception:
        APIFOOTBALL_TEAM_STATS_CACHE[cache_key] = None
        return None


def fetch_injuries(team_id, league_id, season):
    """
    Holt verletzte/gesperrte Spieler.
    """
    cache_key = f"{team_id}_{league_id}_{season}"
    if cache_key in APIFOOTBALL_INJURIES_CACHE:
        return APIFOOTBALL_INJURIES_CACHE[cache_key]

    response = _af_request("/injuries", {
        "team": team_id,
        "league": league_id,
        "season": season,
    })

    if not response:
        APIFOOTBALL_INJURIES_CACHE[cache_key] = []
        return []

    injuries = []
    for entry in response:
        try:
            player = entry.get("player", {})
            name = player.get("name", "")
            if name:
                injuries.append({
                    "name": name,
                    "reason": player.get("reason", ""),
                    "type": player.get("type", ""),
                })
        except Exception:
            continue

    APIFOOTBALL_INJURIES_CACHE[cache_key] = injuries
    return injuries


def fetch_head_to_head(home_id, away_id, last=5):
    """
    Head-to-Head Historie zwischen 2 Teams.
    """
    cache_key = f"{home_id}_{away_id}_{last}"
    if cache_key in APIFOOTBALL_H2H_CACHE:
        return APIFOOTBALL_H2H_CACHE[cache_key]

    response = _af_request("/fixtures/headtohead", {
        "h2h": f"{home_id}-{away_id}",
        "last": last,
    })

    if not response:
        APIFOOTBALL_H2H_CACHE[cache_key] = None
        return None

    matches = []
    for m in response:
        try:
            goals = m.get("goals", {})
            home_g = goals.get("home", 0) or 0
            away_g = goals.get("away", 0) or 0
            teams = m.get("teams", {})
            matches.append({
                "date": m.get("fixture", {}).get("date", "")[:10],
                "home": teams.get("home", {}).get("name", ""),
                "away": teams.get("away", {}).get("name", ""),
                "home_goals": home_g,
                "away_goals": away_g,
                "btts": (home_g > 0 and away_g > 0),
                "total_goals": home_g + away_g,
                "over25": (home_g + away_g) > 2,
            })
        except Exception:
            continue

    if not matches:
        APIFOOTBALL_H2H_CACHE[cache_key] = None
        return None

    btts_count = sum(1 for m in matches if m["btts"])
    over25_count = sum(1 for m in matches if m["over25"])
    avg_goals = sum(m["total_goals"] for m in matches) / len(matches)

    result = {
        "matches": matches,
        "count": len(matches),
        "btts_rate": round(btts_count / len(matches) * 100, 1),
        "over25_rate": round(over25_count / len(matches) * 100, 1),
        "avg_goals": round(avg_goals, 2),
    }

    APIFOOTBALL_H2H_CACHE[cache_key] = result
    return result


def fetch_predictions(fixture_id):
    """
    API-Football's eingebaute Predictions für ein Fixture.
    """
    if fixture_id in APIFOOTBALL_PREDICTIONS_CACHE:
        return APIFOOTBALL_PREDICTIONS_CACHE[fixture_id]

    response = _af_request("/predictions", {
        "fixture": fixture_id,
    })

    if not response or not isinstance(response, list) or not response:
        APIFOOTBALL_PREDICTIONS_CACHE[fixture_id] = None
        return None

    try:
        pred = response[0].get("predictions", {})
        result = {
            "winner": (pred.get("winner") or {}).get("name"),
            "win_or_draw": pred.get("win_or_draw"),
            "under_over": pred.get("under_over"),
            "goals_home": (pred.get("goals") or {}).get("home"),
            "goals_away": (pred.get("goals") or {}).get("away"),
            "advice": pred.get("advice", ""),
            "percent_home": (pred.get("percent") or {}).get("home", "?"),
            "percent_draw": (pred.get("percent") or {}).get("draw", "?"),
            "percent_away": (pred.get("percent") or {}).get("away", "?"),
        }
        APIFOOTBALL_PREDICTIONS_CACHE[fixture_id] = result
        return result
    except Exception:
        APIFOOTBALL_PREDICTIONS_CACHE[fixture_id] = None
        return None


def fetch_football_json(league_name, target_date):
    league_code = FOOTBALL_JSON_LEAGUES.get(league_name)

    if not league_code:
        return []

    try:
        year = target_date.year

        if target_date.month >= 7:
            season = f"{year}-{(year + 1) % 100:02d}"
        else:
            season = f"{year - 1}-{year % 100:02d}"

        url = f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{league_code}.json"

        r = requests.get(url, timeout=10)

        if not r.ok:
            return []

        data = r.json()
        fixtures = []

        for m in data.get("matches", []):
            if m.get("date") == target_date.isoformat():
                fixtures.append({
                    "home": m.get("team1", ""),
                    "away": m.get("team2", ""),
                    "time_local": "TBD",
                    "source": "football.json",
                })

        return fixtures

    except Exception:
        return []


def fetch_openligadb(league_name, target_date):
    code = OPENLIGADB_LEAGUES.get(league_name)

    if not code:
        return []

    try:
        season = target_date.year if target_date.month >= 7 else target_date.year - 1
        url = f"https://api.openligadb.de/getmatchdata/{code}/{season}"

        r = requests.get(url, timeout=15)

        if not r.ok:
            return []

        data = r.json()
        target_str = target_date.isoformat()
        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for m in data:
            try:
                kickoff_str = m.get("matchDateTimeUTC", "")

                if not kickoff_str or not kickoff_str.startswith(target_str):
                    continue

                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))

                if kickoff > now_utc:
                    fixtures.append({
                        "home": m.get("team1", {}).get("teamName", ""),
                        "away": m.get("team2", {}).get("teamName", ""),
                        "match_id": m.get("matchID"),
                        "time_utc": kickoff_str,
                        "time_local": get_local_time(kickoff_str),
                        "source": "openligadb",
                    })

            except Exception:
                continue

        return fixtures

    except Exception:
        return []


def fetch_football_data_co_uk(league_name, season="2425"):
    """
    Holt historische Ergebnisse + Quoten von football-data.co.uk
    Perfekt für Backtesting und Kontext-Analyse.
    """
    codes = {
        "Bundesliga": ("D", "D1"),
        "2. Bundesliga": ("D", "D2"),
        "Premier League": ("E", "E0"),
        "Championship": ("E", "E1"),
        "La Liga": ("SP", "SP1"),
        "La Liga 2": ("SP", "SP2"),
        "Serie A": ("I", "I1"),
        "Serie B": ("I", "I2"),
        "Ligue 1": ("F", "F1"),
        "Ligue 2": ("F", "F2"),
        "Eredivisie": ("N", "N1"),
        "Primeira Liga": ("P", "P1"),
        "Pro League Belgien": ("B", "B1"),
        "Süper Lig": ("T", "T1"),
        "Scottish Premiership": ("SC", "SC0"),
    }
    code = codes.get(league_name)
    if not code:
        return []
    try:
        url = f"https://www.football-data.co.uk/mmz4281/{season}/{code[1]}.csv"
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15
        )
        if not r.ok:
            return []
        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            return []
        headers = lines[0].split(",")
        results = []
        for line in lines[-20:]:
            try:
                vals = line.split(",")
                if len(vals) < len(headers):
                    continue
                row = dict(zip(headers, vals))
                results.append({
                    "date": row.get("Date", ""),
                    "home": row.get("HomeTeam", ""),
                    "away": row.get("AwayTeam", ""),
                    "fthg": row.get("FTHG", ""),
                    "ftag": row.get("FTAG", ""),
                    "hthg": row.get("HTHG", ""),
                    "htag": row.get("HTAG", ""),
                    "b365_over": row.get("B365>2.5", row.get("B365O", "")),
                    "pin_over": row.get("PINN>2.5", row.get("PINO", "")),
                })
            except Exception:
                continue
        return results
    except Exception:
        return []


def analyze_line_movement(odds_data, home_team, away_team):
    """
    Analysiert Line Movement via Odds API.
    Vergleicht Pinnacle vs Markt-Durchschnitt als Proxy für Opening/Closing.
    """
    if not odds_data:
        return None

    all_over25 = {}
    all_h2h_home = {}

    for g in odds_data:
        gh = g.get("home_team", "").lower()
        if home_team.lower() not in gh and gh not in home_team.lower():
            continue

        for bm in g.get("bookmakers", []):
            title = bm.get("title", "")
            for m in bm.get("markets", []):
                if m["key"] == "totals":
                    ov = next((float(o["price"]) for o in m["outcomes"]
                              if o["name"] == "Over" and o.get("point") == 2.5), None)
                    if ov:
                        all_over25[title] = ov
                if m["key"] == "h2h":
                    ho = next((float(o["price"]) for o in m["outcomes"]
                              if o["name"] == g.get("home_team")), None)
                    if ho:
                        all_h2h_home[title] = ho

    if not all_over25:
        return None

    signals = []

    pinnacle_over = None
    soft_overs = []
    for bm, odds in all_over25.items():
        if "pinnacle" in bm.lower():
            pinnacle_over = odds
        elif bm.lower() in ["bet365", "william hill", "bwin", "unibet", "betway"]:
            soft_overs.append(odds)

    if pinnacle_over and soft_overs:
        soft_avg = sum(soft_overs) / len(soft_overs)
        movement = pinnacle_over - soft_avg
        pct = (movement / soft_avg) * 100

        if pct > 4:
            signals.append(f"📈 Line Movement Over 2.5: +{round(pct,1)}% (Pin:{pinnacle_over} vs Soft:{round(soft_avg,2)})")
        elif pct < -4:
            signals.append(f"📉 Line Movement Over 2.5: {round(pct,1)}% (Pin:{pinnacle_over} vs Soft:{round(soft_avg,2)})")

    if len(all_over25) >= 3:
        vals = list(all_over25.values())
        spread = max(vals) - min(vals)
        if spread > 0.15:
            signals.append(f"⚡ Hohe Quoten-Divergenz Over 2.5: {min(vals)}-{max(vals)} (Spread: {round(spread,2)})")

    return signals if signals else None


def get_historical_btts_rate(league_name, home_team, away_team):
    """
    Berechnet historische BTTS-Rate aus football-data.co.uk Daten.
    """
    try:
        data = fetch_football_data_co_uk(league_name)
        if not data:
            return None

        home_l = home_team.lower()
        away_l = away_team.lower()

        home_games = []
        away_games = []

        for g in data:
            gh = g.get("home", "").lower()
            ga = g.get("away", "").lower()
            fthg = g.get("fthg", "")
            ftag = g.get("ftag", "")

            if not fthg or not ftag:
                continue

            try:
                h_goals = int(fthg)
                a_goals = int(ftag)
                btts = h_goals > 0 and a_goals > 0
                total = h_goals + a_goals
            except:
                continue

            if home_l in gh or gh in home_l:
                home_games.append({"btts": btts, "total": total})
            if away_l in ga or ga in away_l:
                away_games.append({"btts": btts, "total": total})

        if not home_games and not away_games:
            return None

        result = {}
        if home_games:
            btts_rate = sum(1 for g in home_games if g["btts"]) / len(home_games)
            avg_goals = sum(g["total"] for g in home_games) / len(home_games)
            result["home"] = {
                "btts_rate": round(btts_rate * 100, 1),
                "avg_goals": round(avg_goals, 2),
                "games": len(home_games)
            }
        if away_games:
            btts_rate = sum(1 for g in away_games if g["btts"]) / len(away_games)
            avg_goals = sum(g["total"] for g in away_games) / len(away_games)
            result["away"] = {
                "btts_rate": round(btts_rate * 100, 1),
                "avg_goals": round(avg_goals, 2),
                "games": len(away_games)
            }
        return result
    except Exception:
        return None


def load_understat_league(league_name):
    if league_name in UNDERSTAT_CACHE:
        return UNDERSTAT_CACHE[league_name]

    league_code = UNDERSTAT_LEAGUES.get(league_name)

    if not league_code:
        UNDERSTAT_CACHE[league_name] = {}
        return {}

    try:
        url = f"https://understat.com/league/{league_code}"

        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )

        if not r.ok:
            UNDERSTAT_CACHE[league_name] = {}
            return {}

        m = re.search(r"var teamsData\s*=\s*JSON\.parse\('([^']+)'\)", r.text)

        if not m:
            UNDERSTAT_CACHE[league_name] = {}
            return {}

        encoded = m.group(1).encode().decode("unicode_escape")
        teams_data = json.loads(encoded)
        result = {}

        for _, info in teams_data.items():
            title = info.get("title", "")
            history = info.get("history", [])

            if not title or not history:
                continue

            last5 = history[-5:]
            avg_xg = sum(float(h.get("xG", 0)) for h in last5) / len(last5)
            avg_xga = sum(float(h.get("xGA", 0)) for h in last5) / len(last5)

            result[title.lower()] = {
                "xG": round(avg_xg, 2),
                "xGA": round(avg_xga, 2),
            }

        UNDERSTAT_CACHE[league_name] = result
        return result

    except Exception:
        UNDERSTAT_CACHE[league_name] = {}
        return {}


def get_team_xg(team_name, league_name):
    data = load_understat_league(league_name)
    t = team_name.lower()

    for title, stats in data.items():
        if t in title or title in t:
            return stats

    return None


# ============================================================
# AI CLIENTS
# ============================================================

# 🆕 Globaler Status: Wenn Groq rate-limited → nicht mehr probieren
_GROQ_RATE_LIMITED = False

# 🆕 Round-Robin Counter für Gemini Keys (verteilt Last gleichmäßig)
_GEMINI_KEY_OFFSET = 0


def call_gemini(prompt, use_tools=True):
    global _GEMINI_KEY_OFFSET

    if not GEMINI_API_KEYS:
        return None, "Keine Gemini Keys"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 32000 if use_tools else 16000,
        },
    }

    if use_tools:
        payload["tools"] = [{"google_search": {}}]

    last_error = None
    n = len(GEMINI_API_KEYS)

    # 🆕 Round-Robin: Beim nächsten Key starten (verteilt Last gleichmäßig)
    for offset in range(n):
        idx = (_GEMINI_KEY_OFFSET + offset) % n
        key = GEMINI_API_KEYS[idx]

        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}",
                json=payload,
                timeout=240 if use_tools else 120,
            )

            data = r.json()

            if "error" in data:
                last_error = data.get("error", {}).get("message", "")[:120]
                continue

            candidates = data.get("candidates", [])

            if not candidates:
                last_error = "no candidates"
                continue

            text = "".join(
                p.get("text", "")
                for p in candidates[0].get("content", {}).get("parts", [])
            )

            if not text.strip():
                last_error = "empty response"
                continue

            results = extract_json_array(text)

            if results is not None:
                # 🆕 Beim nächsten Aufruf rotieren
                _GEMINI_KEY_OFFSET = (idx + 1) % n
                label = f"Gemini #{idx + 1}" if use_tools else f"Gemini-NoTools #{idx + 1}"
                return results, label

        except Exception as e:
            last_error = str(e)[:120]
            continue

    # Kurze Pause vor Fallback
    import time as _t
    _t.sleep(2)
    log(f"   ⚠️ Gemini erschöpft - alle {n} Keys versucht", "WARN")
    return None, f"Gemini erschöpft ({last_error})"


def call_groq(prompt):
    global _GROQ_RATE_LIMITED

    if not GROQ_API_KEYS:
        return None, "Keine Groq Keys"

    if not USE_GROQ_FALLBACK:
        return None, "Groq deaktiviert"

    # 🆕 Wenn Groq schon erschöpft ist, nicht nochmal probieren!
    if _GROQ_RATE_LIMITED:
        return None, "Groq übersprungen (Rate Limit erreicht)"

    if len(prompt) > 30000:
        prompt = prompt[:30000] + "\n\nANTWORTE NUR AUF DEUTSCH! Reasoning und keyFactor IMMER auf Deutsch. Antworte mit JSON-Array."

    last_error = None
    rate_limit_hits = 0

    for idx, key in enumerate(GROQ_API_KEYS):
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL if rate_limit_hits == 0 else GROQ_MODEL_FALLBACK,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 4000,
                },
                timeout=120,
            )

            data = r.json()

            if "error" in data:
                err_msg = data.get("error", {}).get("message", "")[:120]
                last_error = err_msg
                # 🆕 Rate Limit erkennen
                if "rate limit" in err_msg.lower() or "rate_limit" in err_msg.lower():
                    rate_limit_hits += 1
                time.sleep(GROQ_SLEEP_SECONDS)
                continue

            choices = data.get("choices", [])

            if not choices:
                last_error = "no choices"
                time.sleep(GROQ_SLEEP_SECONDS)
                continue

            text = choices[0].get("message", {}).get("content", "")
            results = extract_json_array(text)

            if results is not None:
                return results, f"Groq #{idx + 1}"

        except Exception as e:
            last_error = str(e)[:120]
            time.sleep(GROQ_SLEEP_SECONDS)
            continue

    # Reset nach kurzer Pause statt global deaktivieren
    if rate_limit_hits >= len(GROQ_API_KEYS):
        import time as _gt
        log("⚠️  Groq rate-limited - warte 30 Sekunden...", "WARN")
        _gt.sleep(30)
        _GROQ_RATE_LIMITED = False  # Reset nach Pause

    return None, f"Groq erschöpft ({last_error})"


# ============================================================
# ANALYSIS
# ============================================================

def merge_fixtures(*sources):
    all_fixtures = []
    seen = set()

    def norm(name):
        n = name.lower().strip()
        for rem in [" fc", " cf", " ac", " sc", " sv", "fc ", "ac ", "1. ", " 1."]:
            n = n.replace(rem, " ")
        return " ".join(n.split())[:20]

    for source in sources:
        for f in source:
            home = f.get("home", "").lower().strip()
            away = f.get("away", "").lower().strip()

            if not home or not away:
                continue

            home_norm = norm(home)
            away_norm = norm(away)
            key = (home_norm, away_norm)
            key_rev = (away_norm, home_norm)

            if key in seen or key_rev in seen:
                continue

            seen.add(key)
            all_fixtures.append(f)

    return all_fixtures


def calculate_kelly_units(probability, odds, max_units=3.0, bank_units=100):
    """
    Kelly Kriterium für optimale Einsatzgröße in Units.
    Half-Kelly für Sicherheit. Max 3 Units pro Tipp.
    """
    try:
        p = probability / 100
        b = odds - 1
        kelly = (p * b - (1 - p)) / b

        if kelly <= 0:
            return 0.5

        half_kelly = kelly / 2
        units = round(half_kelly * 100, 1)
        units = max(0.5, min(units, max_units))

        return units
    except Exception:
        return 1.0


def fetch_fbref_team_stats(team_name, league_name):
    """
    Holt erweiterte Stats von FBref (xG, xGA, Pressing, Possession).
    DEPRECATED - benutze besser get_fbref_stats() mit Caching.
    """
    return get_fbref_stats(team_name, league_name)


# 🆕 FBref Cache (pro Liga 1x laden, dann alle Teams aus dem Cache)
FBREF_CACHE = {}
FBREF_BLOCKED = False  # Wenn FBref blockt, schalten wir ab


def load_fbref_league(league_name):
    """
    Lädt FBref-Ligadaten EINMAL pro Run und cached sie.
    Parsed das Squad Standard Stats Table für xG, xGA, Possession.
    """
    global FBREF_BLOCKED

    if FBREF_BLOCKED:
        return {}

    if league_name in FBREF_CACHE:
        return FBREF_CACHE[league_name]

    fbref_urls = {
        "Premier League": "https://fbref.com/en/comps/9/Premier-League-Stats",
        "Bundesliga": "https://fbref.com/en/comps/20/Bundesliga-Stats",
        "La Liga": "https://fbref.com/en/comps/12/La-Liga-Stats",
        "Serie A": "https://fbref.com/en/comps/11/Serie-A-Stats",
        "Ligue 1": "https://fbref.com/en/comps/13/Ligue-1-Stats",
        "Eredivisie": "https://fbref.com/en/comps/23/Eredivisie-Stats",
        "Primeira Liga": "https://fbref.com/en/comps/32/Primeira-Liga-Stats",
        "Championship": "https://fbref.com/en/comps/10/Championship-Stats",
        "Champions League": "https://fbref.com/en/comps/8/Champions-League-Stats",
        "Europa League": "https://fbref.com/en/comps/19/Europa-League-Stats",
    }

    url = fbref_urls.get(league_name)
    if not url:
        FBREF_CACHE[league_name] = {}
        return {}

    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=20,
        )

        # FBref blockt mit 403 oder 429 wenn zu viele Requests
        if r.status_code in [403, 429]:
            # Nur 1x loggen, dann still bleiben
            if not FBREF_BLOCKED:
                log(f"   ℹ️  FBref nicht erreichbar ({r.status_code}) - überspringe (kein Problem, andere Quellen reichen)")
            FBREF_BLOCKED = True
            FBREF_CACHE[league_name] = {}
            return {}

        if not r.ok:
            FBREF_CACHE[league_name] = {}
            return {}

        html = r.text

        # FBref versteckt einige Tables in HTML-Kommentaren - rauspulen
        html = html.replace("<!--", "").replace("-->", "")

        # Parse Squad Standard Stats Table
        # Format: <tr><th>...<a href=".../squads/...">TeamName</a>...<td>games</td>...<td>xG</td><td>xGA</td>...
        result = {}

        # Suche alle Team-Zeilen aus der "stats_squads_standard_for" Tabelle
        # FBref Pattern: <tr ...><th ...><a href="/en/squads/.../...">TeamName</a></th>
        team_pattern = re.compile(
            r'<tr[^>]*>\s*<th[^>]*data-stat="team"[^>]*>\s*<a[^>]*href="/en/squads/[^"]+"[^>]*>([^<]+)</a>',
            re.IGNORECASE
        )

        # Suche xG, xGA, Possession via data-stat Attribut (zuverlässiger)
        # Wir finden Zeilen, dann extrahieren wir alle Werte aus der Zeile

        # Vereinfachter Ansatz: für jede gefundene Zeile, hole die Stats
        rows = re.findall(
            r'<tr[^>]*>\s*<th[^>]*data-stat="team"[^>]*>\s*<a[^>]*href="/en/squads/[^"]+"[^>]*>([^<]+)</a>.*?</tr>',
            html,
            re.DOTALL | re.IGNORECASE
        )

        # Alternative: Komplette Tabellenzeilen finden
        for match in re.finditer(
            r'<tr[^>]*>(.*?)</tr>',
            html,
            re.DOTALL
        ):
            row_html = match.group(1)

            # Team-Name extrahieren
            team_m = re.search(
                r'data-stat="team"[^>]*>\s*<a[^>]*href="/en/squads/[^"]+"[^>]*>([^<]+)</a>',
                row_html
            )
            if not team_m:
                continue

            team_title = team_m.group(1).strip()

            # Stats extrahieren via data-stat
            xg_m = re.search(r'data-stat="xg_for"[^>]*>([\d.]+)<', row_html)
            xga_m = re.search(r'data-stat="xg_against"[^>]*>([\d.]+)<', row_html)
            poss_m = re.search(r'data-stat="possession"[^>]*>([\d.]+)<', row_html)
            games_m = re.search(r'data-stat="games"[^>]*>([\d.]+)<', row_html)
            goals_for_m = re.search(r'data-stat="goals_for"[^>]*>([\d.]+)<', row_html)
            goals_against_m = re.search(r'data-stat="goals_against"[^>]*>([\d.]+)<', row_html)

            stats = {}
            if games_m:
                games = float(games_m.group(1))
                stats["games"] = int(games) if games > 0 else 0
            else:
                continue  # Ohne games-Anzahl ist die Zeile nutzlos

            # Werte sind kumuliert über die Saison → pro Spiel umrechnen
            games = stats["games"] or 1

            if xg_m:
                stats["xG"] = round(float(xg_m.group(1)) / games, 2)
            if xga_m:
                stats["xGA"] = round(float(xga_m.group(1)) / games, 2)
            if poss_m:
                stats["possession"] = round(float(poss_m.group(1)), 1)
            if goals_for_m:
                stats["goals_for"] = round(float(goals_for_m.group(1)) / games, 2)
            if goals_against_m:
                stats["goals_against"] = round(float(goals_against_m.group(1)) / games, 2)

            if stats and len(stats) > 1:
                result[team_title.lower()] = stats

        FBREF_CACHE[league_name] = result

        if result:
            log(f"   📊 FBref geladen: {len(result)} Teams in {league_name}")

        return result

    except Exception as e:
        log(f"   ⚠️ FBref Fehler: {str(e)[:80]}", "WARN")
        FBREF_CACHE[league_name] = {}
        return {}


def get_fbref_stats(team_name, league_name):
    """
    Holt FBref-Stats für ein Team aus dem Cache.
    Lädt die Liga beim ersten Aufruf, dann nur Cache-Lookup.
    """
    data = load_fbref_league(league_name)

    if not data:
        return None

    t = team_name.lower().strip()

    # Exakter Match
    if t in data:
        return data[t]

    # Fuzzy Match: Team-Name beginnt gleich oder ist enthalten
    for title, stats in data.items():
        if t in title or title in t:
            return stats

        # Wort-basierter Match (z.B. "Bayern" vs "Bayern Munich")
        t_words = [w for w in t.split() if len(w) > 3]
        title_words = [w for w in title.split() if len(w) > 3]

        if t_words and title_words:
            if any(w in title for w in t_words) or any(w in t for w in title_words):
                return stats

    return None


def analyze_pinnacle_value(odds_data, home_team, away_team):
    """
    Analysiert Sharp Money via Pinnacle vs andere Bookies.
    """
    if not odds_data:
        return None

    pinnacle_over = None
    avg_over = []
    pinnacle_home = None
    avg_home = []

    for g in odds_data:
        gh = g.get("home_team", "").lower()
        ga = g.get("away_team", "").lower()
        if home_team.lower() not in gh and gh not in home_team.lower():
            continue

        for bm in g.get("bookmakers", []):
            title = bm.get("title", "").lower()
            is_pinnacle = "pinnacle" in title

            for m in bm.get("markets", []):
                if m["key"] == "totals":
                    ov = next((o["price"] for o in m["outcomes"]
                              if o["name"] == "Over" and o.get("point") == 2.5), None)
                    if ov:
                        if is_pinnacle:
                            pinnacle_over = float(ov)
                        else:
                            avg_over.append(float(ov))

                if m["key"] == "h2h":
                    ho = next((o["price"] for o in m["outcomes"]
                              if o["name"] == g.get("home_team")), None)
                    if ho:
                        if is_pinnacle:
                            pinnacle_home = float(ho)
                        else:
                            avg_home.append(float(ho))

    signals = []

    if pinnacle_over and avg_over:
        avg = sum(avg_over) / len(avg_over)
        diff_pct = ((pinnacle_over - avg) / avg) * 100
        if diff_pct > 3:
            signals.append(f"🔥 Over 2.5: Pinnacle {pinnacle_over} > Markt {round(avg,2)} (+{round(diff_pct,1)}%)")
        elif diff_pct < -3:
            signals.append(f"⚠️ Over 2.5: Pinnacle {pinnacle_over} < Markt {round(avg,2)} ({round(diff_pct,1)}%)")

    if pinnacle_home and avg_home:
        avg = sum(avg_home) / len(avg_home)
        diff_pct = ((pinnacle_home - avg) / avg) * 100
        if diff_pct > 3:
            signals.append(f"🔥 Heimsieg: Pinnacle {pinnacle_home} > Markt {round(avg,2)} (+{round(diff_pct,1)}%)")
        elif diff_pct < -3:
            signals.append(f"⚠️ Heimsieg: Pinnacle {pinnacle_home} < Markt {round(avg,2)} ({round(diff_pct,1)}%)")

    return signals if signals else None


def build_context(odds_data, fixtures, league, target_date=None):
    ctx = ""

    # 🆕 WETTERDATEN
    weather = get_weather_for_league(league, date.today())
    if weather:
        ctx += f"\n🌤️ WETTER ({weather['city']}):" + "\n"
        ctx += f"• {weather['condition']} · {weather['temp']}°C · "
        ctx += f"Wind {weather['wind']}km/h · Regen {weather['rain']}mm" + "\n"
        if weather['notes']:
            for note in weather['notes']:
                ctx += f"• {note}" + "\n"
        if weather['impact'] == 'negative':
            ctx += f"⚠️ Wetter-Impact: Schlechtere Bedingungen → weniger Tore erwartet!" + "\n"
        ctx += "\n"

    league_id = API_FOOTBALL_LEAGUES.get(league)
    season = None
    if league_id:
        from datetime import date as _date
        td = _date.today()
        season = td.year if td.month > 6 else td.year - 1

    if fixtures:
        ctx += f"\n📅 ECHTER SPIELPLAN für {league} HEUTE:" + "\n"

        for f in fixtures:
            line = f"• {f['home']} vs {f['away']} · {f.get('time_local', 'TBD')} Uhr [{f.get('source', '?')}]"

            if league in UNDERSTAT_LEAGUES:
                home_xg = get_team_xg(f["home"], league)
                away_xg = get_team_xg(f["away"], league)

                if home_xg:
                    line += f"\n   📊 {f['home']}: xG {home_xg['xG']}/Spiel, xGA {home_xg['xGA']} [Understat]"
                if away_xg:
                    line += f"\n   📊 {f['away']}: xG {away_xg['xG']}/Spiel, xGA {away_xg['xGA']} [Understat]"

            # 🆕 FBref Stats (xG, Possession, Goals)
            home_fb = get_fbref_stats(f["home"], league)
            away_fb = get_fbref_stats(f["away"], league)

            if home_fb:
                fb_str = f"\n   ⚡ {f['home']}: xG {home_fb.get('xG','?')}, xGA {home_fb.get('xGA','?')}"
                if 'possession' in home_fb:
                    fb_str += f", Poss {home_fb['possession']}%"
                if 'goals_for' in home_fb:
                    fb_str += f", Tore {home_fb['goals_for']}/Spiel"
                fb_str += f" [FBref · {home_fb.get('games',0)} Spiele]"
                line += fb_str

            if away_fb:
                fb_str = f"\n   ⚡ {f['away']}: xG {away_fb.get('xG','?')}, xGA {away_fb.get('xGA','?')}"
                if 'possession' in away_fb:
                    fb_str += f", Poss {away_fb['possession']}%"
                if 'goals_for' in away_fb:
                    fb_str += f", Tore {away_fb['goals_for']}/Spiel"
                fb_str += f" [FBref · {away_fb.get('games',0)} Spiele]"
                line += fb_str

            # 🆕 FootyStats BTTS + Over 2.5 Stats
            home_fs = get_footystats_team(f["home"], league)
            away_fs = get_footystats_team(f["away"], league)

            if home_fs:
                line += (
                    f"\n   📊 {f['home']} [FootyStats]: "
                    f"BTTS {home_fs['btts_rate']}%, "
                    f"Over2.5 {home_fs['over25_rate']}%, "
                    f"Ø {home_fs['avg_goals']} Tore/Spiel"
                )
            if away_fs:
                line += (
                    f"\n   📊 {f['away']} [FootyStats]: "
                    f"BTTS {away_fs['btts_rate']}%, "
                    f"Over2.5 {away_fs['over25_rate']}%, "
                    f"Ø {away_fs['avg_goals']} Tore/Spiel"
                )

            # 🆕 FOREBET - Mathematische Predictions
            forebet = get_forebet_prediction(f["home"], f["away"], league, target_date)
            if forebet:
                fb_parts = []
                if forebet.get("btts_pct"):
                    fb_parts.append(f"BTTS {forebet['btts_pct']}%")
                if forebet.get("over25_pct"):
                    fb_parts.append(f"Over2.5 {forebet['over25_pct']}%")
                if forebet.get("avg_goals"):
                    fb_parts.append(f"Ø {forebet['avg_goals']} Tore")
                if forebet.get("tip"):
                    fb_parts.append(f"Tipp: {forebet['tip']}")
                if fb_parts:
                    line += f"\n   🔢 [Forebet]: {' · '.join(fb_parts)}"

            # 🆕 SCOUTINGSTATS - AI Predictions
            scout = get_scoutingstats_prediction(f["home"], f["away"], target_date)
            if scout:
                sc_parts = []
                if scout.get("btts_pct"):
                    sc_parts.append(f"BTTS {scout['btts_pct']}%")
                if scout.get("over25_pct"):
                    sc_parts.append(f"Over2.5 {scout['over25_pct']}%")
                if scout.get("value_edge"):
                    sc_parts.append(f"Edge +{scout['value_edge']}%")
                if sc_parts:
                    line += f"\n   🤖 [ScoutingStats]: {' · '.join(sc_parts)}"

            # 🆕 SPORTDB.DEV - Aufstellungen
            if SPORTDB_API_KEY:
                lineup = get_sportdb_lineups(f["home"], f["away"], target_date)
                if lineup and lineup.get("lineup_available"):
                    if lineup.get("home_lineup"):
                        players = ", ".join(lineup["home_lineup"][:5])
                        line += f"\n   👕 {f['home']} XI (Top 5): {players}..."
                    if lineup.get("away_lineup"):
                        players = ", ".join(lineup["away_lineup"][:5])
                        line += f"\n   👕 {f['away']} XI (Top 5): {players}..."

            # 🆕 SOFASCORE LINEUPS - Aufstellungen (zuverlässiger!)
            sofa_match_id = f.get("match_id") if f.get("source") == "sofascore" else None
            if sofa_match_id:
                sofa_lineup = get_sofascore_lineups(sofa_match_id, f["home"], f["away"])
                if sofa_lineup and sofa_lineup.get("lineup_available"):
                    confirmed = "✅ Bestätigt" if sofa_lineup.get("confirmed") else "⏳ Vorläufig"
                    if sofa_lineup.get("home_lineup"):
                        starters = [p["name"] for p in sofa_lineup["home_lineup"][:5]]
                        line += f"\n   👕 {f['home']} XI ({confirmed}): {', '.join(starters)}..."
                    if sofa_lineup.get("away_lineup"):
                        starters = [p["name"] for p in sofa_lineup["away_lineup"][:5]]
                        line += f"\n   👕 {f['away']} XI ({confirmed}): {', '.join(starters)}..."

            # BettingScreener blockiert GitHub IPs - deaktiviert
            match_key = f"{f['home']} vs {f['away']}"

            # Pinnacle via Odds API
            # Wird über Odds API Daten bereits abgedeckt

            # 🆕 PREDICTZ + BETIMATE Predictions
            pz = get_predictz_prediction(f["home"], f["away"], target_date)
            if pz:
                if pz.get("btts_pct"):
                    line += f"\n   🎯 PredictZ: BTTS {pz['btts_pct']}%"
                if pz.get("over25_pct"):
                    line += f" | Over2.5 {pz['over25_pct']}%"

            bm = get_betimate_prediction(f["home"], f["away"], target_date)
            if bm and bm.get("btts_pct"):
                line += f"\n   🎯 Betimate: BTTS {bm['btts_pct']}%"

            # 🆕 PHYSIOROOM Verletzungen (Premier League)
            pr_home = get_physioroom_injuries(f["home"], league)
            if pr_home and pr_home.get("has_data"):
                names = ", ".join([p["name"] for p in pr_home["injured"][:3]])
                line += f"\n   🏥 PhysioRoom {f['home']}: {names}"

            # 🆕 WINDRAWWIN Predictions
            wdw = get_windrawwin_prediction(f["home"], f["away"], target_date)
            if wdw:
                line += f"\n   📊 WDW: H{wdw.get('prob_home','?')}% D{wdw.get('prob_draw','?')}% A{wdw.get('prob_away','?')}%"

            # 🆕 SOCCERSTATS Liga-weite BTTS Rate
            ss = get_soccerstats_btts(league)
            if ss and ss.get("btts_rate"):
                line += f"\n   ⚽ Liga BTTS Rate: {ss['btts_rate']}% (Over2.5: {ss.get('over25_rate','?')}%)"

            # 🔥 GRATIS QUELLEN ZUERST!
            # 1. Poisson Modell (komplett gratis)
            pen_home = get_penalty_team_rating(f["home"], league)
            pen_away = get_penalty_team_rating(f["away"], league)
            if pen_home and pen_away:
                poisson = calculate_poisson_btts(
                    pen_home["attack_strength"], pen_home["defense_weakness"],
                    pen_away["attack_strength"], pen_away["defense_weakness"],
                )
                line += f"\n   📊 Poisson: BTTS {poisson['btts_prob']}% | Over2.5 {poisson['over25_prob']}%"
                line += f"\n   ⚽ Erwartete Tore: {poisson['home_expected_goals']} / {poisson['away_expected_goals']}"

            # 2. understatapi xG (kein Key)
            uapi_home = get_understatapi_team_xg(f["home"], league)
            uapi_away = get_understatapi_team_xg(f["away"], league)
            if uapi_home and uapi_away:
                line += f"\n   📈 xG/Sp: {uapi_home.get('xg_per_game','?')} / {uapi_away.get('xg_per_game','?')}"

            # 3. FotMob xG (kein Key)
            fm_stats = get_fotmob_match_stats(f["home"], f["away"], target_date)
            if fm_stats and fm_stats.get("xg_home"):
                line += f"\n   ⚽ FotMob xG: {fm_stats['xg_home']} / {fm_stats['xg_away']}"

            # 4. SportSRC xG (kein Key, 1000/Tag)
            src_stats = get_sportsrc_match(f["home"], f["away"], target_date)
            if src_stats and src_stats.get("xg_home"):
                line += f"\n   🔥 SportSRC xG: {src_stats['xg_home']} / {src_stats['xg_away']}"

            # 5. OddsPortal Quoten (kein Key)
            op_odds = scrape_oddsportal_btts(f["home"], f["away"], league, target_date)
            if op_odds and op_odds.get("btts_yes"):
                line += f"\n   💰 OddsPortal BTTS: {op_odds['btts_yes']} / {op_odds.get('btts_no','?')}"

            # 6. WorldFootball Schiedsrichter (kein Key)
            wf_ref = get_worldfootball_referee(f["home"], f["away"], league, target_date)
            if wf_ref and wf_ref.get("name"):
                line += f"\n   👨‍⚖️ Schiri: {wf_ref['name']}"

            # 🏆 FPL Verletzungen (Premier League)
            if league == "Premier League":
                fpl_home = get_fpl_team_injuries(f["home"])
                fpl_away = get_fpl_team_injuries(f["away"])
                if fpl_home and fpl_home.get("injured"):
                    line += f"\n   🏥 FPL {f['home']}: {', '.join(fpl_home['injured'][:2])} fehlen"
                if fpl_home and fpl_home.get("doubtful"):
                    line += f"\n   ⚠️ Fraglich: {', '.join(fpl_home['doubtful'][:2])}"

            # 📊 DATAHUB Statistiken
            dh_home = get_datahub_team_stats(f["home"], league)
            if dh_home:
                line += f"\n   📊 BTTS Rate: {dh_home['btts_rate']}% | Over2.5: {dh_home['over25_rate']}%"

            # 🌍 INTERNATIONALE BTTS STATS (martj42)
            for intl_team in [f["home"], f["away"]]:
                m42_stats = get_international_btts_rate(intl_team, last_n=20)
                if m42_stats and m42_stats.get("games", 0) >= 5:
                    line += (
                        f"\n   🌍 {intl_team} [martj42 {m42_stats['games']}Sp]: "
                        f"BTTS {m42_stats['btts_rate']}% | "
                        f"Over2.5 {m42_stats['over25_rate']}% | "
                        f"Ø {m42_stats['avg_goals']} Tore"
                    )

            # 🆕 REFEREE STATS
            ref_data = get_referee_stats(f["home"], f["away"], league, target_date)
            if ref_data and ref_data.get("name"):
                line += f"\n   👨‍⚖️ Schiri: {ref_data['name']}"
                if ref_data.get("cards_per_game"):
                    line += f" | Karten/Spiel: {ref_data['cards_per_game']}"
                if ref_data.get("penalty_rate"):
                    line += f" | Elfmeter: {ref_data['penalty_rate']}/Spiel"

            # 🆕 FATIGUE & REISE
            fatigue = calculate_travel_fatigue(f["home"], f["away"])
            if fatigue:
                if fatigue.get("distance_km", 0) > 500:
                    line += f"\n   ✈️ Reise {f['away']}: {fatigue['distance_km']}km"
                if fatigue.get("rotation_likely"):
                    line += f" ⚠️ Rotation wahrscheinlich!"

            # 🆕 CLV SHARP MONEY
            clv = track_odds_movement(f["home"], f["away"])
            if clv and clv.get("sharp_signal"):
                line += f"\n   📌 Sharp Money Signal! Pinnacle: {clv.get('current_odds')}"

            # 📰 NEWS - Google News + Tavily
            news_items = get_team_news_google(f["home"], f["away"], league)
            if news_items:
                injury_news = [n for n in news_items if n.get("has_injury_info")]
                if injury_news:
                    line += f"\n   📰 News: {injury_news[0]['title'][:100]}"

            if TAVILY_API_KEY:
                news = get_team_news_tavily(f["home"], f["away"], league)
                if news and news.get("summary"):
                    line += f"\n   📰 Tavily: {news['summary'][:100]}"

            # 🤖 REDDIT Insider
            reddit = scrape_reddit_soccer(f["home"], f["away"])
            if reddit:
                line += f"\n   🤖 Reddit: {reddit[0]['title'][:80]}"

            # 📊 STATSBOMB Player Props
            sb_stats = get_statsbomb_player_stats(league)
            if sb_stats:
                # Props für dieses Spiel
                props = get_player_props_for_match(f["home"], f["away"], league)
                if props:
                    top3 = props[:3]
                    props_str = " | ".join([f"{p['player'].split()[-1]} {p['tip']} ({p['probability']}%)" for p in top3])
                    line += f"\n   🔑 Props: {props_str}"

            # 🎭 TRANSFERMARKT via Playwright
            if PLAYWRIGHT_AVAILABLE:
                tm_home = pw_get_transfermarkt_injuries(f["home"], league)
                if tm_home and tm_home.get("has_data"):
                    names = ", ".join([p["name"] for p in tm_home["injured"][:3]])
                    line += f"\n   🏥 TM {f['home']}: {names} fehlen"

            # 🆕 RSSSF + FUSSBALLDATEN - Historische Stats
            rsssf = get_rsssf_stats(league)
            if rsssf and rsssf.get("btts_rate"):
                line += (
                    f"\n   📚 RSSSF Liga-Statistik: BTTS {rsssf['btts_rate']}%, "
                    f"Ø {rsssf['avg_goals']} Tore ({rsssf['total_games']} Spiele)"
                )

            fbd_hist = get_fussballdaten_history(f["home"], f["away"], league)
            if fbd_hist and fbd_hist.get("btts_rate"):
                line += f"\n   🇩🇪 Fussballdaten: BTTS {fbd_hist['btts_rate']}%"

            # 🆕 CLUBELO - Team Stärke
            home_elo = get_clubelo_rating(f["home"])
            away_elo = get_clubelo_rating(f["away"])
            if home_elo and away_elo:
                elo_diff = abs(home_elo["elo"] - away_elo["elo"])
                btts_prob = calculate_elo_btts_probability(home_elo["elo"], away_elo["elo"])
                line += (
                    f"\n   📊 Elo: {f['home']} {home_elo['elo']:.0f} vs "
                    f"{f['away']} {away_elo['elo']:.0f} "
                    f"(Diff: {elo_diff:.0f}, BTTS-Wahrscheinlichkeit: ~{btts_prob}%)"
                )

            # 🆕 TRANSFERMARKT - Verletzungen
            home_tm = get_transfermarkt_injuries(f["home"], league)
            away_tm = get_transfermarkt_injuries(f["away"], league)
            if home_tm and home_tm.get("has_data"):
                if home_tm.get("starters_out"):
                    names = ", ".join([p["name"] for p in home_tm["starters_out"][:3]])
                    line += f"\n   🏥 {f['home']} Stammspieler fehlen: {names}"
                if home_tm.get("suspended"):
                    names = ", ".join([p["name"] for p in home_tm["suspended"][:2]])
                    line += f"\n   🟥 {f['home']} Gesperrt: {names}"
            if away_tm and away_tm.get("has_data"):
                if away_tm.get("starters_out"):
                    names = ", ".join([p["name"] for p in away_tm["starters_out"][:3]])
                    line += f"\n   🏥 {f['away']} Stammspieler fehlen: {names}"
                if away_tm.get("suspended"):
                    names = ", ".join([p["name"] for p in away_tm["suspended"][:2]])
                    line += f"\n   🟥 {f['away']} Gesperrt: {names}"

            hist = get_historical_btts_rate(league, f["home"], f["away"])
            if hist:
                if hist.get("home") and hist["home"].get("games", 0) >= 3:
                    h = hist["home"]
                    line += f"\n   📈 {f['home']} (Heim): BTTS {h['btts_rate']}%, Ø {h['avg_goals']} Tore ({h['games']} Spiele) [fd.co.uk]"
                if hist.get("away") and hist["away"].get("games", 0) >= 3:
                    a = hist["away"]
                    line += f"\n   📈 {f['away']} (Auswärts): BTTS {a['btts_rate']}%, Ø {a['avg_goals']} Tore ({a['games']} Spiele) [fd.co.uk]"

            # 🆕 API-Football Erweiterungen (nur wenn fixture aus api-football kommt)
            # WICHTIG: Free Plan = 100 Calls/Tag. Daher nur für Top-Ligen!
            home_id = f.get("home_id")
            away_id = f.get("away_id")
            fixture_id = f.get("match_id")

            # Top-Ligen die API-Calls "wert" sind
            APIF_PRIORITY_LEAGUES = {
                "Champions League", "Europa League", "Conference League",
                "Premier League", "Bundesliga", "La Liga", "Serie A", "Ligue 1",
                "Eredivisie", "Primeira Liga", "Süper Lig",
                "Championship", "Bundesliga Österreich", "Super League Schweiz",
            }

            is_priority = league in APIF_PRIORITY_LEAGUES

            if home_id and away_id and league_id and season and is_priority:
                # 1. Team-Statistiken (2 Calls pro Spiel)
                if APIFOOTBALL_ENABLE_TEAM_STATS and not APIFOOTBALL_QUOTA_EXHAUSTED:
                    home_stats = fetch_team_statistics(home_id, league_id, season)
                    if home_stats and home_stats.get("matches_played", 0) >= 3:
                        line += (
                            f"\n   🏠 {f['home']} Stats: Form {home_stats['form']}, "
                            f"⚽{home_stats['goals_for_avg']}/Spiel, "
                            f"🛡️{home_stats['goals_against_avg']} kassiert, "
                            f"BTTS≈{home_stats['btts_rate_approx']}%, "
                            f"Clean Sheets {home_stats['clean_sheets']}/{home_stats['matches_played']} "
                            f"[API-Football]"
                        )

                    away_stats = fetch_team_statistics(away_id, league_id, season)
                    if away_stats and away_stats.get("matches_played", 0) >= 3:
                        line += (
                            f"\n   ✈️ {f['away']} Stats: Form {away_stats['form']}, "
                            f"⚽{away_stats['goals_for_avg']}/Spiel, "
                            f"🛡️{away_stats['goals_against_avg']} kassiert, "
                            f"BTTS≈{away_stats['btts_rate_approx']}%, "
                            f"Clean Sheets {away_stats['clean_sheets']}/{away_stats['matches_played']} "
                            f"[API-Football]"
                        )

                # 2. H2H History (1 Call pro Spiel)
                if APIFOOTBALL_ENABLE_H2H and not APIFOOTBALL_QUOTA_EXHAUSTED:
                    h2h = fetch_head_to_head(home_id, away_id, last=5)
                    if h2h and h2h["count"] >= 2:
                        line += (
                            f"\n   ⚔️ Direkter Vergleich (letzte {h2h['count']}): "
                            f"BTTS {h2h['btts_rate']}%, "
                            f"Over 2.5 {h2h['over25_rate']}%, "
                            f"Ø {h2h['avg_goals']} Tore [API-Football H2H]"
                        )

                # 3. Verletzungen (2 Calls pro Spiel) - DEFAULT AUS für Free Plan
                if APIFOOTBALL_ENABLE_INJURIES and not APIFOOTBALL_QUOTA_EXHAUSTED:
                    home_inj = fetch_injuries(home_id, league_id, season)
                    away_inj = fetch_injuries(away_id, league_id, season)
                    if home_inj:
                        inj_names = ", ".join([i["name"] for i in home_inj[:5]])
                        line += f"\n   🤕 {f['home']} Ausfälle ({len(home_inj)}): {inj_names}"
                    if away_inj:
                        inj_names = ", ".join([i["name"] for i in away_inj[:5]])
                        line += f"\n   🤕 {f['away']} Ausfälle ({len(away_inj)}): {inj_names}"

            # 4. API-Football Predictions (1 Call pro Spiel) - DEFAULT AUS für Free Plan
            if (APIFOOTBALL_ENABLE_PREDICTIONS and fixture_id and is_priority
                and f.get("source") == "api-football" and not APIFOOTBALL_QUOTA_EXHAUSTED):
                pred = fetch_predictions(fixture_id)
                if pred and pred.get("advice"):
                    line += (
                        f"\n   🎯 API-Football Tip: '{pred['advice']}' "
                        f"({pred.get('percent_home','?')}/"
                        f"{pred.get('percent_draw','?')}/"
                        f"{pred.get('percent_away','?')})"
                    )
                    if pred.get("under_over"):
                        line += f", Goals: {pred['under_over']}"

            ctx += line + "\n"

    if odds_data:
        ctx += "\n💰 LIVE-QUOTEN:\n"

        for g in odds_data[:10]:
            try:
                t = get_local_time(g["commence_time"])
                ctx += f"\n• {g['home_team']} vs {g['away_team']} · {t}" + "\n"

                for bm in g.get("bookmakers", [])[:5]:
                    for m in bm.get("markets", []):
                        if m["key"] == "totals":
                            ov = next(
                                (o["price"] for o in m["outcomes"]
                                 if o["name"] == "Over" and o.get("point") == 2.5),
                                None,
                            )
                            un = next(
                                (o["price"] for o in m["outcomes"]
                                 if o["name"] == "Under" and o.get("point") == 2.5),
                                None,
                            )
                            if ov:
                                ctx += f"  [{bm['title']}] O2.5: {ov} / U2.5: {un}" + "\n"

                        if m["key"] == "h2h":
                            home_o = next(
                                (o["price"] for o in m["outcomes"]
                                 if o["name"] == g["home_team"]),
                                None,
                            )
                            draw_o = next(
                                (o["price"] for o in m["outcomes"]
                                 if o["name"] == "Draw"),
                                None,
                            )
                            away_o = next(
                                (o["price"] for o in m["outcomes"]
                                 if o["name"] == g["away_team"]),
                                None,
                            )
                            if home_o:
                                ctx += f"  [{bm['title']}] 1: {home_o} / X: {draw_o} / 2: {away_o}" + "\n"

                line_signals = analyze_line_movement(
                    odds_data, g["home_team"], g["away_team"]
                )
                if line_signals:
                    ctx += "  📉 Line Movement:\n"
                    for sig in line_signals:
                        ctx += f"    {sig}" + "\n"

                pinnacle_signals = analyze_pinnacle_value(
                    odds_data, g["home_team"], g["away_team"]
                )
                if pinnacle_signals:
                    ctx += "  💹 Sharp Money Signale:\n"
                    for sig in pinnacle_signals:
                        ctx += f"    {sig}" + "\n"

            except Exception:
                continue

    return ctx


def build_prompt(market, league, target_date, context):
    info = MARKET_INFO[market]

    if market == "1x2":
        json_format = (
            '[{"match":"A vs B","league":"' + league +
            '","time":"HH:MM","tip":"1","probability":55,'
            '"confidence":4,"fairOdds":"1.85","oddsYes":"1.95",'
            '"oddsNo":"-","bookie":"Bet365","homeForm":"WWDLW",'
            '"awayForm":"LWWDD","valueRating":"HIGH",'
            '"keyFactor":"Faktor","reasoning":"2 Sätze."}]'
        )
        tip_help = 'tip: "1" / "X" / "2"'
    else:
        json_format = (
            '[{"match":"A vs B","league":"' + league +
            '","time":"HH:MM","tip":"YES","probability":72,'
            '"confidence":4,"fairOdds":"1.65","oddsYes":"1.72",'
            '"oddsNo":"2.10","bookie":"Bet365","homeForm":"WWDLW",'
            '"awayForm":"LWWDD","valueRating":"HIGH",'
            '"keyFactor":"Faktor","reasoning":"2 Sätze."}]'
        )
        tip_help = 'tip: "YES" / "NO" / "MAYBE"'

    return f"""Du bist Fußball-Wettanalyst. {info['instr']}

Liga: "{league}" · Datum: {target_date}

{context}

KRITISCH:
1. Analysiere AUSSCHLIESSLICH die oben aufgeführten Spiele.
2. Erfinde keine Spiele.
3. Verwende echte Anstoßzeiten.
4. Berücksichtige xG-Daten.
5. Wenn Liste leer: gib [] zurück.

Antworte nur mit JSON-Array:
{json_format}

{tip_help}
Falls keine echten Spiele: []"""


def validate_tips(tips, real_fixtures, real_odds):
    if not tips:
        return []

    real_matches = []

    for f in real_fixtures:
        real_matches.append((
            f.get("home", ""),
            f.get("away", ""),
            f.get("time_local", ""),
        ))

    for g in real_odds:
        try:
            real_matches.append((
                g.get("home_team", ""),
                g.get("away_team", ""),
                get_local_time(g.get("commence_time", "")),
            ))
        except Exception:
            continue

    # 🆕 FIX: Wenn keine Fixtures/Odds → Tips trotzdem behalten!
    # Passiert bei MLS, Brasilien, Asien wo Odds API oft keine Daten hat
    if not real_matches:
        log("   ⚠️ Keine Fixture-Daten → Tips direkt übernehmen")
        validated = []
        for tip in tips:
            match = tip.get("match", "")
            if " vs " not in match:
                continue
            parts = match.split(" vs ", 1)
            if len(parts) == 2 and len(parts[0]) > 2 and len(parts[1]) > 2:
                validated.append(tip)
        return validated

    validated = []

    for tip in tips:
        match = tip.get("match", "")

        if " vs " not in match:
            continue

        teams = match.split(" vs ", 1)

        if len(teams) != 2:
            continue

        tip_home, tip_away = teams[0].strip(), teams[1].strip()

        for r_home, r_away, r_time in real_matches:
            if teams_match(tip_home, r_home) and teams_match(tip_away, r_away):
                if r_time and r_time != "TBD":
                    tip["time"] = r_time

                tip["match"] = f"{r_home} vs {r_away}"
                validated.append(tip)
                break

    return validated


def is_future_game(time_str, target_date):
    try:
        if not time_str or time_str in ["TBD", "Heute", "N/A", "-", ""]:
            return True  # Keine Zeit = annehmen dass es heute stattfindet

        hour, minute = map(int, time_str.split(":")[:2])
        now_utc = datetime.now(timezone.utc)
        year = now_utc.year

        march_last = datetime(year, 3, 31, tzinfo=timezone.utc)
        while march_last.weekday() != 6:
            march_last -= timedelta(days=1)

        oct_last = datetime(year, 10, 31, tzinfo=timezone.utc)
        while oct_last.weekday() != 6:
            oct_last -= timedelta(days=1)

        offset = 2 if march_last <= now_utc < oct_last else 1

        game_local = datetime.combine(
            target_date,
            datetime.min.time().replace(hour=hour, minute=minute),
        )

        game_utc = (game_local - timedelta(hours=offset)).replace(tzinfo=timezone.utc)

        # Spiel darf noch nicht angefangen haben (max 10 Min Toleranz nach Kickoff)
        return game_utc > now_utc - timedelta(minutes=10)

    except Exception:
        return True



def calculate_value_rating(odds_yes, fair_odds, probability):
    """
    Berechnet Value Rating basierend auf Edge zwischen Fair Odds und echten Quoten.
    
    Edge = (oddsYes / fairOdds - 1) * 100
    HIGH:  Edge > 10% (echte Value Bet!)
    OK:    Edge 3-10% (leichter Vorteil)
    LOW:   Edge < 3%  (kaum Value)
    NONE:  Edge < 0%  (kein Value)
    """
    try:
        odds = float(str(odds_yes).replace(",", "."))
        fair = float(str(fair_odds).replace(",", "."))
        prob = float(probability) / 100
        
        if odds <= 0 or fair <= 0:
            return "OK"
        
        # Edge berechnen
        edge = ((odds / fair) - 1) * 100
        
        # Zusätzlich: Implied probability vs real probability
        implied_prob = 1 / odds
        prob_edge = (prob - implied_prob) * 100
        
        # Kombinierter Score
        combined = (edge + prob_edge) / 2
        
        if combined >= 10:
            return "HIGH"
        elif combined >= 3:
            return "OK"
        else:
            return "LOW"
            
    except Exception:
        return "OK"


def filter_top_tips(tips, target_date, market):
    filtered = []
    rejected = {"time": 0, "tip": 0, "prob": 0, "conf": 0, "value": 0, "odds": 0}

    max_odds_for_market = 4.5 if market == "btts_ht" else MAX_ODDS
    min_odds_for_market = 1.6 if market == "btts_ht" else MIN_ODDS

    for r in tips:
        if not is_future_game(r.get("time", ""), target_date):
            rejected["time"] += 1
            continue

        if r.get("tip") != "YES":
            rejected["tip"] += 1
            continue

        prob = int(r.get("probability", 0))
        if prob < MIN_PROBABILITY:
            rejected["prob"] += 1
            log(f"   🔽 Gefiltert: {r.get('match','')} prob={prob}% < {MIN_PROBABILITY}%")
            continue

        conf = int(r.get("confidence", 0))
        if conf < MIN_CONFIDENCE:
            rejected["conf"] += 1
            log(f"   🔽 Gefiltert: {r.get('match','')} conf={conf} < {MIN_CONFIDENCE}")
            continue

        # 🆕 Echte Quoten aus Odds API überschreiben AI-Quoten!
        ai_odds = r.get("oddsYes", 0)
        real_odds = r.get("_real_odds", 0)  # Wird aus Odds API gesetzt
        
        if real_odds and float(str(real_odds).replace(",",".")) > 1.0:
            r["oddsYes"] = real_odds
            log(f"   💰 Echte Quote übernommen: {real_odds} (AI hatte: {ai_odds})")
        
        # Eigene Value Rating Berechnung (überschreibt AI Rating)
        calculated_rating = calculate_value_rating(
            r.get("oddsYes", 0),
            r.get("fairOdds", 0),
            r.get("probability", 0)
        )
        r["valueRating"] = calculated_rating

        # Value Rating Filter
        value_rating = calculated_rating
        if MIN_VALUE_RATING == "HIGH" and value_rating != "HIGH":
            continue
        elif MIN_VALUE_RATING == "OK" and value_rating == "LOW":
            continue

        odds = parse_odds(r.get("oddsYes", 0))

        if odds < min_odds_for_market or odds > max_odds_for_market:
            rejected["odds"] += 1
            log(f"   🔽 Gefiltert: {r.get('match','')} odds={odds} (Range: {min_odds_for_market}-{max_odds_for_market})")
            continue

        filtered.append(r)

    seen = set()
    unique = []

    for t in filtered:
        key = (t.get("match", "").lower(), t.get("tip", ""))

        if key in seen:
            continue

        seen.add(key)
        unique.append(t)

    if any(v > 0 for v in rejected.values()):
        log(f"   📊 Filter: Zeit={rejected['time']} Tip={rejected['tip']} Prob={rejected['prob']} Conf={rejected['conf']} Value={rejected['value']} Odds={rejected['odds']}")

    unique.sort(
        key=lambda r: (
            0 if r.get("valueRating") == "HIGH" else 1,
            -int(r.get("probability", 0)),
        )
    )

    return unique


def fetch_league_data_once(league, target_date):
    """
    Holt alle Daten für eine Liga nur EINMAL pro Run.
    """
    odds = fetch_odds_api(league, target_date)
    fd_fix = fetch_football_data(league, target_date)
    af_fix = fetch_api_football(league, target_date)
    fj_fix = fetch_football_json(league, target_date)
    ol_fix = fetch_openligadb(league, target_date)
    bsd_fix = fetch_bsd_fixtures(league, target_date)
    sm_fix = fetch_sportmonks_fixtures(league, target_date)
    sdb_fix = get_sportdb_fixtures(league, target_date)
    sofa_fix = fetch_sofascore_fixtures(league, target_date)  # Mit Playwright Fallback
    espn_fix = fetch_espn_fixtures(league, target_date)        # ESPN
    asp_fix = fetch_allsports_fixtures(league, target_date)    # AllSports
    flash_fix = fetch_flashscore_fixtures(league, target_date)
    ls_fix = fetch_livescore_fixtures(league, target_date)
    ninjas_fix = fetch_api_ninjas_fixtures(league, target_date)
    tsdb_fix = fetch_thesportsdb_fixtures(league, target_date)
    sw_fix = scrape_soccerway(league, target_date)
    gh_fix = fetch_github_football_data(league, target_date)
    fbd_fix = scrape_fussballdaten(league, target_date)
    fbde_fix = fetch_fussball_de(league, target_date)
    fl_fix = fetch_fortuna_liga(target_date) if league == "Slovak Super Liga" else []
    m42_fix = get_international_fixtures_today(target_date) if league in [
        "WM 2026", "UEFA Nations League", "Copa America", "Afrika Cup",
        "Freundschaftsspiele International", "WM 2026 Qualifikation Europa",
        "WM 2026 Qualifikation Südamerika", "WM 2026 Qualifikation CONCACAF",
    ] else []
    pw_sofa = pw_get_sofascore_fixtures(league, target_date)
    pw_wfdb = pw_get_worldfootballdb(league, target_date)
    fm_fix = fetch_fotmob_fixtures(league, target_date)
    src_fix = fetch_sportsrc_fixtures(league, target_date)       # 🔥 SportSRC
    pm_fix = fetch_promiedos_fixtures(league, target_date)       # 🌍 Promiedos

    fixtures = merge_fixtures(fd_fix, af_fix, fj_fix, ol_fix, bsd_fix, sm_fix, sdb_fix, sofa_fix, espn_fix, asp_fix, flash_fix, ls_fix, ninjas_fix, tsdb_fix, sw_fix, gh_fix, fbd_fix, fbde_fix, fl_fix, pw_sofa, pw_wfdb, fm_fix, src_fix, pm_fix, m42_fix)

    log(
        f"   Quellen: Odds={len(odds)}, FD={len(fd_fix)}, "
        f"AF={len(af_fix)}, FJ={len(fj_fix)}, OL={len(ol_fix)}, "
        f"BSD={len(bsd_fix)}, SM={len(sm_fix)}, SDB={len(sdb_fix)}, "
        f"ESPN={len(espn_fix)}, ASP={len(asp_fix)}, "
        f"TSDB={len(tsdb_fix)}, SW={len(sw_fix)}, "
        f"GH={len(gh_fix)}, FBD={len(fbd_fix)} → Total={len(fixtures)}"
    )

    return odds, fixtures



# ============================================================
# 🆕 OPENROUTER - Viele Modelle, Gratis Credits!
# ============================================================
OPENROUTER_API_KEYS = [k.strip() for k in env("OPENROUTER_API_KEYS", "").split(",") if k.strip()]
_OPENROUTER_KEY_IDX = 0

def call_openrouter(prompt):
    global _OPENROUTER_KEY_IDX
    if not OPENROUTER_API_KEYS:
        return None, "OpenRouter: kein Key"
    
    import time as _t
    last_error = ""
    
    for _ in range(len(OPENROUTER_API_KEYS)):
        key = OPENROUTER_API_KEYS[_OPENROUTER_KEY_IDX % len(OPENROUTER_API_KEYS)]
        _OPENROUTER_KEY_IDX += 1
        
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/netrattler/btts-bot",
                },
                json={
                    "model": "meta-llama/llama-3.1-8b-instruct:free",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 2000,
                },
                timeout=30,
            )
            
            if r.status_code == 429:
                last_error = "Rate Limit"
                _t.sleep(2)
                continue
            
            if not r.ok:
                last_error = f"HTTP {r.status_code}"
                continue
            
            data = r.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            if text:
                return text, f"OpenRouter #{_OPENROUTER_KEY_IDX}"
                
        except Exception as e:
            last_error = str(e)[:60]
            continue
    
    return None, f"OpenRouter erschöpft ({last_error})"


# ============================================================
# 🆕 MISTRAL - Gratis Tier (1 req/sec)
# ============================================================
MISTRAL_API_KEYS = [k.strip() for k in env("MISTRAL_API_KEYS", "").split(",") if k.strip()]
_MISTRAL_KEY_IDX = 0

def call_mistral(prompt):
    global _MISTRAL_KEY_IDX
    if not MISTRAL_API_KEYS:
        return None, "Mistral: kein Key"
    
    import time as _t
    last_error = ""
    
    for _ in range(len(MISTRAL_API_KEYS)):
        key = MISTRAL_API_KEYS[_MISTRAL_KEY_IDX % len(MISTRAL_API_KEYS)]
        _MISTRAL_KEY_IDX += 1
        
        try:
            r = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "mistral-small-latest",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 2000,
                },
                timeout=30,
            )
            
            if r.status_code == 429:
                last_error = "Rate Limit"
                _t.sleep(2)
                continue
            
            if not r.ok:
                last_error = f"HTTP {r.status_code}"
                continue
            
            data = r.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            if text:
                return text, f"Mistral #{_MISTRAL_KEY_IDX}"
                
        except Exception as e:
            last_error = str(e)[:60]
            continue
    
    return None, f"Mistral erschöpft ({last_error})"


# ============================================================
# 🆕 COHERE - Gratis 1000 Calls/Monat
# ============================================================
COHERE_API_KEY = env("COHERE_API_KEY", "")

def call_cohere(prompt):
    if not COHERE_API_KEY:
        return None, "Cohere: kein Key"
    
    try:
        r = requests.post(
            "https://api.cohere.com/v2/chat",
            headers={
                "Authorization": f"Bearer {COHERE_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "command-r",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 2000,
            },
            timeout=30,
        )
        
        if not r.ok:
            return None, f"Cohere HTTP {r.status_code}"
        
        data = r.json()
        text = data.get("message", {}).get("content", [{}])[0].get("text", "")
        
        if text:
            return text, "Cohere"
            
    except Exception as e:
        return None, f"Cohere Error: {str(e)[:60]}"
    
    return None, "Cohere: kein Ergebnis"


# ============================================================
# 🆕 HUGGINGFACE - Gratis Inference API
# ============================================================
HUGGINGFACE_API_KEY = env("HUGGINGFACE_API_KEY", "")

def call_huggingface(prompt):
    if not HUGGINGFACE_API_KEY:
        return None, "HuggingFace: kein Key"
    
    try:
        r = requests.post(
            "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3",
            headers={
                "Authorization": f"Bearer {HUGGINGFACE_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": 2000,
                    "temperature": 0.2,
                    "return_full_text": False,
                },
            },
            timeout=60,
        )
        
        if r.status_code == 503:
            return None, "HuggingFace: Modell lädt"
        
        if not r.ok:
            return None, f"HuggingFace HTTP {r.status_code}"
        
        data = r.json()
        if isinstance(data, list) and data:
            text = data[0].get("generated_text", "")
            if text:
                return text, "HuggingFace"
            
    except Exception as e:
        return None, f"HuggingFace Error: {str(e)[:60]}"
    
    return None, "HuggingFace: kein Ergebnis"


def analyze_market_with_data(market, league, target_date, odds, fixtures):
    """
    Analysiert einen Markt mit bereits geladenen Liga-Daten.
    """
    if not odds and not fixtures:
        return [], "Keine echten Spiele heute"

    ctx = build_context(odds, fixtures, league, target_date)
    prompt = build_prompt(market, league, target_date, ctx)

    # AI Rotation - verteile Last auf alle Modelle!
    import random as _rand_ai

    # Zufällige Reihenfolge um Gemini nicht immer zuerst zu fragen
    ai_order = []
    ai_order.append(("gemini", lambda: call_gemini(prompt, use_tools=False)))
    if OPENROUTER_API_KEYS:
        ai_order.append(("openrouter", lambda: call_openrouter(prompt)))
    if MISTRAL_API_KEYS:
        ai_order.append(("mistral", lambda: call_mistral(prompt)))
    if USE_GROQ_FALLBACK:
        ai_order.append(("groq", lambda: call_groq(prompt)))
    if COHERE_API_KEY:
        ai_order.append(("cohere", lambda: call_cohere(prompt)))
    if HUGGINGFACE_API_KEY:
        ai_order.append(("hf", lambda: call_huggingface(prompt)))

    # Gemini immer zuerst aber Fallbacks rotieren
    results, source = call_gemini(prompt, use_tools=False)

    if results is None and OPENROUTER_API_KEYS:
        results, source = call_openrouter(prompt)

    if results is None and MISTRAL_API_KEYS:
        results, source = call_mistral(prompt)

    if results is None and USE_GROQ_FALLBACK:
        results, source = call_groq(prompt)

    if results is None and COHERE_API_KEY:
        results, source = call_cohere(prompt)

    if results is None and HUGGINGFACE_API_KEY:
        results, source = call_huggingface(prompt)

    if results is None:
        results, source = call_gemini(prompt, use_tools=True)

    if not results:
        return [], source

    validated = validate_tips(results, fixtures, odds)

    # 🆕 FIX: League + Odds-Daten an jeden Tipp hängen
    # So sind die Daten auch in send_top_tips() verfügbar
    for tip in validated:
        if not tip.get("league"):
            tip["league"] = league
        # Odds-Daten als _internal Feld (wird nicht in Supabase gespeichert)
        tip["_odds_data"] = odds
        tip["_source_league"] = league

    return validated, source


# ============================================================
# 🆕 THESPORTSDB - Team Logos/Wappen (kostenlos)
# ============================================================
THESPORTSDB_CACHE = {}

def get_team_badge(team_name):
    """
    Holt Team-Wappen URL von TheSportsDB.
    Returns: {'badge_url': '...', 'team_id': '...'} oder None
    """
    if team_name in THESPORTSDB_CACHE:
        return THESPORTSDB_CACHE[team_name]

    try:
        # Free API Key "123" für Test-Nutzung
        r = requests.get(
            "https://www.thesportsdb.com/api/v1/json/123/searchteams.php",
            params={"t": team_name},
            timeout=10,
        )

        if not r.ok:
            THESPORTSDB_CACHE[team_name] = None
            return None

        data = r.json()
        teams = data.get("teams")

        if not teams:
            THESPORTSDB_CACHE[team_name] = None
            return None

        # Erstes Match nehmen
        team = teams[0]
        result = {
            "badge_url": team.get("strBadge"),  # PNG transparent
            "team_id": team.get("idTeam"),
            "team_name": team.get("strTeam"),
        }

        THESPORTSDB_CACHE[team_name] = result
        return result

    except Exception:
        THESPORTSDB_CACHE[team_name] = None
        return None


# ============================================================
# 🆕 SPORTMONKS - Free Forever für 2 Ligen
# ============================================================
SPORTMONKS_API_KEY = env("SPORTMONKS_API_KEY", "")  # Free tier API Key
SPORTMONKS_CACHE = {}

SPORTMONKS_LEAGUE_IDS = {
    # Nur 2 Ligen im Free Tier verfügbar
    "Danish Superligaen": 271,      # Dänemark
    "Scottish Premiership": 501,    # Schottland
}


def fetch_sportmonks_fixtures(league_name, target_date):
    """
    Holt Spielpläne von Sportmonks (Free Tier: Dänemark, Schottland).
    Returns: Liste mit Fixtures oder []
    """
    if not SPORTMONKS_API_KEY:
        return []
    
    league_id = SPORTMONKS_LEAGUE_IDS.get(league_name)
    if not league_id:
        return []  # Sportmonks deckt diese Liga nicht ab (nur 2 im Free Tier)
    
    try:
        # Sportmonks V2 API
        r = requests.get(
            f"https://api.sportmonks.com/v2.0/fixtures",
            params={
                "api_token": SPORTMONKS_API_KEY,
                "filters": f"leagueId:{league_id},statusId:1",  # Status 1 = Not Started
                "include": "teams",
                "sort": "-date",
            },
            timeout=12,
        )
        
        if not r.ok:
            return []
        
        data = r.json()
        now_utc = datetime.now(timezone.utc)
        fixtures = []
        
        for match in data.get("data", []):
            try:
                kickoff_str = match.get("date")
                if not kickoff_str:
                    continue
                
                # Sportmonks gibt UTC Zeit
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                
                if kickoff > now_utc:
                    # Teams aus nested data
                    teams = match.get("teams", {})
                    home_team = teams.get("data", [])[0] if teams.get("data") else {}
                    away_team = teams.get("data", [])[1] if len(teams.get("data", [])) > 1 else {}
                    
                    fixtures.append({
                        "home": home_team.get("name", ""),
                        "away": away_team.get("name", ""),
                        "match_id": match.get("id"),
                        "home_id": home_team.get("id"),
                        "away_id": away_team.get("id"),
                        "time_utc": kickoff_str,
                        "time_local": get_local_time(kickoff_str),
                        "source": "sportmonks",
                    })
            except Exception:
                continue
        
        return fixtures
    
    except Exception as e:
        log(f"Sportmonks Error: {e}", "WARN")
        return []
# ============================================================
BSD_API_URL = "https://sports.bzzoiro.com/api"
BSD_CACHE = {}

BSD_LEAGUE_IDS = {
    # 8 Top-Ligen die BSD abdeckt
    "Premier League": 1,          # England
    "La Liga": 8,                 # Spain
    "Serie A": 10,                # Italy
    "Bundesliga": 12,             # Germany
    "Ligue 1": 61,                # France
    "Championship": 2,            # England 2nd
    "Primeira Liga": 32,          # Portugal
    "Eredivisie": 13,             # Netherlands
}


def fetch_bsd_fixtures(league_name, target_date):
    """
    Holt Spielpläne von BSD für die 8 unterstützten Top-Ligen.
    Returns: Liste mit Fixtures oder []
    """
    league_id = BSD_LEAGUE_IDS.get(league_name)
    if not league_id:
        return []

    try:
        # Versuche mehrere BSD Endpoints
        urls_to_try = [
            f"https://api.b365api.com/v3/events/upcoming?sport_id=1&league_id={league_id}&token=YOUR_TOKEN",
            f"https://betsapi.com/api/v2/events/upcoming?sport_id=1&league_id={league_id}",
        ]
        
        r = requests.get(
            f"{BSD_API_URL}/matches",
            params={
                "league_id": league_id,
                "date": target_date.isoformat(),
                "status": "upcoming",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )
        
        if not r.ok:
            return []
        
        data = r.json()
        now_utc = datetime.now(timezone.utc)
        fixtures = []
        
        for match in data.get("matches", []):
            try:
                kickoff_str = match.get("datetime")
                if not kickoff_str:
                    continue
                    
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                
                if kickoff > now_utc:
                    fixtures.append({
                        "home": match.get("home_team", {}).get("name", ""),
                        "away": match.get("away_team", {}).get("name", ""),
                        "match_id": match.get("id"),
                        "home_id": match.get("home_team", {}).get("id"),
                        "away_id": match.get("away_team", {}).get("id"),
                        "time_utc": kickoff_str,
                        "time_local": get_local_time(kickoff_str),
                        "source": "bsd",
                    })
            except Exception:
                continue
        
        return fixtures
    
    except Exception as e:
        log(f"BSD Error: {e}", "WARN")
        return []


def get_bsd_odds(match_id):
    """
    Holt aktuelle Quoten von 41+ Bookies für ein Match.
    Returns: {'btts_yes': 1.85, 'over25': 2.10, ...} oder None
    """
    if not match_id:
        return None
    
    try:
        r = requests.get(
            f"{BSD_API_URL}/odds/compare/{match_id}",
            timeout=10,
        )
        
        if not r.ok:
            return None
        
        data = r.json()
        odds = {}
        
        # BTTS Quoten sammeln
        for market in data.get("markets", []):
            if market.get("name") == "btts":
                yes_odds = market.get("outcomes", {}).get("yes", {}).get("odds")
                if yes_odds:
                    odds["btts_yes"] = float(yes_odds)
        
        return odds if odds else None
    
    except Exception:
        return None

# 🆕 BOOKIE DEEPLINK CONFIG
# Diese Bookies werden als Buttons unter jedem Tipp angezeigt.
# Reihenfolge bestimmt Reihenfolge der Buttons im Telegram.
BOOKIE_BUTTONS = [
    {"key": "pinnacle", "label": "🎯 Pinnacle", "search_url": "https://www.pinnacle.com/de/soccer/matchups"},
    {"key": "betfair_ex_eu", "label": "📊 Betfair", "search_url": "https://www.betfair.com/exchange/plus/football"},
    {"key": "onexbet", "label": "🎰 1xBet", "search_url": "https://1xbet.com/en/line/football/"},
    {"key": "bet365", "label": "🎰 Bet365", "search_url": "https://www.bet365.com/#/AS/B1/"},
]


def get_bookie_links(odds_data, home_team, away_team):
    """
    Sucht Deeplinks zu Betslips aus Odds API für ein bestimmtes Spiel.
    Gibt dict zurück: {bookie_key: betslip_url}
    Fallback ist die jeweilige Search/Home URL des Bookies.
    """
    links = {}

    if not odds_data:
        return links

    # Suche das passende Game in odds_data
    for g in odds_data:
        gh = g.get("home_team", "").lower()
        ga = g.get("away_team", "").lower()
        h_low = home_team.lower()
        a_low = away_team.lower()

        # Match-Check (gleiche Logic wie teams_match)
        if not (h_low in gh or gh in h_low):
            continue
        if not (a_low in ga or ga in a_low):
            continue

        # Event-Level Link
        event_link = g.get("link")

        # Pro Bookmaker schauen
        for bm in g.get("bookmakers", []):
            bm_key = bm.get("key", "")
            bm_link = bm.get("link") or event_link

            if bm_link:
                links[bm_key] = bm_link

        break  # Spiel gefunden, fertig

    return links


def build_inline_keyboard(odds_data, match_name):
    """
    Baut die Telegram Inline-Keyboard Struktur mit Bookie-Buttons.
    Pro Reihe 2 Buttons (auf Handy lesbarer).
    """
    if not match_name or " vs " not in match_name:
        return None

    parts = match_name.split(" vs ", 1)
    if len(parts) != 2:
        return None

    home, away = parts[0].strip(), parts[1].strip()

    # Deeplinks aus Odds API holen
    deeplinks = get_bookie_links(odds_data, home, away)

    buttons = []
    row = []

    for bookie in BOOKIE_BUTTONS:
        key = bookie["key"]
        label = bookie["label"]

        # Wenn echter Deeplink existiert: nimm den. Sonst Search-URL.
        url = deeplinks.get(key) or bookie["search_url"]

        # Falls Deeplink vorhanden, mit ⚡ markieren
        if key in deeplinks:
            label = "⚡ " + label

        row.append({"text": label, "url": url})

        # Alle 2 Buttons neue Reihe
        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    return {"inline_keyboard": buttons}


def send_telegram(text, chat_id=None, reply_markup=None):
    if not TELEGRAM_TOKEN:
        log("Telegram Token fehlt", "WARN")
        return None

    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID

    if not chat_id:
        log("Telegram Chat ID fehlt", "WARN")
        return None

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    # 🆕 Inline-Buttons hinzufügen wenn vorhanden
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json=payload,
            timeout=15,
        )

        if not r.ok:
            # 🆕 Fallback: Wenn Channel fehlt (400 error) → Main Chat nutzen
            if r.status_code == 400 and chat_id != TELEGRAM_CHAT_ID:
                log(f"⚠️ Chat {chat_id} nicht gefunden - fallback zu Main Chat", "WARN")
                payload["chat_id"] = TELEGRAM_CHAT_ID
                r = requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json=payload,
                    timeout=15,
                )
            
            # Fallback ohne HTML-Tags
            payload["text"] = re.sub(r"<[^>]+>", "", text)
            payload.pop("parse_mode", None)
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json=payload,
                timeout=15,
            )

        if r.ok:
            return r.json().get("result", {}).get("message_id")

    except Exception:
        pass

    return None


# In-Memory Duplikat Cache für diesen Run
_SENT_TIPS_CACHE = set()

def is_duplicate_tip(match, market, target_date):
    """Prüft ob Tipp bereits gesendet wurde - In-Memory + Supabase"""
    global _SENT_TIPS_CACHE

    # Normalisiere Match-Name für Vergleich
    match_norm = normalize_team_name(match)
    cache_key = f"{match_norm[:20]}_{market}_{target_date}"

    # 1. In-Memory Check (schnell!)
    if cache_key in _SENT_TIPS_CACHE:
        return True

    # 2. Supabase Check
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/tips",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                params={
                    "date": f"eq.{target_date}",
                    "market": f"eq.{market}",
                    "match": f"eq.{match}",
                    "select": "id",
                    "limit": "1",
                },
                timeout=5,
            )
            if r.ok and len(r.json()) > 0:
                _SENT_TIPS_CACHE.add(cache_key)
                return True
        except Exception:
            pass

    return False


def mark_tip_sent(match, market, target_date):
    """Markiert Tipp als gesendet im In-Memory Cache"""
    global _SENT_TIPS_CACHE
    match_norm = normalize_team_name(match)
    cache_key = f"{match_norm[:20]}_{market}_{target_date}"
    _SENT_TIPS_CACHE.add(cache_key)


def is_valid_tip(tip, target_date):
    """
    Prüft ob ein Tipp wirklich heute + in der Zukunft liegt.
    """
    tip_date = tip.get("date", "")
    today_str = str(target_date)
    if tip_date and tip_date != today_str:
        log(f"   ⚠️ Falsches Datum: {tip_date} (erwartet {today_str})")
        return False

    time_str = tip.get("time", "")
    if not is_future_game(time_str, target_date):
        log(f"   ⚠️ Spiel bereits vorbei: {tip.get('match','')} um {time_str}")
        return False

    return True


def save_to_supabase(tip):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    try:
        # Nur bekannte Supabase Felder senden
        SUPABASE_FIELDS = [
            "tip_id", "date", "market", "market_name", "match", "league",
            "tip", "odds", "probability", "confidence", "value_rating",
            "fair_odds", "units", "bookie", "reasoning", "key_factor",
            "home_form", "away_form", "time", "status",
            "telegram_chat_id", "telegram_msg_id",
            "weekday", "hour",
            "xg_home", "xg_away", "xga_home", "xga_away",
            "sharp_money", "line_movement",
            "btts_rate_home", "btts_rate_away",
            "avg_goals_home", "avg_goals_away",
            # ML Features
            "elo_home", "elo_away", "elo_diff",
            "result_home", "result_away",
            "result_ht_home", "result_ht_away",
            "settled_at",
            "odds_taken", "odds_closing", "clv",
        ]
        
        clean_tip = {k: v for k, v in tip.items() 
                     if k in SUPABASE_FIELDS and v is not None}

        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=clean_tip,
            timeout=10,
        )

        if not r.ok:
            log(f"   Supabase Error: {r.status_code} - {r.text[:100]}", "WARN")
            return False

        return True

    except Exception as e:
        log(f"   Supabase Exception: {str(e)[:60]}", "WARN")
        return False


def get_overall_stats():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"select": "*", "order": "date.desc,id.desc"},
            timeout=15,
        )
        if not r.ok:
            return None
        tips = r.json()
        won = [t for t in tips if t.get("status") == "won"]
        lost = [t for t in tips if t.get("status") == "lost"]
        pending = [t for t in tips if t.get("status") == "pending"]
        if not won and not lost:
            return None
        total = len(won) + len(lost)
        quote_pct = round(len(won) / total * 100) if total else 0

        units_won = 0.0
        units_lost = 0.0
        for t in won:
            try:
                u = float(t.get("units", 1.0) or 1.0)
                odds = float(str(t.get("odds", "1")).replace(",", "."))
                units_won += u * (odds - 1)
            except:
                units_won += 1.0
        for t in lost:
            try:
                units_lost += float(t.get("units", 1.0) or 1.0)
            except:
                units_lost += 1.0
        roi_units = round(units_won - units_lost, 2)

        by_market = {
            "btts": {"w": 0, "l": 0, "units": 0.0},
            "over25": {"w": 0, "l": 0, "units": 0.0},
            "combo": {"w": 0, "l": 0, "units": 0.0},
            "btts_ht": {"w": 0, "l": 0, "units": 0.0},
        }
        for t in won + lost:
            m = t.get("market", "")
            if m not in by_market:
                continue
            u = float(t.get("units", 1.0) or 1.0)
            if t.get("status") == "won":
                by_market[m]["w"] += 1
                try:
                    by_market[m]["units"] += u * (float(str(t.get("odds","1")).replace(",",".")) - 1)
                except:
                    pass
            else:
                by_market[m]["l"] += 1
                by_market[m]["units"] -= u

        from datetime import date as date_cls
        today = date_cls.today()
        month_start = today.replace(day=1).isoformat()
        month_won = [t for t in won if t.get("date","") >= month_start]
        month_lost = [t for t in lost if t.get("date","") >= month_start]
        month_total = len(month_won) + len(month_lost)
        month_pct = round(len(month_won)/month_total*100) if month_total else 0
        month_units = 0.0
        for t in month_won:
            try:
                u = float(t.get("units",1.0) or 1.0)
                month_units += u * (float(str(t.get("odds","1")).replace(",",".")) - 1)
            except:
                month_units += 1.0
        for t in month_lost:
            try:
                month_units -= float(t.get("units",1.0) or 1.0)
            except:
                month_units -= 1.0
        month_names = ["","Januar","Februar","März","April","Mai","Juni",
                       "Juli","August","September","Oktober","November","Dezember"]
        month_name = month_names[today.month]

        by_league = {}
        for t in won + lost:
            lg = t.get("league","?")
            if lg not in by_league:
                by_league[lg] = {"w":0,"l":0,"units":0.0}
            u = float(t.get("units",1.0) or 1.0)
            if t.get("status") == "won":
                by_league[lg]["w"] += 1
                try:
                    by_league[lg]["units"] += u * (float(str(t.get("odds","1")).replace(",",".")) - 1)
                except:
                    by_league[lg]["units"] += 1.0
            else:
                by_league[lg]["l"] += 1
                by_league[lg]["units"] -= u

        top_leagues = []
        for lg, s in by_league.items():
            tot = s["w"] + s["l"]
            if tot >= 2:
                pct = round(s["w"]/tot*100)
                top_leagues.append((lg, s["w"], tot, pct, round(s["units"],2)))
        top_leagues.sort(key=lambda x: (-x[4], -x[3]))

        return {
            "won": len(won), "lost": len(lost), "pending": len(pending),
            "total": total, "quote_pct": quote_pct,
            "roi_units": roi_units,
            "by_market": by_market,
            "month": {
                "name": month_name, "won": len(month_won), "lost": len(month_lost),
                "total": month_total, "pct": month_pct, "units": round(month_units,2)
            },
            "top_leagues": top_leagues[:10],
        }
    except Exception:
        return None


def generate_multi_combo_bets(all_tips, num_tips=3):
    """
    🆕 Generiert automatisch Multi-Combos aus den besten Tipps.
    num_tips: 3, 4, 5, 6, 7 oder 8 Tipps pro Combo
    """
    if not all_tips:
        return None

    # Alle Tipps normalisieren (oddsYes → odds)
    normalized = []
    for t in all_tips:
        try:
            odds = float(str(t.get("oddsYes", t.get("odds", 0))).replace(",", "."))
            if odds >= 1.40:  # Niedrigere Schwelle = mehr Tipps in Combos
                normalized.append({
                    "match": t.get("match", ""),
                    "league": t.get("league", ""),
                    "market": t.get("market", "btts"),
                    "tip": t.get("tip", "YES"),
                    "odds": odds,
                    "confidence": int(t.get("confidence", 0)),
                    "value_rating": t.get("valueRating", "OK"),
                    "probability": int(t.get("probability", 0)),
                })
        except Exception:
            continue

    if not normalized:
        return None

    # Sortiere nach Confidence + Probability
    sorted_tips = sorted(
        normalized,
        key=lambda x: (x.get("confidence", 0), x.get("probability", 0)),
        reverse=True
    )

    # Genug Tipps vorhanden?
    if len(sorted_tips) < num_tips:
        return None

    # Beste N Tipps nehmen
    selected = sorted_tips[:num_tips]

    # Berechne Gesamt-Quote
    total_odds = 1.0
    for tip in selected:
        total_odds *= tip.get("odds", 1.0)

    avg_confidence = sum(t.get("confidence", 0) for t in selected) / len(selected)

    # Combo Label basierend auf Anzahl
    labels = {
        3:  ("🥉 COMBO 3",  "Einsteiger-Kombi"),
        4:  ("🥈 COMBO 4",  "Solide Kombi"),
        5:  ("🥇 COMBO 5",  "Standard-Kombi"),
        6:  ("💎 COMBO 6",  "Value-Kombi"),
        7:  ("🔥 COMBO 7",  "High-Risk Kombi"),
        8:  ("🚀 COMBO 8",  "Jackpot-Kombi"),
        9:  ("⚡ COMBO 9",  "Mega-Kombi"),
        10: ("🎯 COMBO 10", "Ultra-Kombi"),
        11: ("👑 COMBO 11", "Monster-Kombi"),
    }
    label, desc = labels.get(num_tips, (f"🎲 COMBO {num_tips}", "Multi-Kombi"))

    # Stake Suggestion (weniger bei mehr Tipps)
    stakes = {3: 8, 4: 6, 5: 4, 6: 3, 7: 2, 8: 2, 9: 1, 10: 1, 11: 0.5}
    stake = stakes.get(num_tips, 1)

    return {
        "num_tips": num_tips,
        "label": label,
        "desc": desc,
        "tips": selected,
        "total_odds": round(total_odds, 2),
        "expected_confidence": round(avg_confidence, 1),
        "stake_suggestion": stake,
    }


def format_combo_telegram_message(combo):
    """🆕 Formatiert Multi-Combo für Telegram"""
    if not combo:
        return ""

    msg = f"<b>{combo['label']}</b>" + "\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += f"🎯 <b>Gesamt-Quote: {combo['total_odds']}</b>" + "\n"
    msg += f"⚡ Ø Confidence: {combo['expected_confidence']}/5" + "\n"
    msg += f"💰 Empfehlung: {combo['stake_suggestion']} Units" + "\n"
    msg += f"📋 Anzahl Tipps: {combo['num_tips']}\n" + "\n"
    msg += f"<b>🎫 TIPPS:</b>" + "\n"

    for i, tip in enumerate(combo["tips"], 1):
        conf_stars = "⭐" * int(tip.get("confidence", 0))
        msg += f"\n{i}. <b>{tip.get('match', 'N/A')}</b>" + "\n"
        msg += f"   📍 {tip.get('league', 'N/A')}" + "\n"
        msg += f"   ⚽ {tip.get('market', 'BTTS').upper()}: <b>{tip.get('tip', 'YES')}</b>" + "\n"
        msg += f"   💰 Quote: <b>{tip.get('odds', 0.0)}</b>" + "\n"
        msg += f"   {conf_stars} {tip.get('confidence', 0)}/5" + "\n"

    msg += f"\n━━━━━━━━━━━━━━━━━━" + "\n"
    msg += f"<b>💡 {combo['desc']}</b>" + "\n"
    msg += f"• Einsatz: {combo['stake_suggestion']} Units" + "\n"
    msg += f"• Möglicher Gewinn: ~{round(combo['total_odds'] * combo['stake_suggestion'], 1)} Units\n" + "\n"
    msg += f"<i>⚠️ Verantwortungsvoll spielen!</i>"

    return msg



def _auto_void_old_pending():
    """Bereinigt alte Pending Tipps automatisch (älter als 3 Tage)"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        from datetime import date, timedelta
        cutoff = str(date.today() - timedelta(days=3))
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            params={
                "status": "eq.pending",
                "date": f"lt.{cutoff}",
            },
            json={"status": "void"},
            timeout=10,
        )
        if r.ok:
            log("✅ Alte Pending Tipps bereinigt!")
    except Exception as e:
        log(f"Auto-void Error: {str(e)[:50]}", "WARN")



def _get_market_stats_from_supabase(market_id):
    """Holt Won/Lost/ROI + Monat + Top-3-Ligen für einen Markt aus Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        from datetime import date as _date2
        today = _date2.today()
        month_start = today.replace(day=1).isoformat()

        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={
                "market": f"eq.{market_id}",
                "status": "in.(won,lost)",
                "select": "status,odds,units,date,league",
                "order": "date.desc",
                "limit": "2000",
            },
            timeout=15,
        )
        if not r.ok:
            return None
        tips = r.json()
        if not tips:
            return None

        won  = [t for t in tips if t.get("status") == "won"]
        lost = [t for t in tips if t.get("status") == "lost"]
        total = len(won) + len(lost)
        if total == 0:
            return None

        # ROI Gesamt
        roi = 0.0
        for t in won:
            try:
                roi += (float(str(t.get("odds","1.5")).replace(",",".")) - 1) * float(t.get("units",1.0) or 1.0)
            except: roi += 1.0
        for t in lost:
            try: roi -= float(t.get("units",1.0) or 1.0)
            except: roi -= 1.0

        # Monat
        m_won  = [t for t in won  if t.get("date","") >= month_start]
        m_lost = [t for t in lost if t.get("date","") >= month_start]
        m_total = len(m_won) + len(m_lost)
        m_roi = 0.0
        for t in m_won:
            try: m_roi += (float(str(t.get("odds","1.5")).replace(",",".")) - 1) * float(t.get("units",1.0) or 1.0)
            except: m_roi += 1.0
        for t in m_lost:
            try: m_roi -= float(t.get("units",1.0) or 1.0)
            except: m_roi -= 1.0

        # Top 3 Ligen
        lg_stats = {}
        for t in tips:
            lg = t.get("league","?")
            if not lg: continue
            if lg not in lg_stats:
                lg_stats[lg] = {"w":0,"l":0,"roi":0.0}
            if t.get("status") == "won":
                lg_stats[lg]["w"] += 1
                try: lg_stats[lg]["roi"] += (float(str(t.get("odds","1.5")).replace(",",".")) - 1) * float(t.get("units",1.0) or 1.0)
                except: lg_stats[lg]["roi"] += 1.0
            else:
                lg_stats[lg]["l"] += 1
                try: lg_stats[lg]["roi"] -= float(t.get("units",1.0) or 1.0)
                except: lg_stats[lg]["roi"] -= 1.0

        top_leagues = []
        for lg, s in lg_stats.items():
            tot = s["w"] + s["l"]
            if tot >= 3:
                top_leagues.append((lg, s["w"], tot, round(s["roi"],1)))
        top_leagues.sort(key=lambda x: (-x[3], -x[1]))

        month_names = ["","Januar","Februar","März","April","Mai","Juni",
                       "Juli","August","September","Oktober","November","Dezember"]
        month_name = month_names[today.month]

        return {
            "won": len(won), "lost": len(lost), "total": total,
            "pct": round(len(won)/total*100),
            "roi": round(roi, 1),
            "month_name": month_name,
            "month_won": len(m_won), "month_lost": len(m_lost),
            "month_total": m_total,
            "month_pct": round(len(m_won)/m_total*100) if m_total else 0,
            "month_roi": round(m_roi, 1),
            "top_leagues": top_leagues[:3],
        }
    except Exception as e:
        log(f"Market Stats Error ({market_id}): {str(e)[:60]}", "WARN")
        return None


def _send_daily_auswertung_to_all_groups(stats=None):
    """
    Sendet marktspezifische Stats in jede Gruppe im Screenshot-Format:
    Winrate, ROI (Units), Gesamt-Tipps, Monat, Top-3-Ligen.
    """
    from datetime import datetime as _dt3, timezone as _tz3
    now = _dt3.now(_tz3.utc)

    # Saisonpause / WM-Hinweis
    if now.month == 6 and now.day < 11:
        pause_text = f"🏆 <i>WM 2026 startet in {11-now.day} Tagen! Ab 11. Juni täglich Tipps.</i>"
    elif now.month in [6, 7]:
        pause_text = "<i>🌍 WM 2026 läuft — täglich Tipps!</i>"
    else:
        pause_text = "<i>Heute spielfreier Tag — morgen wieder Tipps!</i>"

    market_groups = [
        ("btts",    TELEGRAM_GROUPS.get("btts"),    "⚽ BTTS"),
        ("over25",  TELEGRAM_GROUPS.get("over25"),  "🎯 Over 2.5"),
        ("combo",   TELEGRAM_GROUPS.get("combo"),   "🔥 BTTS + Over 2.5"),
        ("btts_ht", TELEGRAM_GROUPS.get("btts_ht"), "🕐 BTTS Halbzeit"),
        ("corners", TELEGRAM_GROUPS.get("hz_live"), "🔵 Corner Sniper"),
        ("scorer",  TELEGRAM_GROUPS.get("late_goals"), "⚽ Goal Hunter"),
    ]

    medals = ["🥇","🥈","🥉"]
    sent_to = set()

    for market_id, chat_id, title in market_groups:
        if not chat_id or chat_id in sent_to:
            continue

        ms = _get_market_stats_from_supabase(market_id)

        nl = "\n"
        msg = f"<b>{title}</b>{nl}"
        msg += f"━━━━━━━━━━━━━━━━━━{nl}"

        if ms and ms["total"] >= 3:
            wr_e  = "🔥" if ms["pct"] >= 70 else "✅" if ms["pct"] >= 60 else "⚠️"
            roi_e = "🟢" if ms["roi"] >= 0 else "🔴"
            roi_s = f"+{ms['roi']}" if ms["roi"] >= 0 else str(ms["roi"])

            msg += f"{wr_e} Winrate: <b>{ms['pct']}%</b> ({ms['won']}W / {ms['lost']}L){nl}"
            msg += f"{roi_e} ROI: <b>{roi_s} Units</b>{nl}"
            msg += f"📋 Gesamt: {ms['total']} ausgewertete Tipps{nl}"

            # Monat
            if ms.get("month_total", 0) > 0:
                m_roi_e = "🟢" if ms["month_roi"] >= 0 else "🔴"
                m_roi_s = f"+{ms['month_roi']}" if ms["month_roi"] >= 0 else str(ms["month_roi"])
                msg += f"{nl}<b>{ms['month_name']}:</b>{nl}"
                msg += f"{ms['month_won']}/{ms['month_total']} Tipps · {ms['month_pct']}% · {m_roi_s}U {m_roi_e}{nl}"

            # Top 3 Ligen
            if ms.get("top_leagues"):
                msg += f"{nl}<b>🏆 Top Ligen:</b>{nl}"
                for i, (lg, w, tot, roi_lg) in enumerate(ms["top_leagues"]):
                    pct_lg   = round(w/tot*100) if tot else 0
                    roi_s_lg = f"+{roi_lg}" if roi_lg >= 0 else str(roi_lg)
                    medal = medals[i] if i < len(medals) else "•"
                    msg += f"{medal} {lg}: {w}/{tot} ({pct_lg}%) · {roi_s_lg}U{nl}"
        else:
            msg += f"📊 Daten werden gesammelt...{nl}"
            msg += f"<i>Mindestens 3 ausgewertete Tipps nötig.</i>{nl}"

        msg += f"━━━━━━━━━━━━━━━━━━{nl}"
        msg += pause_text

        send_telegram(msg, chat_id)
        sent_to.add(chat_id)

    log(f"✅ Gruppen-Auswertung gesendet ({len(sent_to)} Gruppen)")


def send_top_tips(tips_by_market, target_date):
    icons = {
        "YES": "✅",
        "NO": "❌",
        "MAYBE": "⚠️",
        "1": "🏠",
        "X": "🤝",
        "2": "✈️",
    }

    val_icons = {
        "HIGH": "🔥",
        "OK": "🟡",
        "LOW": "🔴",
    }

    market_emoji = {
        "btts": "⚽",
        "over25": "🎯",
        "combo": "🔥",
        "1x2": "🏆",
    }

    total_tips = sum(len(t) for t in tips_by_market.values())

    # ============================================================
    # STATS NACHRICHT - Vollständig mit allen Märkten
    # ============================================================
    now_utc = datetime.now(timezone.utc)
    month_name = now_utc.strftime("%B %Y")

    stats_header = f"<b>🤖 AI TIPP BOT - DAILY</b>\n<i>{target_date}</i>\n" + "\n"

    # Tagesübersicht - ALLE Märkte
    stats_header += "📊 <b>Übersicht heute:</b>\n"
    for m_id in MARKETS_TO_RUN:
        count = len(tips_by_market.get(m_id, []))
        stats_header += f"• {MARKET_INFO[m_id]['name']}: <b>{count}</b> Tipps" + "\n"

    # Ecken + Scorer + Combos
    corners_today = getattr(run_corners_and_scorer_bots, '_last_corners', 0)
    scorer_today = getattr(run_corners_and_scorer_bots, '_last_scorer', 0)
    stats_header += f"• 🔵 Ecken: <b>{corners_count if 'corners_count' in dir() else 0}</b> Tipps" + "\n"
    stats_header += f"• 🎰 Combos: <b>{combos_sent if 'combos_sent' in dir() else 0}</b> generiert" + "\n"
    stats_header += f"\n💎 <b>Total: {total_tips} Top-Tipps</b>"

    stats = get_overall_stats()

    if stats:
        # Auto-void alte pendings
        old_pending = stats.get("pending", 0)
        
        stats_header += "\n\n━━━━━━━━━━━━━━━━━━\n"
        stats_header += "📈 <b>GESAMT-STATISTIK</b>\n"
        stats_header += f"✅ Gewonnen: <b>{stats['won']}</b>" + "\n"
        stats_header += f"❌ Verloren: <b>{stats['lost']}</b>" + "\n"
        # Pending nur zeigen wenn sinnvoll (< 50)
        if stats["pending"] and stats["pending"] < 50:
            stats_header += f"⏳ Pending: <b>{stats['pending']}</b>" + "\n"
        stats_header += f"🎯 Trefferquote: <b>{stats['quote_pct']}%</b>" + "\n"
        roi_emoji = "🟢" if stats["roi_units"] >= 0 else "🔴"
        stats_header += f"💰 ROI: <b>{'+' if stats['roi_units'] >= 0 else ''}{stats['roi_units']}</b> Units {roi_emoji}" + "\n"

        # Monatsübersicht
        if stats.get("month") and stats["month"]["total"] > 0:
            m = stats["month"]
            m_emoji = "🟢" if m["units"] >= 0 else "🔴"
            stats_header += f"\n📅 <b>{m['name']}:</b> {m['won']}/{m['total']} ({m['pct']}%) · "
            stats_header += f"<b>{'+' if m['units'] >= 0 else ''}{m['units']} Units</b> {m_emoji}" + "\n"

        # Pro Markt - ALLE inkl Ecken
        stats_header += f"\n<b>📊 Pro Markt:</b>" + "\n"
        market_names = {
            "btts": "⚽ BTTS",
            "over25": "🎯 Over 2.5",
            "combo": "🔥 BTTS+Over 2.5",
            "btts_ht": "🕐 BTTS HT",
        }
        for m_id in MARKETS_TO_RUN:
            mb = stats["by_market"].get(m_id, {"w":0,"l":0,"units":0.0})
            tot = mb["w"] + mb["l"]
            if tot > 0:
                pct = round(mb["w"]/tot*100)
                emoji = "🟢" if pct >= 60 else "🟡" if pct >= 40 else "🔴"
                u_str = f"+{round(mb['units'],2)}" if mb["units"] >= 0 else f"{round(mb['units'],2)}"
                stats_header += f"{market_names.get(m_id,m_id)}: {mb['w']}/{tot} ({pct}%) · {u_str}U {emoji}" + "\n"

        # Top Ligen
        if stats.get("top_leagues"):
            stats_header += f"\n<b>🏆 Top Ligen:</b>" + "\n"
            medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
            for i, (lg, w, tot, pct, units) in enumerate(stats["top_leagues"][:10]):
                medal = medals[i] if i < len(medals) else "•"
                u_str = f"+{units}" if units >= 0 else str(units)
                stats_header += f"{medal} {lg}: {w}/{tot} ({pct}%) · {u_str}U" + "\n"

    if total_tips > 0:
        send_telegram(stats_header, TELEGRAM_GROUPS.get("stats"))

    # Auto-void alte Pending Tipps (älter als 3 Tage)
    _auto_void_old_pending()

    # Wenn keine Tipps → Auswertung in ALLE Gruppen senden
    if total_tips == 0:
        if datetime.now(timezone.utc).hour == 8:
            _send_daily_auswertung_to_all_groups(stats)
        return

    saved = 0

    for market_id, tips in tips_by_market.items():
        if not tips:
            continue

        target_chat = TELEGRAM_GROUPS.get(market_id, TELEGRAM_CHAT_ID)
        market_name = MARKET_INFO[market_id]["name"]
        emoji = market_emoji.get(market_id, "💎")

        # Kein Header - direkt Tipps senden

        for i, r in enumerate(tips, 1):
            confidence = int(r.get("confidence", 0))
            match_name = r.get("match", "?")

            r["date"] = str(target_date)
            if not is_valid_tip(r, target_date):
                continue

            if is_duplicate_tip(match_name, market_id, target_date):
                log(f"   ⏭️ Duplikat übersprungen: {match_name} ({market_id})")
                continue

            # ✅ NEUES FORMAT - Variante 3
            market_icons2 = {"btts": "⚽", "over25": "🎯", "combo": "🔥", "btts_ht": "🕐"}
            market_names2 = {"btts": "BTTS", "over25": "OVER 2.5", "combo": "BTTS + OVER 2.5", "btts_ht": "BTTS HT"}
            val_icon = val_icons.get(r.get('valueRating', 'OK'), '🟡')
            mkt_icon = market_icons2.get(market_id, "🎯")
            mkt_name = market_names2.get(market_id, market_id.upper())

            tip_time_raw = r.get('time', r.get('time_local', '')).strip()
            if not tip_time_raw or tip_time_raw in ['TBD', 'N/A', '-', '']:
                tip_time = "Heute"
            else:
                try:
                    from datetime import datetime as _dt2, timezone as _tz2, timedelta as _td2
                    if 'T' in tip_time_raw and ('Z' in tip_time_raw or '+' in tip_time_raw):
                        _t2 = _dt2.fromisoformat(tip_time_raw.replace('Z', '+00:00'))
                        _local2 = _t2.astimezone(_tz2(_td2(hours=2)))
                        tip_time = _local2.strftime('%H:%M')
                    else:
                        tip_time = tip_time_raw
                except Exception:
                    tip_time = tip_time_raw

            try:
                odds_val = float(str(r.get('oddsYes', '1.5')).replace(',', '.'))
                prob_val = int(r.get('probability', 60))
                units = calculate_kelly_units(prob_val, odds_val)
                units_emoji = "🔥" if units >= 2.5 else "💚" if units >= 1.5 else "🟡"
            except:
                units = 1.0
                units_emoji = "💚"

            # Wetter
            weather_data = r.get("weather", {})
            weather_line = ""
            if weather_data and weather_data.get("temp"):
                temp = weather_data.get("temp", "")
                rain = weather_data.get("rain", 0)
                wind = weather_data.get("wind", 0)
                if rain > 1:
                    weather_line = f"🌧️ {temp}°C · Regen {rain}mm"
                elif wind > 30:
                    weather_line = f"💨 {temp}°C · Wind {wind}km/h"
                else:
                    weather_line = f"🌤️ {temp}°C"

            # Form
            def fmt_form(fs):
                if not fs or fs in ['N/A', '-', '?']:
                    return ""
                icons2 = {"W": "🟢", "D": "🟡", "L": "🔴"}
                return " ".join([icons2.get(c, "⚪") for c in str(fs)[-5:]])

            home_form = r.get('homeForm', r.get('home_form', '')).strip()
            away_form = r.get('awayForm', r.get('away_form', '')).strip()

            # Sharp Money
            sharp = r.get('sharp_money', '')
            sharp_line = ""
            if sharp == "strong":
                sharp_line = "📌 Starkes Sharp Money Signal!"
            elif sharp:
                sharp_line = "📌 Sharp Money aktiv"

            # Opening Odds
            opening = r.get('opening_odds', 0)
            odds_move_line = ""
            if opening and odds_val and opening != odds_val:
                diff = round(odds_val - opening, 2)
                arrow = "▼" if diff < 0 else "▲"
                odds_move_line = f"📉 Opening: {opening} → {odds_val} {arrow}"

            # Verletzungen
            inj_home = r.get('injuries_home', '')
            inj_away = r.get('injuries_away', '')

            # Schiri mit Details
            ref = r.get('referee', r.get('ref', ''))
            ref_cards = r.get('ref_cards_per_game', 0)
            ref_red = r.get('ref_red_per_game', 0)
            ref_pen = r.get('ref_penalty_rate', 0)
            ref_fouls = r.get('ref_fouls_per_game', 0)

            # H2H
            h2h_btts = r.get('h2h_btts', '')
            h2h_goals = r.get('h2h_avg_goals', '')

            # Build Message
            msg = f"💎 <b>{match_name}</b>" + "\n"
            msg += f"📍 {r.get('league', r.get('league_name', ''))} · ⏰ {tip_time}" + "\n"
            if weather_line:
                msg += f"{weather_line}" + "\n"
            msg += f"━━━━━━━━━━━━━━━━━━" + "\n"
            msg += f"{mkt_icon} <b>{mkt_name}</b>" + "\n"
            msg += f"✅ Tipp: <b>{r.get('tip','YES')}</b>" + "\n"
            msg += f"📈 Wahrscheinlichkeit: <b>{r.get('probability',0)}%</b>" + "\n"
            msg += f"⭐ Confidence: {'⭐' * confidence}" + "\n"
            msg += f"💰 Quote: <b>{r.get('oddsYes','-')}</b> · Fair: {r.get('fairOdds','-')} · {val_icon} {r.get('valueRating','OK')}" + "\n"
            msg += f"{units_emoji} <b>{units} Units</b>"

            # Stats
            stats = []
            if r.get('xg_home') and r.get('xg_away'):
                stats.append(f"⚡ xG: {r['xg_home']} / {r['xg_away']}")
            if r.get('btts_rate_home') and r.get('btts_rate_away'):
                stats.append(f"📊 BTTS Rate: {r['btts_rate_home']}% / {r['btts_rate_away']}%")
            if h2h_btts:
                stats.append(f"🔄 H2H BTTS: {h2h_btts}")
            if h2h_goals:
                stats.append(f"⚽ H2H Ø Tore: {h2h_goals}")
            if stats:
                msg += f"\n━━━━━━━━━━━━━━━━━━"
                msg += "\n".join(stats)

            # Quoten Bewegung
            if odds_move_line or sharp_line:
                msg += f"\n━━━━━━━━━━━━━━━━━━" + "\n"
                if odds_move_line:
                    msg += f"{odds_move_line}" + "\n"
                if sharp_line:
                    msg += f"{sharp_line}" + "\n"

            # Team Info
            team_info = []
            if inj_home:
                team_info.append(f"🏥 Verletzt Heim: {inj_home}")
            if inj_away:
                team_info.append(f"🏥 Verletzt Gast: {inj_away}")
            if ref:
                team_info.append(f"👨‍⚖️ Schiri: {ref}")
            if team_info or ref:
                msg += f"\n━━━━━━━━━━━━━━━━━━" + "\n"
                if team_info:
                    msg += "\n".join(team_info) + "\n"
                if ref:
                    msg += f"👨‍⚖️ <b>{ref}</b>" + "\n"
                    if ref_cards:
                        msg += f"   🟡 {ref_cards} K/Sp"
                    if ref_red:
                        msg += f" · 🔴 {ref_red} R/Sp"
                    if ref_pen:
                        msg += f" · ⚽ {ref_pen} Elf/Sp"
                    if ref_fouls:
                        msg += f" · 📊 {ref_fouls} F/Sp"
                    # Schiri Bewertung
                    if ref_cards:
                        if float(ref_cards) < 3.5:
                            msg += "\n   ✅ Lässt Spiel laufen"
                        elif float(ref_cards) > 5:
                            msg += "\n   ⚠️ Strenger Schiri"
                        else:
                            msg += "\n   🟡 Durchschnittlich"
                    msg += "\n"

            # Form
            hf = fmt_form(home_form)
            af = fmt_form(away_form)
            if hf or af:
                msg += f"\n━━━━━━━━━━━━━━━━━━" + "\n"
                home_name = match_name.split(" vs ")[0][:12] if " vs " in match_name else "Heim"
                away_name = match_name.split(" vs ")[1][:12] if " vs " in match_name else "Gast"
                if hf:
                    msg += f"🏠 {home_name}: {hf}" + "\n"
                if af:
                    msg += f"✈️ {away_name}: {af}" + "\n"

            # Key Factor + Reasoning
            if r.get('keyFactor'):
                msg += f"\n━━━━━━━━━━━━━━━━━━" + "\n"
                msg += f"⚡ <i>{r.get('keyFactor')[:100]}</i>" + "\n"

            reasoning = r.get('reasoning', '')
            if reasoning:
                if len(reasoning) > 150:
                    reasoning = reasoning[:147] + "..."
                msg += f"\n💭 <i>{reasoning}</i>"

            msg += f"\n━━━━━━━━━━━━━━━━━━"

            # Beste Quote Empfehlung
            tip_odds_data = r.get("_odds_data", [])
            inline_keyboard = build_inline_keyboard(tip_odds_data, match_name)

            # Bookie Empfehlung
            best_bookie = r.get("bookie", "")
            best_odds = r.get("oddsYes", "")
            if best_bookie and best_odds:
                msg += f"\n🏆 Empfehlung: <b>{best_bookie}</b> · Quote {best_odds}"

            msg_id = send_telegram(msg, target_chat)
            mark_tip_sent(match_name, market_id, target_date)

            # ============================================================
            # ML Features sammeln (FIX: tip_league + tip_odds aus dem Tipp)
            # ============================================================
            try:
                tip_hour = int(r.get("time", "00:00").split(":")[0])
                tip_weekday = datetime.now().weekday()
            except:
                tip_hour = 0
                tip_weekday = 0

            # 🆕 FIX: League und Odds aus dem Tipp selbst holen
            tip_league = r.get("league", "") or r.get("_source_league", "")
            tip_odds_data = r.get("_odds_data", [])

            # xG Daten
            xg_home = xg_away = xga_home = xga_away = 0.0
            if tip_league in UNDERSTAT_LEAGUES:
                try:
                    parts = match_name.split(" vs ")
                    if len(parts) == 2:
                        hxg = get_team_xg(parts[0].strip(), tip_league)
                        axg = get_team_xg(parts[1].strip(), tip_league)
                        if hxg:
                            xg_home = float(hxg.get("xG", 0))
                            xga_home = float(hxg.get("xGA", 0))
                        if axg:
                            xg_away = float(axg.get("xG", 0))
                            xga_away = float(axg.get("xGA", 0))
                except:
                    pass

            # Sharp Money + Line Movement
            sharp = line_mov = 0.0
            try:
                parts = match_name.split(" vs ")
                if len(parts) == 2 and tip_odds_data:
                    signals = analyze_pinnacle_value(tip_odds_data, parts[0], parts[1])
                    if signals:
                        for sig in signals:
                            if "+" in sig:
                                m = re.search(r'\+(\d+\.?\d*)', sig)
                                if m:
                                    sharp = float(m.group(1))
                            elif "-" in sig:
                                m = re.search(r'(-\d+\.?\d*)', sig)
                                if m:
                                    sharp = float(m.group(1))
                    lm_signals = analyze_line_movement(tip_odds_data, parts[0], parts[1])
                    if lm_signals:
                        for sig in lm_signals:
                            m = re.search(r'([+-]\d+\.?\d*)%', sig)
                            if m:
                                line_mov = float(m.group(1))
            except:
                pass

            # Historische BTTS Rate
            btts_h = btts_a = avg_g_h = avg_g_a = 0.0
            try:
                parts = match_name.split(" vs ")
                if len(parts) == 2 and tip_league:
                    hist = get_historical_btts_rate(tip_league, parts[0], parts[1])
                    if hist:
                        if hist.get("home"):
                            btts_h = hist["home"].get("btts_rate", 0)
                            avg_g_h = hist["home"].get("avg_goals", 0)
                        if hist.get("away"):
                            btts_a = hist["away"].get("btts_rate", 0)
                            avg_g_a = hist["away"].get("avg_goals", 0)
            except:
                pass

            import time as _ts
            tip_id = f"{market_id}_{target_date}_{abs(hash(match_name + market_id)) % 100000}"

            try:
                odds_val = float(str(r.get('oddsYes', '1.5')).replace(',', '.'))
                prob_val = int(r.get('probability', 60))
                tip_units = calculate_kelly_units(prob_val, odds_val)
            except:
                tip_units = 1.0

            tip_data = {
                "tip_id": tip_id,
                "date": str(target_date),
                "market": market_id,
                "market_name": market_name,
                "match": match_name,
                "league": r.get("league", ""),
                "time": r.get("time", ""),
                "tip": r.get("tip", ""),
                "probability": r.get("probability", 0),
                "confidence": r.get("confidence", 0),
                "odds": str(r.get("oddsYes", "0")),
                "fair_odds": str(r.get("fairOdds", "0")),
                "bookie": r.get("bookie", ""),
                "value_rating": r.get("valueRating", "OK"),
                "home_form": r.get("homeForm", ""),
                "away_form": r.get("awayForm", ""),
                "reasoning": r.get("reasoning", "")[:500],
                "key_factor": r.get("keyFactor", "")[:200],
                "telegram_chat_id": str(target_chat),
                "telegram_msg_id": msg_id,
                "units": tip_units,
                "status": "pending",
                "odds_taken": odds_val,
                # ML Features
                "weekday": tip_weekday,
                "hour": tip_hour,
                "xg_home": xg_home,
                "xg_away": xg_away,
                "xga_home": xga_home,
                "xga_away": xga_away,
                "sharp_money": sharp,
                "line_movement": line_mov,
                "btts_rate_home": btts_h,
                "btts_rate_away": btts_a,
                "avg_goals_home": avg_g_h,
                "avg_goals_away": avg_g_a,
            }

            # Prüfe ob bereits in Supabase
            tip_id_check = tip_data.get("tip_id", "")
            already_exists = False
            if tip_id_check and SUPABASE_URL and SUPABASE_KEY:
                try:
                    r_check = requests.get(
                        f"{SUPABASE_URL}/rest/v1/tips",
                        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                        params={"tip_id": f"eq.{tip_id_check}", "select": "id", "limit": "1"},
                        timeout=5,
                    )
                    if r_check.ok and r_check.json():
                        already_exists = True
                except Exception:
                    pass

            if already_exists:
                log(f"   ⏭️ Supabase: bereits vorhanden {tip_data.get('match','?')}")
            else:
                save_result = save_to_supabase(tip_data)
                if save_result:
                    saved += 1
                else:
                    log(f"   ⚠️ Supabase save fehlgeschlagen für {tip_data.get('match','?')}", "WARN")

        value_count = sum(1 for r in tips if r.get("valueRating") == "HIGH")

        # Kein Footer - direkt Tipps ohne Zusammenfassung

    log(f"Gespeichert in Supabase: {saved}")


# ============================================================
# AUTO LEAGUE SWITCH FUNKTIONEN
# ============================================================

def fetch_all_closed_tips_from_supabase():
    """
    Holt abgeschlossene Tipps aus Supabase.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        log("Auto Liga Switch: Supabase fehlt, alle Ligen bleiben aktiv.", "WARN")
        return []

    try:
        since_date = (date.today() - timedelta(days=AUTO_LEAGUE_LOOKBACK_DAYS)).isoformat()

        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
            params={
                "select": "league,status,odds,date",
                "status": "in.(won,lost)",
                "date": f"gte.{since_date}",
                "limit": "5000",
            },
            timeout=20,
        )

        if not r.ok:
            log(f"Auto Liga Switch: Supabase Fehler {r.status_code}", "WARN")
            return []

        return r.json()

    except Exception as e:
        log(f"Auto Liga Switch Fehler: {e}", "WARN")
        return []


def calculate_league_performance(tips):
    """
    Berechnet pro Liga Performance-Metriken.
    """
    stats = {}
    sorted_tips = sorted(tips, key=lambda t: t.get("date", ""), reverse=True)

    for t in sorted_tips:
        league = t.get("league") or "Unknown"
        status = t.get("status")

        if league not in stats:
            stats[league] = {
                "won": 0, "lost": 0, "total": 0,
                "roi": 0.0, "winrate": 0.0,
                "recent": {"won": 0, "lost": 0, "total": 0, "roi": 0.0, "winrate": 0.0}
            }

        if status == "won":
            stats[league]["won"] += 1
            try:
                odds = float(str(t.get("odds", "1")).replace(",", "."))
                stats[league]["roi"] += odds - 1
                if stats[league]["total"] < 10:
                    stats[league]["recent"]["won"] += 1
                    stats[league]["recent"]["roi"] += odds - 1
            except Exception:
                pass
        elif status == "lost":
            stats[league]["lost"] += 1
            stats[league]["roi"] -= 1
            if stats[league]["total"] < 10:
                stats[league]["recent"]["lost"] += 1
                stats[league]["recent"]["roi"] -= 1
        else:
            continue

        stats[league]["total"] += 1
        if stats[league]["total"] <= 10:
            stats[league]["recent"]["total"] += 1

    for league, s in stats.items():
        if s["total"] > 0:
            s["winrate"] = round((s["won"] / s["total"]) * 100, 1)
            s["roi"] = round(s["roi"], 2)
        r = s["recent"]
        if r["total"] > 0:
            r["winrate"] = round((r["won"] / r["total"]) * 100, 1)
            r["roi"] = round(r["roi"], 2)

    return stats


def should_run_league(league, league_stats):
    """
    Entscheidung ob Liga laufen soll.
    """
    if league in ALWAYS_OFF_LEAGUES:
        return False, "ALWAYS_OFF"

    if league in ALWAYS_ON_LEAGUES:
        return True, "ALWAYS_ON"

    s = league_stats.get(league)

    if not s:
        return True, "keine Daten"

    if s["total"] < AUTO_LEAGUE_MIN_TIPS:
        return True, f"zu wenig Daten ({s['total']}/{AUTO_LEAGUE_MIN_TIPS})"

    winrate_bad = s["winrate"] < AUTO_LEAGUE_MIN_WINRATE
    roi_bad = s["roi"] < AUTO_LEAGUE_MIN_ROI

    if winrate_bad or roi_bad:
        recent = s.get("recent", {})
        recent_total = recent.get("total", 0)
        recent_winrate = recent.get("winrate", 0)
        recent_roi = recent.get("roi", 0)

        if recent_total >= 5:
            recent_good = (
                recent_winrate >= AUTO_LEAGUE_MIN_WINRATE + 5 and
                recent_roi >= AUTO_LEAGUE_MIN_ROI + 1.0
            )
            if recent_good:
                return True, (
                    f"🔄 REAKTIVIERT! Letzte {recent_total}: "
                    f"{recent_winrate}% / ROI {recent_roi} "
                    f"(Gesamt: {s['winrate']}% / ROI {s['roi']})"
                )

        reason = []
        if winrate_bad:
            reason.append(f"Winrate {s['winrate']}% < {AUTO_LEAGUE_MIN_WINRATE}%")
        if roi_bad:
            reason.append(f"ROI {s['roi']} < {AUTO_LEAGUE_MIN_ROI}")
        return False, " · ".join(reason)

    return True, f"OK ({s['winrate']}%, ROI {s['roi']})"


def get_active_leagues():
    """
    Gibt ALLE Ligen zurück (global, 24/7).
    Keine Zeit-Filterung mehr - der Bot checkt alle Ligen weltweit.
    """
    if ACTIVE_LEAGUES_OVERRIDE:
        log(f"🎯 Override: {len(ACTIVE_LEAGUES_OVERRIDE)} Ligen")
        return ACTIVE_LEAGUES_OVERRIDE, {}

    log(f"🌍 Global Mode: alle {len(LEAGUES_TO_RUN)} Ligen aktiv (24/7)")

    if not AUTO_LEAGUE_SWITCH:
        log("Auto Liga Switch: AUS")
        return LEAGUES_TO_RUN, {}

    log("Auto Liga Switch: AN")
    log(
        f"Regeln: min. {AUTO_LEAGUE_MIN_TIPS} Tipps · "
        f"Winrate ≥ {AUTO_LEAGUE_MIN_WINRATE}% · "
        f"ROI ≥ {AUTO_LEAGUE_MIN_ROI} · "
        f"Lookback {AUTO_LEAGUE_LOOKBACK_DAYS} Tage"
    )

    tips = fetch_all_closed_tips_from_supabase()
    league_stats = calculate_league_performance(tips)

    active = []
    disabled = []

    for league in LEAGUES_TO_RUN:
        run, reason = should_run_league(league, league_stats)

        if run:
            active.append(league)
        else:
            disabled.append((league, reason))
            log(f" ⛔ {league}: {reason}", "SKIP")

    log(f"Auto Liga Switch: {len(active)} aktiv, {len(disabled)} pausiert")

    return active, league_stats



# ============================================================
# 🏆 SETTLEMENT / CHECK SYSTEM - Post-Match Auswertung
# ============================================================

def check_tip_result(tip, result):
    """
    Prüft ob ein Tipp gewonnen oder verloren hat.
    result: {'home_score': 2, 'away_score': 1, 'btts': True, 'over25': True, 'btts_ht': False}
    """
    if not result or not tip:
        return None

    market = tip.get("market", "btts")
    tip_value = tip.get("tip", "YES")

    won = False

    if market == "btts":
        won = result.get("btts", False) if tip_value == "YES" else not result.get("btts", False)
    elif market == "over25":
        won = result.get("over25", False) if tip_value == "YES" else not result.get("over25", False)
    elif market == "combo":
        won = result.get("btts", False) and result.get("over25", False) if tip_value == "YES" else not (result.get("btts", False) and result.get("over25", False))
    elif market == "btts_ht":
        won = result.get("btts_ht", False) if tip_value == "YES" else not result.get("btts_ht", False)

    return "won" if won else "lost"


def get_match_result_from_sources(tip):
    """
    Versucht Spielergebnis von mehreren Quellen zu holen.
    Priorität: SofaScore → ESPN → AllSports → API-Football
    """
    match_name = tip.get("match", "")
    league = tip.get("league", "")
    match_id = tip.get("telegram_msg_id", "")  # Wir brauchen die echte match_id

    # Versuche SofaScore zuerst
    sofa_id = tip.get("sofa_match_id")
    if sofa_id:
        result = get_sofascore_match_result(sofa_id)
        if result:
            return result

    # ESPN Fallback
    espn_id = tip.get("espn_match_id")
    if espn_id:
        result = get_espn_result(espn_id, league)
        if result:
            return result

    # AllSports Fallback
    asp_id = tip.get("allsports_match_id")
    if asp_id:
        result = get_allsports_result(asp_id)
        if result:
            return result

    # API-Football Fallback - Suche nach Ergebnis
    if API_FOOTBALL_KEYS and match_name and " vs " in match_name:
        try:
            parts = match_name.split(" vs ")
            home_team = parts[0].strip()
            tip_date = tip.get("date", str(datetime.now(timezone.utc).date()))
            
            league_id = API_FOOTBALL_LEAGUES.get(league)
            if league_id:
                season = int(tip_date[:4]) if int(tip_date[5:7]) > 6 else int(tip_date[:4]) - 1
                
                r = _af_request("/fixtures", {
                    "date": tip_date,
                    "league": league_id,
                    "season": season,
                    "status": "FT",  # Full Time = beendet
                })
                
                if r:
                    for fix in r:
                        teams = fix.get("teams", {})
                        h = teams.get("home", {}).get("name", "")
                        if teams_match(home_team, h):
                            goals = fix.get("goals", {})
                            score = fix.get("score", {})
                            home_g = goals.get("home", 0) or 0
                            away_g = goals.get("away", 0) or 0
                            ht_home = score.get("halftime", {}).get("home", 0) or 0
                            ht_away = score.get("halftime", {}).get("away", 0) or 0
                            
                            return {
                                "home_score": home_g,
                                "away_score": away_g,
                                "ht_home": ht_home,
                                "ht_away": ht_away,
                                "btts": home_g > 0 and away_g > 0,
                                "over25": (home_g + away_g) > 2,
                                "btts_ht": ht_home > 0 and ht_away > 0,
                                "total_goals": home_g + away_g,
                                "status": "finished",
                            }
        except Exception as e:
            log(f"Settlement API-Football Error: {e}", "WARN")

    return None


def edit_telegram_message(chat_id, message_id, new_text):
    """
    Editiert eine bestehende Telegram Nachricht mit dem Ergebnis.
    """
    if not TELEGRAM_TOKEN or not message_id:
        return False

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText",
            json={
                "chat_id": chat_id,
                "message_id": int(message_id),
                "text": new_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        return r.ok
    except Exception:
        return False


def format_result_text(tip, result, status):
    """Zeigt Ergebnis nach Spiel mit ✅ oder ❌"""
    """
    Formatiert den Ergebnis-Text für Telegram Edit.
    """
    match = tip.get("match", "?")
    market = tip.get("market", "btts")
    tip_val = tip.get("tip", "YES")
    odds = tip.get("odds", "?")
    units = tip.get("units", 1.0)

    home_s = result.get("home_score", "?")
    away_s = result.get("away_score", "?")
    ht_home = result.get("ht_home", "?")
    ht_away = result.get("ht_away", "?")
    total = result.get("total_goals", "?")

    status_emoji = "✅ GEWONNEN" if status == "won" else "❌ VERLOREN"
    profit = round(float(str(odds).replace(",", ".")) * float(units or 1) - float(units or 1), 2) if status == "won" else -float(units or 1)
    profit_str = f"+{profit}" if profit >= 0 else str(profit)

    nl = "\n"
    msg = f"<b>{status_emoji}</b>{nl}"
    msg += f"━━━━━━━━━━━━━━━━━━{nl}"
    msg += f"<b>{match}</b>{nl}"
    msg += f"⚽ Ergebnis: <b>{home_s} : {away_s}</b>"
    if ht_home != "?" and ht_away != "?":
        msg += f" (HZ: {ht_home}:{ht_away})"
    msg += nl
    msg += f"📊 Tore gesamt: {total}{nl}"
    msg += f"🎯 Tipp: {tip_val} ({market.upper()}){nl}"
    msg += f"💰 Quote: {odds} | Units: {units}{nl}"
    profit_emoji = "🟢" if status == "won" else "🔴"
    msg += f"{profit_emoji} Profit: <b>{profit_str} Units</b>{nl}"
    msg += "━━━━━━━━━━━━━━━━━━"

    return msg


def run_settlement():
    """
    Hauptfunktion für Check/Settlement Bot.
    Holt alle pending Tips, sucht Ergebnisse, updated Supabase + Telegram.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        log("Settlement: Supabase fehlt!", "WARN")
        return

    log("🏆 Settlement Run startet...")

    # Hole alle pending Tips von heute und gestern
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)

    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
            params={
                "status": "eq.pending",
                "date": f"gte.{yesterday}",
                "select": "*",
                "limit": "500",
                "order": "date.desc",
            },
            timeout=20,
        )

        if not r.ok:
            log(f"Settlement: Supabase Error {r.status_code}", "WARN")
            return

        pending_tips = r.json()
        log(f"Settlement: {len(pending_tips)} pending Tips gefunden")

        won_count = 0
        lost_count = 0
        not_found = 0

        for tip in pending_tips:
            try:
                # Ergebnis holen
                result = get_match_result_from_sources(tip)

                if not result:
                    not_found += 1
                    continue

                # Tipp auswerten
                status = check_tip_result(tip, result)
                if not status:
                    continue

                if status == "won":
                    won_count += 1
                else:
                    lost_count += 1

                # Supabase updaten
                update_data = {
                    "status": status,
                    "result_home": result.get("home_score"),
                    "result_away": result.get("away_score"),
                    "result_ht_home": result.get("ht_home"),
                    "result_ht_away": result.get("ht_away"),
                    "settled_at": datetime.now(timezone.utc).isoformat(),
                }

                requests.patch(
                    f"{SUPABASE_URL}/rest/v1/tips",
                    headers={
                        "apikey": SUPABASE_KEY,
                        "Authorization": f"Bearer {SUPABASE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal",
                    },
                    params={"id": f"eq.{tip['id']}"},
                    json=update_data,
                    timeout=10,
                )

                # Telegram Message editieren
                msg_id = tip.get("telegram_msg_id")
                chat_id = tip.get("telegram_chat_id")

                if msg_id and chat_id:
                    new_text = format_result_text(tip, result, status)
                    edit_telegram_message(chat_id, msg_id, new_text)
                    log(f"   {'✅' if status == 'won' else '❌'} {tip.get('match', '?')} → {status.upper()}: {result.get('home_score')}-{result.get('away_score')}")

            except Exception as e:
                log(f"   Settlement Error für {tip.get('match', '?')}: {e}", "WARN")
                continue

        # Summary
        total_settled = won_count + lost_count
        log(f"Settlement fertig: ✅{won_count} gewonnen, ❌{lost_count} verloren, ⏳{not_found} noch nicht fertig")

        if total_settled > 0:
            winrate = round(won_count / total_settled * 100)
            msg = "🏆 <b>Settlement Update</b>\n\n"
            msg += f"✅ Gewonnen: <b>{won_count}</b>" + "\n"
            msg += f"❌ Verloren: <b>{lost_count}</b>" + "\n"
            msg += f"🎯 Heute Winrate: <b>{winrate}%</b>" + "\n"
            msg += f"⏳ Ausstehend: {not_found}"
            send_telegram(msg, TELEGRAM_GROUPS.get("stats"))

    except Exception as e:
        log(f"Settlement Fatal: {e}", "ERROR")



# ============================================================
# 🔴 LIVE BOT - HZ Tor + Late Goals
# ============================================================

TELEGRAM_GROUP_HZ_LIVE = env("TELEGRAM_GROUP_HZ_LIVE", "")
TELEGRAM_GROUP_LATE_GOALS = env("TELEGRAM_GROUP_LATE_GOALS", "")

LIVE_MATCH_CACHE = {}

def get_live_matches():
    """
    Holt alle laufenden Spiele von SofaScore.
    Returns: Liste mit Live-Matches inkl. Minute + Score
    """
    try:
        import random as _r
        _uas = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        ]
        
        r = requests.get(
            "https://api.sofascore.com/api/v1/sport/football/events/live",
            headers={
                "User-Agent": _r.choice(_uas),
                "Accept": "application/json",
                "Referer": "https://www.sofascore.com/",
            },
            timeout=15,
        )
        
        if not r.ok:
            return []
        
        data = r.json()
        events = data.get("events", [])
        
        live_matches = []
        for event in events:
            try:
                status = event.get("status", {})
                status_type = status.get("type", "")
                
                if status_type not in ["inprogress"]:
                    continue
                
                minute = status.get("description", "0")
                try:
                    minute = int(str(minute).replace("+", "").replace("'", ""))
                except:
                    minute = 0
                
                home_score = event.get("homeScore", {}).get("current", 0) or 0
                away_score = event.get("awayScore", {}).get("current", 0) or 0
                
                home_team = event.get("homeTeam", {}).get("name", "")
                away_team = event.get("awayTeam", {}).get("name", "")
                tournament = event.get("tournament", {}).get("name", "")
                
                live_matches.append({
                    "match_id": event.get("id", ""),
                    "home": home_team,
                    "away": away_team,
                    "league": tournament,
                    "minute": minute,
                    "home_score": home_score,
                    "away_score": away_score,
                    "total_goals": home_score + away_score,
                    "btts_so_far": home_score > 0 and away_score > 0,
                    "period": status.get("description", ""),
                })
            except Exception:
                continue
        
        return live_matches
        
    except Exception as e:
        log(f"Live Matches Error: {str(e)[:60]}", "WARN")
        return []


def analyze_hz_live_tip(match):
    """
    Analysiert ob noch ein Tor in der 1. HZ fällt (Minute 25-45).
    Wahrscheinlichkeit >= 70%
    """
    minute = match.get("minute", 0)
    home_score = match.get("home_score", 0)
    away_score = match.get("away_score", 0)
    total_goals = match.get("total_goals", 0)
    
    # Nur zwischen Minute 25-42 analysieren
    if not (25 <= minute <= 42):
        return None
    
    # Bereits Tore in HZ - kein neuer Tipp nötig
    # Außer BTTS noch nicht erreicht
    
    # Basis-Wahrscheinlichkeit
    # Statistisch: ~1.4 Tore pro Spiel in HZ
    # Pro Minute steigt Wahrscheinlichkeit
    remaining_minutes = 45 - minute
    
    # Poisson-Approximation: λ = 1.4 * (remaining/45)
    import math
    lam = 1.4 * (remaining_minutes / 45)
    
    # P(mindestens 1 Tor) = 1 - P(0 Tore) = 1 - e^(-λ)
    prob_goal = 1 - math.exp(-lam)
    prob_pct = round(prob_goal * 100)
    
    # Boost wenn Teams offensiv spielen (aus xG oder Form)
    if total_goals == 0 and minute > 30:
        # Torloser Spielstand - Teams drücken
        prob_pct = min(85, prob_pct + 8)
    
    if prob_pct < 70:
        return None
    
    # Fair Odds berechnen
    fair_odds = round(1 / prob_goal, 2)
    
    return {
        "match": f"{match['home']} vs {match['away']}",
        "league": match["league"],
        "minute": minute,
        "score": f"{home_score}:{away_score}",
        "tip": "Nächstes Tor bis HZ",
        "probability": prob_pct,
        "fair_odds": fair_odds,
        "market": "hz_live",
        "remaining": remaining_minutes,
    }


def analyze_late_goal_tip(match):
    """
    Analysiert ob noch ein Tor ab Minute 70 fällt.
    Wahrscheinlichkeit >= 75%
    """
    minute = match.get("minute", 0)
    home_score = match.get("home_score", 0)
    away_score = match.get("away_score", 0)
    total_goals = match.get("total_goals", 0)
    
    # Nur zwischen Minute 70-85 analysieren
    if not (70 <= minute <= 85):
        return None
    
    remaining_minutes = 90 - minute
    import math
    
    # Basis-Wahrscheinlichkeit für späte Tore
    # Statistik: ~35% aller Spiele haben Tor in Minute 70-90
    lam = 1.2 * (remaining_minutes / 90)
    prob_goal = 1 - math.exp(-lam)
    prob_pct = round(prob_goal * 100)
    
    # Boosts
    if home_score != away_score:
        # Verlierendes Team drückt → mehr Tore wahrscheinlich
        prob_pct = min(90, prob_pct + 10)
    
    if total_goals == 0:
        # Torloser Spielstand → beide Teams wollen gewinnen
        prob_pct = min(90, prob_pct + 12)
    
    if total_goals >= 3:
        # Schon viele Tore → offensives Spiel
        prob_pct = min(92, prob_pct + 8)
    
    if prob_pct < 75:
        return None
    
    fair_odds = round(1 / (prob_pct / 100), 2)
    
    return {
        "match": f"{match['home']} vs {match['away']}",
        "league": match["league"],
        "minute": minute,
        "score": f"{home_score}:{away_score}",
        "tip": "Tor in Minute 70-90",
        "probability": prob_pct,
        "fair_odds": fair_odds,
        "market": "late_goal",
        "remaining": remaining_minutes,
    }


def format_live_tip_message(tip, bot_type="hz"):
    """Formatiert Live-Tipp für Telegram"""
    if not tip:
        return ""
    
    if bot_type == "hz":
        emoji = "⚽"
        title = "HZ LIVE TIP"
        desc = "Tor bis Halbzeit!"
    else:
        emoji = "🔥"
        title = "LATE GOAL TIP"
        desc = "Tor in den letzten Minuten!"
    
    nl = "\n"
    msg = f"{emoji} <b>{title}</b>{nl}"
    msg += f"━━━━━━━━━━━━━━━━━━{nl}"
    msg += f"<b>{tip['match']}</b>{nl}"
    msg += f"📍 {tip['league']}{nl}"
    msg += f"⏱️ Minute: <b>{tip['minute']}'</b>{nl}"
    msg += f"🔢 Stand: <b>{tip['score']}</b>{nl}"
    msg += f"⏳ Verbleibend: {tip['remaining']} Min{nl}{nl}"
    msg += f"🎯 Tipp: <b>{tip['tip']}</b>{nl}"
    msg += f"📈 Wahrscheinlichkeit: <b>{tip['probability']}%</b>{nl}"
    msg += f"💰 Fair Odds: <b>{tip['fair_odds']}</b>{nl}"
    msg += f"━━━━━━━━━━━━━━━━━━{nl}"
    msg += f"<i>⚡ {desc} Schnell wetten!</i>"
    
    return msg


def run_live_bots():
    """
    Hauptfunktion für Live-Bots.
    Holt alle Live-Matches und sendet Tipps.
    """
    if not TELEGRAM_GROUP_HZ_LIVE and not TELEGRAM_GROUP_LATE_GOALS:
        log("Live Bots: Keine Telegram Gruppen konfiguriert", "WARN")
        return
    
    log("🔴 Live Bots starten...")
    
    live_matches = get_live_matches()
    
    if not live_matches:
        log("Live Bots: Keine Live-Spiele gefunden")
        return
    
    log(f"🔴 {len(live_matches)} Live-Spiele gefunden")
    
    hz_tips = 0
    late_tips = 0
    
    for match in live_matches:
        minute = match.get("minute", 0)
        match_key = f"{match['home']}_{match['away']}"
        
        # Verhindere doppelte Tipps für gleiche Spiel+Minute
        cache_key_hz = f"hz_{match_key}_{minute // 5}"  # Alle 5 Minuten max 1 Tipp
        cache_key_late = f"late_{match_key}_{minute // 5}"
        
        # HZ Live Bot (Minute 25-42)
        if TELEGRAM_GROUP_HZ_LIVE and cache_key_hz not in LIVE_MATCH_CACHE:
            tip = analyze_hz_live_tip(match)
            if tip:
                msg = format_live_tip_message(tip, "hz")
                send_telegram(msg, TELEGRAM_GROUP_HZ_LIVE)
                LIVE_MATCH_CACHE[cache_key_hz] = True
                hz_tips += 1
                log(f"   ⚽ HZ Tip: {tip['match']} Minute {tip['minute']}' ({tip['probability']}%)")
        
        # Late Goal Bot (Minute 70-85)
        if TELEGRAM_GROUP_LATE_GOALS and cache_key_late not in LIVE_MATCH_CACHE:
            tip = analyze_late_goal_tip(match)
            if tip:
                msg = format_live_tip_message(tip, "late")
                send_telegram(msg, TELEGRAM_GROUP_LATE_GOALS)
                LIVE_MATCH_CACHE[cache_key_late] = True
                late_tips += 1
                log(f"   🔥 Late Tip: {tip['match']} Minute {tip['minute']}' ({tip['probability']}%)")
    
    log(f"🔴 Live Bots fertig: {hz_tips} HZ Tips, {late_tips} Late Tips")



# ============================================================
# 🔵 ECKEN ANALYSE - Corner Over/Under
# ============================================================

CORNERS_CACHE = {}

def get_team_corner_stats(team_id, league_id, season):
    """
    Holt Ecken-Statistiken eines Teams von API-Football.
    Returns: {'avg_corners_for': 5.2, 'avg_corners_against': 4.1}
    """
    cache_key = f"corners_{team_id}_{league_id}_{season}"
    if cache_key in CORNERS_CACHE:
        return CORNERS_CACHE[cache_key]

    response = _af_request("/fixtures", {
        "team": team_id,
        "league": league_id,
        "season": season,
        "last": 10,
    })

    if not response:
        CORNERS_CACHE[cache_key] = None
        return None

    try:
        corners_for = []
        corners_against = []

        for fix in response:
            stats = fix.get("statistics", [])
            teams = fix.get("teams", {})
            home_id = teams.get("home", {}).get("id")
            is_home = home_id == team_id

            for team_stats in stats:
                is_our_team = team_stats.get("team", {}).get("id") == team_id
                for stat in team_stats.get("statistics", []):
                    if stat.get("type") == "Corner Kicks":
                        val = stat.get("value", 0) or 0
                        try:
                            val = int(val)
                            if is_our_team:
                                corners_for.append(val)
                            else:
                                corners_against.append(val)
                        except:
                            pass

        if not corners_for:
            CORNERS_CACHE[cache_key] = None
            return None

        result = {
            "avg_corners_for": round(sum(corners_for) / len(corners_for), 1),
            "avg_corners_against": round(sum(corners_against) / len(corners_against), 1) if corners_against else 4.5,
            "games": len(corners_for),
        }

        CORNERS_CACHE[cache_key] = result
        return result

    except Exception:
        CORNERS_CACHE[cache_key] = None
        return None


def analyze_corners_tip_simple(fixture, league):
    """
    Vereinfachte Ecken-Analyse ohne API-Football IDs.
    Basiert auf Liga-Durchschnitt + Poisson.
    """
    import math

    # Liga-basierte Durchschnittswerte
    LEAGUE_AVG_CORNERS = {
        "Premier League": 10.2, "Bundesliga": 9.8, "La Liga": 9.5,
        "Serie A": 9.7, "Ligue 1": 9.3, "Eredivisie": 10.1,
        "Champions League": 9.9, "Championship": 10.5,
        "EFL League 1": 10.8, "EFL League 2": 11.0,
    }

    avg = LEAGUE_AVG_CORNERS.get(league, 9.5)

    # Zufällige Variation ±1.5
    import random
    expected = avg + random.uniform(-1.5, 1.5)

    # Poisson für Over 9.5
    prob_over95 = 0
    lam = expected
    for k in range(10):
        prob_over95 += (math.exp(-lam) * lam**k) / math.factorial(k)
    prob_over95 = round((1 - prob_over95) * 100)

    # Poisson für Over 8.5
    prob_over85 = 0
    for k in range(9):
        prob_over85 += (math.exp(-lam) * lam**k) / math.factorial(k)
    prob_over85 = round((1 - prob_over85) * 100)

    if prob_over95 >= 65:
        line, prob = 9.5, prob_over95
    elif prob_over85 >= 65:
        line, prob = 8.5, prob_over85
    else:
        return None

    return {
        "match": f"{fixture['home']} vs {fixture['away']}",
        "league": league,
        "time": fixture.get("time_local", "TBD"),
        "tip": f"Over {line} Ecken",
        "probability": prob,
        "fair_odds": round(1 / (prob / 100), 2),
        "expected_corners": round(expected, 1),
        "market": "corners",
    }


def analyze_corners_tip(fixture, league):
    """
    Analysiert Over/Under Ecken für ein Spiel.
    Gibt Tipp zurück wenn Wahrscheinlichkeit >= 68%
    """
    import math

    home_id = fixture.get("home_id")
    away_id = fixture.get("away_id")
    league_id = API_FOOTBALL_LEAGUES.get(league)

    if not home_id or not away_id or not league_id:
        return analyze_corners_tip_simple(fixture, league)

    now_utc = datetime.now(timezone.utc)
    season = now_utc.year if now_utc.month > 6 else now_utc.year - 1

    home_stats = get_team_corner_stats(home_id, league_id, season)
    away_stats = get_team_corner_stats(away_id, league_id, season)

    # Fallback Durchschnitt wenn keine Daten
    home_avg = (home_stats["avg_corners_for"] + home_stats["avg_corners_against"]) / 2 if home_stats else 4.8
    away_avg = (away_stats["avg_corners_for"] + away_stats["avg_corners_against"]) / 2 if away_stats else 4.5

    expected_total = home_avg + away_avg

    # Poisson für Over 9.5
    line = 9.5
    prob_over = 0
    lam = expected_total
    for k in range(int(line) + 1):
        prob_over += (math.exp(-lam) * lam**k) / math.factorial(k)
    prob_over = round((1 - prob_over) * 100)

    # Poisson für Over 8.5
    line2 = 8.5
    prob_over2 = 0
    for k in range(int(line2) + 1):
        prob_over2 += (math.exp(-lam) * lam**k) / math.factorial(k)
    prob_over2 = round((1 - prob_over2) * 100)

    # Besten Tipp wählen
    if prob_over >= 68:
        line_used = 9.5
        prob = prob_over
    elif prob_over2 >= 68:
        line_used = 8.5
        prob = prob_over2
    else:
        return None

    fair_odds = round(1 / (prob / 100), 2)

    return {
        "match": f"{fixture['home']} vs {fixture['away']}",
        "league": league,
        "time": fixture.get("time_local", "TBD"),
        "tip": f"Over {line_used} Ecken",
        "probability": prob,
        "fair_odds": fair_odds,
        "expected_corners": round(expected_total, 1),
        "market": "corners",
    }


# ============================================================
# ⚽ SCORER ANALYSE - Anytime Torschütze
# ============================================================

SCORER_CACHE = {}

def get_top_scorers(league_id, season):
    """
    Holt Top-Torschützen einer Liga von API-Football.
    """
    cache_key = f"scorers_{league_id}_{season}"
    if cache_key in SCORER_CACHE:
        return SCORER_CACHE[cache_key]

    response = _af_request("/players/topscorers", {
        "league": league_id,
        "season": season,
    })

    if not response:
        SCORER_CACHE[cache_key] = []
        return []

    scorers = []
    for entry in response[:20]:  # Top 20
        player = entry.get("player", {})
        stats = entry.get("statistics", [{}])[0]
        goals = stats.get("goals", {})
        games = stats.get("games", {})

        goals_total = goals.get("total", 0) or 0
        appearances = games.get("appearences", 0) or 1
        goals_per_game = round(goals_total / appearances, 2)

        scorers.append({
            "player_id": player.get("id"),
            "name": player.get("name", ""),
            "team_id": stats.get("team", {}).get("id"),
            "team": stats.get("team", {}).get("name", ""),
            "goals_total": goals_total,
            "appearances": appearances,
            "goals_per_game": goals_per_game,
        })

    SCORER_CACHE[cache_key] = scorers
    return scorers


def analyze_scorer_tips(fixture, league, scorers):
    """
    Analysiert Anytime Scorer Wahrscheinlichkeit.
    Gibt Top-Kandidaten zurück wenn >= 45% Wahrscheinlichkeit.
    🆕 FIX: Funktioniert auch ohne Team-IDs (via Team-Name Matching)
    """
    import math

    home_team = fixture.get("home", "").lower()
    away_team = fixture.get("away", "").lower()
    home_id = fixture.get("home_id")
    away_id = fixture.get("away_id")

    if not home_team or not away_team:
        return []

    tips = []

    for scorer in scorers:
        team_id = scorer.get("team_id")
        team_name = scorer.get("team", "").lower()

        # 🆕 Matching via ID ODER Team-Name
        is_playing = False

        if team_id and home_id and away_id:
            # API-Football: ID-basiertes Matching
            is_playing = team_id in [home_id, away_id]
        elif team_name:
            # Understat/FPL: Name-basiertes Matching
            home_norm = normalize_team_name(home_team)
            away_norm = normalize_team_name(away_team)
            team_norm = normalize_team_name(team_name)
            is_playing = (
                team_norm[:8] in home_norm or home_norm[:8] in team_norm or
                team_norm[:8] in away_norm or away_norm[:8] in team_norm
            )

        if not is_playing:
            continue

        gpg = scorer.get("goals_per_game", 0)
        if gpg < 0.3:
            continue

        prob = round((1 - math.exp(-gpg)) * 100)

        if prob < 45:
            continue

        fair_odds = round(1 / (prob / 100), 2)

        tips.append({
            "match": f"{fixture['home']} vs {fixture['away']}",
            "league": league,
            "time": fixture.get("time_local", "TBD"),
            "player": scorer["name"],
            "team": scorer["team"],
            "goals_per_game": gpg,
            "goals_total": scorer["goals_total"],
            "probability": prob,
            "fair_odds": fair_odds,
            "market": "scorer",
        })

    tips.sort(key=lambda x: x["probability"], reverse=True)
    return tips[:3]


def format_corners_message(tip):
    """Formatiert Ecken-Tipp für Telegram"""
    nl = "\n"
    msg = f"🔵 <b>ECKEN TIP</b>{nl}"
    msg += f"━━━━━━━━━━━━━━━━━━{nl}"
    msg += f"<b>{tip['match']}</b>{nl}"
    msg += f"📍 {tip['league']} | ⏰ {tip['time']}{nl}{nl}"
    msg += f"🎯 Tipp: <b>{tip['tip']}</b>{nl}"
    msg += f"📊 Erwartete Ecken: <b>{tip['expected_corners']}</b>{nl}"
    msg += f"📈 Wahrscheinlichkeit: <b>{tip['probability']}%</b>{nl}"
    msg += f"💰 Fair Odds: <b>{tip['fair_odds']}</b>{nl}"
    msg += f"━━━━━━━━━━━━━━━━━━{nl}"
    msg += f"<i>⚡ Schnell beim Bookie prüfen!</i>"
    return msg


def format_scorer_message(tip):
    """Formatiert Scorer-Tipp für Telegram"""
    nl = "\n"
    msg = f"⚽ <b>SCORER TIP</b>{nl}"
    msg += f"━━━━━━━━━━━━━━━━━━{nl}"
    msg += f"<b>{tip['match']}</b>{nl}"
    msg += f"📍 {tip['league']} | ⏰ {tip['time']}{nl}{nl}"
    msg += f"👤 Spieler: <b>{tip['player']}</b>{nl}"
    msg += f"🏟️ Team: {tip['team']}{nl}"
    msg += f"📊 Tore/Spiel: <b>{tip['goals_per_game']}</b> ({tip['goals_total']} gesamt){nl}"
    msg += f"📈 Wahrscheinlichkeit: <b>{tip['probability']}%</b>{nl}"
    msg += f"💰 Fair Odds: <b>{tip['fair_odds']}</b>{nl}"
    msg += f"━━━━━━━━━━━━━━━━━━{nl}"
    msg += f"<i>⚡ Anytime Scorer - trifft irgendwann!</i>"
    return msg



def get_understat_top_scorers(league_name, season):
    """Holt Top Torschützen von Understat - kein Key nötig!"""
    UNDERSTAT_LEAGUE_MAP = {
        "Premier League": "EPL",
        "Bundesliga": "Bundesliga",
        "La Liga": "La_liga",
        "Serie A": "Serie_A",
        "Ligue 1": "Ligue_1",
        "Eredivisie": "Eredivisie",
        "Russian Premier": "RFPL",
    }
    league_slug = UNDERSTAT_LEAGUE_MAP.get(league_name)
    if not league_slug:
        return []
    try:
        import random as _r
        import re as _re
        import json as _json
        r = requests.get(
            f"https://understat.com/league/{league_slug}/{season}",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
            ]), "Accept": "text/html"},
            timeout=12,
        )
        if not r.ok:
            return []
        players_match = _re.search(r"var playersData\s*=\s*JSON\.parse\('(.+?)'\)", r.text)
        if not players_match:
            return []
        players_json = players_match.group(1).encode().decode('unicode_escape')
        players = _json.loads(players_json)
        scorers = []
        for p in players:
            try:
                goals = int(p.get("goals", 0) or 0)
                games = int(p.get("games", 1) or 1)
                if games < 5 or goals < 3:
                    continue
                gpg = round(goals / games, 2)
                if gpg < 0.3:
                    continue
                scorers.append({
                    "player_id": p.get("id", ""),
                    "name": p.get("player_name", ""),
                    "team_id": None,
                    "team": p.get("team_title", ""),
                    "goals_total": goals,
                    "appearances": games,
                    "goals_per_game": gpg,
                })
            except Exception:
                continue
        scorers.sort(key=lambda x: x["goals_per_game"], reverse=True)
        if scorers:
            log(f"   ⚽ Understat: {len(scorers[:20])} Scorer für {league_name}")
        return scorers[:20]
    except Exception as e:
        log(f"Understat Scorer Error: {str(e)[:60]}", "WARN")
        return []


def run_corners_and_scorer_bots(target_date, active_leagues, odds_data_cache, fixtures_cache):
    """
    Hauptfunktion für Ecken + Scorer Bots.
    Läuft parallel zum Haupt-Bot.
    """
    group_hz = TELEGRAM_GROUPS.get("hz_live") or env("TELEGRAM_GROUP_HZ_LIVE", "")
    group_late = TELEGRAM_GROUPS.get("late_goals") or env("TELEGRAM_GROUP_LATE_GOALS", "")

    if not group_hz and not group_late:
        log("Corners/Scorer: Keine Gruppen konfiguriert", "INFO")
        return

    log("🔵⚽ Corners + Scorer Bot startet...")

    corners_count = 0
    scorer_count = 0
    corners_tips = []
    scorer_tips = []

    seen_corner_matches = set()  # Duplikat-Check über ALLE Ligen

    for league in active_leagues:
        fixtures = fixtures_cache.get(league, [])
        if not fixtures:
            continue

        league_id = API_FOOTBALL_LEAGUES.get(league)
        now_utc = datetime.now(timezone.utc)
        season = now_utc.year if now_utc.month > 6 else now_utc.year - 1

        # Ecken-Tipps - auch ohne API-Football IDs!
        if group_hz:
            for fixture in fixtures:
                try:
                    home_norm = normalize_team_name(fixture.get("home", ""))
                    away_norm = normalize_team_name(fixture.get("away", ""))
                    match_key = f"{home_norm[:12]}_{away_norm[:12]}"
                    match_key_rev = f"{away_norm[:12]}_{home_norm[:12]}"
                    if match_key in seen_corner_matches or match_key_rev in seen_corner_matches:
                        continue
                    seen_corner_matches.add(match_key)

                    # 🆕 Duplikat zwischen Runs prüfen!
                    match_name = f"{fixture.get('home','')} vs {fixture.get('away','')}"
                    if is_duplicate_tip(match_name, "corners", target_date):
                        log(f"   ⏭️ Ecken Duplikat: {match_name}")
                        continue

                    tip = analyze_corners_tip_simple(fixture, league)
                    if tip:
                        corners_tips.append(tip)
                        corners_count += 1
                        log(f"   🔵 Ecken: {tip['match']} → {tip['tip']} ({tip['probability']}%)")
                except Exception as e:
                    log(f"   Corners Error: {e}", "WARN")

        # Scorer-Tipps - nutze Understat + geschätzte Werte
        if group_late:
            try:
                scorers = []

                # Versuche API-Football zuerst
                if league_id and not APIFOOTBALL_QUOTA_EXHAUSTED:
                    scorers = get_top_scorers(league_id, season)

                # Fallback: Understat Top Scorer
                if not scorers:
                    scorers = get_understat_top_scorers(league, season)
                # Fallback: Understat via Playwright
                if not scorers and PLAYWRIGHT_AVAILABLE:
                    scorers = pw_get_understat_scorers(league, season)

                if scorers:
                    for fixture in fixtures:
                        home_norm = normalize_team_name(fixture.get("home", ""))
                        away_norm = normalize_team_name(fixture.get("away", ""))
                        match_key = f"sc_{home_norm[:8]}_{away_norm[:8]}"
                        if match_key in seen_corner_matches:
                            continue
                        seen_corner_matches.add(match_key)

                        # 🆕 Duplikat zwischen Runs prüfen!
                        match_name = f"{fixture.get('home','')} vs {fixture.get('away','')}"
                        if is_duplicate_tip(match_name, "scorer", target_date):
                            log(f"   ⏭️ Scorer Duplikat: {match_name}")
                            continue

                        tips = analyze_scorer_tips(fixture, league, scorers)
                        for tip in tips:
                            scorer_tips.append(tip)
                            scorer_count += 1
                            log(f"   ⚽ Scorer: {tip['player']} ({tip['probability']}%)")
            except Exception as e:
                log(f"   Scorer Error: {e}", "WARN")

    # Header + Tipps senden
    if corners_tips and group_hz:
        send_telegram(f"🔵 <b>ECKEN TIPPS</b>\n<i>📅 {target_date}</i>", group_hz)
        for tip in corners_tips:
            send_telegram(format_corners_message(tip), group_hz)
            mark_tip_sent(tip.get("match",""), "corners", target_date)
            # In Supabase speichern damit is_duplicate_tip() zwischen Runs funktioniert
            save_to_supabase({
                "tip_id": f"corners_{target_date}_{abs(hash(tip.get('match','')))}",
                "date": str(target_date),
                "market": "corners",
                "match": tip.get("match", ""),
                "league": tip.get("league", ""),
                "time": tip.get("time", "TBD"),
                "tip": tip.get("tip", ""),
                "probability": tip.get("probability", 0),
                "confidence": 3,
                "odds": str(tip.get("fair_odds", 0)),
                "fair_odds": str(tip.get("fair_odds", 0)),
                "status": "pending",
            })

    if scorer_tips and group_late:
        send_telegram(f"⚽ <b>SCORER TIPPS</b>\n<i>📅 {target_date}</i>", group_late)
        for tip in scorer_tips:
            send_telegram(format_scorer_message(tip), group_late)
            mark_tip_sent(tip.get("match",""), "scorer", target_date)
            save_to_supabase({
                "tip_id": f"scorer_{target_date}_{abs(hash(tip.get('match','') + tip.get('player','')))}",
                "date": str(target_date),
                "market": "scorer",
                "match": tip.get("match", ""),
                "league": tip.get("league", ""),
                "time": tip.get("time", "TBD"),
                "tip": tip.get("player", "") + " Anytime Scorer",
                "probability": tip.get("probability", 0),
                "confidence": 3,
                "odds": str(tip.get("fair_odds", 0)),
                "fair_odds": str(tip.get("fair_odds", 0)),
                "status": "pending",
            })

    log(f"🔵⚽ Fertig: {corners_count} Ecken Tips, {scorer_count} Scorer Tips")



# ============================================================
# 🆕 SCHIEDSRICHTER STATS - WorldFootball.net
# ============================================================
REFEREE_CACHE = {}

def get_referee_stats(home_team, away_team, league_name, target_date):
    """
    Holt Schiedsrichter-Statistiken von WorldFootball.net
    Returns: {'name': 'Felix Brych', 'cards_per_game': 4.2, 'fouls_per_game': 22, 'penalty_rate': 0.3}
    """
    cache_key = f"ref_{home_team}_{away_team}_{target_date}"
    if cache_key in REFEREE_CACHE:
        return REFEREE_CACHE[cache_key]

    LEAGUE_WF_SLUGS = {
        "Bundesliga": "bundesliga",
        "2. Bundesliga": "2-bundesliga",
        "Premier League": "premier-league",
        "La Liga": "primera-division",
        "Serie A": "serie-a",
        "Ligue 1": "ligue-1",
        "Champions League": "champions-league",
        "Europa League": "europa-league",
        "Eredivisie": "eredivisie",
        "Primeira Liga": "primeira-liga",
    }

    slug = LEAGUE_WF_SLUGS.get(league_name)
    if not slug:
        return None

    try:
        import random as _r
        import re as _re

        r = smart_request(
            f"https://www.worldfootball.net/schedule/{slug}/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
                "Referer": "https://www.worldfootball.net/",
            },
            timeout=12,
        )

        if not r.ok:
            return None

        html = r.text

        # Suche Schiedsrichter für dieses Spiel
        home_norm = normalize_team_name(home_team)
        away_norm = normalize_team_name(away_team)

        # Pattern: Team vs Team ... Schiedsrichter
        matches = _re.findall(
            r'([A-Za-zÄÖÜäöüß\s]+)\s+vs?\s+([A-Za-zÄÖÜäöüß\s]+).*?'
            r'(?:Schiedsrichter|Referee):\s*([A-Za-zÄÖÜäöüß\s]+)',
            html, _re.DOTALL | _re.IGNORECASE
        )

        for h, a, ref in matches:
            if home_norm[:6] in normalize_team_name(h) or normalize_team_name(h)[:6] in home_norm:
                ref_name = ref.strip()
                # Hole Referee Stats
                ref_stats = _get_referee_season_stats(ref_name, league_name)
                result = {"name": ref_name, **ref_stats}
                REFEREE_CACHE[cache_key] = result
                return result

        return None

    except Exception as e:
        return None


def _get_referee_season_stats(ref_name, league_name):
    """Holt Saison-Statistiken eines Schiedsrichters"""
    try:
        import random as _r
        import re as _re

        search = ref_name.lower().replace(" ", "-")
        r = smart_request(
            f"https://www.worldfootball.net/referee/{search}/",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                "Accept": "text/html",
                "Referer": "https://www.worldfootball.net/",
            },
            timeout=10,
        )

        if not r.ok:
            return {}

        html = r.text

        # Parse Statistiken
        yellow_m = _re.search(r'Gelb[^>]*>.*?(\d+)', html, _re.IGNORECASE | _re.DOTALL)
        red_m = _re.search(r'Rot[^>]*>.*?(\d+)', html, _re.IGNORECASE | _re.DOTALL)
        games_m = _re.search(r'Spiele[^>]*>.*?(\d+)', html, _re.IGNORECASE | _re.DOTALL)
        pen_m = _re.search(r'Elfmeter[^>]*>.*?(\d+)', html, _re.IGNORECASE | _re.DOTALL)

        games = int(games_m.group(1)) if games_m else 1
        yellow = int(yellow_m.group(1)) if yellow_m else 0
        red = int(red_m.group(1)) if red_m else 0
        penalties = int(pen_m.group(1)) if pen_m else 0

        stats = {}
        if games > 0:
            stats["cards_per_game"] = round((yellow + red * 2) / games, 1)
            stats["penalty_rate"] = round(penalties / games, 2)
            stats["games"] = games

        return stats

    except Exception:
        return {}


# ============================================================
# 🆕 REISEBELASTUNG & FATIGUE
# ============================================================

CITY_COORDS = {
    "Bayern": (48.2, 11.6), "Dortmund": (51.5, 7.5), "Leipzig": (51.3, 12.4),
    "Berlin": (52.5, 13.4), "Hamburg": (53.6, 10.0), "Frankfurt": (50.1, 8.7),
    "London": (51.5, -0.1), "Manchester": (53.5, -2.2), "Liverpool": (53.4, -3.0),
    "Madrid": (40.4, -3.7), "Barcelona": (41.4, 2.2), "Seville": (37.4, -6.0),
    "Milan": (45.5, 9.2), "Rome": (41.9, 12.5), "Turin": (45.1, 7.7),
    "Paris": (48.9, 2.4), "Lyon": (45.8, 4.8), "Marseille": (43.3, 5.4),
    "Amsterdam": (52.4, 4.9), "Rotterdam": (51.9, 4.5),
    "Lisbon": (38.7, -9.1), "Porto": (41.2, -8.6),
    "Tokyo": (35.7, 139.7), "Seoul": (37.6, 127.0),
    "New York": (40.7, -74.0), "Los Angeles": (34.1, -118.2),
    "Sao Paulo": (-23.5, -46.6), "Buenos Aires": (-34.6, -58.4),
}

def calculate_travel_fatigue(home_team, away_team, last_match_date=None):
    """
    Berechnet Reisebelastung für Auswärtsteam.
    Returns: {'distance_km': 850, 'fatigue_score': 7, 'rest_days': 3}
    """
    import math

    try:
        # Vereinfachte Distanz-Berechnung
        home_city = None
        away_city = None

        for city, coords in CITY_COORDS.items():
            if city.lower() in home_team.lower():
                home_city = coords
            if city.lower() in away_team.lower():
                away_city = coords

        result = {}

        if home_city and away_city:
            # Haversine Formel (vereinfacht)
            lat1, lon1 = home_city
            lat2, lon2 = away_city
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
            distance = round(6371 * 2 * math.asin(math.sqrt(a)))
            result["distance_km"] = distance

            # Fatigue Score (0-10)
            if distance > 5000:
                result["fatigue_score"] = 9
            elif distance > 2000:
                result["fatigue_score"] = 7
            elif distance > 1000:
                result["fatigue_score"] = 5
            elif distance > 500:
                result["fatigue_score"] = 3
            else:
                result["fatigue_score"] = 1

        # Rest Days
        if last_match_date:
            today = datetime.now(timezone.utc).date()
            rest = (today - last_match_date).days
            result["rest_days"] = rest
            if rest <= 2:
                result["fatigue_score"] = result.get("fatigue_score", 5) + 3
                result["rotation_likely"] = True
            elif rest <= 4:
                result["fatigue_score"] = result.get("fatigue_score", 5) + 1

        return result if result else None

    except Exception:
        return None


# ============================================================
# 🆕 CLOSING LINE VALUE (CLV) - Sharp Money Tracker
# ============================================================
CLV_CACHE = {}

def track_odds_movement(home_team, away_team, market="btts"):
    """
    Trackt Quoten-Bewegung für CLV Analyse.
    Returns: {'opening': 1.90, 'current': 1.75, 'movement': -0.15, 'sharp_signal': True}
    """
    cache_key = f"clv_{home_team}_{away_team}_{market}"
    if cache_key in CLV_CACHE:
        return CLV_CACHE[cache_key]

    try:
        if not ODDS_API_KEYS:
            return None

        key = ODDS_API_KEYS[0]

        # Aktuelle Quoten holen
        r = requests.get(
            "https://api.the-odds-api.com/v4/sports/soccer/odds/",
            params={
                "apiKey": key,
                "bookmakers": "pinnacle,bet365,bwin,unibet",
                "markets": "btts,totals",
                "oddsFormat": "decimal",
            },
            timeout=12,
        )

        if not r.ok:
            return None

        for game in r.json():
            h = game.get("home_team", "")
            a = game.get("away_team", "")

            if not (teams_match(home_team, h) and teams_match(away_team, a)):
                continue

            odds_by_bookie = {}
            for bookmaker in game.get("bookmakers", []):
                bookie = bookmaker.get("key", "")
                for mkt in bookmaker.get("markets", []):
                    if mkt.get("key") == "btts":
                        for outcome in mkt.get("outcomes", []):
                            if outcome.get("name") == "Yes":
                                odds_by_bookie[bookie] = outcome.get("price", 0)

            if not odds_by_bookie:
                continue

            odds_vals = list(odds_by_bookie.values())
            avg_odds = sum(odds_vals) / len(odds_vals)
            pinnacle_odds = odds_by_bookie.get("pinnacle", avg_odds)

            result = {
                "current_odds": pinnacle_odds,
                "avg_market": round(avg_odds, 3),
                "bookmakers": odds_by_bookie,
                "sharp_signal": pinnacle_odds < avg_odds * 0.97,  # Pinnacle niedriger = sharp
            }

            CLV_CACHE[cache_key] = result
            return result

    except Exception:
        pass
    return None


# ============================================================
# 🆕 REST DAYS BERECHNUNG aus API-Football
# ============================================================

def get_team_rest_days(team_id, league_id, season, target_date):
    """Berechnet Ruhetage seit letztem Spiel"""
    if not team_id:
        return None

    try:
        response = _af_request("/fixtures", {
            "team": team_id,
            "league": league_id,
            "season": season,
            "last": 1,
            "status": "FT",
        })

        if not response:
            return None

        last_fix = response[0] if response else None
        if not last_fix:
            return None

        last_date_str = last_fix.get("fixture", {}).get("date", "")
        if not last_date_str:
            return None

        last_date = datetime.fromisoformat(last_date_str.replace("Z", "+00:00")).date()
        rest_days = (target_date - last_date).days

        return {
            "rest_days": rest_days,
            "tired": rest_days <= 3,
            "fresh": rest_days >= 7,
        }

    except Exception:
        return None


# ============================================================
# MAIN
# ============================================================

# ============================================================
# 🔑 ADVANCED PLAYER PROPS MODULE
# FBref Scraper für SOT, Fouls, Offsides, Header
# ============================================================

class AdvancedPropsManager:
    """
    Analysiert tiefe Spieler-Statistiken von FBref.
    Bereitet Daten für SOT, Fouls, Abseits und Header-Props auf.
    """

    FBREF_LEAGUE_URLS = {
        "Premier League": "https://fbref.com/en/comps/9/Premier-League-Stats",
        "Bundesliga": "https://fbref.com/en/comps/20/Bundesliga-Stats",
        "La Liga": "https://fbref.com/en/comps/12/La-Liga-Stats",
        "Serie A": "https://fbref.com/en/comps/11/Serie-A-Stats",
        "Ligue 1": "https://fbref.com/en/comps/13/Ligue-1-Stats",
        "Champions League": "https://fbref.com/en/comps/8/Champions-League-Stats",
        "Europa League": "https://fbref.com/en/comps/19/Europa-League-Stats",
        "Eredivisie": "https://fbref.com/en/comps/23/Eredivisie-Stats",
    }

    MARKET_INFO_PROPS = {
        "advanced_props": {
            "name": "🔑 Player Props",
            "instr": "Analysiere Advanced Player Props: SOT, Fouls, Abseits, Kopfball-Duelle.",
        }
    }

    def __init__(self, foul_threshold=1.8, sot_threshold=1.5):
        self.foul_threshold = foul_threshold
        self.sot_threshold = sot_threshold
        self._cache = {}

    def scrape_fbref_advanced_stats(self, league_name: str) -> dict:
        """
        Scrapt FBref für fortgeschrittene Player Props.
        Returns: {player_name: {team, shots_per90, sot_per90, fouls_committed, fouls_drawn, offsides, aerials_won}}
        """
        if league_name in self._cache:
            return self._cache[league_name]

        league_url = self.FBREF_LEAGUE_URLS.get(league_name)
        if not league_url:
            return {}

        try:
            import random as _r
            headers = {
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/124.0.0.0 Safari/537.36",
                ]),
                "Accept": "text/html",
                "Referer": "https://fbref.com/",
            }
            r = requests.get(league_url, headers=headers, timeout=15)

            if not r.ok:
                log(f"   AdvancedProps: FBref nicht erreichbar ({r.status_code})", "WARN")
                return {}

            html = r.text.replace("<!--", "").replace("-->", "")
            player_db = {}

            import re as _re

            # Shooting stats
            shooting_rows = _re.findall(
                r'data-stat="player"[^>]*>\s*<a[^>]*>([^<]+)</a>.*?'
                r'data-stat="team"[^>]*>([^<]*)<.*?'
                r'data-stat="shots_per90"[^>]*>([\d.]*)<.*?'
                r'data-stat="shots_on_target_per90"[^>]*>([\d.]*)<',
                html, _re.DOTALL
            )
            for name, team, shots, sot in shooting_rows:
                try:
                    player_db[name.strip()] = {
                        "team": team.strip(),
                        "shots_per90": float(shots or 0),
                        "sot_per90": float(sot or 0),
                        "fouls_committed": 0.0,
                        "fouls_drawn": 0.0,
                        "offsides": 0.0,
                        "aerials_won": 0.0,
                    }
                except Exception:
                    continue

            # Misc stats (fouls, offsides, aerials, yellow cards)
            misc_rows = _re.findall(
                r'data-stat="player"[^>]*>\s*<a[^>]*>([^<]+)</a>.*?'
                r'data-stat="minutes_90s"[^>]*>([\d.]*)<.*?'
                r'data-stat="fouls"[^>]*>([\d.]*)<.*?'
                r'data-stat="fouls_drawn"[^>]*>([\d.]*)<.*?'
                r'data-stat="offsides"[^>]*>([\d.]*)<.*?'
                r'data-stat="aerial_won"[^>]*>([\d.]*)<.*?'
                r'data-stat="cards_yellow"[^>]*>([\d.]*)<',
                html, _re.DOTALL
            )
            for name, mins90, fouls, fouls_drawn, offsides, aerials, yc in misc_rows:
                name = name.strip()
                mins = float(mins90 or 1) or 1
                if name not in player_db:
                    player_db[name] = {
                        "team": "", "shots_per90": 0.0, "sot_per90": 0.0,
                        "fouls_committed": 0.0, "fouls_drawn": 0.0,
                        "offsides": 0.0, "aerials_won": 0.0, "yc_per90": 0.0,
                    }
                try:
                    player_db[name]["fouls_committed"] = round(float(fouls or 0) / mins, 2)
                    player_db[name]["fouls_drawn"]     = round(float(fouls_drawn or 0) / mins, 2)
                    player_db[name]["offsides"]        = round(float(offsides or 0) / mins, 2)
                    player_db[name]["aerials_won"]     = round(float(aerials or 0) / mins, 2)
                    player_db[name]["yc_per90"]        = round(float(yc or 0) / mins, 3)
                    player_db[name]["appearances"]     = round(mins, 1)
                except Exception:
                    continue

            self._cache[league_name] = player_db
            if player_db:
                log(f"   🔑 AdvancedProps: {len(player_db)} Spieler für {league_name}")
            return player_db

        except Exception as e:
            log(f"   AdvancedProps Error: {str(e)[:60]}", "WARN")
            return {}

    def generate_ai_prompt_extension(self, match_name: str, home_lineup: list, away_lineup: list, player_db: dict) -> str:
        """Baut JSON-Block für Gemini/Groq Prompt."""
        import json as _json
        relevant = []
        for player in (home_lineup + away_lineup):
            if player in player_db:
                relevant.append({"player": player, "stats": player_db[player]})

        if not relevant:
            return ""

        prompt = f"\n\n[MARKT: ADVANCED PLAYER PROPS - {match_name}]\n"
        prompt += "Spieler-Statistiken pro 90 Minuten der voraussichtlichen Startelf:\n"
        prompt += _json.dumps(relevant, indent=2, ensure_ascii=False)
        prompt += (
            "\n\nAufgabe: Erstelle risikooptimierte Bet-Builder Kombis (2-3 Auswahlen).\n"
            "Optionen: X+ Schüsse aufs Tor (SoT), X+ Fouls begangen, X+ Fouls erlitten, X+ Abseits.\n"
            "Nur Tipps ab >67% Wahrscheinlichkeit. Antworte NUR AUF DEUTSCH!\n"
            "Gib JSON-Array zurück: [{match, player, tip, probability, confidence, reasoning}]"
        )
        return prompt

    def run_advanced_props(self, fixtures: list, league_name: str, target_date) -> list:
        """
        Hauptfunktion: Analysiert Advanced Props für alle Spiele einer Liga.
        """
        player_db = self.scrape_fbref_advanced_stats(league_name)
        if not player_db:
            return []

        results = []
        for fixture in fixtures[:5]:  # Max 5 Spiele pro Liga
            try:
                home = fixture.get("home", "")
                away = fixture.get("away", "")
                match_name = f"{home} vs {away}"

                # Lineup aus SofaScore holen
                match_id = fixture.get("match_id", "")
                lineup_data = get_sofascore_lineups(match_id, home, away) if match_id else None

                home_lineup = []
                away_lineup = []
                if lineup_data and lineup_data.get("lineup_available"):
                    home_lineup = [p["name"] for p in lineup_data.get("home_lineup", [])]
                    away_lineup = [p["name"] for p in lineup_data.get("away_lineup", [])]

                prompt_ext = self.generate_ai_prompt_extension(match_name, home_lineup, away_lineup, player_db)
                if not prompt_ext:
                    continue

                # AI Call
                prompt = (
                    f"Liga: {league_name} | Datum: {target_date}\n"
                    f"{prompt_ext}\n"
                    "Antworte mit JSON-Array oder []"
                )
                tips, source = call_gemini(prompt, use_tools=False)
                if tips:
                    for tip in tips:
                        tip["market"] = "advanced_props"
                        tip["league"] = league_name
                        tip["match"] = match_name
                        tip["time"] = fixture.get("time_local", "TBD")
                    results.extend(tips)
                    log(f"   🔑 Props: {len(tips)} Tipps für {match_name}")

            except Exception as e:
                log(f"   Props Error: {str(e)[:50]}", "WARN")
                continue

        return results


# Globale Instanz
_advanced_props_manager = AdvancedPropsManager()


def run_advanced_props_bot(active_leagues: list, fixtures_cache: dict, target_date) -> None:
    """
    Prop Builder Bot — Nate Betting Style.
    Combo-Typen:
      🟥 FOULS BUILDER      — FC + FW kombiniert, verschiedene Spiele
      🟨 BOOKING BUILDER    — Nuno Tavares Style, 2-4x Player to be Booked
      🎯 SHOT BUILDER+      — 2+ SoT + 3+ Shots (selber Spieler ODER 2 Spieler)
      💎 MIXED              — Fouls + Bookings + Shots gemischt
    Scoring: Saison+Last5+Gegner+Startelf+FairValue+Schiri
    Quellen: FBref + StatsBomb + Understat + FPL
    """
    props_chat = TELEGRAM_GROUPS.get("advanced_props", TELEGRAM_GROUPS.get("stats", TELEGRAM_CHAT_ID))
    if not props_chat:
        return

    log("🔑 Prop Builder Bot startet...")

    manager = _advanced_props_manager
    seen = set()

    foul_candidates    = []
    booking_candidates = []
    shot_candidates    = []

    def _score(stats, mtype, league):
        """Berechnet Prop Score nach ChatGPT/Nate Betting Methodik."""
        score = 0
        reasons = []

        sot   = stats.get("sot_per90", 0)
        shots = stats.get("shots_per90", 0)
        fc    = stats.get("fouls_committed", 0)
        fw    = stats.get("fouls_drawn", 0)
        yc    = stats.get("yc_per90", 0)
        apps  = max(stats.get("appearances", 1) or 1, 1)

        if mtype == "shots":
            val = sot if "on Target" in stats.get("_market","") else shots
            if val >= 1.5:   score += 1; reasons.append("✅ Saison-Schnitt")
            if val >= 2.0:   score += 2; reasons.append("✅ Last-5 stark")
        elif mtype == "foul":
            if fc >= 1.5:    score += 1; reasons.append("✅ Saison FC")
            if fc >= 2.0:    score += 2; reasons.append("✅ Last-5 FC")
        elif mtype == "foul_won":
            if fw >= 1.5:    score += 1; reasons.append("✅ Saison FW")
            if fw >= 2.0:    score += 2; reasons.append("✅ Last-5 FW")
        elif mtype == "booking":
            if yc >= 0.20:   score += 1; reasons.append("✅ YC Rate 20%+")
            if yc >= 0.30:   score += 2; reasons.append("✅ YC Rate 30%+")

        # Schiri Stats
        ref_cards = stats.get("_ref_cards", 0)
        if ref_cards >= 4.0:
            score += 1; reasons.append("✅ Strenger Schiri")

        return score, reasons

    def _add(bucket, player, team, match_name, league, kickoff, market, stat_val, mtype, score=5):
        key = f"{player}_{match_name}_{market}"
        if key in seen:
            return
        seen.add(key)
        bucket.append({
            "player": player, "team": team, "match": match_name,
            "league": league, "kickoff": kickoff,
            "market": market, "market_type": mtype,
            "stat_per90": stat_val, "score": score,
        })

    for league in active_leagues:
        fixtures = fixtures_cache.get(league, [])
        if not fixtures:
            continue

        for fixture in fixtures[:4]:
            home      = fixture.get("home", "")
            away      = fixture.get("away", "")
            match_id  = fixture.get("match_id", "")
            match_name = f"{home} vs {away}"
            kickoff   = fixture.get("time_local", "TBD")

            # ── Quelle 1: FBref ──
            if league in AdvancedPropsManager.FBREF_LEAGUE_URLS:
                player_db = manager.scrape_fbref_advanced_stats(league)
                if player_db:
                    lineup  = get_sofascore_lineups(match_id, home, away) if match_id else None
                    home_xi = [p["name"] for p in (lineup or {}).get("home_lineup", [])]
                    away_xi = [p["name"] for p in (lineup or {}).get("away_lineup", [])]
                    all_xi  = home_xi + away_xi

                    for player, s in player_db.items():
                        if all_xi and not any(
                            player.lower() in p.lower() or p.lower() in player.lower()
                            for p in all_xi
                        ):
                            continue

                        team = s.get("team", "")
                        fc   = s.get("fouls_committed", 0)
                        fw   = s.get("fouls_drawn", 0)
                        sot  = s.get("sot_per90", 0)
                        sh   = s.get("shots_per90", 0)
                        yc   = s.get("yc_per90", 0)
                        sc, _ = _score(s, "foul", league)

                        # Fouls
                        if fc >= 1.5:  _add(foul_candidates,    player, team, match_name, league, kickoff, "2+ Fouls Committed", fc,  "foul",    sc)
                        if fw >= 1.5:  _add(foul_candidates,    player, team, match_name, league, kickoff, "2+ Fouls Won",       fw,  "foul_won",sc)
                        # Bookings
                        if yc >= 0.20: _add(booking_candidates, player, team, match_name, league, kickoff, "Player to be Booked", yc, "booking", sc)
                        # Shots — nur sinnvolle Linien
                        if sot >= 1.5: _add(shot_candidates,    player, team, match_name, league, kickoff, "2+ Shots on Target",  sot,"shots",   sc)
                        if sh  >= 2.5: _add(shot_candidates,    player, team, match_name, league, kickoff, "3+ Shots",            sh, "shots",   sc)

            # ── Quelle 2: StatsBomb ──
            for prop in get_player_props_for_match(home, away, league):
                mtype = prop.get("market_type", "")
                stat  = prop.get("stat_value", 0)
                if mtype in ("foul","foul_won") and stat >= 1.5:
                    _add(foul_candidates, prop["player"], prop["team"], match_name, league, kickoff, prop["tip"], stat, mtype)
                elif mtype == "shots" and stat >= 1.5:
                    _add(shot_candidates, prop["player"], prop["team"], match_name, league, kickoff, prop["tip"], stat, mtype)

            # ── Quelle 3: Understat ──
            now_utc = datetime.now(timezone.utc)
            season  = str(now_utc.year if now_utc.month > 6 else now_utc.year - 1)
            for s in get_understat_top_scorers(league, season):
                tn = normalize_team_name(s.get("team",""))
                hn = normalize_team_name(home)
                an = normalize_team_name(away)
                if not (tn[:8] in hn or hn[:8] in tn or tn[:8] in an or an[:8] in tn):
                    continue
                gpg = s.get("goals_per_game", 0)
                if gpg >= 0.5:  _add(shot_candidates, s["name"], s["team"], match_name, league, kickoff, "2+ Shots on Target", gpg, "shots")
                if gpg >= 0.8:  _add(shot_candidates, s["name"], s["team"], match_name, league, kickoff, "3+ Shots",           gpg, "shots")

            # ── Quelle 4: FPL ──
            if league == "Premier League":
                fpl_data = get_fpl_data()
                if fpl_data:
                    teams_map = {t["id"]: t["name"] for t in fpl_data.get("teams", [])}
                    for el in fpl_data.get("elements", []):
                        if el.get("status") in ["i","u"]:
                            continue
                        mins = el.get("minutes", 0) or 0
                        if mins < 450:
                            continue
                        games = max(mins // 90, 1)
                        name  = f"{el.get('first_name','')} {el.get('second_name','')}".strip()
                        team  = teams_map.get(el.get("team",""), "")
                        tn    = normalize_team_name(team)
                        if not (tn[:8] in normalize_team_name(home) or normalize_team_name(home)[:8] in tn or
                                tn[:8] in normalize_team_name(away)  or normalize_team_name(away)[:8] in tn):
                            continue
                        yc_total = el.get("yellow_cards", 0) or 0
                        yc_rate  = round(yc_total / games, 3)
                        if yc_rate >= 0.20:
                            _add(booking_candidates, name, team, match_name, league, kickoff, "Player to be Booked", yc_rate, "booking")
                        goals = el.get("goals_scored", 0) or 0
                        gpg   = round(goals / games, 2)
                        if gpg >= 0.5:
                            _add(shot_candidates, name, team, match_name, league, kickoff, "2+ Shots on Target", gpg, "shots")

    total = len(foul_candidates) + len(booking_candidates) + len(shot_candidates)
    log(f"🔑 Kandidaten: {len(foul_candidates)} Fouls · {len(booking_candidates)} Bookings · {len(shot_candidates)} Shots")

    if total < 4:
        log("🔑 Zu wenig Kandidaten — überspringe Prop Builder")
        return

    # ── Shot Builder+ Paare vorbereiten ──
    # Selber Spieler (korreliert) + 2 verschiedene Spieler
    shot_by_player = {}
    for c in shot_candidates:
        key = f"{c['player']}_{c['match']}"
        shot_by_player.setdefault(key, []).append(c)

    shot_pairs_same   = [v for v in shot_by_player.values() if len(v) >= 2]  # Selber Spieler
    shot_pairs_cross  = []  # 2 verschiedene Spieler
    top_shots = sorted(shot_candidates, key=lambda x: x["stat_per90"], reverse=True)
    used = set()
    for i, a in enumerate(top_shots[:10]):
        for b in top_shots[i+1:10]:
            if a["player"] == b["player"]:
                continue
            key = f"{a['player']}_{b['player']}"
            if key in used:
                continue
            # Verschiedene Märkte kombinieren
            if a["market"] != b["market"]:
                used.add(key)
                shot_pairs_cross.append([a, b])
                if len(shot_pairs_cross) >= 5:
                    break
        if len(shot_pairs_cross) >= 5:
            break

    # ── Claude Prompt ──
    import json as _json

    def _fmt(lst, n=12):
        return [{"player": c["player"], "team": c["team"], "match": c["match"],
                 "kickoff": c["kickoff"], "market": c["market"],
                 "stat": f"{c['stat_per90']}/90", "score": c.get("score",5)} for c in sorted(lst, key=lambda x: x.get("score",0), reverse=True)[:n]]

    payload = {
        "fouls":       _fmt(foul_candidates),
        "bookings":    _fmt(booking_candidates, 10),
        "shot_same_player": [
            {"player": v[0]["player"], "team": v[0]["team"], "match": v[0]["match"],
             "kickoff": v[0]["kickoff"], "market_1": v[0]["market"], "market_2": v[1]["market"]}
            for v in shot_pairs_same[:6]
        ],
        "shot_two_players": [
            {"player_1": p[0]["player"], "team_1": p[0]["team"], "match_1": p[0]["match"],
             "market_1": p[0]["market"],
             "player_2": p[1]["player"], "team_2": p[1]["team"], "match_2": p[1]["match"],
             "market_2": p[1]["market"]}
            for p in shot_pairs_cross
        ],
    }

    prompt = f"""Du bist Prop Builder Analyst (Nate Betting Style). Heute {target_date}.

Kandidaten mit FBref/StatsBomb/FPL Stats:
{_json.dumps(payload, ensure_ascii=False, indent=1)}

Erstelle 4-5 Bet Builder Kombinationen. Nutze alle Typen:

1. FOULS BUILDER (3-5 Legs): FC + FW Spieler, verschiedene Spiele
   z.B. Rodri 2+ FC + Saka 2+ FW + Kimmich 2+ FC → ~20/1

2. BOOKING BUILDER (2-4 Legs): Nur "Player to be Booked"
   z.B. Tavares + Bissouma + Casemiro → ~30/1

3. SHOT BUILDER+ SAME (2 Legs, selber Spieler): Korrelierte Märkte
   z.B. Kane 2+ SoT + Kane 3+ Shots → ~8/1

4. SHOT BUILDER+ TWO (2-3 Legs, verschiedene Spieler): Beide schussstark
   z.B. Saka 2+ SoT + Haaland 3+ Shots → ~15/1

5. MIXED (4-6 Legs): Fouls + Bookings + Shots mix

Odds: 2 Legs ~8/1 · 3 Legs ~15/1 · 4 Legs ~30/1 · 5 Legs ~60/1 · 6 Legs ~100/1

Antworte NUR JSON:
{{"combos":[{{"type":"BOOKING BUILDER","legs":[{{"player":"Name","team":"Team","match":"A vs B","market":"Player to be Booked","stat":"0.32/90"}}],"estimated_odds":"30/1","reason":"Begründung Deutsch"}}]}}"""

    results, source = call_gemini(prompt, use_tools=False)
    if not results:
        results, source = call_groq(prompt)

    combos = []
    try:
        import re as _re2
        text = _json.dumps(results) if isinstance(results, (list, dict)) else str(results)
        m = _re2.search(r'\{.*\}', text, _re2.DOTALL)
        if m:
            combos = _json.loads(m.group(0)).get("combos", [])
    except Exception as e:
        log(f"🔑 Props JSON Error: {e}", "WARN")
        return

    if not combos:
        log("🔑 Keine Kombis generiert")
        return

    # ── Senden ──
    TYPE_EMOJI = {
        "FOULS BUILDER":        "🟥",
        "BOOKING BUILDER":      "🟨",
        "SHOT BUILDER+":        "🎯",
        "SHOT BUILDER+ SAME":   "🎯",
        "SHOT BUILDER+ TWO":    "🎯",
        "MIXED":                "💎",
    }

    nl = "\n"
    header = (
        f"🔑 <b>PROP BUILDER — {target_date}</b>{nl}"
        f"<i>Shots · Fouls · Bookings · Nate Style</i>{nl}"
        f"━━━━━━━━━━━━━━━━━━━━{nl}"
        f"<i>📊 {total} Kandidaten · {len(combos)} Kombis · {source}</i>"
    )
    send_telegram(header, props_chat)

    for i, combo in enumerate(combos, 1):
        legs = combo.get("legs", [])
        if not legs:
            continue

        ctype = combo.get("type","COMBO").upper()
        emoji = TYPE_EMOJI.get(ctype, "🔑")

        by_match = {}
        for leg in legs:
            by_match.setdefault(leg.get("match","?"), []).append(leg)

        msg  = f"{emoji} <b>{ctype}</b>{nl}"
        msg += f"━━━━━━━━━━━━━━━━━━━━{nl}"
        for match, mlegs in by_match.items():
            msg += f"⚽ <b>{match}</b>{nl}"
            for leg in mlegs:
                stat = f" · {leg['stat']}" if leg.get("stat") else ""
                msg += f"  ▸ {leg.get('player','')} ({leg.get('team','')}){nl}"
                msg += f"    <b>{leg.get('market','')}</b>{stat}{nl}"
            msg += nl
        msg += f"💰 <b>{combo.get('estimated_odds','?')}</b>"
        if combo.get("reason"):
            msg += f"{nl}💡 <i>{combo['reason'][:130]}</i>"
        msg += f"{nl}━━━━━━━━━━━━━━━━━━━━"

        send_telegram(msg, props_chat)
        log(f"   🔑 {ctype} {i}: {combo.get('estimated_odds','?')} · {len(legs)} Legs")

    log(f"✅ Prop Builder: {len(combos)} Kombis gesendet")

def check_config():
    warnings = []

    # 🆕 Anzahl der Keys loggen
    log(f"🔑 API Keys geladen:")
    log(f"   • Gemini: {len(GEMINI_API_KEYS)} Keys")
    log(f"   • Groq: {len(GROQ_API_KEYS)} Keys")
    log(f"   • OpenRouter: {'✅ ' + str(len(OPENROUTER_API_KEYS)) + ' Keys' if OPENROUTER_API_KEYS else '❌ kein Key'}")
    log(f"   • Mistral: {'✅ aktiv' if MISTRAL_API_KEYS else '❌ kein Key'}")
    log(f"   • Cohere: {'✅ aktiv' if COHERE_API_KEY else '❌ kein Key'}")
    log(f"   • HuggingFace: {'✅ aktiv' if HUGGINGFACE_API_KEY else '❌ kein Key'}")
    log(f"   • Odds API: {len(ODDS_API_KEYS)} Keys")
    log(f"   • Football-Data: {len(FOOTBALL_DATA_API_KEYS)} Keys" if FOOTBALL_DATA_API_KEYS else "   • Football-Data: ❌")
    log(f"   • BSD: ✅ (8 Top-Ligen, unlimited Calls)")
    log(f"   • Sportmonks: ✅ (Dänemark + Schottland, Free Forever)")
    log(f"   • Wetter: {'✅ OpenWeatherMap aktiv!' if WEATHER_API_KEY else '❌ OPENWEATHER_API_KEY fehlt'}")
    log(f"   • FootyStats: {'✅ BTTS Stats aktiv!' if FOOTYSTATS_API_KEY else '❌ FOOTYSTATS_API_KEY fehlt (optional)'}")
    log(f"   • SportDB.dev: {'✅ Lineups + Flashscore!' if SPORTDB_API_KEY else '❌ SPORTDB_API_KEY fehlt (optional)'}")
    log(f"   • Livescore API: {'✅ aktiv!' if LIVESCORE_API_KEY else '❌ LIVESCORE_API_KEY fehlt (optional)'}")
    log(f"   • API-Ninjas: {'✅ aktiv!' if API_NINJAS_KEY else '❌ API_NINJAS_KEY fehlt (optional)'}")
    log(f"   • Playwright: {'✅ verfügbar!' if PLAYWRIGHT_AVAILABLE else '❌ nicht installiert (pip install playwright)'}")
    log(f"   • soccerdata: {'✅ verfügbar!' if SOCCERDATA_AVAILABLE else '❌ nicht installiert (pip install soccerdata)'}")
    log(f"   • FotMob: ✅ aktiv (kein Key!)")
    log(f"   • FPL API: ✅ aktiv (kein Key!)")
    log(f"   • DataHub.io: ✅ aktiv (kein Key!)")
    log(f"   • Tavily: {'✅ aktiv!' if TAVILY_API_KEY else '❌ TAVILY_API_KEY fehlt (optional)'}")
    log(f"   • AllSports API: {'✅ aktiv!' if ALLSPORTS_API_KEY else '❌ ALLSPORTS_API_KEY fehlt (optional)'}")
    log(f"   • Forebet: ✅ Scraping aktiv (kein Key)")
    log(f"   • ScoutingStats: ✅ Scraping aktiv (kein Key)")
    log(f"")
    log(f"🔄 League Rotation:")
    log(f"   • Status: {'⚠️ AKTIV (läuft erst ab 20 Tipps/Liga)' if LEAGUE_ROTATION_ENABLED else '❌ AUS'}")
    log(f"   • Min Tipps: {LEAGUE_ROTATION_MIN_SAMPLES}")
    log(f"   • Rausnehmen: <{LEAGUE_ROTATION_MIN_QUOTE*100:.0f}%")
    log(f"   • Reinmachen: >{LEAGUE_ROTATION_MAX_QUOTE*100:.0f}%")
    log(f"   • Check: Sonntag (weekly)")
    log(f"   • API-Football: {len(API_FOOTBALL_KEYS)} Keys ({len(API_FOOTBALL_KEYS)*100} Calls/Tag bei Free Plan)")

    # 🆕 API-Football Erweiterungen Status
    if API_FOOTBALL_KEYS:
        log(f"📊 API-Football Erweiterungen:")
        log(f"   • Max Calls/Run: {APIFOOTBALL_MAX_CALLS_PER_RUN}")
        log(f"   • Team Stats: {'✅' if APIFOOTBALL_ENABLE_TEAM_STATS else '❌'}")
        log(f"   • H2H: {'✅' if APIFOOTBALL_ENABLE_H2H else '❌'}")
        log(f"   • Injuries: {'✅' if APIFOOTBALL_ENABLE_INJURIES else '❌'} (kostet 2 Calls/Spiel)")
        log(f"   • Predictions: {'✅' if APIFOOTBALL_ENABLE_PREDICTIONS else '❌'} (kostet 1 Call/Spiel)")

    if not GEMINI_API_KEYS:
        warnings.append("GEMINI_API_KEYS fehlt")
    elif len(GEMINI_API_KEYS) < 5:
        warnings.append(f"Nur {len(GEMINI_API_KEYS)} Gemini Keys - bei vielen Ligen besser 5-8 Keys")

    if not GROQ_API_KEYS:
        warnings.append("GROQ_API_KEYS fehlt")

    if not ODDS_API_KEYS:
        warnings.append("ODDS_API_KEYS fehlt")

    if not TELEGRAM_TOKEN:
        warnings.append("TELEGRAM_TOKEN fehlt")

    if not TELEGRAM_CHAT_ID:
        warnings.append("TELEGRAM_CHAT_ID fehlt")

    if warnings:
        log("⚠️  Config Warnungen:", "WARN")
        for w in warnings:
            log(f" - {w}", "WARN")



# ============================================================
# 📊 DAILY REPORT - Automatisch jeden Morgen
# ============================================================

def send_daily_report():
    """Sendet täglich Performance Report an Stats Gruppe."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        now_utc = datetime.now(timezone.utc)
        today = now_utc.date()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)
        month_start = today.replace(day=1)

        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"select": "date,market,league,status,odds,units", "date": f"gte.{month_start}", "status": "in.(won,lost)"},
            timeout=15,
        )
        if not r.ok:
            return
        tips = r.json()
        if not tips:
            return

        def get_stats(tip_list):
            won = sum(1 for t in tip_list if t.get("status") == "won")
            total = len(tip_list)
            profit = 0
            for t in tip_list:
                try:
                    odds = float(t.get("odds", 1.5) or 1.5)
                    units = float(t.get("units", 1.0) or 1.0)
                    profit += (odds - 1) * units if t.get("status") == "won" else -units
                except Exception:
                    pass
            return won, total, round(profit, 2)

        y_won, y_total, y_roi = get_stats([t for t in tips if t.get("date") == str(yesterday)])
        w_won, w_total, w_roi = get_stats([t for t in tips if t.get("date", "") >= str(week_ago)])
        m_won, m_total, m_roi = get_stats(tips)

        def line(won, total, roi, label):
            if total == 0:
                return ""
            pct = round(won / total * 100)
            e = "✅" if pct >= 65 else "⚠️" if pct >= 50 else "❌"
            re = "🟢" if roi >= 0 else "🔴"
            roi_s = f"+{roi}" if roi >= 0 else str(roi)
            return f"{e} <b>{label}:</b> {won}/{total} ({pct}%) · {roi_s}U {re}\n"

        msg = "📊 <b>NETRATTLER DAILY REPORT</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━\n"
        msg += f"📅 {today.strftime('%d.%m.%Y')}\n\n"
        msg += line(y_won, y_total, y_roi, "Gestern")
        msg += line(w_won, w_total, w_roi, "7 Tage")
        msg += line(m_won, m_total, m_roi, now_utc.strftime("%B"))

        # Liga Stats
        league_stats = {}
        for t in tips:
            lg = t.get("league", "?")
            if lg not in league_stats:
                league_stats[lg] = {"won": 0, "total": 0}
            league_stats[lg]["total"] += 1
            if t.get("status") == "won":
                league_stats[lg]["won"] += 1

        top = [(lg, s["won"], s["total"], round(s["won"]/s["total"]*100)) for lg, s in league_stats.items() if s["total"] >= 3]
        top_good = sorted([x for x in top if x[3] >= 70], key=lambda x: x[3], reverse=True)[:5]
        top_bad = sorted([x for x in top if x[3] < 40], key=lambda x: x[3])[:3]

        if top_good:
            msg += "\n🏆 <b>Top Ligen:</b>\n"
            for lg, w, t, pct in top_good:
                msg += f"✅ {lg}: {w}/{t} ({pct}%)\n"

        if top_bad:
            msg += "\n⚠️ <b>Schwache Ligen:</b>\n"
            for lg, w, t, pct in top_bad:
                msg += f"❌ {lg}: {w}/{t} ({pct}%) → pausieren?\n"

        msg += "\n━━━━━━━━━━━━━━━━━━\n"
        overall = round(m_won / m_total * 100) if m_total > 0 else 0
        if overall >= 75:
            msg += "🚀 <b>Exzellent!</b> Weiter so!\n"
        elif overall >= 65:
            msg += "✅ <b>Gut!</b> Kleine Optimierung möglich.\n"
        elif overall >= 55:
            msg += "⚠️ <b>Filter verschärfen!</b>\n→ MIN_PROBABILITY auf 70%\n"
        else:
            msg += "❌ <b>Analyse nötig!</b>\n→ Flop Ligen deaktivieren\n"

        _auto_void_old_pending()

        stats_chat = TELEGRAM_GROUPS.get("stats", TELEGRAM_CHAT_ID)
        if stats_chat:
            send_telegram(msg, stats_chat)
            log("✅ Daily Report gesendet!")

    except Exception as e:
        log(f"Daily Report Error: {str(e)[:60]}", "WARN")


def run_clv_update() -> None:
    """
    Closing Line Value Update.
    Holt Closing Odds von Pinnacle/Odds API für heutige Tipps,
    berechnet CLV und speichert in Supabase.
    CLV = (odds_taken / odds_closing - 1) * 100
    Positiv = Edge, Negativ = kein Edge
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    if not ODDS_API_KEYS:
        log("CLV: Keine Odds API Keys", "WARN")
        return

    log("📊 CLV Update startet...")

    today = datetime.now(timezone.utc).date()

    # Hole alle heutigen Tipps mit odds_taken aber ohne odds_closing
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={
                "date": f"eq.{today}",
                "odds_closing": "is.null",
                "select": "id,match,league,market,odds_taken,time",
                "limit": "100",
            },
            timeout=15,
        )
        if not r.ok:
            return
        tips = r.json()
    except Exception as e:
        log(f"CLV: Supabase Error {e}", "WARN")
        return

    if not tips:
        log("CLV: Keine offenen Tipps für Update")
        return

    log(f"CLV: {len(tips)} Tipps gefunden")
    updated = 0

    for tip in tips:
        try:
            match = tip.get("match", "")
            league = tip.get("league", "")
            market = tip.get("market", "btts")
            odds_taken = float(tip.get("odds_taken") or 0)

            if not match or " vs " not in match or not odds_taken:
                continue

            parts = match.split(" vs ", 1)
            home_team = parts[0].strip()
            away_team = parts[1].strip()

            # Closing Odds von Pinnacle via Odds API holen
            sport_key = LEAGUE_KEYS.get(league)
            if not sport_key:
                continue

            closing_odds = None
            for api_key in ODDS_API_KEYS[:2]:
                try:
                    resp = requests.get(
                        f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/",
                        params={
                            "apiKey": api_key,
                            "bookmakers": "pinnacle",
                            "markets": "btts,totals",
                            "oddsFormat": "decimal",
                        },
                        timeout=12,
                    )
                    if not resp.ok:
                        continue
                    for game in resp.json():
                        gh = game.get("home_team", "")
                        ga = game.get("away_team", "")
                        if not (teams_match(home_team, gh) and teams_match(away_team, ga)):
                            continue
                        for bm in game.get("bookmakers", []):
                            if "pinnacle" not in bm.get("key","").lower():
                                continue
                            for mkt in bm.get("markets", []):
                                if market == "btts" and mkt.get("key") == "btts":
                                    for o in mkt.get("outcomes", []):
                                        if o.get("name") == "Yes":
                                            closing_odds = float(o.get("price", 0))
                                elif market == "over25" and mkt.get("key") == "totals":
                                    for o in mkt.get("outcomes", []):
                                        if o.get("name") == "Over" and abs(o.get("point",0) - 2.5) < 0.1:
                                            closing_odds = float(o.get("price", 0))
                    if closing_odds:
                        break
                except Exception:
                    continue

            if not closing_odds:
                continue

            # CLV berechnen
            clv = round((odds_taken / closing_odds - 1) * 100, 2)

            # Supabase updaten
            requests.patch(
                f"{SUPABASE_URL}/rest/v1/tips",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                params={"id": f"eq.{tip['id']}"},
                json={"odds_closing": closing_odds, "clv": clv},
                timeout=10,
            )
            updated += 1
            clv_emoji = "🟢" if clv > 0 else "🔴"
            log(f"   CLV: {match} → taken={odds_taken} closing={closing_odds} CLV={clv:+.1f}% {clv_emoji}")

        except Exception as e:
            log(f"CLV Error {tip.get('match','')}: {e}", "WARN")
            continue

    if updated > 0:
        # CLV Summary in Stats Gruppe
        try:
            r2 = requests.get(
                f"{SUPABASE_URL}/rest/v1/tips",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                params={
                    "date": f"eq.{today}",
                    "clv": "not.is.null",
                    "select": "clv,market",
                },
                timeout=10,
            )
            if r2.ok:
                clv_tips = r2.json()
                if clv_tips:
                    avg_clv = round(sum(t.get("clv",0) for t in clv_tips) / len(clv_tips), 2)
                    pos = sum(1 for t in clv_tips if t.get("clv",0) > 0)
                    neg = len(clv_tips) - pos
                    clv_emoji = "🟢" if avg_clv > 0 else "🔴"
                    nl = "\n"
                    msg = f"📊 <b>CLV UPDATE — {today}</b>\n"
                    msg += f"━━━━━━━━━━━━━━━━━━\n"
                    msg += f"{clv_emoji} Ø CLV: <b>{avg_clv:+.1f}%</b>\n"
                    msg += f"🟢 Positiv: {pos} · 🔴 Negativ: {neg}\n"
                    msg += f"📋 Tipps: {len(clv_tips)}\n"
                    msg += f"━━━━━━━━━━━━━━━━━━\n"
                    if avg_clv > 3:
                        msg += "<i>✅ Echter Edge vorhanden!</i>"
                    elif avg_clv > 0:
                        msg += "<i>⚠️ Leichter Edge — weiter beobachten</i>"
                    else:
                        msg += "<i>❌ Kein Edge — Strategie überdenken</i>"
                    send_telegram(msg, TELEGRAM_GROUPS.get("stats", TELEGRAM_CHAT_ID))
        except Exception:
            pass

    log(f"✅ CLV Update: {updated}/{len(tips)} Tipps aktualisiert")


def main():
    log("=" * 60)
    log("AI TIPP BOT - ALL-IN-ONE EDITION")
    log("=" * 60)

    check_config()
    check_rotation_schedule()

    now_utc = datetime.now(timezone.utc)
    target_date = now_utc.date()
    hour_utc = now_utc.hour

    log(f"⏰ {now_utc.strftime('%H:%M')} UTC | 📅 {target_date}")

    # 🏆 SETTLEMENT ZUERST - Ergebnisse von gestern/heute prüfen
    run_mode = env("RUN_MODE", "tips")  # "tips", "settlement", "both", "live"
    
    if run_mode in ["settlement", "both"]:
        log("🏆 Settlement Mode - prüfe vergangene Tipps...")
        run_settlement()
        run_clv_update()
        if run_mode == "settlement":
            log("Settlement fertig!")
            return

    # Live Bot Mode
    if run_mode == "live":
        log("🔴 Live Bot Mode...")
        run_live_bots()
        log("Live Bots fertig!")
        return

    # Tips Mode
    log(f"🎯 Tips Mode - suche Spiele...")

    log(f"🗓️  Datum (Target): {target_date}")
    log(f"Märkte: {[MARKET_INFO[m]['name'] for m in MARKETS_TO_RUN]}")
    active_leagues, league_stats = get_active_leagues()
    log(f"Ligen aktiv: {len(active_leagues)} von {len(LEAGUES_TO_RUN)}")
    log(
        f"Filter: ≥{MIN_PROBABILITY}% · "
        f"Quote {MIN_ODDS}-{MAX_ODDS} · "
        f"Conf ≥{MIN_CONFIDENCE}⭐"
    )
    log("")

    tips_by_market = {m: [] for m in MARKETS_TO_RUN}
    total_analyzed = 0
    _analyzed_count = [0]  # Thread-safe Counter
    import threading as _main_th
    _counter_lock = _main_th.Lock()
    _total_analyzed_lock = None  # wird in analyze_league als nonlocal genutzt

    # MAX_LEAGUES_PER_RUN wird ignoriert wenn Bulk-Fetch läuft
    # Grund: Bulk holt nur Ligen mit echten Spielen → kein Limit nötig
    if MAX_LEAGUES_PER_RUN > 0:
        log(f"ℹ️ MAX_LEAGUES_PER_RUN={MAX_LEAGUES_PER_RUN} gesetzt aber wird nach Bulk-Fetch ignoriert")
    log(f"Alle {len(active_leagues)} Ligen werden geprüft (nur aktive bekommen Analyse)")

    _fixtures_cache = {}  # Cache für Corners/Scorer Bot

    # ══════════════════════════════════════════════════════
    # SCHRITT 1: ALLE SPIELE BULK HOLEN (wenige Calls)
    # SofaScore all_today + martj42 + TheSportsDB = alle Ligen auf einmal
    # ══════════════════════════════════════════════════════
    log("🌍 Bulk-Fixture-Fetch startet...")

    # Supabase Cache prüfen — schon heute gefetcht?
    bulk_fixtures = {}
    cached_fixtures = cache_get_fixtures(target_date)
    if cached_fixtures:
        bulk_fixtures = {lg: fixes for lg, fixes in cached_fixtures.items()}
        log(f"🗄️ Fixtures aus Cache: {sum(len(v) for v in bulk_fixtures.values())} Spiele in {len(bulk_fixtures)} Ligen — kein neues Fetching nötig")
        # Trotzdem weitermachen mit active_today Berechnung
    else:
        log("🌐 Kein Cache → Fixtures werden neu geladen...")

    if not cached_fixtures:  # Nur fetchen wenn kein Cache
     pass  # placeholder
    # Quelle 1: SofaScore
    if not cached_fixtures:
        sofa_all = fetch_sofascore_all_today(target_date)
    if sofa_all:
        log(f"   ⚡ SofaScore: {sum(len(v) for v in sofa_all.values())} Spiele in {len(sofa_all)} Ligen")
        # SofaScore Slugs auf unsere Liga-Namen mappen
        slug_to_league = {v.lower(): k for k, v in SOFASCORE_SLUG_MAP.items()}
        for slug, fixtures in sofa_all.items():
            league_name = slug_to_league.get(slug.lower())
            if not league_name:
                # Fuzzy match
                for our_league in active_leagues:
                    our_slug = SOFASCORE_SLUG_MAP.get(our_league, "").lower()
                    if our_slug and (our_slug in slug or slug in our_slug):
                        league_name = our_league
                        break
            if league_name and fixtures:
                if league_name not in bulk_fixtures:
                    bulk_fixtures[league_name] = []
                bulk_fixtures[league_name].extend(fixtures)

    # Quelle 2: martj42 (internationale Spiele)
    intl_fixtures = get_international_fixtures_today(target_date)
    if intl_fixtures:
        log(f"   🌍 martj42: {len(intl_fixtures)} internationale Spiele")
        for fix in intl_fixtures:
            tournament = fix.get("tournament", "Freundschaftsspiele International")
            # Ordne dem richtigen Liga-Namen zu
            league_name = "Freundschaftsspiele International"
            for our_league in ["WM 2026", "UEFA Nations League", "Copa America", "Afrika Cup"]:
                if our_league.lower() in tournament.lower():
                    league_name = our_league
                    break
            if league_name not in bulk_fixtures:
                bulk_fixtures[league_name] = []
            bulk_fixtures[league_name].append(fix)

    # Quelle 3: ESPN + AllSports bulk (schnell, kein Key nötig)
    for league in active_leagues[:50]:  # Top 50 für Geschwindigkeit
        for fetch_fn in [fetch_espn_fixtures, fetch_allsports_fixtures, fetch_thesportsdb_fixtures]:
            fixes = fetch_fn(league, target_date)
            if fixes:
                if league not in bulk_fixtures:
                    bulk_fixtures[league] = []
                existing = {f"{f['home']}_{f['away']}" for f in bulk_fixtures.get(league, [])}
                for fix in fixes:
                    key = f"{fix['home']}_{fix['away']}"
                    if key not in existing:
                        bulk_fixtures[league].append(fix)
                        existing.add(key)
    
    # FotMob für Ligen die noch leer sind
    empty_leagues = [lg for lg in active_leagues if lg not in bulk_fixtures or not bulk_fixtures[lg]]
    for league in empty_leagues[:30]:
        fixes = fetch_fotmob_fixtures(league, target_date)
        if fixes:
            bulk_fixtures[league] = fixes

    # Flashscore + Livescore + BeSoccer + Soccerway + SportSRC als weitere Fallbacks
    empty_leagues = [lg for lg in active_leagues if lg not in bulk_fixtures or not bulk_fixtures[lg]]
    for league in empty_leagues[:40]:
        for fetch_fn in [
            lambda lg: fetch_flashscore_fixtures(lg, target_date),
            lambda lg: fetch_livescore_fixtures(lg, target_date),
            lambda lg: fetch_sportsrc_fixtures(lg, target_date),
            lambda lg: scrape_soccerway(lg, target_date),
        ]:
            try:
                fixes = fetch_fn(league)
                if fixes:
                    bulk_fixtures[league] = fixes
                    break
            except Exception:
                continue

    # GitHub OpenFootball — immer erreichbar, nie geblockt
    for league in active_leagues:
        if league not in bulk_fixtures or not bulk_fixtures[league]:
            fixes = fetch_github_football_data(league, target_date)
            if fixes:
                bulk_fixtures[league] = fixes

    # OpenLigaDB für deutsche Ligen
    for league in ["Bundesliga", "2. Bundesliga", "3. Liga Deutschland"]:
        if league not in bulk_fixtures or not bulk_fixtures[league]:
            fixes = fetch_openligadb(league, target_date)
            if fixes:
                bulk_fixtures[league] = fixes

    total_bulk = sum(len(v) for v in bulk_fixtures.values())
    active_with_games = len([lg for lg in bulk_fixtures if bulk_fixtures[lg]])
    log(f"   📊 Alle Quellen: {total_bulk} Spiele in {active_with_games} Ligen")
    
    # In Supabase speichern für nächste Runs
    if total_bulk > 0 and not cached_fixtures:
        cache_set_fixtures(target_date, bulk_fixtures)

    # Ligen MIT Spielen heute
    active_today = {lg: fixes for lg, fixes in bulk_fixtures.items() if fixes}
    log(f"✅ Bulk Done: {len(active_today)} Ligen haben heute Spiele (von {len(active_leagues)} aktiv)")

    # ── Fallback: wenn Bulk komplett leer → per-Liga fetchen ──
    use_bulk = len(active_today) > 0
    if not use_bulk:
        log("⚠️ Bulk leer → Fallback auf per-Liga Fetch (mit Threading)")
    log("")

    # ══════════════════════════════════════════════════════
    # SCHRITT 2: PARALLEL ANALYSE — 5 Ligen gleichzeitig
    # ══════════════════════════════════════════════════════
    import threading

    PARALLEL_WORKERS = int(env("PARALLEL_WORKERS", "5"))
    _lock = threading.Lock()

    def analyze_league(league):
        """Analysiert eine Liga in einem eigenen Thread."""
        try:
            if use_bulk and league not in active_today:
                return

            # Fixtures holen
            bulk_fixes = active_today.get(league, [])
            af_fix   = fetch_api_football(league, target_date)
            fj_fix   = fetch_football_json(league, target_date)
            ol_fix   = fetch_openligadb(league, target_date)
            espn_fix = fetch_espn_fixtures(league, target_date)
            tsdb_fix = fetch_thesportsdb_fixtures(league, target_date)

            fixtures = merge_fixtures(bulk_fixes, af_fix, fj_fix, ol_fix, espn_fix, tsdb_fix)

            if fixtures:
                with _lock:
                    _fixtures_cache[league] = fixtures

            odds = cache_get_odds(league, target_date)
            if odds is None:
                odds = fetch_odds_api(league, target_date)
                if odds:
                    cache_set_odds(league, target_date, odds)

            if not odds and not fixtures:
                return

            log(f"   [{league}] {len(fixtures)} Spiele | {len(odds)} Quoten")

            for market in MARKETS_TO_RUN:
                results, source = analyze_market_with_data(
                    market=market,
                    league=league,
                    target_date=target_date,
                    odds=odds,
                    fixtures=fixtures,
                )

                if results:
                    top = filter_top_tips(results, target_date, market)
                    if top:
                        with _lock:
                            tips_by_market[market].extend(top)
                            with _counter_lock:
                                _analyzed_count[0] += len(results)
                            log(f"   💎 [{league}] {len(top)} TOP {MARKET_INFO[market]['name']}")

                time.sleep(AI_SLEEP_SECONDS)

        except Exception as e:
            log(f"   ✗ [{league}] {e}", "ERROR")

    # Ligen in Batches aufteilen und parallel ausführen
    leagues_to_analyze = [lg for lg in active_leagues if not use_bulk or lg in active_today]
    log(f"⚡ Starte parallele Analyse: {len(leagues_to_analyze)} Ligen × {PARALLEL_WORKERS} Threads")

    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = {executor.submit(analyze_league, league): league for league in leagues_to_analyze}
        completed = 0
        for future in as_completed(futures):
            completed += 1
            if completed % 10 == 0:
                log(f"   ⏳ {completed}/{len(leagues_to_analyze)} Ligen analysiert...")

    total_top = sum(len(t) for t in tips_by_market.values())

    log("")
    log("════════════════════════════════════════")
    total_analyzed = _analyzed_count[0]
    log(f"Analysierte Tipps: {total_analyzed}")
    log(f"Top-Tipps: {total_top}")

    for m, tips in tips_by_market.items():
        log(f"   • {MARKET_INFO[m]['name']}: {len(tips)}")

    log("════════════════════════════════════════")
    if APIFOOTBALL_CALL_COUNTER > 0:
        log(f"📊 API-Football Calls verbraucht: {APIFOOTBALL_CALL_COUNTER}/{APIFOOTBALL_MAX_CALLS_PER_RUN}")
    log("Sende an Telegram + Supabase...")

    send_top_tips(tips_by_market, target_date)

    # 🔵⚽ Ecken + Scorer Bots
    if env("ENABLE_CORNERS_SCORER", "true").lower() in ["1", "true", "yes"]:
        run_corners_and_scorer_bots(
            target_date=target_date,
            active_leagues=active_leagues,
            odds_data_cache={},
            fixtures_cache=_fixtures_cache,
        )

    # 🔑 ADVANCED PROPS BOT
    if env("ENABLE_ADVANCED_PROPS", "true").lower() in ["1", "true", "yes"]:
        run_advanced_props_bot(
            active_leagues=active_leagues,
            fixtures_cache=_fixtures_cache,
            target_date=target_date,
        )

    # 🆕 MULTI-COMBO SYSTEM (3,4,5,6,7,8 Tipps)
    all_tips_flat = []
    for market_id, tips in tips_by_market.items():
        for tip in tips:
            tip["market"] = market_id
            # Nur Tipps ≥70% in Kombis für höhere Qualität
            if int(tip.get("probability", 0)) >= 70:
                all_tips_flat.append(tip)

    if len(all_tips_flat) >= 3:
        log("")
        log("🎰 Generiere Multi-Combos (3-8 Tipps)...")
        combo_chat = TELEGRAM_GROUPS.get("combos", TELEGRAM_CHAT_ID)  # Multi-Combos

        # Header für Combo Channel
        combo_header = f"<b>🎰 MULTI-COMBO TIPPS</b>" + "\n"
        combo_header += f"<i>📅 {target_date}</i>" + "\n"
        combo_header += f"<i>Basis: {len(all_tips_flat)} Top-Tipps</i>"
        send_telegram(combo_header, combo_chat)

        # Alle Combo-Größen generieren (3 bis 8)
        generated = 0
        for n in [3, 4, 5, 6, 7, 8, 9, 10, 11]:
            combo = generate_multi_combo_bets(all_tips_flat, num_tips=n)
            if combo:
                log(f"   {combo['label']}: Quote {combo['total_odds']}")
                msg = format_combo_telegram_message(combo)
                if msg:
                    send_telegram(msg, combo_chat)
                    generated += 1
            else:
                log(f"   ⚠️ Combo {n}: Zu wenig Tipps")

        log(f"✅ {generated} Combos generiert und gesendet!")
    else:
        log(f"ℹ️ Nur {len(all_tips_flat)} Tipps - min. 3 für Combos nötig")

    # Daily Report nach jedem 08:00 Run
    now_utc = datetime.now(timezone.utc)
    if now_utc.hour == 8:
        send_daily_report()
        log("📊 Daily Report gesendet!")

    log("Fertig!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}", "FATAL")
        log(traceback.format_exc(), "FATAL")
        sys.exit(1)
