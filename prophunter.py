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
    from pybaseball import batting_stats as pb_batting
    from pybaseball import playerid_lookup
    PYBASEBALL = True
    print("  pybaseball OK")
except Exception:
    PYBASEBALL = False

try:
    from nba_api.stats.static import players as nba_db
    from nba_api.stats.endpoints import playergamelog, playerdashboardbygeneralsplits
    NBA_API = True
    print("  nba_api OK")
except Exception:
    NBA_API = False

try:
    import nfl_data_py as nfl
    NFL_DATA = True
    print("  nfl_data_py OK")
except Exception:
    NFL_DATA = False

# ─── CONFIG ───
ODDS_API_KEY   = os.environ.get("ODDS_API_KEY", "")
GEMINI_KEYS    = [k.strip() for k in os.environ.get("GEMINI_API_KEY","").split(",") if k.strip()]
TG_TOKEN       = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT        = os.environ.get("TELEGRAM_CHAT_ID", "")

ODDS_BASE  = "https://api.the-odds-api.com/v4"
BOOKMAKERS = "bet365,draftkings,fanduel,betmgm,williamhill,pinnacle"
UA         = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
YEAR       = datetime.now(timezone.utc).year

SPORTS = {
    "baseball_mlb": {"emoji":"⚾","name":"MLB",
        "markets":[("batter_home_runs","Home Run",None,3.5)]},
    "basketball_nba": {"emoji":"🏀","name":"NBA",
        "markets":[
            ("player_points_alternate","Points",25,3.5),
            ("player_double_double","Double Double",None,3.0),
            ("player_triple_double","Triple Double",None,6.0)]},
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
    for bm in (data.get("bookmakers") or []):
        for mkt in (bm.get("markets") or []):
            if mkt.get("key") != mkey: continue
            for o in (mkt.get("outcomes") or []):
                desc, pt = o.get("description",""), o.get("point")
                if desc and desc not in ("Over","Yes"): continue
                if min_pt and pt and pt < min_pt: continue
                name = o.get("name") or o.get("participant","")
                if not name or name in ("Over","Under","Yes","No"):
                    name = o.get("description","") or name
                if not name: continue
                k = f"{name}|{pt or ''}"
                out.setdefault(k,{"player":name,"point":pt,"prices":[]})
                out[k]["prices"].append(o.get("price",0))
    res = []
    for v in out.values():
        avg = sum(v["prices"])/len(v["prices"])
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
        print(f"  warn pybaseball: {e}"); return {}

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

    # NBA enrichment (only top candidates to save API calls)
    nba_props = [p for p in all_props if p["sport"]=="NBA"][:10]
    for p in nba_props:
        ns = fetch_nba_player_stats(p["player"])
        if ns:
            tags = [f"Ø{ns['avg_pts']}Pts/{ns['games']}G",f"Ø{ns['avg_min']}Min"]
            p["enrichment"] = p.get("enrichment","") + " | " + " ".join(tags)

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
- MLB HR: high Barrel% (>10%), high ISO (>0.200), good HardHit%, HR-friendly weather, weak pitcher
- NBA: low minutes projection vs line, sell-high regression, tough defensive matchup (cite avg pts vs line)
- NFL: matchup advantage vs defensive weakness, recent form trend

Write sharp 2-sentence analysis per pick citing actual data.
Build 2-leg combos if ≥4 value singles; 3-leg only if ≥5.
Staking: confident 1u, speculative 0.25u, 2-leg 0.5u, 3-leg 0.25u.

Include "team" = short code + nickname (MLB: "ATL Braves", NBA: "OKC Thunder", NFL: "KC Chiefs").
Return ONLY valid JSON (no markdown), empty array [] if no value:
[
{{"type":"single","emoji":"⚾","player":"Name","team":"ATL Braves","market":"Home Run","odds":5.5,"stake":1,"analysis":"sharp data-driven reasoning"}},
{{"type":"kombi2","legs":["ATL Name HR","PHI Name HR"],"odds":12.0,"stake":0.5}},
{{"type":"big","legs":["L1","L2","L3"],"odds":40.0,"stake":0.25}}
]"""

    for key in GEMINI_KEYS:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
            r = requests.post(url, json={"contents":[{"parts":[{"text":prompt}]}],
                "generationConfig":{"temperature":0.7,"maxOutputTokens":2048}}, timeout=60)
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
    entry = {"date":today,"evaluated":False,"picks":[]}
    for p in picks:
        if p.get("type")=="single":
            entry["picks"].append({
                "player":p.get("player",""),"team":p.get("team",""),
                "market":p.get("market",""),"odds":p.get("odds",0),
                "stake":p.get("stake",1),"sport":"MLB" if p.get("emoji")=="⚾" else "NBA" if p.get("emoji")=="🏀" else "NFL",
                "result":None})
    history.append(entry)
    json.dump(history, open("picks_history.json","w"), indent=2)
    print(f"  Saved {len(entry['picks'])} picks")

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
