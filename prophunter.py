#!/usr/bin/env python3
"""
PROP HUNTER — Automated MLB/NBA/NFL Player Props Tipster Bot
Data: pybaseball (MLB Statcast/FanGraphs) + nba_api (NBA) + nfl_data_py (NFL)
AI:   Gemini (free, key rotation)
Odds: the-odds-api.com (Betfair/Pinnacle/bet365)

pip install requests pybaseball nba_api nfl_data_py
"""

import os, io, json, time, requests
from datetime import datetime, timedelta, timezone

# Optional stats libraries (graceful fallback if unavailable)
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT = True
    print("  playwright OK")
except Exception:
    PLAYWRIGHT = False
try:
    from pybaseball import batting_stats as pb_batting
    from pybaseball import playerid_lookup
    PYBASEBALL = True
    print("  pybaseball OK")
except Exception:
    PYBASEBALL = False

try:
    import statsapi  # toddrob99/MLB-StatsAPI - fallback for MLB data
    MLB_STATSAPI = True
    print("  MLB-StatsAPI OK")
except Exception:
    MLB_STATSAPI = False

try:
    from nba_api.stats.static import players as nba_db
    from nba_api.stats.endpoints import playergamelog, playerdashboardbygeneralsplits
    NBA_API = True
    print("  nba_api OK")
except Exception:
    NBA_API = False

try:
    import nflreadpy as nfl  # newer replacement for nfl_data_py
    NFL_DATA = True
    print("  nflreadpy OK")
except Exception:
    try:
        import nfl_data_py as nfl  # fallback to deprecated version
        NFL_DATA = True
        print("  nfl_data_py OK (deprecated)")
    except Exception:
        NFL_DATA = False

# ─── CONFIG ───
ODDS_API_KEY   = os.environ.get("ODDS_API_KEY", "")
GEMINI_KEYS    = [k.strip() for k in os.environ.get("GEMINI_API_KEY","").split(",") if k.strip()]
GROQ_KEYS      = [k.strip() for k in os.environ.get("GROQ_API_KEY","").split(",") if k.strip()]
TG_TOKEN       = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT        = os.environ.get("TELEGRAM_CHAT_ID", "")

ODDS_BASE  = "https://api.the-odds-api.com/v4"
BOOKMAKERS = "bet365,draftkings,fanduel,betmgm,williamhill,pinnacle"
UA         = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
YEAR       = datetime.now(timezone.utc).year

SPORTS = {
    # ⚾ Baseball
    "baseball_mlb": {"emoji":"⚾","name":"MLB",
        "markets":[("batter_home_runs","Home Run",None,3.5)]},
    # 🏀 Basketball
    "basketball_nba": {"emoji":"🏀","name":"NBA",
        "markets":[
            ("player_points_alternate","Points",25,3.5),
            ("player_double_double","Double Double",None,3.0),
            ("player_triple_double","Triple Double",None,6.0)]},
    "basketball_wnba": {"emoji":"🏀","name":"WNBA",
        "markets":[
            ("player_points_alternate","Points",15,3.5),
            ("player_double_double","Double Double",None,3.0)]},
    "basketball_euroleague": {"emoji":"🏀","name":"Euroleague",
        "markets":[
            ("player_points_alternate","Points",15,3.5)]},
    # 🏈 American Football
    "americanfootball_nfl": {"emoji":"🏈","name":"NFL",
        "markets":[
            ("player_anytime_td","Anytime TD",None,2.5),
            ("player_pass_tds_alternate","Pass TDs",None,3.0),
            ("player_rush_yds_alternate","Rush Yds",None,3.0),
            ("player_reception_yds_alternate","Rec Yds",None,3.0)]},
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
        r = requests.get(f"{ODDS_BASE}/sports/{sport}/events/{eid}/odds", params={
            "apiKey":ODDS_API_KEY,"regions":"us,eu,uk","markets":markets,
            "oddsFormat":"decimal","bookmakers":BOOKMAKERS}, timeout=30)
        if r.status_code != 200: return None
        d = r.json()
        bms = d.get("bookmakers",[])
        if bms: print(f"  props OK: {len(bms)} bookmakers")
        return d
    except Exception: return None

def extract(data, mkey, label, min_pt, min_odds):
    out = {}
    _logged = [False]
    for bm in (data.get("bookmakers") or []):
        for mkt in (bm.get("markets") or []):
            if mkt.get("key") != mkey: continue
            outcomes = mkt.get("outcomes") or []
            # Debug first market
            if not _logged[0] and outcomes:
                _logged[0] = True
                sample = outcomes[0]
                print(f"  [struct] name={sample.get('name')} desc={sample.get('description')} pt={sample.get('point')} price={sample.get('price')}")
            for o in outcomes:
                desc       = o.get("description","") or ""
                name_field = o.get("name","") or ""
                pt         = o.get("point")
                price      = o.get("price",0)

                # Handle both bookmaker structures:
                # Type A: name=PlayerName, description=Over/Under  (most US books)
                # Type B: name=Over/Under, description=PlayerName  (some EU books)
                TYPE_WORDS = {"Over","Under","Yes","No",""}
                if name_field in TYPE_WORDS:
                    # Type B
                    player_name  = desc
                    outcome_type = name_field
                else:
                    # Type A
                    player_name  = name_field
                    outcome_type = desc

                # Only keep Over / Yes / empty (for HR: "will player hit HR" = effectively Over)
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

# ─── MLB: pybaseball (FanGraphs batting stats) ───
def fetch_mlb_stats():
    if not PYBASEBALL: return {}
    try:
        df = pb_batting(YEAR, qual=1)
        if df is None or len(df) == 0:
            df = pb_batting(YEAR-1, qual=1)
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
                "hr":    g("HR"),
                "iso":   g("ISO"),
                "barrel": g("Barrel%", ["Barrel/PA%","EV"]),
                "hardhit": g("HardHit%", ["Hard%","HardHit"]),
                "xslg":  g("xSLG", ["xSLG_custom"]),
            }
        print(f"  pybaseball: {len(out)} batters loaded")
        return out
    except Exception as e:
        print(f"  warn pybaseball: {e}")
        # Fallback 1: MLB-StatsAPI
        if MLB_STATSAPI:
            try:
                return fetch_mlb_statsapi()
            except Exception as e2:
                print(f"  warn mlb-statsapi: {e2}")
        # Fallback 2: Playwright → FanGraphs
        result = scrape_fangraphs_batting()
        if result: return result
        # Fallback 3: Playwright → Baseball Savant
        return scrape_baseball_savant()

# ─── PLAYWRIGHT SCRAPER (fallback for 403s) ───
def playwright_scrape(url, wait_selector=None, timeout=30000):
    """Generic Playwright scraper — handles JS-heavy pages + bot protection."""
    if not PLAYWRIGHT: return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width":1280,"height":800}
            )
            page = ctx.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout)
            if wait_selector:
                page.wait_for_selector(wait_selector, timeout=timeout)
            content = page.content()
            browser.close()
            return content
    except Exception as e:
        print(f"  warn playwright {url[:50]}: {e}")
        return None

def playwright_fetch_csv(url, timeout=30000):
    """Fetch CSV/text content via Playwright."""
    if not PLAYWRIGHT: return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = ctx.new_page()
            response = page.goto(url, timeout=timeout)
            body = response.body().decode("utf-8", errors="replace") if response else None
            browser.close()
            return body
    except Exception as e:
        print(f"  warn playwright csv: {e}")
        return None

def scrape_fangraphs_batting():
    """Playwright fallback for FanGraphs batting stats (pybaseball 403)."""
    if not PLAYWRIGHT: return {}
    print("  Playwright → FanGraphs...")
    url = f"https://www.fangraphs.com/leaders/major-league?pos=all&stats=bat&lg=all&qual=20&season={YEAR}&month=0&ind=0&rost=0&type=8&pageitems=500"
    html = playwright_scrape(url, wait_selector="table.rgMasterTable, .fg-data-grid", timeout=40000)
    if not html: return {}
    try:
        from html.parser import HTMLParser
        import re
        # Extract stats from JSON data embedded in page
        pattern = r'"Name":"([^"]+)"[^}]*"ISO":([0-9.]+)[^}]*"Hard%":([0-9.]+)[^}]*"Barrel%":([0-9.]+)'
        matches = re.findall(pattern, html)
        out = {}
        for m in matches:
            name, iso, hardhit, barrel = m
            out[name.lower()] = {"iso": float(iso), "hardhit": float(hardhit), "barrel": float(barrel), "hr": None, "xslg": None}
        if out: print(f"  FanGraphs (PW): {len(out)} batters")
        return out
    except Exception as e:
        print(f"  warn fangraphs parse: {e}"); return {}

def scrape_baseball_savant():
    """Playwright fallback for Baseball Savant percentile rankings."""
    if not PLAYWRIGHT: return {}
    print("  Playwright → Baseball Savant...")
    url = f"https://baseballsavant.mlb.com/leaderboard/percentile-rankings?type=batter&year={YEAR}&csv=true"
    body = playwright_fetch_csv(url)
    if not body: return {}
    try:
        import csv, io
        out = {}
        for row in csv.DictReader(io.StringIO(body)):
            name = (row.get("player_name") or "").strip()
            if not name: continue
            if "," in name:
                p = [x.strip() for x in name.split(",")]
                name = f"{p[1]} {p[0]}" if len(p)==2 else name
            def g(k):
                v = row.get(k,"")
                try: return int(float(v)) if v not in ("",None) else None
                except: return None
            out[name.lower()] = {
                "hr": g("hr") or g("home_run"), "xslg": g("xslg"),
                "xiso": g("xiso") or g("iso"), "barrel": g("brl_percent") or g("brl"),
                "hardhit": g("hard_hit_percent") or g("exit_velocity")}
        if out: print(f"  Savant (PW): {len(out)} profiles")
        return out
    except Exception as e:
        print(f"  warn savant parse: {e}"); return {}

def scrape_nba_stats_player(player_name):
    """Playwright fallback for NBA player stats (nba_api timeout)."""
    if not PLAYWRIGHT: return None
    try:
        last = player_name.split()[-1].lower()
        url = f"https://www.basketball-reference.com/search/search.fcgi?search={player_name.replace(' ','+')}"
        html = playwright_scrape(url, timeout=20000)
        if not html: return None
        import re
        pts = re.findall(r'"pts_per_g":"?([0-9.]+)"?', html)
        mp = re.findall(r'"mp_per_g":"?([0-9.]+)"?', html)
        if pts:
            return {"avg_pts": float(pts[0]), "avg_min": float(mp[0]) if mp else 0, "games": 0}
    except Exception as e:
        print(f"  warn pw nba {player_name}: {e}")
    return None

def fetch_mlb_statsapi():
    """Fallback: MLB-StatsAPI for basic batter stats."""
    if not MLB_STATSAPI: return {}
    try:
        out = {}
        # Get current season stats for all batters
        people = statsapi.get('sports_players', {'season': YEAR, 'sportId': 1})
        for p in (people.get('people') or [])[:200]:
            name = p.get('fullName','').lower()
            pid  = p.get('id')
            if not name or not pid: continue
            s = statsapi.player_stat_data(pid, group='hitting', type='season')
            stats_data = (s.get('stats') or [{}])[0].get('stats', {})
            hr = stats_data.get('homeRuns', 0)
            if hr and int(hr) > 3:
                out[name] = {"hr": int(hr), "iso": None, "barrel": None, "hardhit": None, "xslg": None}
        print(f"  MLB-StatsAPI: {len(out)} batters")
        return out
    except Exception as e:
        print(f"  warn mlb-statsapi: {e}"); return {}

def match_batter(player, stats):
    pl = player.lower()
    if pl in stats: return stats[pl]
    last = pl.split()[-1] if pl.split() else pl
    for n, d in stats.items():
        if n.split() and n.split()[-1] == last:
            if pl.split()[0][:3] in n: return d
    return None

def pct_tag(val, label, high_thresh=15.0):
    """Convert raw % stat to percentile-style label."""
    if val is None: return None
    # FanGraphs barrel% elite = >10%, good = 6-10%
    # We just show the raw value with label
    return f"{label} {val}%"

# ─── NBA: nba_api ───
def fetch_nba_player_stats(player_name):
    if not NBA_API: return None
    try:
        results = nba_db.find_players_by_full_name(player_name)
        if not results:
            # Try last name
            last = player_name.split()[-1]
            results = [p for p in nba_db.get_players() if p['last_name'].lower()==last.lower()]
        if not results: return None
        pid = results[0]['id']
        time.sleep(0.6)  # Rate limit
        log = playergamelog.PlayerGameLog(
            player_id=pid,
            season=f"{YEAR-1}-{str(YEAR)[2:]}",
            season_type_all_star="Playoffs"
        ).get_data_frames()[0]
        if log.empty:
            log = playergamelog.PlayerGameLog(
                player_id=pid,
                season=f"{YEAR-1}-{str(YEAR)[2:]}",
            ).get_data_frames()[0]
        if log.empty: return None
        recent = log.head(10)
        avg_pts = round(recent["PTS"].mean(), 1)
        # MIN can be "34:25" or numeric
        def parse_min(m):
            try:
                if isinstance(m, str) and ":" in m: return float(m.split(":")[0])
                return float(m)
            except: return 0
        avg_min = round(sum(parse_min(m) for m in recent["MIN"])/len(recent), 1)
        under_rate = round((recent["PTS"] < recent["PTS"].mean()).mean()*100)
        return {"avg_pts":avg_pts,"avg_min":avg_min,"games":len(recent),"under_rate":under_rate}
    except Exception as e:
        print(f"  warn nba_api {player_name}: {e}"); return None

# ─── NFL: nfl_data_py ───
def fetch_nfl_player_stats(player_name):
    if not NFL_DATA: return None
    try:
        season = YEAR - 1  # Use last season (off-season now)
        df = nfl.import_weekly_data([season])
        if df is None or df.empty: return None
        name_lower = player_name.lower()
        mask = df["player_display_name"].str.lower().str.contains(name_lower.split()[-1], na=False)
        player_df = df[mask]
        if player_df.empty: return None
        recent = player_df.tail(8)
        stats = {}
        if "passing_yards" in recent.columns: stats["pass_yds"] = round(recent["passing_yards"].mean(), 1)
        if "rushing_yards" in recent.columns: stats["rush_yds"] = round(recent["rushing_yards"].mean(), 1)
        if "receiving_yards" in recent.columns: stats["rec_yds"] = round(recent["receiving_yards"].mean(), 1)
        if "passing_tds" in recent.columns: stats["pass_tds"] = round(recent["passing_tds"].mean(), 1)
        return stats if stats else None
    except Exception as e:
        print(f"  warn nfl_data {player_name}: {e}"); return None

# ─── WEATHER (Open-Meteo, free, no key) ───
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

# ─── GATHER ───
def gather():
    all_props, active = [], []
    mlb_stats, weather_cache, nfl_stats_cache = {}, {}, {}

    for sport, cfg in SPORTS.items():
        events = fetch_events(sport)
        if not events: continue
        active.append(f"{cfg['emoji']} {cfg['name']} ({len(events)})")

        # Load MLB stats once
        if sport == "baseball_mlb" and not mlb_stats:
            mlb_stats = fetch_mlb_stats()

        markets = ",".join(m[0] for m in cfg["markets"])
        for ev in events[:6]:
            data = fetch_props(sport, ev["id"], markets)
            if not data: continue
            home = ev.get("home_team","")
            wx = None
            if cfg["name"] == "MLB":
                if home not in weather_cache:
                    weather_cache[home] = fetch_weather(home)
                wx = weather_cache[home]

            for mk, label, mp, mo in cfg["markets"]:
                for p in extract(data, mk, label, mp, mo):
                    p["sport"] = cfg["name"]
                    p["emoji"] = cfg["emoji"]
                    p["game"]  = f"{ev['away_team']} @ {home}"
                    extra = []

                    if cfg["name"] == "MLB" and mlb_stats:
                        batter = match_batter(p["player"], mlb_stats)
                        if batter:
                            if batter.get("barrel"): extra.append(f"Barrel {batter['barrel']}%")
                            if batter.get("iso"):    extra.append(f"ISO {batter['iso']}")
                            if batter.get("hardhit"):extra.append(f"HardHit {batter['hardhit']}%")
                            if batter.get("xslg"):   extra.append(f"xSLG {batter['xslg']}")
                    if wx: extra.append(f"Wetter: {wx}")
                    if extra: p["enrichment"] = " | ".join(extra)

                    all_props.append(p)

    # NBA enrichment skipped - stats.nba.com blocks CI/CD environments
    # nba_api works locally but times out on GitHub Actions

    # NFL enrichment (off-season: last season data)
    nfl_props = [p for p in all_props if p["sport"]=="NFL"][:8]
    for p in nfl_props:
        if p["player"] not in nfl_stats_cache:
            nfl_stats_cache[p["player"]] = fetch_nfl_player_stats(p["player"])
        ns = nfl_stats_cache[p["player"]]
        if ns:
            tags = [f"{k}:{v}" for k,v in ns.items() if v]
            p["enrichment"] = p.get("enrichment","") + " | " + " ".join(tags[:3])

    print(f"  Active: {', '.join(active) if active else 'NONE'}")
    print(f"  Total props enriched: {len(all_props)}")
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
    for p in props[:50]:
        ln = f"- {p['emoji']} {p['player']} ({p['game']}) {p['market']} @ {p['odds']}"
        if p.get("enrichment"): ln += f"  [{p['enrichment']}]"
        lines.append(ln)

    prompt = f"""You are an ELITE sharp sports betting analyst. Below are REAL player props with REAL odds for games in the next 12 hours, enriched with advanced stats.

PROPS:
{chr(10).join(lines)}

Select ONLY genuine VALUE picks — where stats show edge the odds don't reflect. QUALITY OVER QUANTITY (2-8 picks).

VALUE CRITERIA:
- ⚾ MLB HR: high Barrel%/ISO/HardHit%, HR-friendly weather, weak pitcher vs batter handedness
- 🏀 NBA/WNBA: minutes/usage vs line, sell-high regression, defensive matchup (Wembanyama = rim protection)
- 🏈 NFL: matchup vs defensive weakness, recent yardage form
COMBO STRATEGY (like NETRATTLER — probability-first):
- Kombis müssen aus den WAHRSCHEINLICHSTEN Legs gebaut werden, nicht den höchsten Odds
- Kombiniere Spieler mit höchster Hit-Rate: hohe Barrel%/ISO für HR, klare Minuten-Edge für NBA
- NIEMALS 2 Longshots (>6.0) in einem Kombi — mindestens 1 Leg muss solid sein (@3.0-4.5)
- Ziel: realistische Gewinn-Chance, nicht maximale Odds
- Cross-sport combos erlaubt: z.B. solider HR @4.0 + sicherer NBA Points @2.0
- Bewerte jeden Leg nach: Trefferquote × Quote = Expected Value

Write sharp 2-sentence analysis per pick citing actual data.
KOMBI REGELN — 2 Typen wie JK:

TYPE 1 — PROBABILITY KOMBIS (2-Leg, 3 Stück):
- Aus den wahrscheinlichsten Singles (@3.0-5.0)
- Ziel-Kombi-Quote: @8-20
- Stake: 0.5u — reale Gewinnchance

TYPE 2 — LOTTERY BIGS (3-Leg, 2 Stück):
- Mix: 1-2 solide Legs + 1-2 Longshots (@6.0-10.0)
- Ziel-Kombi-Quote: @40-150+
- Stake: 0.25u — kleiner Einsatz, grosse Auszahlung möglich

Staking Singles: sicherer Single 1u, spekulativer Longshot 0.25u

Include "team" = short code + nickname (MLB: "ATL Braves", NBA: "OKC Thunder", NFL: "KC Chiefs").
Return ONLY valid JSON (no markdown), empty array [] if no value:
[
{{"type":"single","emoji":"⚾","player":"Name","team":"ATL Braves","market":"Home Run","odds":5.5,"stake":1,"analysis":"sharp data-driven reasoning"}},
{{"type":"kombi2","legs":["ATL Name HR","PHI Name HR"],"odds":12.0,"stake":0.5}},
{{"type":"big","legs":["L1","L2","L3"],"odds":40.0,"stake":0.25}}
]"""

    for i, key in enumerate(GEMINI_KEYS):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
            r = requests.post(url, json={"contents":[{"parts":[{"text":prompt}]}],
                "generationConfig":{"temperature":0.7,"maxOutputTokens":2048}}, timeout=60)
            if r.status_code == 429:
                print(f"  Gemini key {i+1} rate limited, next...")
                time.sleep(3); continue
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
    # All Gemini keys failed → try Groq
    if GROQ_KEYS:
        print("  All Gemini keys failed → trying Groq fallback...")
        return groq_analyze(prompt)
    return None

# ─── POST (Format B — bet365 style) ───
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
    post += "📊 ANALYZE. TARGET. CASH. 🎯\n@prophunter"
    return post

# ─── DEDUP ───
def already_posted_today():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    posted = set()
    if os.path.exists("picks_history.json"):
        try:
            for entry in json.load(open("picks_history.json")):
                if entry["date"] == today:
                    for p in entry.get("picks",[]): posted.add(p.get("player","").lower())
        except Exception: pass
    return posted

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

# ─── TELEGRAM ───
def send_telegram(text):
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id":TG_CHAT,"text":text}, timeout=30)
        print("  Telegram: OK" if r.status_code==200 else f"  Telegram: {r.text[:120]}")
    except Exception as e: print(f"  Telegram error: {e}")

# ─── MAIN ───
def main():
    print("="*40)
    print("PROP HUNTER starting...")
    print(f"  pybaseball={PYBASEBALL} | nba_api={NBA_API} | nfl_data_py={NFL_DATA}")
    print("Fetching games + odds + stats + weather (next 12h)...")
    props = gather()
    if not props:
        print("  No props found. Exiting (no post)."); return
    print("Gemini value analysis...")
    picks = gemini_analyze(props)
    if not picks:
        print("  No value found. Exiting (no post)."); return
    posted = already_posted_today()
    if posted:
        before = len([p for p in picks if p.get("type")=="single"])
        picks = [p for p in picks if not (p.get("type")=="single" and p.get("player","").lower() in posted)]
        after = len([p for p in picks if p.get("type")=="single"])
        if before != after: print(f"  Dedup: {before}→{after} singles")
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
