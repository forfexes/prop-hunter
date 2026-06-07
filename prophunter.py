#!/usr/bin/env python3
"""
PROP HUNTER v2 — Automated MLB/NBA/NFL Player Props Tipster Bot
Enhanced with:
  • Confirmed lineups filter (kills dead picks BEFORE Gemini sees them)
  • NBA stats via balldontlie.io (replaces broken nba_api in CI)
  • MLB pitcher matchup data (SP HR/9 + handedness)
  • NFL snap counts + target share (full coverage, not just first 8)
  • Vegas totals/spreads as additional signal
  • MLB park factors (static constants, no API call)
  • Rapidfuzz player matching (no more "Smith" matches 47 players)
  • Smart per-sport season detection

Data sources (ALL FREE, no API keys needed for enrichment):
  • The Odds API   → odds (existing)
  • pybaseball     → MLB batter + pitcher stats (existing, extended)
  • balldontlie.io → NBA stats + lineups (NEW)
  • MLB-StatsAPI   → confirmed lineups + starting pitchers (NEW)
  • ESPN API       → NFL injury report (NEW)
  • nfl_data_py    → NFL weekly + snap counts (extended)
  • Open-Meteo     → weather (existing)
  • Gemini + Groq  → AI analysis (existing)

pip install requests pybaseball nba_api nfl_data_py rapidfuzz
"""

import os, io, json, time, requests
try:
    from py_ball import playerstats as pyball_stats
    from py_ball.utils import WNBA_HEADERS
    PYBALL = True
except Exception:
    PYBALL = False

try:
    from supabase import create_client as sb_create
    SUPABASE = True
except Exception:
    SUPABASE = False
from datetime import datetime, timedelta, timezone

# ─── OPTIONAL LIBRARIES (graceful fallback) ───
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT = True
    print("  playwright OK")
except Exception:
    PLAYWRIGHT = False

try:
    from pybaseball import batting_stats as pb_batting
    from pybaseball import pitching_stats as pb_pitching
    from pybaseball import playerid_lookup
    PYBASEBALL = True
    print("  pybaseball OK")
except Exception:
    PYBASEBALL = False

try:
    import statsapi
    MLB_STATSAPI = True
    print("  MLB-StatsAPI OK")
except Exception:
    MLB_STATSAPI = False

try:
    from nba_api.stats.static import players as nba_db
    from nba_api.stats.endpoints import playergamelog
    NBA_API = True
    print("  nba_api OK")
except Exception:
    NBA_API = False

try:
    import nflreadpy as nfl
    NFL_DATA = True
    print("  nflreadpy OK")
except Exception:
    try:
        import nfl_data_py as nfl
        NFL_DATA = True
        print("  nfl_data_py OK (deprecated)")
    except Exception:
        NFL_DATA = False

try:
    from rapidfuzz import fuzz, process as fuzz_process
    RAPIDFUZZ = True
    print("  rapidfuzz OK")
except Exception:
    RAPIDFUZZ = False
    print("  rapidfuzz MISSING → install: pip install rapidfuzz")

# ─── CONFIG ───
ODDS_API_KEY   = os.environ.get("ODDS_API_KEY", "")
GEMINI_KEYS    = [k.strip() for k in os.environ.get("GEMINI_API_KEY","").split(",") if k.strip()]
GROQ_KEYS      = [k.strip() for k in os.environ.get("GROQ_API_KEY","").split(",") if k.strip()]
API_SPORTS_KEYS = [k.strip() for k in os.environ.get("API_SPORTS_KEY","").split(",") if k.strip()]
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TG_TOKEN       = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT        = os.environ.get("TELEGRAM_CHAT_ID", "")
BALLDONTLIE_KEY = os.environ.get("BALLDONTLIE_API_KEY", "")  # OPTIONAL — free tier still works

ODDS_BASE  = "https://api.the-odds-api.com/v4"
BOOKMAKERS = "bet365,draftkings,fanduel,betmgm,williamhill,pinnacle"
UA         = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# ─── SMART SEASON DETECTION ───
def season_for(sport):
    """Different sports have different active seasons throughout the year."""
    now = datetime.now(timezone.utc)
    y, m = now.year, now.month
    if sport in ("baseball_mlb",):
        # MLB: March-November = current year; Dec-Feb = previous year
        return y if 3 <= m <= 11 else y - 1
    if sport in ("basketball_nba","basketball_wnba","basketball_euroleague"):
        # NBA: Oct-June season → if before October, use previous start year
        return y - 1 if m < 10 else y
    if sport in ("americanfootball_nfl",):
        # NFL: Sept-Feb → if before September, use previous year
        return y - 1 if m < 9 else y
    return y

YEAR_MLB = season_for("baseball_mlb")
YEAR_NBA = season_for("basketball_nba")
YEAR_NFL = season_for("americanfootball_nfl")
print(f"  seasons: MLB={YEAR_MLB} | NBA={YEAR_NBA}-{(YEAR_NBA+1)%100:02d} | NFL={YEAR_NFL}")

SPORTS = {
    "baseball_mlb": {"emoji":"⚾","name":"MLB",
        "markets":[
            ("batter_home_runs","Home Run",None,3.5),
            ("batter_hits","Hits Over 1.5",None,1.7),
            ("batter_total_bases","Total Bases",None,1.8),
            ("pitcher_strikeouts","Pitcher K",None,1.8),
            ("batter_stolen_bases","Stolen Base",None,4.0),
            ("batter_rbis","RBI",None,2.5),
            ("pitcher_outs","Outs Recorded",None,1.8),
            ("pitcher_earned_runs","Earned Runs U",None,1.8),
            ("pitcher_hits_allowed","Hits Allowed U",None,1.8)]},
    "basketball_nba": {"emoji":"🏀","name":"NBA",
        "markets":[
            ("player_points_alternate","Points",25,3.5),
            ("player_rebounds_alternate","Rebounds",8,3.0),
            ("player_assists_alternate","Assists",6,3.0),
            ("player_blocks_alternate","Blocks",2,3.5),
            ("player_steals_alternate","Steals",2,3.5),
            ("player_threes_alternate","3PM",2,2.5),
            ("player_points_rebounds_assists","PRA",35,1.8),
            ("player_points_rebounds","PR",30,1.8),
            ("player_points_assists","PA",30,1.8),
            ("player_double_double","Double Double",None,3.0),
            ("player_triple_double","Triple Double",None,6.0)]},
    "basketball_wnba": {"emoji":"🏀","name":"WNBA",
        "markets":[
            ("player_points_alternate","Points",15,3.5),
            ("player_rebounds_alternate","Rebounds",6,3.0),
            ("player_assists_alternate","Assists",5,3.0),
            ("player_threes_alternate","3PM",2,2.5),
            ("player_points_rebounds_assists","PRA",20,1.8),
            ("player_double_double","Double Double",None,3.0)]},
    "basketball_euroleague": {"emoji":"🏀","name":"Euroleague",
        "markets":[
            ("player_points_alternate","Points",12,3.0),
            ("player_rebounds_alternate","Rebounds",5,2.8),
            ("player_assists_alternate","Assists",4,2.8),
            ("player_threes_alternate","3PM",2,2.5)]},
    "americanfootball_nfl": {"emoji":"🏈","name":"NFL",
        "markets":[
            ("player_anytime_td","Anytime TD",None,2.5),
            ("player_pass_tds_alternate","Pass TDs",None,3.0),
            ("player_pass_yds_alternate","Pass Yds",None,1.8),
            ("player_rush_yds_alternate","Rush Yds",None,3.0),
            ("player_reception_yds_alternate","Rec Yds",None,3.0),
            ("player_receptions_alternate","Receptions",None,1.8)]},
}

BALLPARKS = {
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

# Park Factors (3-year FanGraphs avg, 100 = neutral, >100 = HR-friendly)
PARK_FACTORS_HR = {
    "Colorado Rockies":118,"Cincinnati Reds":115,"New York Yankees":113,"Philadelphia Phillies":108,
    "Boston Red Sox":107,"Baltimore Orioles":106,"Milwaukee Brewers":105,"Atlanta Braves":104,
    "Chicago Cubs":103,"Houston Astros":103,"Toronto Blue Jays":102,"Texas Rangers":102,
    "Minnesota Twins":101,"Arizona Diamondbacks":100,"Washington Nationals":100,"Los Angeles Angels":100,
    "St. Louis Cardinals":99,"Chicago White Sox":99,"Kansas City Royals":98,"Detroit Tigers":97,
    "Tampa Bay Rays":96,"New York Mets":96,"Cleveland Guardians":95,"San Francisco Giants":94,
    "Los Angeles Dodgers":93,"Athletics":92,"Pittsburgh Pirates":92,"Seattle Mariners":91,
    "Miami Marlins":89,"San Diego Padres":86,
}

def time_window():
    now = datetime.now(timezone.utc)
    return now, now + timedelta(hours=12)

# ─── ODDS API ───
def fetch_events(sport):
    now, end = time_window()
    try:
        r = requests.get(f"{ODDS_BASE}/sports/{sport}/events", params={
            "apiKey":ODDS_API_KEY,"dateFormat":"iso",
            "commenceTimeFrom":now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "commenceTimeTo":end.strftime("%Y-%m-%dT%H:%M:%SZ")}, timeout=30)
        data = r.json() if r.status_code==200 else []
        if data: print(f"  {sport}: {len(data)} events, quota left: {r.headers.get('x-requests-remaining','?')}")
        else: print(f"  {sport}: status={r.status_code}")
        return data
    except Exception as e:
        print(f"  warn events {sport}: {e}"); return []

def fetch_props(sport, eid, markets):
    try:
        # Include totals + spreads as a context signal
        all_markets = markets + ",totals,spreads"
        r = requests.get(f"{ODDS_BASE}/sports/{sport}/events/{eid}/odds", params={
            "apiKey":ODDS_API_KEY,"regions":"us,eu,uk","markets":all_markets,
            "oddsFormat":"decimal","bookmakers":BOOKMAKERS}, timeout=30)
        if r.status_code != 200: return None
        d = r.json()
        return d
    except Exception: return None

def extract_game_totals(data):
    """Return avg totals line + spread favorite for game-context signal."""
    totals, spreads = [], []
    for bm in (data.get("bookmakers") or []):
        for mkt in (bm.get("markets") or []):
            if mkt.get("key") == "totals":
                for o in mkt.get("outcomes") or []:
                    if o.get("name") == "Over" and o.get("point") is not None:
                        totals.append(o["point"])
            elif mkt.get("key") == "spreads":
                for o in mkt.get("outcomes") or []:
                    pt = o.get("point")
                    if pt is not None: spreads.append((o.get("name",""), pt))
    avg_total = round(sum(totals)/len(totals), 1) if totals else None
    return avg_total

def extract(data, mkey, label, min_pt, min_odds):
    out = {}
    _logged = [False]
    for bm in (data.get("bookmakers") or []):
        for mkt in (bm.get("markets") or []):
            if mkt.get("key") != mkey: continue
            outcomes = mkt.get("outcomes") or []
            if not _logged[0] and outcomes:
                _logged[0] = True
            for o in outcomes:
                desc       = o.get("description","") or ""
                name_field = o.get("name","") or ""
                pt         = o.get("point")
                price      = o.get("price",0)

                TYPE_WORDS = {"Over","Under","Yes","No",""}
                if name_field in TYPE_WORDS:
                    player_name  = desc
                    outcome_type = name_field
                else:
                    player_name  = name_field
                    outcome_type = desc

                if outcome_type and outcome_type not in ("Over","Yes"): continue
                if not player_name or player_name in TYPE_WORDS: continue
                if min_pt and pt is not None and pt < min_pt: continue

                k = f"{player_name}|{pt or ''}"
                out.setdefault(k,{"player":player_name,"point":pt,"prices":[]})
                out[k]["prices"].append(price)

    res = []
    for v in out.values():
        prices = [p for p in v["prices"] if p > 1]
        if not prices: continue
        avg = sum(prices)/len(prices)
        if avg >= min_odds:
            lbl = label
            if v["point"] and label in ("Points","Rush Yds","Rec Yds","Pass TDs"):
                lbl = f"{int(v['point'])}+ {label}"
            res.append({"player":v["player"],"odds":round(avg,2),"market":lbl})
    return res

# ─── FUZZY PLAYER MATCHING ───
def fuzzy_match(player_name, candidates_dict, threshold=85):
    """Match player against a dict of {name: data}. Returns matched data or None."""
    if not player_name or not candidates_dict: return None
    pl = player_name.lower().strip()
    # Exact first
    if pl in candidates_dict: return candidates_dict[pl]
    if not RAPIDFUZZ:
        # Fallback to old method
        last = pl.split()[-1] if pl.split() else pl
        for n, d in candidates_dict.items():
            if n.split() and n.split()[-1] == last:
                if pl.split() and pl.split()[0][:3] in n: return d
        return None
    # Rapidfuzz match
    keys = list(candidates_dict.keys())
    best = fuzz_process.extractOne(pl, keys, scorer=fuzz.WRatio, score_cutoff=threshold)
    if best:
        return candidates_dict[best[0]]
    return None

# ─── MLB STATS: BATTERS ───
def fetch_mlb_batters():
    if not PYBASEBALL: return {}
    try:
        df = pb_batting(YEAR_MLB, qual=1)
        if df is None or len(df) == 0:
            df = pb_batting(YEAR_MLB-1, qual=1)
        out = {}
        for _, row in df.iterrows():
            name = str(row.get("Name","")).lower()
            if not name: continue
            def g(col, fallbacks=[]):
                for c in [col]+fallbacks:
                    v = row.get(c)
                    if v is not None and str(v) not in ("nan",""):
                        try: return round(float(v),1)
                        except: pass
                return None
            out[name] = {
                "hr":g("HR"), "iso":g("ISO"),
                "barrel":g("Barrel%", ["Barrel/PA%","EV"]),
                "hardhit":g("HardHit%", ["Hard%","HardHit"]),
                "xslg":g("xSLG", ["xSLG_custom"]),
                "bat_hand":None,  # filled from MLB-StatsAPI later if needed
            }
        print(f"  MLB batters: {len(out)} loaded")
        return out
    except Exception as e:
        print(f"  warn pybaseball batters: {e}")
        return {}

# ─── MLB STATS: PITCHERS (NEW) ───
def fetch_mlb_pitchers():
    """Fetch starting pitcher stats: ERA, HR/9, K/9, hand."""
    if not PYBASEBALL: return {}
    try:
        df = pb_pitching(YEAR_MLB, qual=1)
        if df is None or len(df) == 0:
            df = pb_pitching(YEAR_MLB-1, qual=1)
        out = {}
        for _, row in df.iterrows():
            name = str(row.get("Name","")).lower()
            if not name: continue
            def g(col, fallbacks=[]):
                for c in [col]+fallbacks:
                    v = row.get(c)
                    if v is not None and str(v) not in ("nan",""):
                        try: return round(float(v),2)
                        except: pass
                return None
            out[name] = {
                "era": g("ERA"),
                "hr9": g("HR/9"),
                "k9":  g("K/9"),
                "whip":g("WHIP"),
                "fip": g("FIP"),
                "hand":None,  # filled via MLB-StatsAPI
            }
        print(f"  MLB pitchers: {len(out)} loaded")
        return out
    except Exception as e:
        print(f"  warn pybaseball pitchers: {e}")
        return {}

# ─── MLB CONFIRMED LINEUPS + STARTING PITCHERS (NEW) ───
def fetch_mlb_lineups_today():
    """Returns dict { team_name: {lineup:[player_names], opp_sp: name, opp_sp_hand: 'L'/'R'} }"""
    if not MLB_STATSAPI: return {}
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        schedule = statsapi.schedule(date=today)
        out = {}
        for game in schedule:
            game_pk = game.get("game_id")
            if not game_pk: continue
            try:
                box = statsapi.boxscore_data(game_pk)
            except Exception:
                box = None
            for side in ("home","away"):
                team_name = game.get(f"{side}_name","")
                opp_side = "away" if side == "home" else "home"
                opp_sp = game.get(f"{opp_side}_probable_pitcher","")
                lineup_players = []
                if box:
                    batters = box.get(side,{}).get("batters",[])
                    for bid in batters:
                        info = box.get(side,{}).get("players",{}).get(f"ID{bid}",{})
                        full_name = info.get("person",{}).get("fullName","")
                        if full_name: lineup_players.append(full_name)
                out[team_name] = {
                    "lineup": lineup_players,
                    "opp_sp": opp_sp,
                    "opp_sp_hand": None,  # TBD
                }
        print(f"  MLB lineups today: {len(out)} teams")
        return out
    except Exception as e:
        print(f"  warn mlb lineups: {e}")
        return {}

# ─── NBA STATS via balldontlie.io (NEW — replaces nba_api block) ───
def _bdl_headers():
    h = {"Accept":"application/json"}
    if BALLDONTLIE_KEY: h["Authorization"] = BALLDONTLIE_KEY
    return h

_BDL_PLAYER_CACHE = {}

def bdl_find_player(name):
    if name in _BDL_PLAYER_CACHE: return _BDL_PLAYER_CACHE[name]
    try:
        r = requests.get("https://api.balldontlie.io/v1/players",
            params={"search":name,"per_page":5}, headers=_bdl_headers(), timeout=15)
        if r.status_code != 200: return None
        results = r.json().get("data",[])
        if not results: return None
        # Best match: full name equality, else first
        pl_lower = name.lower()
        best = None
        for p in results:
            full = f"{p.get('first_name','')} {p.get('last_name','')}".lower().strip()
            if full == pl_lower: best = p; break
        if not best: best = results[0]
        _BDL_PLAYER_CACHE[name] = best
        return best
    except Exception as e:
        print(f"  warn bdl player {name}: {e}"); return None

def fetch_nba_player_stats_bdl(player_name):
    """NBA player season averages via balldontlie.io — works in GitHub Actions."""
    player = bdl_find_player(player_name)
    if not player: return None
    pid = player.get("id")
    try:
        r = requests.get("https://api.balldontlie.io/v1/season_averages",
            params={"season":YEAR_NBA,"player_ids[]":pid},
            headers=_bdl_headers(), timeout=15)
        if r.status_code != 200: return None
        data = r.json().get("data",[])
        if not data:
            # try previous season
            r = requests.get("https://api.balldontlie.io/v1/season_averages",
                params={"season":YEAR_NBA-1,"player_ids[]":pid},
                headers=_bdl_headers(), timeout=15)
            data = r.json().get("data",[]) if r.status_code==200 else []
        if not data: return None
        s = data[0]
        return {
            "avg_pts": round(float(s.get("pts",0)),1),
            "avg_reb": round(float(s.get("reb",0)),1),
            "avg_ast": round(float(s.get("ast",0)),1),
            "avg_min": s.get("min","0"),
            "games":   int(s.get("games_played",0)),
            "fg_pct":  round(float(s.get("fg_pct",0))*100,1),
            "team_id": player.get("team",{}).get("id"),
        }
    except Exception as e:
        print(f"  warn bdl stats {player_name}: {e}"); return None

# ─── NFL STATS (extended: covers ALL props now, not just 8) ───
_NFL_WEEKLY_CACHE = None
_NFL_SNAPS_CACHE = None

def _nfl_weekly():
    global _NFL_WEEKLY_CACHE
    if _NFL_WEEKLY_CACHE is not None: return _NFL_WEEKLY_CACHE
    if not NFL_DATA:
        _NFL_WEEKLY_CACHE = None; return None
    try:
        df = nfl.import_weekly_data([YEAR_NFL])
        if df is None or df.empty:
            df = nfl.import_weekly_data([YEAR_NFL-1])
        _NFL_WEEKLY_CACHE = df
        print(f"  NFL weekly: {len(df) if df is not None else 0} rows loaded")
        return df
    except Exception as e:
        print(f"  warn nfl weekly: {e}"); _NFL_WEEKLY_CACHE = None; return None

def _nfl_snaps():
    global _NFL_SNAPS_CACHE
    if _NFL_SNAPS_CACHE is not None: return _NFL_SNAPS_CACHE
    if not NFL_DATA:
        _NFL_SNAPS_CACHE = None; return None
    try:
        df = nfl.import_snap_counts([YEAR_NFL])
        if df is None or df.empty:
            df = nfl.import_snap_counts([YEAR_NFL-1])
        _NFL_SNAPS_CACHE = df
        print(f"  NFL snaps: {len(df) if df is not None else 0} rows loaded")
        return df
    except Exception as e:
        _NFL_SNAPS_CACHE = None; return None

def fetch_nfl_player_stats(player_name):
    df = _nfl_weekly()
    if df is None: return None
    try:
        name_lower = player_name.lower()
        last = name_lower.split()[-1]
        first = name_lower.split()[0] if name_lower.split() else ""
        mask = (df["player_display_name"].str.lower().str.startswith(first[:3])) & \
               (df["player_display_name"].str.lower().str.contains(last, na=False))
        player_df = df[mask]
        if player_df.empty:
            # Fallback: last name only
            mask = df["player_display_name"].str.lower().str.contains(last, na=False)
            player_df = df[mask]
            if player_df.empty: return None
        # Use a single canonical name (most rows)
        top_name = player_df["player_display_name"].mode().iloc[0]
        player_df = df[df["player_display_name"] == top_name]
        recent = player_df.tail(8)
        stats = {}
        for col, key in [
            ("passing_yards","pass_yds"),("rushing_yards","rush_yds"),
            ("receiving_yards","rec_yds"),("passing_tds","pass_tds"),
            ("rushing_tds","rush_tds"),("receiving_tds","rec_tds"),
            ("targets","targets"),("receptions","rec"),
        ]:
            if col in recent.columns:
                v = round(float(recent[col].mean()), 1)
                if v > 0: stats[key] = v
        # Snap share
        snaps_df = _nfl_snaps()
        if snaps_df is not None and not snaps_df.empty:
            try:
                sname_col = "player" if "player" in snaps_df.columns else "pfr_player_name"
                sn = snaps_df[snaps_df[sname_col].str.lower() == top_name.lower()].tail(4)
                if not sn.empty and "offense_pct" in sn.columns:
                    stats["snap_pct"] = round(float(sn["offense_pct"].mean())*100, 0)
            except Exception:
                pass
        return stats if stats else None
    except Exception as e:
        return None

# ─── NFL INJURY (ESPN, free) ───
_NFL_INJURIES_CACHE = None
def fetch_nfl_injuries():
    global _NFL_INJURIES_CACHE
    if _NFL_INJURIES_CACHE is not None: return _NFL_INJURIES_CACHE
    out = {}
    try:
        r = requests.get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries",
                         timeout=15)
        if r.status_code != 200:
            _NFL_INJURIES_CACHE = out; return out
        for team_block in r.json().get("injuries", []):
            for inj in team_block.get("injuries", []):
                athlete = inj.get("athlete",{})
                name = athlete.get("displayName","")
                status = inj.get("status","")  # Out / Questionable / Doubtful / Active
                if name and status:
                    out[name.lower()] = status
        print(f"  NFL injuries: {len(out)} players tracked")
    except Exception as e:
        print(f"  warn nfl injuries: {e}")
    _NFL_INJURIES_CACHE = out
    return out

# ─── WEATHER ───
def fetch_weather(home_team):
    park = BALLPARKS.get(home_team)
    if not park: return None
    lat, lon, outdoor = park
    if not outdoor: return "Dome (kein Wettereinfluss)"
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude":lat,"longitude":lon,
            "hourly":"temperature_2m,wind_speed_10m,wind_direction_10m",
            "forecast_days":1}, timeout=20)
        if r.status_code != 200: return None
        h = r.json().get("hourly",{})
        temps, winds = h.get("temperature_2m",[]), h.get("wind_speed_10m",[])
        if temps and winds:
            i = min(22, len(temps)-1)
            t, w = temps[i], winds[i]
            note = f"{t:.0f}°C, Wind {w:.0f}km/h"
            if t >= 24 and w >= 15: note += " (HR-freundlich 🌬️)"
            elif t < 12: note += " (kalt, HR-hemmend 🥶)"
            return note
    except Exception: return None

# ─── LINEUP FILTERS ───
def is_in_mlb_lineup(player_name, home_team, away_team, lineups):
    """Return True if player is in confirmed lineup OR no lineup data (don't block)."""
    home_lu = lineups.get(home_team, {})
    away_lu = lineups.get(away_team, {})
    home_players = [p.lower() for p in home_lu.get("lineup",[])]
    away_players = [p.lower() for p in away_lu.get("lineup",[])]
    # If neither team has lineup data, assume not yet posted → allow
    if not home_players and not away_players: return True, None, None
    pl = player_name.lower()
    if RAPIDFUZZ:
        all_players = home_players + away_players
        if all_players:
            best = fuzz_process.extractOne(pl, all_players, scorer=fuzz.WRatio, score_cutoff=88)
            if best:
                # determine which team + opp pitcher
                if best[0] in home_players:
                    return True, home_team, home_lu.get("opp_sp","")
                else:
                    return True, away_team, away_lu.get("opp_sp","")
        return False, None, None
    # No rapidfuzz: substring
    for p in home_players:
        if pl in p or p in pl: return True, home_team, home_lu.get("opp_sp","")
    for p in away_players:
        if pl in p or p in pl: return True, away_team, away_lu.get("opp_sp","")
    return False, None, None

def is_nfl_player_active(player_name, injuries):
    """Return (is_active, status_label). Out/Doubtful = blocked."""
    if not injuries: return True, None
    status = injuries.get(player_name.lower())
    if not status: return True, None
    if status.lower() in ("out","injured reserve","suspended"): return False, status
    return True, status  # Questionable / Probable still pass through


# ─── WNBA: py_ball + ESPN (double-source) ───
def fetch_wnba_stats_espn(player_name):
    """ESPN WNBA player season stats — no key needed."""
    try:
        # Step 1: Search for player
        r = requests.get("https://site.api.espn.com/apis/common/v3/search",
            params={"query": player_name, "limit": 5, "type": "athlete", "leagues": "wnba"},
            headers=UA, timeout=15)
        if r.status_code != 200: return None
        hits = r.json().get("athletes") or r.json().get("items") or []
        if not hits: return None
        pid = hits[0].get("id") or hits[0].get("athlete", {}).get("id")
        if not pid: return None
        # Step 2: Get stats
        r2 = requests.get(
            f"https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/athletes/{pid}/statistics",
            headers=UA, timeout=15)
        if r2.status_code != 200: return None
        cats = r2.json().get("statistics", {}).get("categories") or []
        out = {}
        for cat in cats:
            for stat in cat.get("stats", []):
                out[stat.get("name","").lower()] = stat.get("value")
        if not out: return None
        return {
            "avg_pts":  out.get("avgpoints") or out.get("points"),
            "avg_reb":  out.get("avgrebounds") or out.get("rebounds"),
            "avg_ast":  out.get("avgassists") or out.get("assists"),
            "avg_min":  out.get("avgminutes") or out.get("minutespergame"),
            "games":    out.get("gamesplayed"),
        }
    except Exception as e:
        return None

def fetch_wnba_stats_pyball(player_name):
    """py_ball WNBA stats from stats.wnba.com."""
    if not PYBALL: return None
    try:
        from py_ball import player as pb_player
        search = pb_player.Player(headers=WNBA_HEADERS,
            endpoint="commonallplayers", league_id="10", season="2025-26")
        df = search.data.get("CommonAllPlayers", {})
        rows = df.get("data", [])
        headers = df.get("headers", [])
        name_idx = headers.index("DISPLAY_FIRST_LAST") if "DISPLAY_FIRST_LAST" in headers else None
        id_idx = headers.index("PERSON_ID") if "PERSON_ID" in headers else None
        if name_idx is None or id_idx is None: return None
        from rapidfuzz import process
        names = [r[name_idx] for r in rows]
        match, score, idx = process.extractOne(player_name, names)
        if score < 80: return None
        pid = rows[idx][id_idx]
        time.sleep(0.3)
        stats = pyball_stats.PlayerStats(headers=WNBA_HEADERS,
            endpoint="playercareerstats", player_id=str(pid), league_id="10")
        sdata = stats.data.get("SeasonTotalsRegularSeason",{})
        if not sdata.get("data"): return None
        row = sdata["data"][-1]
        hdr = sdata.get("headers",[])
        def g(k): return row[hdr.index(k)] if k in hdr else None
        gp = g("GP") or 1
        return {
            "avg_pts": round((g("PTS") or 0)/gp, 1),
            "avg_reb": round((g("REB") or 0)/gp, 1),
            "avg_ast": round((g("AST") or 0)/gp, 1),
        }
    except Exception as e:
        return None

def fetch_wnba_player_stats(player_name):
    """Try ESPN first, then py_ball."""
    result = fetch_wnba_stats_espn(player_name)
    if result: return result
    return fetch_wnba_stats_pyball(player_name)

# ─── api-sports.io (backup for all leagues) ───
def fetch_apisports_player(player_name, sport="basketball"):
    """api-sports.io backup — 100 req/day free."""
    if not API_SPORTS_KEYS: return None
    endpoints = {
        "basketball": "https://v2.nba.api-sports.io",
        "baseball":   "https://v1.baseball.api-sports.io",
        "football":   "https://v1.american-football.api-sports.io",
    }
    base = endpoints.get(sport, endpoints["basketball"])
    for key in API_SPORTS_KEYS:
        try:
            r = requests.get(f"{base}/players",
                params={"search": player_name.split()[-1], "season": YEAR},
                headers={"x-apisports-key": key}, timeout=20)
            if r.status_code != 200: continue
            players = r.json().get("response", [])
            if not players: continue
            p = players[0]
            stats = p.get("statistics", [{}])[0]
            return {
                "avg_pts": stats.get("points", {}).get("average"),
                "avg_reb": stats.get("rebounds", {}).get("total", {}).get("average"),
                "avg_ast": stats.get("assists", {}).get("average"),
                "games":   stats.get("games", {}).get("played"),
            }
        except Exception: continue
    return None


# ─── PROPSMADNESS SCRAPER (Playwright) ───
async def fetch_propsmadness_player(page, player_name, market="player-points"):
    """Scrape hit rate + stats from PropsMadness for a player."""
    try:
        # Go to PropsMadness and search for player
        await page.goto("https://propsmadness.com/nba", timeout=30000)
        await page.wait_for_timeout(2000)
        
        # Click search / type player name
        search = page.locator("input[placeholder*='search'], input[placeholder*='player'], input[type='search']").first
        await search.click()
        await search.fill(player_name.split()[-1])  # Last name search
        await page.wait_for_timeout(1500)
        
        # Find and click matching player
        options = page.locator(f"[data-player], .player-option, li:has-text('{player_name}')")
        if await options.count() > 0:
            await options.first.click()
            await page.wait_for_timeout(2000)
        
        # Extract hit rate
        hit_rate_el = page.locator(".hit-rate, [class*='HitRate'], [class*='hitRate']").first
        hit_rate_text = await hit_rate_el.text_content() if await hit_rate_el.count() > 0 else ""
        
        # Extract stats
        pts_el = page.locator("text=Pts").locator("..").locator("[class*='value'], span").first
        avg_pts = await pts_el.text_content() if await pts_el.count() > 0 else None
        
        import re
        hr_match = re.search(r'(\d+)%\s*\((\d+)/(\d+)\)', hit_rate_text)
        hit_rate = int(hr_match.group(1)) if hr_match else None
        
        return {
            "hit_rate": hit_rate,
            "avg": float(avg_pts) if avg_pts and avg_pts.replace('.','').isdigit() else None,
            "source": "propsmadness"
        }
    except Exception as e:
        return None

def fetch_propsmadness_sync(player_name, market="player-points"):
    """Sync wrapper for PropsMadness scraper."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA["User-Agent"])
            
            # Navigate to PropsMadness
            page.goto("https://propsmadness.com/nba", timeout=30000)
            page.wait_for_timeout(2500)
            
            # Use keyboard shortcut or search
            page.keyboard.press("Slash")
            page.wait_for_timeout(500)
            
            # Type player last name
            last_name = player_name.split()[-1]
            page.keyboard.type(last_name)
            page.wait_for_timeout(1500)
            
            # Select first matching result
            results = page.locator(f"text={last_name}").all()
            if results:
                # Click first result that matches full name approximately
                for r in results[:5]:
                    txt = r.text_content() or ""
                    if last_name.lower() in txt.lower():
                        r.click()
                        break
                page.wait_for_timeout(2000)
            
            # Extract Hit Rate from page
            import re
            content_text = page.content()
            
            # Look for hit rate pattern: "65% (13/20)"
            hr_match = re.search(r'(\d+)%[^<]*(\d+)/(\d+)', content_text)
            hit_rate = int(hr_match.group(1)) if hr_match else None
            wins = int(hr_match.group(2)) if hr_match else None
            total = int(hr_match.group(3)) if hr_match else None
            
            # Look for avg stats
            pts_match = re.search(r'"pts[^"]*"[^:]*:\s*([0-9.]+)', content_text)
            avg_pts = float(pts_match.group(1)) if pts_match else None
            
            browser.close()
            
            if hit_rate:
                return {
                    "hit_rate": hit_rate,
                    "hit_count": wins,
                    "total_games": total,
                    "avg": avg_pts,
                }
    except Exception as e:
        print(f"  warn propsmadness {player_name}: {e}")
    return None

def enrich_with_propsmadness(props_list):
    """Enrich top NBA props with PropsMadness hit rate data."""
    # Only for NBA/WNBA, limit to 5 players to save time
    nba_props = [p for p in props_list if p.get("sport") in ("NBA","WNBA")][:5]
    enriched = 0
    for p in nba_props:
        data = fetch_propsmadness_sync(p["player"])
        if data and data.get("hit_rate"):
            hr = data["hit_rate"]
            tag = f"PropsMadness: {hr}% ({data.get('hit_count','?')}/{data.get('total_games','?')})"
            p["enrichment"] = p.get("enrichment","") + " | " + tag
            p["pm_hit_rate"] = hr
            enriched += 1
    if enriched:
        print(f"  PropsMadness: {enriched} players enriched")
    return props_list

# ─── GATHER ───
def gather():
    all_props, active = [], []
    mlb_batters, mlb_pitchers, mlb_lineups = {}, {}, {}
    weather_cache, nfl_stats_cache = {}, {}
    nfl_injuries = {}

    for sport, cfg in SPORTS.items():
        events = fetch_events(sport)
        if not events: continue
        active.append(f"{cfg['emoji']} {cfg['name']} ({len(events)})")

        # Lazy-load MLB enrichment data once
        if sport == "baseball_mlb":
            if not mlb_batters:  mlb_batters  = fetch_mlb_batters()
            if not mlb_pitchers: mlb_pitchers = fetch_mlb_pitchers()
            if not mlb_lineups:  mlb_lineups  = fetch_mlb_lineups_today()
        if sport == "americanfootball_nfl" and not nfl_injuries:
            nfl_injuries = fetch_nfl_injuries()

        markets = ",".join(m[0] for m in cfg["markets"])
        for ev in events[:6]:
            data = fetch_props(sport, ev["id"], markets)
            if not data: continue
            home = ev.get("home_team","")
            away = ev.get("away_team","")
            game_total = extract_game_totals(data)
            wx = None
            park_factor = None
            if cfg["name"] == "MLB":
                if home not in weather_cache:
                    weather_cache[home] = fetch_weather(home)
                wx = weather_cache[home]
                park_factor = PARK_FACTORS_HR.get(home)

            for mk, label, mp, mo in cfg["markets"]:
                for p in extract(data, mk, label, mp, mo):
                    p["sport"] = cfg["name"]
                    p["emoji"] = cfg["emoji"]
                    p["game"]  = f"{away} @ {home}"
                    if game_total: p["game_total"] = game_total
                    extra = []

                    # ── MLB ENRICHMENT + LINEUP FILTER ──
                    if cfg["name"] == "MLB":
                        in_lineup, team, opp_sp = is_in_mlb_lineup(p["player"], home, away, mlb_lineups)
                        if not in_lineup and mlb_lineups:
                            # Skip — player NOT in confirmed lineup
                            continue
                        if team: p["team"] = team
                        # Batter stats
                        batter = fuzzy_match(p["player"], mlb_batters)
                        if batter:
                            if batter.get("barrel"): extra.append(f"Barrel {batter['barrel']}%")
                            if batter.get("iso"):    extra.append(f"ISO {batter['iso']}")
                            if batter.get("hardhit"):extra.append(f"HardHit {batter['hardhit']}%")
                            if batter.get("xslg"):   extra.append(f"xSLG {batter['xslg']}")
                            if batter.get("hr") is not None:  extra.append(f"HR {int(batter['hr'])}")
                        # Pitcher matchup
                        if opp_sp and mlb_pitchers:
                            pit = fuzzy_match(opp_sp, mlb_pitchers)
                            if pit:
                                pit_summary = f"vs {opp_sp}"
                                if pit.get("era"):  pit_summary += f" ERA{pit['era']}"
                                if pit.get("hr9"):  pit_summary += f" HR/9 {pit['hr9']}"
                                if pit.get("whip"): pit_summary += f" WHIP{pit['whip']}"
                                extra.append(pit_summary)
                            else:
                                extra.append(f"vs {opp_sp}")
                        if park_factor: extra.append(f"Park HR-Factor {park_factor}")
                    if wx: extra.append(f"Wetter: {wx}")
                    if game_total: extra.append(f"O/U {game_total}")
                    if extra: p["enrichment"] = " | ".join(extra)

                    all_props.append(p)

    # ── NBA ENRICHMENT (balldontlie, post-loop for all NBA props) ──
    nba_props = [p for p in all_props if p["sport"] in ("NBA","WNBA")]
    nba_cache = {}
    for p in nba_props:
        if p["player"] not in nba_cache:
            nba_cache[p["player"]] = fetch_nba_player_stats_bdl(p["player"])
        ns = nba_cache[p["player"]]
        if ns:
            tags = [f"PTS {ns['avg_pts']}", f"MIN {ns['avg_min']}", f"GP {ns['games']}"]
            if ns.get("avg_reb"): tags.append(f"REB {ns['avg_reb']}")
            if ns.get("avg_ast"): tags.append(f"AST {ns['avg_ast']}")
            existing = p.get("enrichment","")
            p["enrichment"] = (existing + " | " if existing else "") + " ".join(tags)

    # ── NFL ENRICHMENT (ALL props now, not just first 8) ──
    nfl_props = [p for p in all_props if p["sport"]=="NFL"]
    for p in nfl_props:
        # Injury filter
        active_p, status = is_nfl_player_active(p["player"], nfl_injuries)
        if not active_p:
            # Mark for removal
            p["_remove"] = True
            continue
        if p["player"] not in nfl_stats_cache:
            nfl_stats_cache[p["player"]] = fetch_nfl_player_stats(p["player"])
        ns = nfl_stats_cache[p["player"]]
        tags = []
        if ns:
            for k, v in ns.items():
                tags.append(f"{k}:{v}")
        if status: tags.append(f"⚠️{status}")
        if tags:
            existing = p.get("enrichment","")
            p["enrichment"] = (existing + " | " if existing else "") + " ".join(tags[:5])

    # Remove inactive NFL players
    all_props = [p for p in all_props if not p.get("_remove")]

    print(f"  Active: {', '.join(active) if active else 'NONE'}")
    print(f"  Total props enriched (after lineup/injury filter): {len(all_props)}")
    
    # PropsMadness: Hit Rate für Top-NBA Props
    if PW_OK:
        all_props = enrich_with_propsmadness(all_props)
    return all_props

# ─── GROQ FALLBACK ───
def groq_analyze(prompt):
    models = ["llama-3.3-70b-versatile","llama-3.1-70b-versatile","mixtral-8x7b-32768"]
    for key in GROQ_KEYS:
        for model in models:
            try:
                r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
                    json={"model":model,"messages":[{"role":"user","content":prompt}],
                          "max_tokens":2048,"temperature":0.7}, timeout=60)
                if r.status_code == 200:
                    text = r.json()["choices"][0]["message"]["content"]
                    text = text.replace("```json","").replace("```","").strip()
                    s, e = text.find("["), text.rfind("]")+1
                    picks = json.loads(text[s:e])
                    print(f"  Groq ({model}): {len(picks)} picks")
                    return picks
                elif r.status_code == 429:
                    print(f"  Groq 429, next model..."); continue
            except Exception as ex:
                print(f"  warn groq {ex}"); continue
    return None

# ─── GEMINI ───
def gemini_analyze(props):
    if not props or not GEMINI_KEYS: return None
    lines = []
    for p in props[:60]:
        ln = f"- {p['emoji']} {p['player']} ({p['game']}) {p['market']} @ {p['odds']}"
        if p.get("enrichment"): ln += f"  [{p['enrichment']}]"
        lines.append(ln)

    prompt = f"""Du bist der BESTE Sharp Sports Betting Analyst der Welt. Finde ECHTEN VALUE in diesen Props — wir sind besser als JK!

PROPS:
{chr(10).join(lines)}

ALLE Spieler vorausgefiltert (bestätigte Lineups, keine DNPs).

=== ⚾ MLB STRATEGIE ===
Home Run: Barrel% > 10% + HardHit% > 40% + Pitcher HR/9 > 1.2 + HR-Park (>105) + warm + Wind raus → 0.25u
Total Bases: Kontakt-Hitter, gutes Matchup → 0.25u
Stolen Base: SB-Rate > 70%, Läufer auf Base → 0.25u
Pitcher K OVER: K/9 > 9.0 gegen K-anfälliges Lineup → 0.25u
Outs Recorded UNDER: Pitcher mit ERA > 5.0 / schlechter Form → 0.25u
RBI: Runner on base, Clutch-Hitter → 0.25u
→ MLB immer 0.25u Stakes (Volume-Strategie wie JK!)

=== 🏀 NBA/WNBA STRATEGIE ===
OVER: avg_last5 > linie × 1.08 → 1u solid
UNDER: avg_last5 < linie × 0.85 → 1u solid
3PM: avg 3PM > 3/Spiel → Over sinnvoll
PRA: Starkes All-Around Game, hohe Minuten
Blocks/Steals: Nur bei klarem statistischen Edge

LADDER (gleicher Spieler, 2 Schwellen):
- Niveau 1: linie × 0.85 @1.8-2.5 → 0.75u
- Niveau 2: linie × 1.1  @3.0-6.0 → 0.25u
- Nur wenn Spieler in 3/5 letzten Spielen Niveau 2 erreichte

=== 🏀 EUROLEAGUE ===
Linien 12-15 Punkte normal. Nur klare Over/Under wählen.
Rebounds/Assists/3PM wenn klarer Trend in Daten.

=== 🏈 NFL ===
Nur wenn aktive Saison! snap_pct > 70% Pflicht.

=== KOMBI-SYSTEM (alle Paare abdecken!) ===

BET BUILDER – Same Game Parlay (@3-12):
- Gleicher Spieler: Brunson 30+ Pts + 5+ Ast
- Gleiche Partie: Wemby 20+ + Castle 5+ Ast
- Stake: 0.5u

TYPE 1 – 2-LEG KOMBIS (alle Paare!):
Top-3 Picks → AB + AC + BC = 3 Kombis
Target @8-25 | Stake: 0.5u

TYPE 2 – 3-LEG LOTTERY:
ABC aus Top-3 Picks
Target @40-150 | Stake: 0.25u

TYPE 3 – SUPER LOTTERY (wenn 4+ starke Picks):
ABCD = 4-Leg
Target @200+ | Stake: 0.10u

→ Wenn 7 HR alle stark: alle 21 Paare wären möglich, aber wähle die 3 BESTEN Paare + 1 Triple!
→ Kein künstliches Limit bei Singles! Alle echten Value-Picks rein!

Alle Analysen auf DEUTSCH! Echte Daten zitieren (Barrel%, Odds, avg letzte 5).
Team: MLB="ATL Braves", NBA="NYK Knicks", NFL="KC Chiefs"

Return ONLY valid JSON (kein Markdown):
[
{{"type":"single","emoji":"⚾","player":"Name","team":"ATL Braves","market":"Home Run","odds":5.5,"stake":0.25,"probability":0.22,"analysis":"Deutsch: Barrel% 14%, HR/9 1.8, Coors Field 110, 28°C Wind raus"}},
{{"type":"single","emoji":"🏀","player":"Name","team":"NYK Knicks","market":"Points UNDER 35.5","odds":1.90,"stake":1.0,"probability":0.60,"analysis":"Deutsch: avg letzte 5 = 27.3, klar unter 35.5"}},
{{"type":"single","emoji":"🏀","player":"Name","team":"SAS Spurs","market":"3PM Over 1.5","odds":2.49,"stake":0.5,"probability":0.62,"analysis":"Deutsch: avg 2.3 3PM/Spiel, 4/5 letzten Spiele getroffen"}},
{{"type":"ladder","emoji":"🏀","player":"Name","team":"NYK","picks":[{{"market":"30+ Points","odds":2.50,"stake":0.75}},{{"market":"35+ Points","odds":5.00,"stake":0.25}}],"analysis":"Deutsch: 3/5 letzten Spiele über 35, Heimspiel NYC"}},
{{"type":"betbuilder","legs":["Brunson 30+ Pts","Brunson 5+ Ast"],"game":"NYK vs SAS","odds":8.50,"stake":0.5,"analysis":"Deutsch: Same-Game Parlay"}},
{{"type":"kombi2","legs":["ATL Name HR","PHI Name HR"],"odds":20.75,"stake":0.5}},
{{"type":"big","legs":["Suzuki HR","Goodman HR","Wood HR"],"odds":99.23,"stake":0.25}},
{{"type":"super","legs":["L1","L2","L3","L4"],"odds":250.0,"stake":0.10}}
]"""

    for i, key in enumerate(GEMINI_KEYS):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
            r = requests.post(url, json={"contents":[{"parts":[{"text":prompt}]}],
                "generationConfig":{"temperature":0.7,"maxOutputTokens":2048}}, timeout=60)
            if r.status_code == 429:
                print(f"  Gemini key {i+1} rate limited, next..."); time.sleep(3); continue
            if r.status_code != 200:
                print(f"  warn gemini {r.status_code}, next..."); continue
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = text.replace("```json","").replace("```","").strip()
            s, e = text.find("["), text.rfind("]")+1
            picks = json.loads(text[s:e])
            print(f"  Gemini: {len(picks)} picks")
            return picks
        except Exception as ex:
            print(f"  warn gemini {ex}, next..."); continue
    if GROQ_KEYS:
        print("  All Gemini keys failed → trying Groq fallback...")
        return groq_analyze(prompt)
    return None

# ─── POST ───
def build_post(picks):
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    singles = [p for p in picks if p.get("type")=="single"]
    kombis  = [p for p in picks if p.get("type")=="kombi2"]
    bigs    = [p for p in picks if p.get("type")=="big"]
    post = f"🎯 PROP HUNTER — {today}\n\n📋 VALUE SINGLES:\n\n"
    for p in singles:
        post += f"{p.get('emoji','⚾')} {p.get('team','')} — {p['player']}\n"
        post += f"   └ {p['market']} @{p['odds']:.2f} → {p['stake']}u\n"
        if p.get("analysis"): post += f"   💡 {p['analysis']}\n"
        post += "\n"
    if kombis:
        post += "🔥 2-LEG KOMBIS:\n"
        for p in kombis:
            post += f"• {' + '.join(p['legs'])} @{p['odds']:.2f} → {p['stake']}u\n"
        post += "\n"
    if bigs:
        post += "💣 BIG KOMBIS:\n"
        for p in bigs:
            post += f"• {' + '.join(p['legs'])} @{p['odds']:.2f} → {p['stake']}u\n"
        post += "\n"
    post += "📊 ANALYSIERT. GEZIELT. GEWONNEN. 🎯\n@prophunter"
    return post

# ─── DEDUP ───
def already_posted_today():
    """Returns (player|market keys, player names) already posted today."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    posted_keys = set()
    posted_players = set()
    if os.path.exists("picks_history.json"):
        try:
            for entry in json.load(open("picks_history.json")):
                if entry["date"] == today:
                    for p in entry.get("picks",[]):
                        pl = p.get("player","").lower()
                        mk = p.get("market","").lower()
                        posted_keys.add(f"{pl}|{mk}")
                        posted_players.add(pl)
        except Exception: pass
    return posted_keys, posted_players

def save_picks(picks):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history = []
    if os.path.exists("picks_history.json"):
        try: history = json.load(open("picks_history.json"))
        except Exception: pass
    entry = {"date":today,"evaluated":False,"picks":[],"kombis":[]}
    for p in picks:
        if p.get("type")=="single":
            entry["picks"].append({
                "player":p.get("player",""),"team":p.get("team",""),
                "market":p.get("market",""),"odds":p.get("odds",0),
                "stake":p.get("stake",1),
                "probability":p.get("probability"),
                "sport":"MLB" if p.get("emoji")=="⚾" else "NBA" if p.get("emoji")=="🏀" else "NFL",
                "result":None})
        elif p.get("type") in ("kombi2","big"):
            entry["kombis"].append({
                "type":p.get("type","kombi2"),
                "legs":p.get("legs",[]),
                "odds":p.get("odds",0),
                "stake":p.get("stake",0.5),
                "result":None})
    history.append(entry)
    json.dump(history, open("picks_history.json","w"), indent=2)
    print(f"  Saved {len(entry['picks'])} singles + {len(entry['kombis'])} kombis")
    # Log to Supabase for ML
    for p in entry["picks"]:
        log_pick_supabase(p)
    if entry["picks"]: print(f"  Supabase: {len(entry['picks'])} picks logged")

# ─── TELEGRAM ───
def send_telegram(text):
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id":TG_CHAT,"text":text}, timeout=30)
        print("  Telegram: OK" if r.status_code==200 else f"  Telegram: {r.text[:120]}")
    except Exception as e: print(f"  Telegram error: {e}")

# ─── MAIN ───

# ─── SUPABASE ML LOGGING ───
_sb_client = None
def get_sb():
    global _sb_client
    if _sb_client is None and SUPABASE and SUPABASE_URL and SUPABASE_KEY:
        try: _sb_client = sb_create(SUPABASE_URL, SUPABASE_KEY)
        except Exception as e: print(f"  warn supabase init: {e}")
    return _sb_client

def log_pick_supabase(pick, features=None):
    """Log pick + ML features to Supabase for future model training."""
    sb = get_sb()
    if not sb: return
    try:
        f = features or {}
        row = {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "player": pick.get("player",""),
            "team": pick.get("team",""),
            "sport": "MLB" if pick.get("emoji")=="⚾" else "NBA" if pick.get("emoji")=="🏀" else "NFL",
            "market": pick.get("market",""),
            "odds": pick.get("odds",0),
            "stake": pick.get("stake",1),
            "barrel_pct": f.get("barrel"),
            "iso": f.get("iso"),
            "hard_hit": f.get("hardhit"),
            "xslg": f.get("xslg"),
            "pitcher_hr9": f.get("pitcher_hr9"),
            "park_factor": f.get("park_factor"),
            "temp_c": f.get("temp_c"),
            "wind_kmh": f.get("wind_kmh"),
            "avg_pts": f.get("avg_pts"),
            "avg_min": f.get("avg_min"),
            "result": "pending",
        }
        sb.table("prop_picks").insert(row).execute()
    except Exception as e:
        print(f"  warn supabase log: {e}")

def update_result_supabase(player, date_str, result, profit):
    """Update pick result in Supabase after evaluation."""
    sb = get_sb()
    if not sb: return
    try:
        sb.table("prop_picks").update({
            "result": result, "profit": profit
        }).eq("player", player).eq("date", date_str).eq("result", "pending").execute()
    except Exception as e:
        print(f"  warn supabase update: {e}")

def main():
    print("="*40)
    print("PROP HUNTER v2 starting...")
    print(f"  pybaseball={PYBASEBALL} | balldontlie=ready | nfl_data={NFL_DATA} | rapidfuzz={RAPIDFUZZ}")
    print("Fetching games + odds + stats + lineups + injuries (next 12h)...")
    props = gather()
    if not props:
        print("  No props found. Exiting (no post)."); return
    print("Gemini value analysis...")
    picks = gemini_analyze(props)
    if not picks:
        print("  No value found. Exiting (no post)."); return
    posted_keys, posted_players = already_posted_today()
    posted = posted_players  # backwards compat
    if posted:
        before = len([p for p in picks if p.get("type")=="single"])
        picks = [p for p in picks if not (p.get("type")=="single" and p.get("player","").lower() in posted)]
        after = len([p for p in picks if p.get("type")=="single"])
        # Also filter combos containing already-posted players
        before_k = len([p for p in picks if p.get("type") in ("kombi2","big","super","betbuilder")])
        picks = [p for p in picks if p.get("type") not in ("kombi2","big","super","betbuilder") or
                 not any(any(pl in leg.lower() for pl in posted_players) 
                         for leg in p.get("legs",[]))]
        after_k = len([p for p in picks if p.get("type") in ("kombi2","big","super","betbuilder")])
        if before != after: print(f"  Dedup Singles: {before}→{after}")
        if before_k != after_k: print(f"  Dedup Kombis: {before_k}→{after_k}")
    if not [p for p in picks if p.get("type")=="single"]:
        print("  All picks already posted today. Skipping."); return
    post = build_post(picks)
    print("\n"+post+"\n")
    send_telegram(post)
    save_picks(picks)
    print("="*40)
    print("Done!")

if __name__ == "__main__":
    main()
