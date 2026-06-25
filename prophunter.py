#!/usr/bin/env python3
"""PROP HUNTER v3 — Single File Edition
MLB / NBA / WNBA / NFL Player Props Tipster
Inspiriert von Basket Premium (82.5% WR), Basket Blitz VIP, JK (300u+)
"""
from __future__ import annotations
import asyncio, json, logging, os, re, time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Literal, Optional, Set, Tuple
import requests
from pydantic import BaseModel, ConfigDict, Field, field_validator, ValidationError

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
def _csv(k): return [x.strip() for x in os.environ.get(k,"").split(",") if x.strip()]
ODDS_API_KEYS  = _csv("ODDS_API_KEY")
GEMINI_KEYS    = _csv("GEMINI_API_KEY")
GROQ_KEYS      = _csv("GROQ_API_KEY")
BALLDONTLIE_KEY= os.environ.get("BALLDONTLIE_API_KEY","")
ODDSPAPI_KEY   = os.environ.get("ODDSPAPI","")
SUPABASE_URL   = os.environ.get("SUPABASE_URL","")
SUPABASE_KEY   = os.environ.get("SUPABASE_KEY","")
TG_TOKEN       = os.environ.get("TELEGRAM_BOT_TOKEN","")
TG_CHAT        = os.environ.get("TELEGRAM_CHAT_ID","")
ODDS_BASE      = "https://api.the-odds-api.com/v4"
BOOKMAKERS     = "bet365,draftkings,fanduel,betmgm,williamhill,pinnacle"
SHARP_BOOK     = "pinnacle"
UA             = "Mozilla/5.0 PropHunter/3.0"
HTTP_H         = {"User-Agent": UA}
TIMEOUT        = 30
MAX_EVENTS     = 8
MAX_PROPS_AI   = 70
KELLY_F        = 0.25
MAX_STAKE      = 1.5
MIN_STAKE      = 0.1
CACHE_TTL      = 6*3600
CACHE_FILE     = "odds_cache.json"
HISTORY_FILE   = "picks_history.json"
CLV_FILE       = "clv_history.json"
LOOKAHEAD_H    = 12
PM_MAX         = 5
STATCAST_DAYS  = 30
NBA_LAST_N     = 10
NFL_LAST_N     = 5
AI_TOKENS      = 3000
AI_TEMP        = 0.6
AI_RETRY       = 1
GEMINI_MODEL   = "gemini-2.0-flash"
GROQ_MODELS    = ["llama-3.3-70b-versatile","llama-3.1-70b-versatile","mixtral-8x7b-32768"]
FUZZY_THR      = 85
LINEUP_THR     = 88

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
_LOG_DONE = False
def setup_logging(level=logging.INFO):
    global _LOG_DONE
    if _LOG_DONE: return
    root = logging.getLogger(); root.setLevel(level); root.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    sh = logging.StreamHandler(); sh.setFormatter(fmt); root.addHandler(sh)
    try:
        fh = RotatingFileHandler("prophunter.log", maxBytes=2_000_000, backupCount=3)
        fh.setFormatter(fmt); root.addHandler(fh)
    except OSError: pass
    for n in ("urllib3","requests","httpx"): logging.getLogger(n).setLevel(logging.WARNING)
    _LOG_DONE = True
setup_logging()
log = logging.getLogger("prophunter")
# Suppress noisy font warnings
logging.getLogger("matplotlib").setLevel(logging.ERROR)
logging.getLogger("PIL").setLevel(logging.ERROR)

# ─────────────────────────────────────────────
# SEASON DETECTION
# ─────────────────────────────────────────────
def season_for(sport, now=None):
    now = now or datetime.now(timezone.utc); y,m = now.year,now.month
    if sport=="baseball_mlb": return y if 3<=m<=11 else y-1
    if sport in ("basketball_nba","basketball_euroleague"): return y-1 if m<10 else y
    if sport=="basketball_wnba": return y if 5<=m<=10 else y-1
    if sport=="americanfootball_nfl": return y-1 if m<9 else y
    return y
def is_nfl_offseason(): return datetime.now(timezone.utc).month in (3,4,5,6,7,8)
YEAR_MLB=season_for("baseball_mlb"); YEAR_NBA=season_for("basketball_nba")
YEAR_NFL=season_for("americanfootball_nfl")
log.info("seasons: MLB=%s | NBA=%s-%02d | NFL=%s%s",
    YEAR_MLB, YEAR_NBA, (YEAR_NBA+1)%100, YEAR_NFL, " (OFF)" if is_nfl_offseason() else "")

# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────
class Prop(BaseModel):
    model_config = ConfigDict(extra="allow")
    player:str; market:str; odds:float=Field(gt=1,lt=1000); point:Optional[float]=None
    sport:str; emoji:str; game:str; home:Optional[str]=None; away:Optional[str]=None
    commence_time:Optional[datetime]=None; pinnacle_odds:Optional[float]=None
    pinnacle_opp_odds:Optional[float]=None; game_total:Optional[float]=None
    enrichment:Optional[str]=None; features:dict=Field(default_factory=dict)

PickType=Literal["single","ladder","betbuilder","kombi2","big","super"]
class LadderLeg(BaseModel):
    market:str; odds:float=Field(gt=1); stake:float=Field(ge=0)
class Pick(BaseModel):
    model_config = ConfigDict(extra="allow")
    type:PickType; odds:float=Field(gt=1); stake:float=Field(ge=0,le=5)
    tier:Optional[int]=None; emoji:Optional[str]=None; player:Optional[str]=None
    team:Optional[str]=None; market:Optional[str]=None
    direction:Optional[Literal["over","under","yes","no"]]=None
    probability:Optional[float]=Field(default=None,ge=0,le=1)
    analysis:Optional[str]=None; legs:Optional[List[str]]=None
    picks:Optional[List[LadderLeg]]=None; game:Optional[str]=None
    ev:Optional[float]=None; edge_pct:Optional[float]=None
    @field_validator("stake")
    @classmethod
    def cap(cls,v): return round(min(v,5.0),2)
class HistoricalPick(BaseModel):
    date:str; player:str; team:str; market:str; sport:str; odds:float; stake:float
    direction:Optional[str]=None; probability:Optional[float]=None; dedup_key:str
    result:Optional[str]="pending"; profit:Optional[float]=None
    closing_odds:Optional[float]=None; clv_pct:Optional[float]=None
    created_at:str=Field(default_factory=lambda:datetime.now(timezone.utc).isoformat())

def dedup_key(player,market,point,direction):
    return "|".join([(player or "").lower().strip(),(market or "").lower().strip(),
                     f"{point:g}" if point is not None else "",(direction or "over").lower()])


# ─────────────────────────────────────────────
# SPORTS / MARKETS
# ─────────────────────────────────────────────
from typing import NamedTuple
class Market(NamedTuple):
    key:str; label:str; min_point:Optional[float]; min_odds:float
class SportCfg(NamedTuple):
    emoji:str; name:str; markets:List[Market]
SPORTS:Dict[str,SportCfg]={
    "baseball_mlb":SportCfg("⚾","MLB",[
        Market("batter_home_runs","Home Run",None,3.5),
        Market("batter_hits","Hits Over 1.5",None,1.7),
        Market("batter_total_bases","Total Bases",None,1.8),
        Market("pitcher_strikeouts","Pitcher K",None,1.8),
        Market("batter_stolen_bases","Stolen Base",None,4.0),
        Market("batter_rbis","RBI",None,2.5),
        Market("pitcher_outs","Outs Recorded",None,1.8),
        Market("pitcher_earned_runs","Earned Runs U",None,1.8),
        Market("pitcher_hits_allowed","Hits Allowed U",None,1.8),
    ]),
    "basketball_nba":SportCfg("🏀","NBA",[
        Market("player_rebounds_assists","Rebounds+Assists",10,1.8),
        Market("player_points_rebounds_assists","PRA",35,1.8),
        Market("player_points_rebounds","PR",30,1.8),
        Market("player_points_assists","PA",30,1.8),
        Market("player_rebounds_alternate","Rebounds",8,1.9),
        Market("player_assists_alternate","Assists",6,1.9),
        Market("player_threes_alternate","3PM",2,1.9),
        Market("player_double_double","Double Double",None,2.5),
        Market("player_points_alternate","Points",25,3.5),
        Market("player_blocks_alternate","Blocks",2,3.5),
        Market("player_steals_alternate","Steals",2,3.5),
        Market("player_triple_double","Triple Double",None,6.0),
    ]),
    "basketball_wnba":SportCfg("🏀","WNBA",[
        Market("player_rebounds_assists","Rebounds+Assists",8,1.8),
        Market("player_points_rebounds_assists","PRA",20,1.8),
        Market("player_points_rebounds","PR",18,1.8),
        Market("player_points_assists","PA",18,1.8),
        Market("player_points_alternate","Points",15,3.5),
        Market("player_rebounds_alternate","Rebounds",6,1.9),
        Market("player_assists_alternate","Assists",5,1.9),
        Market("player_threes_alternate","3PM",2,2.0),
        Market("player_double_double","Double Double",None,2.5),
    ]),
    "basketball_euroleague":SportCfg("🏀","Euroleague",[
        Market("player_points_alternate","Points",12,3.0),
        Market("player_rebounds_alternate","Rebounds",5,2.8),
        Market("player_assists_alternate","Assists",4,2.8),
        Market("player_threes_alternate","3PM",2,2.5),
    ]),
    "americanfootball_nfl":SportCfg("🏈","NFL",[
        Market("player_anytime_td","Anytime TD",None,2.5),
        Market("player_pass_tds_alternate","Pass TDs",None,3.0),
        Market("player_pass_yds_alternate","Pass Yds",None,1.8),
        Market("player_rush_yds_alternate","Rush Yds",None,3.0),
        Market("player_reception_yds_alternate","Rec Yds",None,3.0),
        Market("player_receptions_alternate","Receptions",None,1.8),
    ]),
}


# ─────────────────────────────────────────────
# BALLPARKS
# ─────────────────────────────────────────────
BALLPARKS:Dict[str,Tuple[float,float,bool]]={
    "Arizona Diamondbacks":(33.4455,-112.0667,False),"Atlanta Braves":(33.8908,-84.4678,True),
    "Baltimore Orioles":(39.2839,-76.6217,True),"Boston Red Sox":(42.3467,-71.0972,True),
    "Chicago Cubs":(41.9484,-87.6553,True),"Chicago White Sox":(41.8299,-87.6338,True),
    "Cincinnati Reds":(39.0975,-84.5069,True),"Cleveland Guardians":(41.4962,-81.6852,True),
    "Colorado Rockies":(39.7559,-104.9942,True),"Detroit Tigers":(42.3390,-83.0485,True),
    "Houston Astros":(29.7572,-95.3556,False),"Kansas City Royals":(39.0517,-94.4803,True),
    "Los Angeles Angels":(33.8003,-117.8827,True),"Los Angeles Dodgers":(34.0739,-118.2400,True),
    "Miami Marlins":(25.7781,-80.2197,False),"Milwaukee Brewers":(43.0280,-87.9712,False),
    "Minnesota Twins":(44.9817,-93.2776,True),"New York Mets":(40.7571,-73.8458,True),
    "New York Yankees":(40.8296,-73.9262,True),"Athletics":(38.7600,-121.2700,True),
    "Philadelphia Phillies":(39.9061,-75.1665,True),"Pittsburgh Pirates":(40.4469,-80.0057,True),
    "San Diego Padres":(32.7073,-117.1566,True),"San Francisco Giants":(37.7786,-122.3893,True),
    "Seattle Mariners":(47.5914,-122.3325,False),"St. Louis Cardinals":(38.6226,-90.1928,True),
    "Tampa Bay Rays":(27.7682,-82.6534,False),"Texas Rangers":(32.7473,-97.0847,False),
    "Toronto Blue Jays":(43.6414,-79.3894,False),"Washington Nationals":(38.8730,-77.0074,True),
}
PARK_FACTORS:Dict[str,int]={
    "Colorado Rockies":118,"Cincinnati Reds":115,"New York Yankees":113,
    "Philadelphia Phillies":108,"Boston Red Sox":107,"Baltimore Orioles":106,
    "Milwaukee Brewers":105,"Atlanta Braves":104,"Chicago Cubs":103,
    "Houston Astros":103,"Toronto Blue Jays":102,"Texas Rangers":102,
    "Minnesota Twins":101,"Arizona Diamondbacks":100,"Washington Nationals":100,
    "Los Angeles Angels":100,"St. Louis Cardinals":99,"Chicago White Sox":99,
    "Kansas City Royals":98,"Detroit Tigers":97,"Tampa Bay Rays":96,
    "New York Mets":96,"Cleveland Guardians":95,"San Francisco Giants":94,
    "Los Angeles Dodgers":93,"Athletics":92,"Pittsburgh Pirates":92,
    "Seattle Mariners":91,"Miami Marlins":89,"San Diego Padres":86,
}

# ─────────────────────────────────────────────
# BETTING MATH
# ─────────────────────────────────────────────
def implied_prob(odds): return 1/odds if odds>1 else 0
def no_vig(over,under):
    if over<=1 or under<=1: return None
    p1,p2=implied_prob(over),implied_prob(under); t=p1+p2
    return p1/t if t>0 else None
def ev(prob,odds,stake=1): return stake*(prob*(odds-1)-(1-prob))
def edge_pct(prob,odds): return prob-implied_prob(odds)
def kelly_stake(prob,odds,frac=KELLY_F):
    if prob<=0 or prob>=1 or odds<=1: return 0
    b=odds-1; q=1-prob; f=(prob*b-q)/b
    return round(max(MIN_STAKE,min(MAX_STAKE,f*frac*100/100)),2) if f>0 else 0
def stake_for(prob,odds,ai=None):
    if prob is None: return ai or 0.25
    k=kelly_stake(prob,odds)
    if ai is None: return k or 0.25
    return min(round((k+ai)/2,2),ai)


# ─────────────────────────────────────────────
# OPTIONAL LIBRARIES
# ─────────────────────────────────────────────
try: from rapidfuzz import fuzz,process; RAPIDFUZZ=True
except: RAPIDFUZZ=False
try:
    import contextlib, io
    from pybaseball import batting_stats as pb_bat,pitching_stats as pb_pit,statcast_batter,playerid_lookup
    def _quiet_lookup(last,first,fuzzy=True):
        with contextlib.redirect_stdout(io.StringIO()):
            return playerid_lookup(last,first,fuzzy=fuzzy)
    PYBASEBALL=True
except Exception: PYBASEBALL=False; _quiet_lookup=None
except: PYBASEBALL=False
try: import statsapi; MLB_STATS=True
except: MLB_STATS=False
try: from py_ball import playerstats as pyball_stats; from py_ball.utils import WNBA_HEADERS; PYBALL=True
except: PYBALL=False
try:
    import nflreadpy as nfl; NFL_DATA=True
except:
    try: import nfl_data_py as nfl; NFL_DATA=True
    except: NFL_DATA=False
try: from playwright.async_api import async_playwright; PLAYWRIGHT=True
except: PLAYWRIGHT=False
try: from supabase import create_client; HAS_SUPABASE=True
except: HAS_SUPABASE=False
try: import cloudscraper; HAS_CLOUDSCRAPER=True
except: HAS_CLOUDSCRAPER=False

# ─────────────────────────────────────────────
# CLOUDSCRAPER HELPER
# ─────────────────────────────────────────────
def _cs_get(url, timeout=20):
    """GET via cloudscraper (bypasses Cloudflare). Falls back to requests."""
    try:
        if HAS_CLOUDSCRAPER:
            cs = cloudscraper.create_scraper()
            r = cs.get(url, timeout=timeout)
            return r.text if r.status_code == 200 else None
        r = requests.get(url, headers=HTTP_H, timeout=timeout)
        return r.text if r.status_code == 200 else None
    except Exception as e:
        log.debug("cs_get %s: %s", url, e)
        return None

# ─────────────────────────────────────────────
# ENRICHMENT: STATZ.AI (NBA Hit Rates)
# ─────────────────────────────────────────────
_STATZ_CACHE: dict = {}

def fetch_statz_hitrates(sport: str = "nba") -> dict:
    """
    Holt Hit Rates von statz.ai via Playwright (JS-rendered).
    Gibt dict zurück: {player_name_lower: [{prop, l5, l10, season, odds}]}
    """
    cache_key = f"statz_{sport}"
    if cache_key in _STATZ_CACHE:
        return _STATZ_CACHE[cache_key]
    if not PLAYWRIGHT:
        log.warning("statz.ai: Playwright nicht verfügbar")
        return {}
    url = f"https://statz.ai/{sport}/hit-rates"
    result = {}
    try:
        import asyncio, re as _re
        async def _scrape():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                ctx = await browser.new_context(user_agent=UA)
                page = await ctx.new_page()
                await page.goto(url, timeout=30000, wait_until="networkidle")
                # Warten bis Tabelle geladen
                try:
                    await page.wait_for_selector("table tbody tr", timeout=10000)
                except Exception:
                    pass
                await page.wait_for_timeout(2000)
                # Alle Tabellenzeilen extrahieren
                rows = await page.query_selector_all("table tbody tr")
                data = []
                for row in rows:
                    cells = await row.query_selector_all("td")
                    cell_texts = []
                    for cell in cells:
                        t = await cell.inner_text()
                        cell_texts.append(t.strip())
                    data.append(cell_texts)
                await browser.close()
                return data
        rows_data = asyncio.run(_scrape())
        for cells in rows_data:
            if len(cells) < 5: continue
            player = cells[0].split('\n')[0].strip().lower()
            prop   = cells[2].strip() if len(cells) > 2 else ""
            l5     = cells[3].strip() if len(cells) > 3 else ""
            l10    = cells[4].strip() if len(cells) > 4 else ""
            season = cells[5].strip() if len(cells) > 5 else ""
            odds   = cells[6].strip() if len(cells) > 6 else ""
            if not player or not prop: continue
            if "%" not in (l5+l10+season): continue
            result.setdefault(player, []).append({
                "prop": prop, "l5": l5, "l10": l10,
                "season": season, "odds": odds
            })
        log.info("statz.ai: %d Spieler geladen (%s)", len(result), sport)
        _STATZ_CACHE[cache_key] = result
        return result
    except Exception as e:
        log.warning("statz.ai Playwright: %s", e)
        return {}

def enrich_statz(props: list) -> list:
    """Fügt statz.ai Hit Rates als Enrichment hinzu (NBA/WNBA)."""
    nba_props = [p for p in props if p.sport in ("NBA", "WNBA")]
    if not nba_props: return props
    # Beide Sports laden falls nötig
    data: dict = {}
    sports_present = set(p.sport for p in nba_props)
    for s in sports_present:
        sport_key = "wnba" if s == "WNBA" else "nba"
        data.update(fetch_statz_hitrates(sport_key))
    if not data: return props
    enriched = 0
    for p in nba_props:
        name = (p.player or "").lower().strip()
        # Fuzzy match
        matched = data.get(name)
        if not matched and RAPIDFUZZ:
            keys = list(data.keys())
            res = process.extractOne(name, keys, scorer=fuzz.token_sort_ratio)
            if res and res[1] >= FUZZY_THR:
                matched = data[res[0]]
        if not matched: continue
        # Besten passenden Prop finden
        market_lower = (p.market or "").lower()
        best = None
        for entry in matched:
            prop_lower = entry["prop"].lower()
            if any(k in market_lower for k in prop_lower.split()):
                best = entry
                break
        if not best:
            best = matched[0]  # Erstes nehmen
        tag = f"Statz L5:{best['l5']} L10:{best['l10']} Season:{best['season']}"
        p.enrichment = (p.enrichment + " | " if p.enrichment else "") + tag
        enriched += 1
    log.info("statz.ai enriched: %d", enriched)
    return props

# ─────────────────────────────────────────────
# ENRICHMENT: PROPCRUNCHER (Best Play Grade)
# ─────────────────────────────────────────────
_PROPCRUNCHER_CACHE: dict = {}

def fetch_propcruncher(sport: str) -> dict:
    """
    Holt Best Play Grades von propcruncher.com.
    Gibt dict zurück: {player_name_lower: {"grade": "S", "prop": "Rebounds", "line": "o 3.5"}}
    """
    cache_key = f"pc_{sport}"
    if cache_key in _PROPCRUNCHER_CACHE:
        return _PROPCRUNCHER_CACHE[cache_key]
    sport_map = {
        "NBA": "nba", "WNBA": "wnba", "MLB": "mlb",
        "NHL": "nhl", "NFL": "nfl"
    }
    slug = sport_map.get(sport, sport.lower())
    url = f"https://propcruncher.com/props/{slug}/today"
    html = _cs_get(url)
    if not html:
        log.warning("propcruncher: kein Response für %s", sport)
        return {}
    try:
        import re as _re
        result = {}
        # Tabelle: Player | Prop | Line | Grade
        rows = _re.findall(r'<tr[^>]*>(.*?)</tr>', html, _re.DOTALL | _re.IGNORECASE)
        def txt(s): return _re.sub(r'<[^>]+>', '', s).strip()
        for row in rows:
            cells = [txt(c) for c in _re.findall(r'<td[^>]*>(.*?)</td>', row, _re.DOTALL | _re.IGNORECASE)]
            if len(cells) < 4: continue
            player_raw = cells[0].split('\n')[0].strip().lower()
            # Strip team/matchup suffix: "pete crow-armstrongchc vs nym" → "pete crow-armstrong"
            import re as _re2
            player = _re2.sub(r'[a-z]{2,3}\s+vs\s+[a-z]{2,3}.*$', '', player_raw).strip()
            player = _re2.sub(r'\s+[a-z]{2,3}$', '', player).strip()
            prop = cells[1].strip()
            line = cells[2].strip()
            grade = cells[3].strip()
            if not player or grade not in ("S", "A", "B", "C"): continue
            if player not in result or grade < result[player]["grade"]:
                result[player] = {"grade": grade, "prop": prop, "line": line}
        log.info("propcruncher: %d Spieler (%s)", len(result), sport)
        if result:
            sample = list(result.items())[:5]
            log.info("propcruncher sample names: %s", [k for k,_ in sample])
        _PROPCRUNCHER_CACHE[cache_key] = result
        return result
    except Exception as e:
        log.warning("propcruncher parse: %s", e)
        return {}

def enrich_propcruncher(props: list) -> list:
    """Fügt ProCruncher Best Play Grade als Enrichment hinzu."""
    sports = set(p.sport for p in props if p.sport in ("NBA","WNBA","MLB","NHL","NFL"))
    if not sports: return props
    all_data: dict = {}
    for sport in sports:
        d = fetch_propcruncher(sport)
        all_data.update(d)
    enriched = 0
    pc_keys = list(all_data.keys())
    log.info("propcruncher pick names: %s", [(p.player or "").lower().strip() for p in props[:5]])
    log.info("propcruncher pc keys sample: %s", pc_keys[:10])
    for p in props:
        name = (p.player or "").lower().strip()
        matched = all_data.get(name)
        if not matched and RAPIDFUZZ:
            keys = list(all_data.keys())
            res = process.extractOne(name, keys, scorer=fuzz.token_sort_ratio)
            if res and res[1] >= FUZZY_THR:
                matched = all_data[res[0]]
        if not matched: continue
        grade = matched.get("grade", "")
        if grade in ("S", "A"):
            tag = f"PC:{grade} {matched.get('prop','')} {matched.get('line','')}"
            p.enrichment = (p.enrichment + " | " if p.enrichment else "") + tag
            enriched += 1
    log.info("propcruncher enriched: %d", enriched)
    return props

# ─────────────────────────────────────────────
# ENRICHMENT: FREEPLAYERPROPS (NHL Game Logs)
# ─────────────────────────────────────────────
_FPP_SLUG_CACHE: dict = {}
_FPP_STATS_CACHE: dict = {}

def _fpp_find_slug(player_name: str, sport: str = "nhl") -> Optional[str]:
    """Sucht den FPP Slug für einen Spieler via Sportseite."""
    sport_map = {"NHL": "hockey/nhl", "NBA": "basketball/nba",
                 "MLB": "baseball/mlb", "NFL": "american-football/nfl"}
    path = sport_map.get(sport, "hockey/nhl")
    cache_key = f"{sport}_slugs"
    if cache_key not in _FPP_SLUG_CACHE:
        url = f"https://freeplayerprops.com/{path}"
        html = _cs_get(url)
        if not html:
            _FPP_SLUG_CACHE[cache_key] = {}
            return None
        import re as _re
        # Links: /hockey/nhl/connor-mcdavid/f65rr45d
        links = _re.findall(
            rf'href="(/{path}/([a-z0-9-]+)/([a-z0-9]+))"', html)
        slug_map = {}
        for full, name_slug, uid in links:
            display = name_slug.replace("-", " ")
            slug_map[display] = full
        _FPP_SLUG_CACHE[cache_key] = slug_map
    slug_map = _FPP_SLUG_CACHE.get(cache_key, {})
    name_lower = player_name.lower()
    if name_lower in slug_map:
        return slug_map[name_lower]
    if RAPIDFUZZ:
        keys = list(slug_map.keys())
        res = process.extractOne(name_lower, keys, scorer=fuzz.token_sort_ratio)
        if res and res[1] >= FUZZY_THR:
            return slug_map[res[0]]
    return None

def fetch_fpp_gamelogs(player_name: str, sport: str = "NHL", season: str = "2025-26") -> list:
    """Holt Game Logs von freeplayerprops.com für NHL/NBA/MLB."""
    cache_key = f"fpp_{sport}_{player_name}"
    if cache_key in _FPP_STATS_CACHE:
        return _FPP_STATS_CACHE[cache_key]
    slug = _fpp_find_slug(player_name, sport)
    if not slug:
        return []
    url = f"https://freeplayerprops.com{slug}/gamelog/{season}/all"
    html = _cs_get(url)
    if not html:
        return []
    try:
        import re as _re
        def txt(s): return _re.sub(r'<[^>]+>', '', s).strip()
        rows = _re.findall(r'<tr[^>]*>(.*?)</tr>', html, _re.DOTALL | _re.IGNORECASE)
        # Header-Zeile überspringen
        games = []
        for row in rows[1:]:
            cells = [txt(c) for c in _re.findall(r'<td[^>]*>(.*?)</td>', row, _re.DOTALL | _re.IGNORECASE)]
            if len(cells) < 10: continue
            try:
                # Spalten: #, Date, Team, Opp, Result, G, A, P, +/-, PIM, PPG, PPP, ...S(shots)
                game = {
                    "date": cells[1], "result": cells[4],
                    "goals": int(cells[5] or 0), "assists": int(cells[6] or 0),
                    "points": int(cells[7] or 0),
                }
                # Shots on goal: Spalte 21 (S)
                if len(cells) > 21:
                    try: game["shots"] = int(cells[21] or 0)
                    except: game["shots"] = 0
                games.append(game)
            except Exception:
                continue
        log.info("FPP %s %s: %d games", sport, player_name, len(games))
        _FPP_STATS_CACHE[cache_key] = games
        return games
    except Exception as e:
        log.warning("FPP parse %s: %s", player_name, e)
        return []

def enrich_fpp_nhl(props: list) -> list:
    """Fügt FreePlayerProps NHL Stats als Enrichment hinzu."""
    nhl_props = [p for p in props if p.sport == "NHL"]
    if not nhl_props: return props
    enriched = 0
    for p in nhl_props:
        games = fetch_fpp_gamelogs(p.player or "", "NHL")
        if not games or len(games) < 3: continue
        l5 = games[:5]
        avg_pts = sum(g.get("points", 0) for g in l5) / len(l5)
        avg_shots = sum(g.get("shots", 0) for g in l5) / len(l5)
        streak_pts = 0
        for g in l5:
            if g.get("points", 0) > 0: streak_pts += 1
            else: break
        tag = f"FPP L5: {avg_pts:.1f}pts {avg_shots:.1f}sog streak:{streak_pts}"
        p.enrichment = (p.enrichment + " | " if p.enrichment else "") + tag
        enriched += 1
    log.info("FPP NHL enriched: %d", enriched)
    return props

# ─────────────────────────────────────────────
# ENRICHMENT: BALLDONTLIE PLAYER PROPS (NBA/WNBA)
# ─────────────────────────────────────────────
_BDL_PROPS_CACHE: dict = {}

def fetch_bdl_props(sport: str = "nba") -> dict:
    """
    Holt Player Props von BallDontLie (braucht GOAT Plan).
    Gibt dict zurück: {player_name_lower: [{market, line, over_odds, under_odds}]}
    """
    cache_key = f"bdl_props_{sport}"
    if cache_key in _BDL_PROPS_CACHE:
        return _BDL_PROPS_CACHE[cache_key]
    key = BDL_KEY
    if not key:
        return {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base = "https://api.balldontlie.io/v1" if sport == "nba" else f"https://{sport}.balldontlie.io/v1"
    url = f"{base}/player_props"
    try:
        r = requests.get(url, headers={"Authorization": key},
                         params={"date": today, "per_page": 100}, timeout=20)
        if r.status_code == 402:
            log.warning("BDL Props: GOAT Plan erforderlich")
            return {}
        if r.status_code != 200:
            log.warning("BDL Props: %s", r.status_code)
            return {}
        data = r.json().get("data", [])
        result: dict = {}
        for item in data:
            pname = (item.get("player", {}) or {}).get("display_name", "").lower()
            if not pname: continue
            entry = {
                "market": item.get("stat_type", ""),
                "line": item.get("line"),
                "over_odds": item.get("over_odds"),
                "under_odds": item.get("under_odds"),
            }
            result.setdefault(pname, []).append(entry)
        log.info("BDL Props: %d Spieler (%s)", len(result), sport)
        _BDL_PROPS_CACHE[cache_key] = result
        return result
    except Exception as e:
        log.warning("BDL Props: %s", e)
        return {}

def enrich_bdl_props(props: list) -> list:
    """Nutzt BallDontLie Props als zusätzliche Odds-Quelle für NBA/WNBA."""
    sports = set(p.sport for p in props if p.sport in ("NBA", "WNBA"))
    if not sports: return props
    all_data: dict = {}
    for s in sports:
        all_data.update(fetch_bdl_props(s.lower()))
    if not all_data: return props
    enriched = 0
    for p in props:
        if p.sport not in ("NBA", "WNBA"): continue
        matched = _fuzzy(p.player or "", all_data)
        if not matched: continue
        market_lower = (p.market or "").lower()
        for entry in matched:
            m = (entry.get("market") or "").lower()
            if any(k in market_lower for k in m.split("_")):
                line = entry.get("line")
                over = entry.get("over_odds")
                if line and over:
                    tag = f"BDL {entry['market']} {line} @{over}"
                    p.enrichment = (p.enrichment + " | " if p.enrichment else "") + tag
                    enriched += 1
                break
    log.info("BDL Props enriched: %d", enriched)
    return props

# ─────────────────────────────────────────────
# ENRICHMENT: DATASTREAK (Hit Rates, alle Sports)
# ─────────────────────────────────────────────
_DATASTREAK_CACHE: dict = {}

def fetch_datastreak(sport: str) -> dict:
    """
    Holt Hit Rates von thedatastreak.com via Playwright.
    Gibt dict zurück: {player_name_lower: {l5, l10, season, streak}}
    """
    cache_key = f"ds_{sport}"
    if cache_key in _DATASTREAK_CACHE:
        return _DATASTREAK_CACHE[cache_key]
    sport_map = {"NBA": "nba", "WNBA": "wnba", "MLB": "mlb", "NHL": "nhl", "NFL": "nfl"}
    slug = sport_map.get(sport)
    if not slug or not PLAYWRIGHT:
        return {}
    url = f"https://thedatastreak.com/{slug}/props"
    result: dict = {}
    try:
        import asyncio
        async def _scrape():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, timeout=25000, wait_until="networkidle")
                await page.wait_for_timeout(3000)
                content = await page.inner_text("body")
                await browser.close()
                return content
        content = asyncio.run(_scrape())
        import re as _re
        # Parse: "PlayerName L5:80% L10:75% Season:72%"
        # DataStreak zeigt Tabellen — suche nach Mustern
        lines = content.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line or len(line) < 3:
                i += 1; continue
            # Hit rate patterns: Zahlen mit %
            pct_matches = _re.findall(r'(\d+)%', line)
            if len(pct_matches) >= 2:
                # Spielername ist wahrscheinlich die Zeile davor
                name = lines[i-1].strip().lower() if i > 0 else ""
                if name and len(name) > 3 and not any(c.isdigit() for c in name):
                    result[name] = {
                        "l5": pct_matches[0] + "%",
                        "l10": pct_matches[1] + "%",
                        "season": pct_matches[2] + "%" if len(pct_matches) > 2 else "",
                    }
            i += 1
        log.info("DataStreak %s: %d Spieler", sport, len(result))
    except Exception as e:
        log.warning("DataStreak %s: %s", sport, e)
    _DATASTREAK_CACHE[cache_key] = result
    return result

def enrich_datastreak(props: list) -> list:
    """Fügt DataStreak Hit Rates als Enrichment hinzu."""
    sports = set(p.sport for p in props)
    all_data: dict = {}
    for s in sports:
        d = fetch_datastreak(s)
        if d: all_data.update(d)
    if not all_data: return props
    enriched = 0
    for p in props:
        matched = _fuzzy(p.player or "", all_data)
        if not matched: continue
        tag = f"DS L5:{matched.get('l5','')} L10:{matched.get('l10','')} S:{matched.get('season','')}"
        p.enrichment = (p.enrichment + " | " if p.enrichment else "") + tag
        enriched += 1
    log.info("DataStreak enriched: %d", enriched)
    return props

# ─────────────────────────────────────────────
# ENRICHMENT: ODDSPEDIA (Odds Vergleich)
# ─────────────────────────────────────────────
_ODDSPEDIA_CACHE: dict = {}

def fetch_oddspedia(sport: str) -> dict:
    """
    Holt Odds von oddspedia.com via cloudscraper.
    Gibt dict zurück: {player_name_lower: {market, best_odds, bookmaker}}
    """
    cache_key = f"op_{sport}"
    if cache_key in _ODDSPEDIA_CACHE:
        return _ODDSPEDIA_CACHE[cache_key]
    sport_map = {
        "NBA": "basketball/nba", "WNBA": "basketball/wnba",
        "MLB": "baseball/mlb", "NHL": "ice-hockey/nhl", "NFL": "american-football/nfl"
    }
    slug = sport_map.get(sport)
    if not slug:
        return {}
    url = f"https://oddspedia.com/{slug}/player-props"
    html = _cs_get(url)
    if not html:
        log.warning("Oddspedia: kein Response für %s", sport)
        return {}
    try:
        import re as _re
        def txt(s): return _re.sub(r'<[^>]+>', '', s).strip()
        result: dict = {}
        rows = _re.findall(r'<tr[^>]*>(.*?)</tr>', html, _re.DOTALL | _re.IGNORECASE)
        for row in rows:
            cells = [txt(c) for c in _re.findall(r'<td[^>]*>(.*?)</td>', row, _re.DOTALL | _re.IGNORECASE)]
            if len(cells) < 3: continue
            player = cells[0].split('\n')[0].strip().lower()
            market = cells[1].strip() if len(cells) > 1 else ""
            odds_str = cells[2].strip() if len(cells) > 2 else ""
            bookie = cells[3].strip() if len(cells) > 3 else ""
            if not player or not odds_str: continue
            try:
                odds_val = float(odds_str)
                if odds_val < 1.01: continue
            except: continue
            if player not in result or odds_val > result[player].get("best_odds", 0):
                result[player] = {"market": market, "best_odds": odds_val, "bookmaker": bookie}
        log.info("Oddspedia: %d Spieler (%s)", len(result), sport)
        _ODDSPEDIA_CACHE[cache_key] = result
        return result
    except Exception as e:
        log.warning("Oddspedia parse: %s", e)
        return {}

def enrich_oddspedia(props: list) -> list:
    """Fügt Oddspedia beste verfügbare Odds als Enrichment hinzu."""
    sports = set(p.sport for p in props)
    all_data: dict = {}
    for s in sports:
        d = fetch_oddspedia(s)
        if d: all_data.update(d)
    if not all_data: return props
    enriched = 0
    for p in props:
        matched = _fuzzy(p.player or "", all_data)
        if not matched: continue
        best = matched.get("best_odds", 0)
        bk = matched.get("bookmaker", "")
        if best > p.odds + 0.05:  # Nur wenn Oddspedia besser ist
            tag = f"OP best:{best} @{bk}"
            p.enrichment = (p.enrichment + " | " if p.enrichment else "") + tag
            enriched += 1
    log.info("Oddspedia enriched: %d", enriched)
    return props

def _fuzzy(name, d, thr=85):
    if not name or not d: return None
    nl = name.lower().strip()
    if nl in d: return d[nl]
    if not RAPIDFUZZ: return None
    best = process.extractOne(nl, list(d.keys()), scorer=fuzz.WRatio, score_cutoff=thr)
    return d[best[0]] if best else None

# ─────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────
def load_cache(force_stale=False):
    if not os.path.exists(CACHE_FILE): return {}
    try:
        d=json.load(open(CACHE_FILE)); age=time.time()-d.get("timestamp",0)
        ttl=d.get("ttl",CACHE_TTL)
        if age<ttl:
            log.info("Odds cache HIT (%.0fmin)",age/60); return d.get("odds",{})
        if force_stale:
            log.info("Odds cache STALE (%.0fmin) — using anyway (keys exhausted)",age/60)
            return d.get("odds",{})
        log.info("Odds cache expired (%.0fmin)",age/60)
    except Exception as e: log.warning("cache load: %s",e)
    return {}
def save_cache(odds,earliest=None):
    ttl=CACHE_TTL
    if earliest:
        try:
            ts=datetime.fromisoformat(earliest.replace("Z","+00:00")).timestamp()
            delta=max(0,ts-time.time()); ttl=int(min(CACHE_TTL,max(60,delta/3)))
        except: pass
    # When no keys left, extend TTL to 24h so stale cache covers next run
    if _all_keys_dead(): ttl=86400
    try: json.dump({"timestamp":time.time(),"ttl":ttl,"odds":odds},open(CACHE_FILE,"w"),indent=2)
    except: pass


# ─────────────────────────────────────────────
# ODDS API
# ─────────────────────────────────────────────
_kid=0
_dead_keys: set = set()
def _key():
    if not ODDS_API_KEYS: return ""
    # Find first non-dead key
    for i in range(len(ODDS_API_KEYS)):
        idx = (_kid + i) % len(ODDS_API_KEYS)
        if idx not in _dead_keys:
            return ODDS_API_KEYS[idx]
    return ""  # all dead
def _next_key():
    global _kid
    _dead_keys.add(_kid % len(ODDS_API_KEYS))
    _kid+=1
    remaining = len(ODDS_API_KEYS) - len(_dead_keys)
    log.warning("Odds API → key %d/%d (%d dead)", (_kid%max(1,len(ODDS_API_KEYS)))+1, len(ODDS_API_KEYS), len(_dead_keys))
    return _key()
def _all_keys_dead():
    return len(_dead_keys) >= len(ODDS_API_KEYS) if ODDS_API_KEYS else True
def _req(url,params,retries=1):
    if _all_keys_dead(): return None
    for i in range(retries+1):
        k = _key()
        if not k: return None
        params["apiKey"] = k
        try: r=requests.get(url,params=params,headers=HTTP_H,timeout=TIMEOUT)
        except requests.RequestException as e: log.warning("HTTP: %s",e); time.sleep(1); continue
        if r.status_code==200:
            rem = r.headers.get("x-requests-remaining","?")
            log.debug("ok quota=%s", rem)
            # Proactively switch if quota nearly exhausted
            if rem != "?" and int(rem) == 0:
                log.warning("Odds API key quota=0, marking dead")
                _next_key()
            return r.json()
        if r.status_code in (401,422) and ODDS_API_KEYS:
            log.warning("Odds API quota exhausted on key %d", (_kid%len(ODDS_API_KEYS))+1)
            _next_key()
            if _all_keys_dead(): log.error("ALL Odds API keys exhausted!"); return None
            continue
        if r.status_code in (429,500,502,503):
            _next_key(); time.sleep(1); continue
        log.warning("Odds API %d", r.status_code); return None
    return None
_events_cache: dict = {}
def fetch_events(sport):
    if not ODDS_API_KEYS: return []
    # Check in-memory cache first (valid for 30min)
    cached = _events_cache.get(sport)
    if cached and time.time() - cached[0] < 1800:
        log.debug("%s: %d events (cached)", sport, len(cached[1]))
        return cached[1]
    if _all_keys_dead(): return []
    now=datetime.now(timezone.utc); end=now+timedelta(hours=LOOKAHEAD_H)
    data=_req(f"{ODDS_BASE}/sports/{sport}/events",{"apiKey":_key(),"dateFormat":"iso",
        "commenceTimeFrom":now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commenceTimeTo":end.strftime("%Y-%m-%dT%H:%M:%SZ")}) or []
    _events_cache[sport] = (time.time(), data)
    log.info("%s: %d events",sport,len(data)); return data
def fetch_props(sport,eid,mkeys):
    return _req(f"{ODDS_BASE}/sports/{sport}/events/{eid}/odds",
        {"apiKey":_key(),"regions":"us,eu,uk","markets":",".join(mkeys+["totals"]),
         "oddsFormat":"decimal","bookmakers":BOOKMAKERS})
def extract_total(data):
    tots=[]
    for bm in data.get("bookmakers",[]):
        for m in bm.get("markets",[]):
            if m.get("key")=="totals":
                for o in m.get("outcomes",[]):
                    if o.get("name")=="Over" and o.get("point"): tots.append(float(o["point"]))
    return round(sum(tots)/len(tots),1) if tots else None
def extract_props_from_data(data,mkey,label,min_pt,min_odds,sport,emoji,home,away,ct_iso):
    agg={}
    for bm in data.get("bookmakers",[]):
        bk=bm.get("key","")
        for mkt in bm.get("markets",[]):
            if mkt.get("key")!=mkey: continue
            for o in mkt.get("outcomes",[]):
                desc=o.get("description","") or ""; nf=o.get("name","") or ""
                pt=o.get("point"); price=o.get("price",0)
                if nf in {"Over","Under","Yes","No",""}:
                    pl,ot=desc,nf
                else: pl,ot=nf,desc
                if not pl or pl in {"Over","Under","Yes","No",""}: continue
                if min_pt and pt is not None and pt<min_pt: continue
                if price<=1: continue
                k=f"{pl}|{pt if pt is not None else ''}"
                rec=agg.setdefault(k,{"player":pl,"point":pt,"prices":[],"po":None,"pu":None})
                if bk==SHARP_BOOK:
                    if ot in ("Over","Yes"): rec["po"]=price
                    elif ot in ("Under","No"): rec["pu"]=price
                if ot in ("Over","Yes") or ot=="": rec["prices"].append(price)
    out=[]
    ct=None
    if ct_iso:
        try: ct=datetime.fromisoformat(ct_iso.replace("Z","+00:00"))
        except: pass
    for rec in agg.values():
        prices=[p for p in rec["prices"] if p>1]
        if not prices: continue
        avg=sum(prices)/len(prices)
        if avg<min_odds: continue
        fair=no_vig(rec["po"],rec["pu"]) if rec["po"] and rec["pu"] else None
        out.append(Prop(player=rec["player"],market=label,odds=round(avg,2),point=rec["point"],
            sport=sport,emoji=emoji,game=f"{away} @ {home}",home=home,away=away,commence_time=ct,
            pinnacle_odds=rec["po"],pinnacle_opp_odds=rec["pu"],
            features={"fair_prob":fair} if fair else {}))
    return out


# ─────────────────────────────────────────────
# WEATHER
# ─────────────────────────────────────────────
def fetch_weather(team):
    park=BALLPARKS.get(team)
    if not park: return None
    lat,lon,outdoor=park
    if not outdoor: return "Dome"
    try:
        r=requests.get("https://api.open-meteo.com/v1/forecast",params={
            "latitude":lat,"longitude":lon,"forecast_days":1,
            "hourly":"temperature_2m,wind_speed_10m,relative_humidity_2m,surface_pressure"},timeout=TIMEOUT)
        if r.status_code!=200: return None
        h=r.json().get("hourly",{}); i=min(22,len(h.get("temperature_2m",[]))-1)
        if i<0: return None
        t=h["temperature_2m"][i]; w=h["wind_speed_10m"][i]
        hum=h.get("relative_humidity_2m",[None]*24)[i]; p=h.get("surface_pressure",[None]*24)[i]
        note=f"{t:.0f}°C Wind{w:.0f}km/h"
        if hum: note+=f" {hum:.0f}%Hum"
        if p: note+=f" {p:.0f}hPa"
        if t>=24 and w>=15: note+=" 🌬️HR+"
        elif t<12: note+=" 🥶HR-"
        return note
    except: return None

# ─────────────────────────────────────────────
# MLB SOURCES
# ─────────────────────────────────────────────
_mlb_bat={}; _mlb_pit={}; _mlb_lu={}; _mlb_id_cache={}
def fetch_team_strikeout_rates() -> dict:
    """Holt Strikeout-Raten pro Team (wie anfällig für Ks) via MLB StatsAPI."""
    cache_key = "team_k_rates"
    if cache_key in _PLAYER_STATS_CACHE:
        return _PLAYER_STATS_CACHE[cache_key]
    try:
        r = requests.get(
            "https://statsapi.mlb.com/api/v1/stats",
            params={"sportId":1,"season":YEAR_MLB,"gameType":"R",
                    "stats":"season","group":"hitting","limit":30,
                    "fields":"stats,splits,team,name,stat,strikeOuts,plateAppearances"},
            headers=HTTP_H, timeout=TIMEOUT)
        if r.status_code != 200: return {}
        out = {}
        for split in r.json().get("stats",[{}])[0].get("splits",[]):
            name = split.get("team",{}).get("name","").lower()
            stat = split.get("stat",{})
            so = int(stat.get("strikeOuts",0) or 0)
            pa = int(stat.get("plateAppearances",1) or 1)
            out[name] = round(so/pa*100, 1) if pa>0 else 20.0
        _PLAYER_STATS_CACHE[cache_key] = out
        log.info("Team K-Rates: %d Teams", len(out))
        return out
    except Exception as e:
        log.warning("team K-rates: %s", e)
        return {}

def get_pitcher_strikeout_context(pitcher: str, opponent_team: str) -> dict:
    """Kombiniert Pitcher K/9 + Gegner K-Rate für Strikeout-Wahrscheinlichkeit."""
    pitchers = fetch_mlb_pitchers()
    k_rates = fetch_team_strikeout_rates()
    pn = pitcher.lower()
    pit_stats = next((v for k,v in pitchers.items() if pn in k or k in pn), {})
    opp_k_rate = k_rates.get(opponent_team.lower(), 20.0)
    k9 = float(pit_stats.get("k9", 8.0) or 8.0)
    # Erwartete Ks = (K/9 * opp_k_rate_adj) / 9 Innings
    league_avg_k_rate = 22.5
    opp_adj = opp_k_rate / league_avg_k_rate
    expected_ks = round(k9 * opp_adj, 1)
    return {
        "k9": k9,
        "opp_k_rate": opp_k_rate,
        "expected_ks": expected_ks,
        "is_strikeout_pitcher": k9 >= 9.0,
        "opp_k_vulnerable": opp_k_rate >= 24.0,
    }

def fetch_mlb_batters_savant():
    """Fallback: MLB Stats API season batting stats."""
    if not MLB_STATS: return {}
    try:
        import statsapi
        params = {"sportId":1,"season":YEAR_MLB,"gameType":"R",
                  "stats":"season","group":"hitting","limit":500,
                  "fields":"stats,splits,player,fullName,stat,homeRuns,avg,ops,slugging"}
        r = requests.get("https://statsapi.mlb.com/api/v1/stats",
            params=params, headers=HTTP_H, timeout=TIMEOUT)
        if r.status_code != 200: return {}
        out = {}
        for split in r.json().get("stats",[{}])[0].get("splits",[]):
            name = split.get("player",{}).get("fullName","").lower()
            stat = split.get("stat",{})
            if not name: continue
            out[name] = {
                "hr":   int(stat.get("homeRuns",0) or 0),
                "avg":  float(stat.get("avg",0) or 0),
                "ops":  float(stat.get("ops",0) or 0),
                "slg":  float(stat.get("slugging",0) or 0),
            }
        log.info("MLB batters (StatsAPI): %d", len(out))
        return out
    except Exception as e:
        log.warning("statsapi batters: %s", e)
        return {}

def fetch_mlb_pitchers_statsapi():
    """Fallback: MLB Stats API season pitching stats."""
    if not MLB_STATS: return {}
    try:
        params = {"sportId":1,"season":YEAR_MLB,"gameType":"R",
                  "stats":"season","group":"pitching","limit":300,
                  "fields":"stats,splits,player,fullName,stat,era,strikeoutsPer9Inn,homeRunsPer9,whip"}
        r = requests.get("https://statsapi.mlb.com/api/v1/stats",
            params=params, headers=HTTP_H, timeout=TIMEOUT)
        if r.status_code != 200: return {}
        out = {}
        for split in r.json().get("stats",[{}])[0].get("splits",[]):
            name = split.get("player",{}).get("fullName","").lower()
            stat = split.get("stat",{})
            if not name: continue
            out[name] = {
                "era":  float(stat.get("era",0) or 0),
                "k9":   float(stat.get("strikeoutsPer9Inn",0) or 0),
                "hr9":  float(stat.get("homeRunsPer9",0) or 0),
                "whip": float(stat.get("whip",0) or 0),
            }
        log.info("MLB pitchers (StatsAPI): %d", len(out))
        return out
    except Exception as e:
        log.warning("statsapi pitchers: %s", e)
        return {}

def fetch_mlb_batters():
    if not PYBASEBALL: return fetch_mlb_batters_savant()
    try:
        import contextlib, io as _io
        with contextlib.redirect_stdout(_io.StringIO()):
            df=pb_bat(YEAR_MLB,qual=1)
        if df is None or len(df)==0:
            with contextlib.redirect_stdout(_io.StringIO()):
                df=pb_bat(YEAR_MLB-1,qual=1)
    except Exception as e: log.warning("pb_bat: %s",e); return fetch_mlb_batters_savant()
    out={}
    for _,row in df.iterrows():
        n=str(row.get("Name","")).lower().strip()
        if not n: continue
        def g(col,*fb):
            for c in (col,*fb):
                v=row.get(c)
                if v is not None and str(v) not in ("nan",""):
                    try: return round(float(v),1)
                    except: pass
            return None
        out[n]={"hr":g("HR"),"iso":g("ISO"),"barrel":g("Barrel%","Barrel/PA%"),
                "hardhit":g("HardHit%","Hard%"),"xslg":g("xSLG"),"xwoba":g("xwOBA")}
    log.info("MLB batters: %d",len(out)); return out
def fetch_mlb_pitchers():
    if not PYBASEBALL: return fetch_mlb_pitchers_statsapi()
    try:
        import contextlib, io as _io
        with contextlib.redirect_stdout(_io.StringIO()):
            df=pb_pit(YEAR_MLB,qual=1)
        if df is None or len(df)==0:
            with contextlib.redirect_stdout(_io.StringIO()):
                df=pb_pit(YEAR_MLB-1,qual=1)
    except Exception as e: log.warning("pb_pit: %s",e); return fetch_mlb_pitchers_statsapi()
    out={}
    for _,row in df.iterrows():
        n=str(row.get("Name","")).lower().strip()
        if not n: continue
        def g(c):
            v=row.get(c)
            try: return round(float(v),2)
            except: return None
        out[n]={"era":g("ERA"),"hr9":g("HR/9"),"k9":g("K/9"),"whip":g("WHIP"),"fip":g("FIP"),"xera":g("xERA")}
    log.info("MLB pitchers: %d",len(out)); return out
def fetch_mlb_lineups():
    if not MLB_STATS: return {}
    today=datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try: schedule=statsapi.schedule(date=today)
    except Exception as e: log.warning("schedule: %s",e); return {}
    out={}
    for game in schedule:
        gid=game.get("game_id")
        if not gid: continue
        try: box=statsapi.boxscore_data(gid)
        except: box=None
        for side in ("home","away"):
            team=game.get(f"{side}_name","")
            opp="away" if side=="home" else "home"
            osp=game.get(f"{opp}_probable_pitcher","")
            ids=[]; names=[]
            if box:
                for bid in box.get(side,{}).get("batters",[]):
                    info=box.get(side,{}).get("players",{}).get(f"ID{bid}",{})
                    pid=info.get("person",{}).get("id"); pn=info.get("person",{}).get("fullName","")
                    if pid: ids.append(int(pid))
                    if pn: names.append(pn)
            out[team]={"lineup_ids":ids,"lineup_names":names,"opp_sp":osp}
    log.info("MLB lineups: %d teams",len(out)); return out
def resolve_mlb_id(name):
    if not PYBASEBALL: return None
    if name in _mlb_id_cache: return _mlb_id_cache[name]
    try:
        parts=name.split()
        if len(parts)<2: _mlb_id_cache[name]=None; return None
        ids=_quiet_lookup(parts[-1],parts[0],fuzzy=True) if _quiet_lookup else None
        mid=int(ids.iloc[0]["key_mlbam"]) if ids is not None and len(ids) else None
        _mlb_id_cache[name]=mid; return mid
    except: _mlb_id_cache[name]=None; return None
def mlb_in_lineup(player,home,away,lu):
    h=lu.get(home,{}); a=lu.get(away,{})
    if not h and not a: return True,None,None
    mid=resolve_mlb_id(player)
    if mid:
        if mid in h.get("lineup_ids",[]): return True,home,h.get("opp_sp")
        if mid in a.get("lineup_ids",[]): return True,away,a.get("opp_sp")
    if not RAPIDFUZZ: return False,None,None
    all_names=[(n,home,h.get("opp_sp")) for n in h.get("lineup_names",[])]
    all_names+=[(n,away,a.get("opp_sp")) for n in a.get("lineup_names",[])]
    if not all_names: return False,None,None
    best=process.extractOne(player.lower(),[x[0].lower() for x in all_names],
        scorer=fuzz.WRatio,score_cutoff=LINEUP_THR)
    if best: return True,all_names[best[2]][1],all_names[best[2]][2]
    return False,None,None
def fetch_statcast(player,days=30):
    if not PYBASEBALL: return None
    try:
        parts=player.split()
        if len(parts)<2: return None
        ids=_quiet_lookup(parts[-1],parts[0],fuzzy=True) if _quiet_lookup else None
        if ids is None or len(ids)==0: return None
        mid=int(ids.iloc[0]["key_mlbam"])
        end=date.today(); start=end-timedelta(days=days)
        df=statcast_batter(start.isoformat(),end.isoformat(),mid)
        if df is None or len(df)==0: return None
        bbe=df[df["type"]=="X"]
        if len(bbe)==0: return None
        bar=(bbe["barrel"]==1).sum() if "barrel" in bbe.columns else 0
        hard=(bbe["launch_speed"]>=95).sum()
        hr=(df["events"]=="home_run").sum() if "events" in df.columns else 0
        return {"barrel_pct":round(100*bar/len(bbe),1),"hardhit_pct":round(100*hard/len(bbe),1),"hr_last30":int(hr)}
    except Exception as e: log.debug("statcast %s: %s",player,e); return None


# ─────────────────────────────────────────────
# NBA / WNBA SOURCES
# ─────────────────────────────────────────────
BDL="https://api.balldontlie.io/v1"
_plr_cache={}
def _bdl(path,params):
    h={"Accept":"application/json"}
    if BALLDONTLIE_KEY: h["Authorization"]=BALLDONTLIE_KEY
    try: r=requests.get(f"{BDL}{path}",params=params,headers=h,timeout=TIMEOUT)
    except: return None
    return r.json() if r.status_code==200 else None
def resolve_nba_players(names):
    out={}
    for name in set(names):
        if not name: continue
        if name in _plr_cache: out[name]=_plr_cache[name]; continue
        d=_bdl("/players",{"search":name,"per_page":5})
        if not d: continue
        results=d.get("data",[])
        if not results: continue
        nl=name.lower()
        best=next((p for p in results if f"{p.get('first_name','')} {p.get('last_name','')}".lower().strip()==nl),results[0])
        _plr_cache[name]=best; out[name]=best
    return out
def fetch_nba_averages(pids):
    if not pids: return {}
    params=[("season",YEAR_NBA)]+[("player_ids[]",p) for p in pids]
    d=_bdl("/season_averages",params)
    rows=(d or {}).get("data",[])
    if not rows:
        params=[("season",YEAR_NBA-1)]+[("player_ids[]",p) for p in pids]
        d=_bdl("/season_averages",params); rows=(d or {}).get("data",[])
    out={}
    for s in rows:
        out[int(s["player_id"])]={"avg_pts":round(float(s.get("pts",0)),1),"avg_reb":round(float(s.get("reb",0)),1),
            "avg_ast":round(float(s.get("ast",0)),1),"avg_min":s.get("min","0"),
            "games":int(s.get("games_played",0)),"fg3_pct":round(float(s.get("fg3_pct",0))*100,1)}
    return out
def enrich_nba_batch(names):
    players=resolve_nba_players(names)
    if not players: return {}
    ids=[int(p["id"]) for p in players.values() if p.get("id")]
    avgs=fetch_nba_averages(ids)
    out={}
    for name,p in players.items():
        pid=int(p["id"])
        out[name]={"team":p.get("team",{}).get("abbreviation"),"season":avgs.get(pid)}
    return out
def fetch_wnba_stats(player):
    # ESPN first
    try:
        r=requests.get("https://site.api.espn.com/apis/common/v3/search",
            params={"query":player,"limit":5,"type":"athlete","leagues":"wnba"},headers=HTTP_H,timeout=TIMEOUT)
        if r.status_code==200:
            hits=r.json().get("athletes") or r.json().get("items") or []
            if hits:
                pid=hits[0].get("id") or hits[0].get("athlete",{}).get("id")
                if pid:
                    r2=requests.get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/athletes/{pid}/statistics",
                        headers=HTTP_H,timeout=TIMEOUT)
                    if r2.status_code==200:
                        cats=r2.json().get("statistics",{}).get("categories") or []
                        out={}
                        for cat in cats:
                            for s in cat.get("stats",[]):
                                out[s.get("name","").lower()]=s.get("value")
                        if out: return {"avg_pts":out.get("avgpoints"),"avg_reb":out.get("avgrebounds"),"avg_ast":out.get("avgassists")}
    except: pass
    return None


# ─────────────────────────────────────────────
# NFL SOURCES
# ─────────────────────────────────────────────
_nfl_weekly=None; _nfl_inj=None
def _get_weekly():
    global _nfl_weekly
    if _nfl_weekly is not None or not NFL_DATA: return _nfl_weekly
    try:
        df=nfl.import_weekly_data([YEAR_NFL])
        if df is None or df.empty: df=nfl.import_weekly_data([YEAR_NFL-1])
        _nfl_weekly=df; log.info("NFL weekly: %d rows",len(df))
    except Exception as e: log.warning("NFL weekly: %s",e)
    return _nfl_weekly
def fetch_nfl_stats(player):
    df=_get_weekly()
    if df is None: return None
    try:
        nl=player.lower(); last=nl.split()[-1]; first=nl.split()[0]
        mask=(df["player_display_name"].str.lower().str.startswith(first[:3]) &
              df["player_display_name"].str.lower().str.contains(last,na=False,regex=False))
        sub=df[mask]
        if sub.empty: return None
        top=sub["player_display_name"].mode().iloc[0]
        sub=df[df["player_display_name"]==top].tail(NFL_LAST_N)
        stats={}
        for col,key in [("passing_yards","pass_yds"),("rushing_yards","rush_yds"),
                        ("receiving_yards","rec_yds"),("receptions","rec"),("targets","tgt")]:
            if col in sub.columns:
                v=round(float(sub[col].mean()),1)
                if v>0: stats[key]=v
        return stats or None
    except Exception as e: log.debug("NFL stats %s: %s",player,e); return None
def fetch_nfl_injuries():
    global _nfl_inj
    if _nfl_inj is not None: return _nfl_inj
    out={}
    try:
        r=requests.get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries",
            headers=HTTP_H,timeout=TIMEOUT)
        if r.status_code==200:
            for tb in r.json().get("injuries",[]):
                for inj in tb.get("injuries",[]):
                    n=inj.get("athlete",{}).get("displayName",""); s=inj.get("status","")
                    if n and s: out[n.lower()]=s
        log.info("NFL injuries: %d",len(out))
    except: pass
    _nfl_inj=out; return out


# ─────────────────────────────────────────────
# PROPSMADNESS
# ─────────────────────────────────────────────
STEALTH="""Object.defineProperty(navigator,'webdriver',{get:()=>undefined});window.chrome={runtime:{}};"""
async def _pm_scrape(page,player):
    try:
        await page.goto("https://propsmadness.com/nba",timeout=30000,wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        await page.keyboard.press("Slash"); await page.wait_for_timeout(400)
        await page.keyboard.type(player.split()[-1]); await page.wait_for_timeout(1200)
        for r in await page.locator(f"text={player.split()[-1]}").all():
            txt=(await r.text_content() or "").lower()
            if player.split()[-1].lower() in txt: await r.click(); break
        await page.wait_for_timeout(1800)
        m=re.search(r'(\d+)%[^<]{0,40}(\d+)/(\d+)',await page.content())
        if m: return {"hit_rate":int(m.group(1)),"hit_count":int(m.group(2)),"total":int(m.group(3))}
    except: pass
    return None
async def _pm_async(names):
    out={}
    async with async_playwright() as pw:
        br=await pw.chromium.launch(headless=True)
        ctx=await br.new_context(user_agent=UA)
        await ctx.add_init_script(STEALTH)
        page=await ctx.new_page()
        for name in names[:PM_MAX]:
            d=await _pm_scrape(page,name)
            if d: out[name]=d
        await br.close()
    return out
def enrich_propsmadness(props):
    if not PLAYWRIGHT: return props
    cands=[p for p in props if p.sport in ("NBA","WNBA")]
    if not cands: return props
    cands.sort(key=lambda p:p.odds,reverse=True)
    names=[p.player for p in cands[:PM_MAX]]
    try: enriched=asyncio.run(_pm_async(names))
    except Exception as e: log.warning("PropsMadness: %s",e); return props
    for p in props:
        d=enriched.get(p.player)
        if d:
            p.features["pm_hit_rate"]=d["hit_rate"]
            tag=f"PM {d['hit_rate']}% ({d['hit_count']}/{d['total']})"
            p.enrichment=(p.enrichment+" | " if p.enrichment else "")+tag
    log.info("PropsMadness enriched: %d",len(enriched))
    return props

# ─────────────────────────────────────────────
# SUPABASE
# ─────────────────────────────────────────────
_sb=None
def _get_sb():
    global _sb
    if _sb is None and HAS_SUPABASE and SUPABASE_URL and SUPABASE_KEY:
        try: _sb=create_client(SUPABASE_URL,SUPABASE_KEY)
        except Exception as e: log.warning("supabase init: %s",e)
    return _sb
def sb_insert(row):
    sb=_get_sb()
    if not sb: return
    # Only keep columns that exist in schema
    safe = {k:v for k,v in row.items() if k not in ("closing_odds","clv_pct","features")}
    try: sb.table("prop_picks").insert(safe).execute()
    except Exception as e: log.warning("sb insert: %s",e)


# ─────────────────────────────────────────────
# HISTORY / DEDUP
# ─────────────────────────────────────────────
def load_history():
    if not os.path.exists(HISTORY_FILE): return []
    try: return json.load(open(HISTORY_FILE))
    except: return []
def save_history(h):
    try: json.dump(h,open(HISTORY_FILE,"w"),indent=2,default=str)
    except Exception as e: log.warning("history save: %s",e)
def already_posted():
    today=datetime.now(timezone.utc).strftime("%Y-%m-%d")
    keys=set(); players=set()
    for entry in load_history():
        if entry.get("date")!=today: continue
        for p in entry.get("picks",[]):
            k=p.get("dedup_key") or dedup_key(p.get("player",""),p.get("market",""),p.get("point"),p.get("direction","over"))
            keys.add(k)
            pl=(p.get("player") or "").lower()
            if pl: players.add(pl)
    return keys,players
def persist(picks):
    today=datetime.now(timezone.utc).strftime("%Y-%m-%d")
    h=load_history()
    entry=next((e for e in h if e.get("date")==today),None)
    if entry is None: entry={"date":today,"picks":[],"kombis":[]}; h.append(entry)
    singles=[p for p in picks if p.type=="single"]
    combos=[p for p in picks if p.type in ("kombi2","big","super","betbuilder","ladder")]
    sport_map={"⚾":"MLB","🏀":"NBA/WNBA","🏈":"NFL"}
    for p in singles:
        dk=dedup_key(p.player or "",p.market or "",getattr(p,"point",None),p.direction)
        hp=HistoricalPick(date=today,player=p.player or "",team=p.team or "",
            market=p.market or "",sport=sport_map.get(p.emoji or "","?"),
            odds=p.odds,stake=p.stake,direction=p.direction,probability=p.probability,dedup_key=dk)
        entry["picks"].append(hp.model_dump())
        sb_insert({**hp.model_dump(),"features":getattr(p,"features",{}) or {}})
    for p in combos:
        entry["kombis"].append({"type":p.type,"legs":p.legs or [],"odds":p.odds,"stake":p.stake,"result":"pending"})
    save_history(h)
    log.info("persisted %d singles + %d combos",len(singles),len(combos))


# ─────────────────────────────────────────────
# AI PROMPT + VALIDATOR
# ─────────────────────────────────────────────
SYSTEM="""Du bist der SHARPSTE deutsche Sports-Betting-Analyst.
Inspiriert von Basket Premium (82.5% WR Nov), Basket Blitz VIP, JK (300u+).
MUSST ausschliesslich gueltiges JSON Array zurueckgeben. Keine Code-Fences, kein Text.

DATENINTERPRETATION:
- edge_pct >= 3% = +EV | avg_last > linie×1.08 = Over | < 0.87 = Under
- Barrel% >= 12, HardHit% >= 45 = MLB HR Edge | NBA last10 > season+2 = Form Heat
- Lineup CONFIRMED = posten | Injury Out = NICHT posten

TIER 2 (stabil @1.65-1.95): Rebounds+Ast, PRA, 3PM, Assists
WNBA BESONDERS WICHTIG: Wenn WNBA Spiele vorhanden → MINDESTENS 2 WNBA Picks!
WNBA Stars: Caitlin Clark, A'ja Wilson, Breanna Stewart, Sabrina Ionescu, Angel Reese
WNBA Märkte: Points, Rebounds+Assists, PRA, 3PM, Steals, Blocks — alle @1.75-1.95

MLB PITCHER STRIKEOUTS (sehr profitabler Markt!):
→ K/9 des Pitchers × Gegner K-Rate = erwartete Strikeouts
→ Über 5.5 Ks: wenn K/9 ≥ 9.0 UND Gegner K-Rate ≥ 23%
→ Über 6.5 Ks: nur bei Elite-Pitcher (Strider, Cole, Wheeler) gegen K-anfällige Lineups
→ NIEMALS Pitcher K wenn < 4 innings erwartet (Bullpen-Risk!)

MLB ANALYSE-FRAMEWORK (aus dem Dokument):
→ Pitcher vs Gegner-Lineup: Kontakt-Hitter = weniger Ks, Power-Hitter = mehr Ks
→ Heim/Auswärts Split: viele Spieler haben 15-20% bessere Heim-Stats
→ Gegner-Defensive Rating für NBA (Pace × Net Rating)
→ Verletzungslisten IMMER prüfen (NFL/NBA Inactive Reports)
→ Spielminuten-Trend: Back-to-Back = weniger Minuten für Stars
TIER 1 (longshots @3.5+): HR, Triple Double, Blocks, NFL Anytime TD

STAKES: @1.65-1.95=1.0u | @2.00-2.50=0.75u | @2.50-3.50=0.5u | @3.50-6.00=0.25u | @6+= 0.10u

KOMBIS:
- BET BUILDER Same-Game (@3-8): 2-3 Props gleiches Spiel, 0.5u
- 2-LEG @6-15: Top Picks paaren (AB+AC+BC alle abdecken!), 0.5u
- 3-LEG LOTTERY @30-100: 0.25u | 4-LEG SUPER @100-300: 0.10u"""

def build_prompt(props):
    # Sports gleichmässig verteilen: nicht einfach [:70] nehmen (MLB würde WNBA verdrängen)
    from collections import defaultdict
    by_sport = defaultdict(list)
    for p in props:
        by_sport[p.sport or "OTHER"].append(p)
    # Priorität: WNBA/NBA zuerst, dann MLB, dann Rest
    sport_order = ["WNBA","NBA","MLB","NHL","NFL","OTHER"]
    interleaved = []
    buckets = [by_sport[s] for s in sport_order if s in by_sport]
    buckets += [by_sport[s] for s in by_sport if s not in sport_order]
    i = 0
    while len(interleaved) < MAX_PROPS_AI and any(buckets):
        b = buckets[i % len(buckets)]
        if b: interleaved.append(b.pop(0))
        i += 1
    lines=[]
    for p in interleaved:
        fair=p.features.get("fair_prob"); edge=""
        if fair:
            ep=round((fair-implied_prob(p.odds))*100,1); edge=f" edge={ep:+.1f}%"
        ln=f"- {p.emoji} {p.player} ({p.game}) {p.market} @{p.odds}{edge}"
        if p.enrichment: ln+=f"  [{p.enrichment}]"
        lines.append(ln)
    return f"""{SYSTEM}

PROPS HEUTE:
{chr(10).join(lines) if lines else "(no props)"}

JSON SCHEMA:
[
  {{"type":"single","tier":2,"emoji":"🏀","player":"Josh Hart","team":"NYK","market":"Rebounds+Assists Over 10.5","direction":"over","odds":1.83,"stake":1.0,"probability":0.72,"analysis":"L5 avg 12.3, 4/5 über Linie"}},
  {{"type":"single","tier":1,"emoji":"⚾","player":"Seiya Suzuki","team":"CHC","market":"Home Run","direction":"over","odds":4.5,"stake":0.25,"probability":0.22,"analysis":"Barrel 14%, HR/9 1.8"}},
  {{"type":"ladder","emoji":"🏀","player":"Brunson","team":"NYK","picks":[{{"market":"30+ Points","odds":2.5,"stake":0.75}},{{"market":"35+ Points","odds":5.0,"stake":0.25}}],"odds":2.5,"stake":1.0}},
  {{"type":"betbuilder","legs":["Hart Reb+Ast 10.5+","Bridges PRA 22.5+"],"game":"NYK vs SAS","odds":3.6,"stake":0.5}},
  {{"type":"kombi2","legs":["Hart Reb+Ast","Suzuki HR"],"odds":8.5,"stake":0.5}},
  {{"type":"big","legs":["Suzuki HR","Goodman HR","Wood HR"],"odds":99.2,"stake":0.25}},
  {{"type":"super","legs":["L1","L2","L3","L4"],"odds":250.0,"stake":0.1}}
]"""

_FENCE=re.compile(r"^```(?:json)?\s*|\s*```$",re.MULTILINE)
def strip_fence(t): return _FENCE.sub("",t or "").strip()
def parse_picks(raw):
    body=strip_fence(raw); s=body.find("["); e=body.rfind("]")
    if s==-1 or e<=s: return [],"no array"
    try: data=json.loads(body[s:e+1])
    except json.JSONDecodeError as ex: return [],str(ex)
    if not isinstance(data,list): return [],"not a list"
    picks=[]; errs=[]
    for i,r in enumerate(data):
        try: picks.append(Pick.model_validate(r))
        except ValidationError as ex: errs.append(f"[{i}]{ex.errors()[0]['msg']}")
    if not picks and errs: return [],"; ".join(errs[:3])
    if errs: log.warning("dropped %d picks: %s",len(errs),errs[:2])
    return picks,None
def call_with_retry(prompt,llm,retries=AI_RETRY):
    cur=prompt
    for attempt in range(retries+1):
        raw=llm(cur)
        if not raw: return []
        picks,err=parse_picks(raw)
        if picks or attempt>=retries: return picks
        log.warning("LLM invalid (attempt %d): %s",attempt+1,err)
        cur=prompt+f"\n\nDeine Antwort war ungültig: {err}\nGib NUR valides JSON Array zurück."
    return []

# ─────────────────────────────────────────────
# AI CLIENTS
# ─────────────────────────────────────────────
def call_gemini(prompt):
    for key in GEMINI_KEYS:
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
        try:
            r=requests.post(url,json={"contents":[{"parts":[{"text":prompt}]}],
                "generationConfig":{"temperature":AI_TEMP,"maxOutputTokens":AI_TOKENS}},timeout=TIMEOUT*2)
            if r.status_code==429: time.sleep(2); continue
            if r.status_code!=200: log.warning("gemini %d",r.status_code); continue
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e: log.warning("gemini: %s",e)
    return None
def call_groq(prompt):
    for key in GROQ_KEYS:
        for model in GROQ_MODELS:
            try:
                r=requests.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
                    json={"model":model,"messages":[{"role":"user","content":prompt}],
                          "max_tokens":AI_TOKENS,"temperature":AI_TEMP},timeout=TIMEOUT*2)
                if r.status_code==200: return r.json()["choices"][0]["message"]["content"]
                if r.status_code==429: continue
            except Exception as e: log.warning("groq %s: %s",model,e)
    return None


# ─────────────────────────────────────────────
# POST BUILDER
# ─────────────────────────────────────────────
def build_post(picks):
    today=datetime.now(timezone.utc).strftime("%d.%m.%Y")
    singles=[p for p in picks if p.type=="single"]
    ladders=[p for p in picks if p.type=="ladder"]
    builders=[p for p in picks if p.type=="betbuilder"]
    kombis=[p for p in picks if p.type=="kombi2"]
    bigs=[p for p in picks if p.type in ("big","super")]
    tier2=[p for p in singles if (p.tier or 1)==2]
    tier1=[p for p in singles if (p.tier or 1)!=2]
    out=[f"🎯 PROP HUNTER — {today}",""]
    def fmt(p):
        m=p.market or ""
        if p.direction=="under" and "under" not in m.lower(): m=f"UNDER {m}"
        # Linie anzeigen wenn vorhanden und nicht bereits im market-Namen enthalten
        point_str=""
        _point = getattr(p, "point", None)
        if _point is not None and str(_point) not in m and f"{_point:g}" not in m:
            dir_word="Under" if p.direction=="under" else "Over"
            point_str=f" {dir_word} {_point:g}"
        elif _point is None and p.direction and "over" not in m.lower() and "under" not in m.lower():
            point_str=""
        line=f"{p.emoji or '🎯'} {p.team or ''} — {p.player}\n   └ {m}{point_str} @{p.odds:.2f} → {p.stake}u"
        if p.edge_pct is not None: line+=f"  (edge {p.edge_pct:+.1f}%)"
        if p.analysis: line+=f"\n   💡 {p.analysis}"
        return line
    if tier2:
        out+=["🔵 STABILE PICKS (High Confidence):",""]
        for p in tier2: out+=[fmt(p),""]
    if tier1:
        out+=["🟡 VALUE PICKS:",""]
        for p in tier1: out+=[fmt(p),""]
    if ladders:
        out+=["🪜 LADDERS:"]
        for p in ladders:
            for leg in (p.picks or []): out.append(f"• {p.player} {leg.market} @{leg.odds:.2f} → {leg.stake}u")
        out.append("")
    if builders:
        out+=["🎯 BET BUILDER:"]
        for p in builders: out.append(f"• {' + '.join(p.legs or [])} @{p.odds:.2f} → {p.stake}u")
        out.append("")
    if kombis:
        out+=["🔥 2-LEG KOMBIS:"]
        for p in kombis: out.append(f"• {' + '.join(p.legs or [])} @{p.odds:.2f} → {p.stake}u")
        out.append("")
    if bigs:
        out+=["💣 LOTTERY BIGS:"]
        for p in bigs:
            pfx="🚀" if p.type=="super" else "•"
            out.append(f"{pfx} {' + '.join(p.legs or [])} @{p.odds:.1f} → {p.stake}u")
        out.append("")
    out+=["📊 ANALYSIERT · GEZIELT · GEWONNEN 🎯","@prophunter"]
    return "\n".join(out)

# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────
def send_telegram(text,dry_run=False):
    if dry_run: log.info("DRY-RUN Telegram (%d chars)",len(text)); return True
    if not TG_TOKEN or not TG_CHAT: log.warning("Telegram not configured"); return False
    try:
        r=requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id":TG_CHAT,"text":text,"disable_web_page_preview":True},timeout=TIMEOUT)
        if r.status_code==200: log.info("Telegram OK"); return True
        log.error("Telegram %d: %s",r.status_code,r.text[:160]); return False
    except Exception as e: log.error("Telegram: %s",e); return False


# ─────────────────────────────────────────────
# GATHER (main data pipeline)
# ─────────────────────────────────────────────
def gather(sport_filter=None):
    all_props=[]; active=[]; earliest=None
    cache=load_cache(); new_cache={}
    # If all keys dead, try stale cache then OddsPapi backup
    if _all_keys_dead() and not cache:
        log.warning("All keys dead — trying stale cache")
        cache=load_cache(force_stale=True)
    # OddsPapi backup wenn Odds API Keys exhausted
    if _all_keys_dead() and ODDSPAPI_KEY and not cache:
        log.info("OddsPapi Backup aktiviert — Odds API exhausted")
        sports_to_try = list(SPORTS.keys()) if not sport_filter else \
            [k for k,v in SPORTS.items() if v.name.lower()==sport_filter.lower()]
        for sk in sports_to_try:
            op_props = fetch_oddspapi_props(sk)
            if op_props:
                active.append(f"(OP){sk.split('_')[-1].upper()}({len(op_props)})")
                # Konvertiere OddsPapi Props in Prop-Objekte
                for raw in op_props:
                    try:
                        sport_label = {
                            "baseball_mlb":"MLB","basketball_nba":"NBA",
                            "basketball_wnba":"WNBA","americanfootball_nfl":"NFL",
                            "icehockey_nhl":"NHL"
                        }.get(raw["sport"],"?")
                        dec = raw.get("decimal_odds",0)
                        if not dec or dec<=1: continue
                        p = Prop(
                            player=raw.get("player_name",""),
                            market=raw.get("market_key",""),
                            odds=round(dec,2),
                            point=raw.get("line"),
                            sport=sport_label,
                            game=f"{raw.get('away_team','')} @ {raw.get('home_team','')}",
                            direction="over" if "over" in (raw.get("selection","")).lower() else "under",
                            features={},
                            emoji=SPORTS.get(sk,SPORTS["baseball_mlb"]).emoji,
                        )
                        all_props.append(p)
                    except Exception: continue
        if all_props:
            log.info("OddsPapi: %d props total", len(all_props))
            all_props=enrich_propsmadness(all_props)
            all_props=enrich_propcruncher(all_props)
            log.info("ACTIVE (OddsPapi): %s | props: %d"," ".join(active),len(all_props))
            return all_props
    mlb_b={}; mlb_p={}; mlb_lu={}; nfl_inj={}; wx={}
    sports=SPORTS
    if sport_filter:
        sports={k:v for k,v in SPORTS.items() if v.name.lower()==sport_filter.lower()}
    for sk,cfg in sports.items():
        events=fetch_events(sk)
        if not events: continue
        active.append(f"{cfg.emoji}{cfg.name}({len(events)})")
        if sk=="baseball_mlb":
            if not mlb_b: mlb_b=fetch_mlb_batters()
            if not mlb_p: mlb_p=fetch_mlb_pitchers()
            if not mlb_lu: mlb_lu=fetch_mlb_lineups()
        if sk=="americanfootball_nfl" and not nfl_inj:
            nfl_inj=fetch_nfl_injuries()
        mkeys=[m.key for m in cfg.markets]
        for ev in events[:MAX_EVENTS]:
            home=ev.get("home_team",""); away=ev.get("away_team",""); ct=ev.get("commence_time")
            if ct and (earliest is None or ct<earliest): earliest=ct
            ck=f"{sk}_{ev['id']}"
            data=cache.get(ck) or fetch_props(sk,ev["id"],mkeys)
            if not data: continue
            new_cache[ck]=data
            total=extract_total(data)
            wxd=None; pf=None
            if cfg.name=="MLB":
                if home not in wx: wx[home]=fetch_weather(home)
                wxd=wx[home]; pf=PARK_FACTORS.get(home)
            for m in cfg.markets:
                for p in extract_props_from_data(data,m.key,m.label,m.min_point,m.min_odds,
                                                  cfg.name,cfg.emoji,home,away,ct):
                    p.game_total=total; extras=[]
                    # MLB enrichment
                    if cfg.name=="MLB":
                        ok,team,osp=mlb_in_lineup(p.player,home,away,mlb_lu)
                        if not ok and mlb_lu: continue
                        if team: p.team=team
                        bat=_fuzzy(p.player,mlb_b)
                        if bat:
                            for k,lbl in [("barrel","Barrel"),("hardhit","HardHit"),("xwoba","xwOBA")]:
                                if bat.get(k): extras.append(f"{lbl}{bat[k]}")
                        # fetch_statcast skipped (FanGraphs blocked in CI)
                        if osp and mlb_p:
                            pit=_fuzzy(osp,mlb_p)
                            if pit:
                                s=f"vs {osp}"
                                for k,lbl in [("era","ERA"),("hr9","HR/9"),("whip","WHIP")]:
                                    if pit.get(k): s+=f" {lbl}{pit[k]}"
                                extras.append(s)
                        if pf: extras.append(f"Park{pf}")
                    # NFL enrichment
                    if cfg.name=="NFL":
                        status=nfl_inj.get(p.player.lower())
                        if status and status.lower() in ("out","injured reserve","ir"): continue
                        if status: extras.append(f"⚠️{status}")
                        ns=fetch_nfl_stats(p.player)
                        if ns: extras+=[f"{k}:{v}" for k,v in list(ns.items())[:4]]
                    if wxd: extras.append(f"WX:{wxd}")
                    if total: extras.append(f"O/U{total}")
                    # Player ML: historische Hit-Rate einrechnen
                    try:
                        import re as _re2
                        _line_m = _re2.search(r"(\d+\.?\d*)", p.market or "")
                        if _line_m:
                            _ml = player_ml_probability(
                                p.player, p.sport or m.sport, p.market or "", 
                                float(_line_m.group(1)),
                                direction=p.direction or "over"
                            )
                            if _ml is not None:
                                extras.append(f"ML:{round(_ml*100,0):.0f}%")
                                if p.probability:
                                    p.probability = int(0.4*_ml*100 + 0.6*p.probability)
                    except Exception:
                        pass
                    if extras: p.enrichment=" | ".join(extras)
                    p.event_id=ev["id"]; p.sport_key=sk
                    all_props.append(p)
    # NBA/WNBA batch enrichment
    nba=[p for p in all_props if p.sport=="NBA"]
    if nba:
        data=enrich_nba_batch([p.player for p in nba])
        for p in nba:
            d=data.get(p.player)
            if not d: continue
            if d.get("team"): p.team=d["team"]
            s=d.get("season")
            if s:
                tags=[f"PTS{s['avg_pts']}","REB{:.0f}".format(s['avg_reb'] or 0),"AST{:.0f}".format(s['avg_ast'] or 0),f"3P%{s.get('fg3_pct',0)}"]
                p.enrichment=(p.enrichment+" | " if p.enrichment else "")+" ".join(tags)
    for p in [p for p in all_props if p.sport=="WNBA"]:
        ws=fetch_wnba_stats(p.player)
        if ws:
            tags=[f"PTS{ws.get('avg_pts')}","REB{:.1f}".format(ws.get('avg_reb') or 0)]
            p.enrichment=(p.enrichment+" | " if p.enrichment else "")+" ".join(t for t in tags if t)
    all_props=enrich_propsmadness(all_props)
    all_props=enrich_statz(all_props)
    all_props=enrich_propcruncher(all_props)
    all_props=enrich_fpp_nhl(all_props)
    all_props=enrich_bdl_props(all_props)
    all_props=enrich_datastreak(all_props)
    all_props=enrich_oddspedia(all_props)
    if new_cache:
        combined={**cache,**new_cache}; save_cache(combined,earliest)
    log.info("ACTIVE: %s | props: %d"," ".join(active),len(all_props))
    return all_props

# ─────────────────────────────────────────────
# ANALYSE
# ─────────────────────────────────────────────
def analyse(props):
    if not props: return []
    prompt=build_prompt(props)
    def llm(p): return call_gemini(p) or call_groq(p)
    picks=call_with_retry(prompt,llm)
    log.info("LLM: %d picks",len(picks))
    for pk in picks:
        if pk.type!="single": continue
        m=next((p for p in props if p.player==pk.player and (pk.market or "").lower() in (p.market or "").lower()),None)
        if m:
            fair=m.features.get("fair_prob")
            base_prob = fair if fair else pk.probability
            sport_label = m.sport
            blended_prob = blend_with_ml(pk, base_prob, sport_label)
            if blended_prob:
                pk.edge_pct=round(edge_pct(blended_prob,pk.odds)*100,2)
                pk.ev=round(ev(blended_prob,pk.odds),3)
                pk.stake=stake_for(blended_prob,pk.odds,pk.stake)
            elif pk.probability:
                pk.stake=stake_for(pk.probability,pk.odds,pk.stake)
    return picks

# ─────────────────────────────────────────────
# FILTER DEDUP
# ─────────────────────────────────────────────
def filter_picks(picks):
    posted_keys,posted_players=already_posted()
    if not posted_keys: return picks
    before=len(picks)
    out=[]
    for p in picks:
        if p.type=="single":
            dk=dedup_key(p.player or "",p.market or "",getattr(p,"point",None),p.direction)
            if dk in posted_keys: continue
        # Kombis/BetBuilder: nicht blocken — dürfen auch beim 2. Run erscheinen
        out.append(p)
    log.info("dedup: %d → %d",before,len(out))
    return out


# ─────────────────────────────────────────────
# ML MODEL — Win Probability Calibration
# ─────────────────────────────────────────────
ML_MIN_SAMPLES = 60         # min settled picks before ML kicks in
ML_MODEL_FILE  = "ml_model.pkl"
ML_BLEND_WEIGHT = 0.4       # 40% ML, 60% LLM/Kelly when blending

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import roc_auc_score, brier_score_loss
    import pickle
    SKLEARN_OK = True
except Exception:
    SKLEARN_OK = False

ML_FEATURE_NAMES = [
    "odds", "stake", "tier", "is_under", "is_mlb", "is_nba", "is_wnba",
    "weekday", "hour", "edge_pct",
]

def _pick_features(p: dict):
    """Extract numeric feature vector from a historical pick dict."""
    try:
        odds = float(p.get("odds", 2.0) or 2.0)
        stake = float(p.get("stake", 0.5) or 0.5)
        tier = 2 if "stabil" in str(p.get("tier","")).lower() else 1
        direction = (p.get("direction") or "over").lower()
        is_under = 1.0 if direction == "under" else 0.0
        sport = (p.get("sport") or "").upper()
        is_mlb = 1.0 if sport == "MLB" else 0.0
        is_nba = 1.0 if "NBA" in sport else 0.0
        is_wnba = 1.0 if "WNBA" in sport else 0.0
        created = p.get("created_at") or p.get("date") or ""
        weekday = hour = 0
        try:
            dt = datetime.fromisoformat(str(created).replace("Z","+00:00")) if "T" in str(created) else datetime.strptime(created,"%Y-%m-%d")
            weekday = dt.weekday(); hour = getattr(dt,"hour",17)
        except Exception:
            pass
        edge = float(p.get("edge_pct", 0) or 0)
        return [odds, stake, tier, is_under, is_mlb, is_nba, is_wnba, weekday, hour, edge]
    except Exception:
        return None

def build_ml_dataset():
    """Builds (X, y) from picks_history.json — only settled picks (win/loss)."""
    X, y = [], []
    for entry in load_history():
        for p in entry.get("picks", []):
            res = p.get("result")
            if res not in ("win","loss"): continue
            feats = _pick_features(p)
            if feats is None: continue
            X.append(feats); y.append(1 if res=="win" else 0)
    return X, y

def train_ml_model():
    """Trains a logistic regression on historical picks. Requires ML_MIN_SAMPLES settled picks."""
    if not SKLEARN_OK:
        log.warning("sklearn nicht installiert — ML übersprungen")
        return None
    X, y = build_ml_dataset()
    n = len(y)
    if n < ML_MIN_SAMPLES:
        log.info("ML: nur %d/%d Picks — noch zu wenig Daten, training übersprungen", n, ML_MIN_SAMPLES)
        return None
    if len(set(y)) < 2:
        log.info("ML: nur eine Klasse vorhanden (alle win oder alle loss) — kein Training möglich")
        return None

    import numpy as np
    X = np.array(X); y = np.array(y)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    # Walk-forward validation (TimeSeriesSplit) statt random split — picks sind zeitlich geordnet
    n_splits = min(5, max(2, n // 20))
    tscv = TimeSeriesSplit(n_splits=n_splits)
    aucs, briers = [], []
    for train_idx, test_idx in tscv.split(Xs):
        if len(set(y[train_idx])) < 2: continue
        m = LogisticRegression(max_iter=500, C=0.5)
        m.fit(Xs[train_idx], y[train_idx])
        proba = m.predict_proba(Xs[test_idx])[:,1]
        try:
            aucs.append(roc_auc_score(y[test_idx], proba))
            briers.append(brier_score_loss(y[test_idx], proba))
        except Exception:
            pass

    # Final model trained on all data
    model = LogisticRegression(max_iter=500, C=0.5)
    model.fit(Xs, y)

    avg_auc = sum(aucs)/len(aucs) if aucs else 0.5
    avg_brier = sum(briers)/len(briers) if briers else 0.25
    log.info("ML trainiert: n=%d | walk-forward AUC=%.3f | Brier=%.3f", n, avg_auc, avg_brier)

    payload = {"model": model, "scaler": scaler, "n_samples": n, "auc": avg_auc, "trained_at": datetime.now(timezone.utc).isoformat()}
    try:
        with open(ML_MODEL_FILE, "wb") as f: pickle.dump(payload, f)
    except Exception as e:
        log.warning("ML model save failed: %s", e)
    return payload

def load_ml_model():
    if not SKLEARN_OK or not os.path.exists(ML_MODEL_FILE):
        return None
    try:
        import pickle
        with open(ML_MODEL_FILE, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None

def ml_predict_proba(pick: Pick, sport_label: str) -> float | None:
    """Returns ML win-probability for a Pick, or None if no model / not enough data."""
    payload = load_ml_model()
    if not payload: return None
    if payload.get("auc", 0) < 0.52:
        return None  # model not better than coinflip — don't trust it
    feats = _pick_features({
        "odds": pick.odds, "stake": pick.stake, "tier": "stabil" if (pick.tier or 1)==2 else "value",
        "direction": pick.direction, "sport": sport_label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "edge_pct": pick.edge_pct or 0,
    })
    if feats is None: return None
    try:
        import numpy as np
        Xs = payload["scaler"].transform(np.array([feats]))
        return float(payload["model"].predict_proba(Xs)[0][1])
    except Exception:
        return None

def blend_with_ml(pick: Pick, llm_prob: float | None, sport_label: str) -> float | None:
    """Blends LLM/fair probability with ML model probability if available."""
    ml_prob = ml_predict_proba(pick, sport_label)
    if ml_prob is None or llm_prob is None:
        return llm_prob
    blended = ML_BLEND_WEIGHT * ml_prob + (1 - ML_BLEND_WEIGHT) * llm_prob
    log.debug("ML blend: llm=%.2f ml=%.2f -> %.2f", llm_prob, ml_prob, blended)
    return blended


# ─────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────
def run(dry_run=False,sport_filter=None):
    log.info("="*40)
    log.info("PROP HUNTER v3 (dry=%s sport=%s)",dry_run,sport_filter or "all")
    props=gather(sport_filter)
    if not props: log.warning("no props found"); return
    picks=analyse(props)
    if not picks: log.warning("no picks from LLM"); return
    picks=filter_picks(picks)
    if not picks: log.warning("all posted today"); return
    body=build_post(picks)
    print("\n"+body+"\n")
    send_telegram(body,dry_run=dry_run)
    if not dry_run: persist(picks)
    log.info("done — %d picks (%d singles)",len(picks),sum(1 for p in picks if p.type=="single"))

if __name__=="__main__":
    import argparse,sys
    parser=argparse.ArgumentParser(description="PROP HUNTER v3")
    parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--sport",choices=["mlb","nba","wnba","nfl","euroleague"])
    parser.add_argument("-v","--verbose",action="store_true")
    parser.add_argument("--train-ml",action="store_true",help="train ML model from picks_history.json and exit")
    args=parser.parse_args()
    if args.train_ml:
        if args.verbose: setup_logging(logging.DEBUG)
        result = train_ml_model()
        if result:
            log.info("✅ ML Training fertig: n=%d AUC=%.3f", result["n_samples"], result["auc"])
        else:
            log.info("❌ ML Training nicht möglich (zu wenig Daten oder sklearn fehlt)")
        raise SystemExit(0)
    if args.verbose: setup_logging(logging.DEBUG)
    run(dry_run=args.dry_run,sport_filter=args.sport)


# ─────────────────────────────────────────────
# NHL API (aktiv ab Oktober)
# ─────────────────────────────────────────────
NHL_BASE = "https://api-web.nhle.com/v1"

def fetch_nhl_player_gamelogs(player_name: str, num_games: int = 20) -> list:
    """Holt NHL Game Logs via offizielle NHL API (kein Key nötig!)."""
    cache_key = f"nhl_{player_name}"
    if cache_key in _PLAYER_STATS_CACHE:
        return _PLAYER_STATS_CACHE[cache_key]
    try:
        # Spieler suchen
        r = requests.get(f"{NHL_BASE}/player/search?q={player_name.replace(' ','+')}&limit=5",
            headers=HTTP_H, timeout=TIMEOUT)
        if r.status_code != 200: return []
        players = r.json().get("searchResults", {}).get("playerSearchResults", [])
        if not players: return []
        pid = players[0].get("playerId")
        if not pid: return []
        # Game Log der aktuellen Saison
        r2 = requests.get(f"{NHL_BASE}/player/{pid}/game-log/20242025/2",
            headers=HTTP_H, timeout=TIMEOUT)
        if r2.status_code != 200: return []
        games = r2.json().get("gameLog", [])[:num_games]
        result = []
        for g in games:
            result.append({
                "date": str(g.get("gameDate",""))[:10],
                "goals": int(g.get("goals",0) or 0),
                "assists": int(g.get("assists",0) or 0),
                "points": int(g.get("points",0) or 0),
                "shots": int(g.get("shots",0) or 0),
                "toi": str(g.get("toi","0:00")),
                "is_home": g.get("homeRoadFlag","H") == "H",
                "opponent": str(g.get("opponentAbbrev","")),
            })
        _PLAYER_STATS_CACHE[cache_key] = result
        log.info("NHL API: %d game logs für %s", len(result), player_name)
        return result
    except Exception as e:
        log.warning("NHL gamelogs: %s", e)
        return []

# ─────────────────────────────────────────────
# PLAYER PERFORMANCE MODEL (historische Daten)
# ─────────────────────────────────────────────

_PLAYER_STATS_CACHE = {}

def fetch_nba_player_gamelogs(player_name: str, num_games: int = 30) -> list:
    """Holt historische NBA Game Logs — nba_api zuerst, balldontlie als Fallback."""
    cache_key = f"nba_gl_{player_name}"
    if cache_key in _PLAYER_STATS_CACHE:
        return _PLAYER_STATS_CACHE[cache_key]
    # Primär: nba_api (offizielle NBA.com Daten)
    result = fetch_nba_api_gamelogs(player_name)
    if result:
        _PLAYER_STATS_CACHE[cache_key] = result[:num_games]
        return result[:num_games]
    h = {"Accept": "application/json"}
    if BDL_KEY: h["Authorization"] = BDL_KEY
    try:
        r = requests.get("https://api.balldontlie.io/v1/players",
            params={"search": player_name, "per_page": 5}, headers=h, timeout=20)
        if r.status_code != 200: return []
        players = r.json().get("data", [])
        if not players: return []
        pid = players[0]["id"]
        r2 = requests.get("https://api.balldontlie.io/v1/stats",
            params={"player_ids[]": pid, "per_page": num_games, "seasons[]": [2024, 2025]},
            headers=h, timeout=20)
        if r2.status_code != 200: return []
        games = r2.json().get("data", [])
        result = []
        for g in games:
            try:
                result.append({
                    "date": g.get("game", {}).get("date", "")[:10],
                    "pts": float(g.get("pts") or 0),
                    "reb": float(g.get("reb") or 0),
                    "ast": float(g.get("ast") or 0),
                    "blk": float(g.get("blk") or 0),
                    "stl": float(g.get("stl") or 0),
                    "fg3m": float(g.get("fg3m") or 0),
                    "min": float(str(g.get("min") or "0").split(":")[0]),
                    "opponent": g.get("game", {}).get("visitor_team_id", ""),
                    "is_home": g.get("game", {}).get("home_team_id") == g.get("team", {}).get("id"),
                    "team": g.get("team", {}).get("abbreviation", ""),
                })
            except Exception:
                continue
        _PLAYER_STATS_CACHE[cache_key] = result
        return result
    except Exception as e:
        log.warning("NBA gamelogs error: %s", e)
        return []



def fetch_nhl_player_stats(player_name: str, last_n: int = 20) -> list:
    """Holt NHL Game Logs via offizieller NHL API (kein Key nötig!)."""
    cache_key = f"nhl_gl_{player_name}"
    if cache_key in _PLAYER_STATS_CACHE:
        return _PLAYER_STATS_CACHE[cache_key]
    try:
        # Spieler suchen
        r = requests.get(
            "https://search.d3.nhle.com/api/v1/search",
            params={"q": player_name, "type": "player", "culture": "en-us", "limit": 5},
            headers=HTTP_H, timeout=10)
        if r.status_code != 200: return []
        results = r.json()
        if not results: return []
        pid = results[0].get("playerId")
        if not pid: return []
        # Game Log
        r2 = requests.get(
            f"https://api-web.nhle.com/v1/player/{pid}/game-log/now",
            headers=HTTP_H, timeout=10)
        if r2.status_code != 200: return []
        games = r2.json().get("gameLog", [])[:last_n]
        result = []
        for g in games:
            result.append({
                "date": g.get("gameDate","")[:10],
                "goals": int(g.get("goals",0) or 0),
                "assists": int(g.get("assists",0) or 0),
                "points": int(g.get("points",0) or 0),
                "shots": int(g.get("shots",0) or 0),
                "ppp": int(g.get("powerPlayPoints",0) or 0),
                "toi": g.get("toi","0:00"),
                "is_home": g.get("homeRoadFlag","H") == "H",
                "team": g.get("teamAbbrev",""),
                "opponent": g.get("opponentAbbrev",""),
            })
        _PLAYER_STATS_CACHE[cache_key] = result
        return result
    except Exception as e:
        log.warning("NHL stats error: %s", e)
        return []

def fetch_nhl_player_gamelogs(player_name: str, num_games: int = 20) -> list:
    return fetch_nhl_player_stats(player_name, num_games)

def fetch_mlb_player_gamelogs(player_name: str, num_games: int = 30) -> list:
    """Holt historische MLB Game Logs via MLB StatsAPI."""
    cache_key = f"mlb_gl_{player_name}"
    if cache_key in _PLAYER_STATS_CACHE:
        return _PLAYER_STATS_CACHE[cache_key]
    try:
        import statsapi
        # Spieler ID suchen
        search = statsapi.lookup_player(player_name)
        if not search: return []
        pid = search[0]["id"]
        # Game Logs der aktuellen Saison
        logs = statsapi.player_stat_data(pid, group="hitting", type="gameLog")
        result = []
        for g in (logs.get("stats", [{}])[0].get("splits", []))[:num_games]:
            try:
                s = g.get("stat", {})
                result.append({
                    "date": g.get("date", "")[:10],
                    "hits": int(s.get("hits", 0) or 0),
                    "hr": int(s.get("homeRuns", 0) or 0),
                    "tb": int(s.get("totalBases", 0) or 0),
                    "rbi": int(s.get("rbi", 0) or 0),
                    "sb": int(s.get("stolenBases", 0) or 0),
                    "opponent": g.get("opponent", {}).get("name", ""),
                    "is_home": g.get("isHome", False),
                    "team": g.get("team", {}).get("abbreviation", ""),
                })
            except Exception:
                continue
        _PLAYER_STATS_CACHE[cache_key] = result
        return result
    except Exception as e:
        log.warning("MLB gamelogs error: %s", e)
        return []


def save_gamelogs_to_supabase(player: str, sport: str, games: list):
    """Speichert Game Logs in Supabase player_stats Tabelle."""
    sb = _get_sb()
    if not sb or not games: return
    rows = []
    for g in games:
        row = {"player": player, "sport": sport,
               "game_date": g.get("date"), "season": 2025}
        row.update({k: v for k, v in g.items() if k not in ("date",)})
        rows.append(row)
    try:
        sb.table("player_stats").upsert(rows, on_conflict="player,sport,game_date").execute()
        log.info("Supabase: %d game logs gespeichert für %s", len(rows), player)
    except Exception as e:
        log.warning("Supabase player_stats error: %s", e)


def compute_player_features(games: list, line: float, stat_key: str) -> dict | None:
    """Berechnet ML-Features aus historischen Game Logs."""
    if len(games) < 5: return None
    vals = [float(g.get(stat_key, 0) or 0) for g in games]
    l5  = vals[:5];  l10 = vals[:10]; l20 = vals[:20]
    hit_rate_l5  = sum(1 for v in l5  if v > line) / len(l5)
    hit_rate_l10 = sum(1 for v in l10 if v > line) / len(l10) if l10 else 0
    hit_rate_l20 = sum(1 for v in l20 if v > line) / len(l20) if l20 else 0
    avg_l5  = sum(l5)  / len(l5)
    avg_l10 = sum(l10) / len(l10) if l10 else avg_l5
    streak = 0
    for v in l5:
        if v > line: streak += 1
        else: break
    home_games  = [g for g in games if g.get("is_home")]
    away_games  = [g for g in games if not g.get("is_home")]
    home_hit_rate = sum(1 for g in home_games if float(g.get(stat_key,0) or 0) > line) / len(home_games) if home_games else hit_rate_l10
    away_hit_rate = sum(1 for g in away_games if float(g.get(stat_key,0) or 0) > line) / len(away_games) if away_games else hit_rate_l10
    # Heim/Auswärts-Bonus (20% bessere Heim-Stats ist typisch)
    is_home_game = games[0].get("is_home", True) if games else True
    location_adj = (home_hit_rate - away_hit_rate) * 0.5 if home_games and away_games else 0
    return {
        "hit_rate_l5": hit_rate_l5, "hit_rate_l10": hit_rate_l10,
        "hit_rate_l20": hit_rate_l20, "avg_l5": avg_l5, "avg_l10": avg_l10,
        "streak": streak, "home_hit_rate": home_hit_rate,
        "away_hit_rate": away_hit_rate,
        "location_adj": home_hit_rate - away_hit_rate,
        "line_vs_avg": avg_l10 - line,
    }


def player_ml_probability(player: str, sport: str, market: str,
                           line: float, direction: str = "over") -> float | None:
    """
    Hauptfunktion: berechnet ML-Wahrscheinlichkeit für einen Player Prop.
    Gibt None zurück wenn zu wenig Daten.
    """
    # Stat Key aus Markt ableiten
    STAT_MAP = {
        # MLB
        "hits": "hits", "home run": "hr", "total bases": "tb",
        "rbi": "rbi", "stolen base": "sb", "strikeout": "k_pitcher",
        # NBA/WNBA
        "points": "pts", "rebounds": "reb", "assists": "ast",
        "pra": "pts", "3pm": "fg3m", "blocks": "blk", "steals": "stl",
        "rebounds+assists": "reb",
        # NHL
        "shots on goal": "shots", "goals": "goals",
        "power play": "ppp", "nhl assists": "assists",
        "nhl points": "points",
    }
    stat_key = None
    market_lower = market.lower()
    for k, v in STAT_MAP.items():
        if k in market_lower:
            stat_key = v
            break
    if not stat_key: return None

    # Game Logs laden
    if sport in ("NBA", "WNBA"):
        # nba_api zuerst (direkter NBA.com), dann balldontlie als Fallback
        games = fetch_nba_api_gamelogs(player) or fetch_nba_player_gamelogs(player)
    elif sport == "MLB":
        games = fetch_mlb_player_gamelogs(player)
    else:
        return None

    if len(games) < 5: return None

    # Features berechnen
    feats = compute_player_features(games, line, stat_key)
    if not feats: return None

    # Einfaches gewichtetes Modell (kein Training nötig — direkte Heuristik)
    # Gewichtung: L5 Hit Rate 40%, L10 Hit Rate 35%, L20 Hit Rate 15%, Streak 10%
    location_adj = feats.get("location_adj", 0)
    prob = (0.40 * feats["hit_rate_l5"] +
            0.35 * feats["hit_rate_l10"] +
            0.15 * feats["hit_rate_l20"] +
            0.10 * min(feats["streak"] / 5, 1.0))
    if is_home_game: prob += location_adj * 0.3

    # Bonus/Malus für Linie vs Durchschnitt
    if feats["line_vs_avg"] > 3: prob -= 0.05   # Linie viel über Schnitt → Malus
    if feats["line_vs_avg"] < -3: prob += 0.05  # Linie weit unter Schnitt → Bonus

    if direction == "under":
        prob = 1 - prob

    # In Supabase speichern für Tracking
    sb = _get_sb()
    if sb:
        try:
            sb.table("ml_predictions").insert({
                "player": player, "sport": sport, "market": market,
                "line": line, "direction": direction,
                "ml_prob": round(prob, 3),
            }).execute()
        except Exception:
            pass

    log.info("Player ML [%s %s %s @%.1f]: %.1f%%", sport, player, market, line, prob*100)
    return round(prob, 3)
