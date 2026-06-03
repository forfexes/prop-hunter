#!/usr/bin/env python3
"""
PROP HUNTER — Automated MLB/NBA/NFL Player Props Tipster Bot
Value-only picks. Runs via GitHub Actions, posts to Telegram.
Uses Gemini (free) + Baseball Savant + Open-Meteo weather + NBA/NFL data.

Secrets (GitHub Settings > Secrets):
- ODDS_API_KEY
- GEMINI_API_KEY  (comma-separated for rotation)
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
"""

import os
import io
import csv
import json
import requests
from datetime import datetime, timedelta, timezone

ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
GEMINI_KEYS = [k.strip() for k in os.environ.get("GEMINI_API_KEY", "").split(",") if k.strip()]
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

ODDS_BASE = "https://api.the-odds-api.com/v4"
BOOKMAKERS = "bet365,draftkings,fanduel,betmgm,williamhill,pinnacle"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
YEAR = datetime.now(timezone.utc).year

# MLB ballpark coordinates for weather (home team -> lat,lon, outdoor?)
BALLPARKS = {
    "Arizona Diamondbacks": (33.4455, -112.0667, False),
    "Atlanta Braves": (33.8908, -84.4678, True),
    "Baltimore Orioles": (39.2839, -76.6217, True),
    "Boston Red Sox": (42.3467, -71.0972, True),
    "Chicago Cubs": (41.9484, -87.6553, True),
    "Chicago White Sox": (41.8299, -87.6338, True),
    "Cincinnati Reds": (39.0975, -84.5069, True),
    "Cleveland Guardians": (41.4962, -81.6852, True),
    "Colorado Rockies": (39.7559, -104.9942, True),
    "Detroit Tigers": (42.3390, -83.0485, True),
    "Houston Astros": (29.7572, -95.3556, False),
    "Kansas City Royals": (39.0517, -94.4803, True),
    "Los Angeles Angels": (33.8003, -117.8827, True),
    "Los Angeles Dodgers": (34.0739, -118.2400, True),
    "Miami Marlins": (25.7781, -80.2197, False),
    "Milwaukee Brewers": (43.0280, -87.9712, False),
    "Minnesota Twins": (44.9817, -93.2776, True),
    "New York Mets": (40.7571, -73.8458, True),
    "New York Yankees": (40.8296, -73.9262, True),
    "Oakland Athletics": (38.7600, -121.2700, True),
    "Athletics": (38.7600, -121.2700, True),
    "Philadelphia Phillies": (39.9061, -75.1665, True),
    "Pittsburgh Pirates": (40.4469, -80.0057, True),
    "San Diego Padres": (32.7073, -117.1566, True),
    "San Francisco Giants": (37.7786, -122.3893, True),
    "Seattle Mariners": (47.5914, -122.3325, False),
    "St. Louis Cardinals": (38.6226, -90.1928, True),
    "Tampa Bay Rays": (27.7682, -82.6534, False),
    "Texas Rangers": (32.7473, -97.0847, False),
    "Toronto Blue Jays": (43.6414, -79.3894, False),
    "Washington Nationals": (38.8730, -77.0074, True),
}

SPORTS = {
    "baseball_mlb": {"emoji": "⚾", "name": "MLB",
        "markets": [("batter_home_runs", "Home Run", None, 3.5)]},
    "basketball_nba": {"emoji": "🏀", "name": "NBA",
        "markets": [
            ("player_points_alternate", "Points", 25, 3.5),
            ("player_double_double", "Double Double", None, 3.0),
            ("player_triple_double", "Triple Double", None, 6.0)]},
    "americanfootball_nfl": {"emoji": "🏈", "name": "NFL",
        "markets": [
            ("player_anytime_td", "Anytime TD", None, 2.5),
            ("player_pass_tds_alternate", "Pass TDs", None, 3.0),
            ("player_rush_yds_alternate", "Rush Yds", None, 3.0),
            ("player_reception_yds_alternate", "Rec Yds", None, 3.0)]},
}

def time_window():
    now = datetime.now(timezone.utc)
    return now, now + timedelta(hours=12)

# ─── ODDS ───
def fetch_events(sport):
    now, end = time_window()
    try:
        r = requests.get(f"{ODDS_BASE}/sports/{sport}/events", params={
            "apiKey": ODDS_API_KEY, "dateFormat": "iso",
            "commenceTimeFrom": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "commenceTimeTo": end.strftime("%Y-%m-%dT%H:%M:%SZ")}, timeout=30)
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        print(f"  warn events {sport}: {e}"); return []

def fetch_props(sport, eid, markets):
    try:
        r = requests.get(f"{ODDS_BASE}/sports/{sport}/events/{eid}/odds", params={
            "apiKey": ODDS_API_KEY, "regions": "us,eu,uk", "markets": markets,
            "oddsFormat": "decimal", "bookmakers": BOOKMAKERS}, timeout=30)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def extract(data, mkey, label, min_pt, min_odds):
    out = {}
    for bm in (data.get("bookmakers") or []):
        for mkt in (bm.get("markets") or []):
            if mkt.get("key") != mkey: continue
            for o in (mkt.get("outcomes") or []):
                desc, pt = o.get("description", ""), o.get("point")
                if desc and desc not in ("Over", "Yes"): continue
                if min_pt and pt and pt < min_pt: continue
                name = o.get("name") or o.get("participant", "")
                if not name or name in ("Over","Under","Yes","No"):
                    name = o.get("description","") or name
                if not name: continue
                k = f"{name}|{pt or ''}"
                out.setdefault(k, {"player": name, "point": pt, "prices": []})
                out[k]["prices"].append(o.get("price", 0))
    res = []
    for v in out.values():
        avg = sum(v["prices"])/len(v["prices"])
        if avg >= min_odds:
            lbl = label
            if v["point"] and label in ("Points","Rush Yds","Rec Yds","Pass TDs"):
                lbl = f"{int(v['point'])}+ {label}"
            res.append({"player": v["player"], "odds": round(avg,2), "market": lbl})
    return res

# ─── BASEBALL SAVANT ───
def fetch_savant():
    try:
        r = requests.get("https://baseballsavant.mlb.com/leaderboard/percentile-rankings",
            params={"type":"batter","year":str(YEAR),"csv":"true"}, headers=UA, timeout=30)
        # Fallback to previous year if current year empty
        if r.status_code == 200 and len(r.text) < 200:
            r = requests.get("https://baseballsavant.mlb.com/leaderboard/percentile-rankings",
                params={"type":"batter","year":str(YEAR-1),"csv":"true"}, headers=UA, timeout=30)
        if r.status_code != 200:
            print(f"  warn savant {r.status_code}"); return {}
        out = {}
        for row in csv.DictReader(io.StringIO(r.text)):
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
        print(f"  Savant: {len(out)} profiles"); return out
    except Exception as e:
        print(f"  warn savant: {e}"); return {}

def match_savant(player, savant):
    pl = player.lower()
    if pl in savant: return savant[pl]
    last = pl.split()[-1] if pl.split() else pl
    for n, d in savant.items():
        if n.split() and n.split()[-1] == last: return d
    return None

# ─── WEATHER (Open-Meteo, free, no key) ───
def fetch_weather(home_team):
    park = BALLPARKS.get(home_team)
    if not park: return None
    lat, lon, outdoor = park
    if not outdoor: return "Dome (kein Wettereinfluss)"
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "hourly": "temperature_2m,wind_speed_10m,wind_direction_10m",
            "forecast_days": 1}, timeout=20)
        if r.status_code != 200: return None
        h = r.json().get("hourly", {})
        temps = h.get("temperature_2m", [])
        winds = h.get("wind_speed_10m", [])
        if temps and winds:
            # Use evening hour (~index 19 = 19:00 local approx)
            i = min(22, len(temps)-1)
            t, w = temps[i], winds[i]
            note = f"{t:.0f}°C, Wind {w:.0f}km/h"
            if t >= 24 and w >= 15: note += " (HR-freundlich)"
            elif t < 12: note += " (HR-hemmend)"
            return note
    except Exception:
        return None
    return None

# ─── GATHER ───
def gather():
    all_props, active = [], []
    savant, weather_cache = {}, {}
    for sport, cfg in SPORTS.items():
        events = fetch_events(sport)
        if not events: continue
        active.append(f"{cfg['emoji']} {cfg['name']} ({len(events)})")
        if sport == "baseball_mlb" and not savant:
            savant = fetch_savant()
        markets = ",".join(m[0] for m in cfg["markets"])
        for ev in events[:6]:
            data = fetch_props(sport, ev["id"], markets)
            if not data: continue
            home = ev.get("home_team", "")
            wx = None
            if cfg["name"] == "MLB":
                if home not in weather_cache:
                    weather_cache[home] = fetch_weather(home)
                wx = weather_cache[home]
            for mk, label, mp, mo in cfg["markets"]:
                for p in extract(data, mk, label, mp, mo):
                    p["sport"], p["emoji"] = cfg["name"], cfg["emoji"]
                    p["game"] = f"{ev['away_team']} @ {home}"
                    if cfg["name"] == "MLB":
                        if wx: p["weather"] = wx
                        if savant:
                            sv = match_savant(p["player"], savant)
                            if sv:
                                t = []
                                if sv.get("barrel"): t.append(f"Barrel {sv['barrel']}%ile")
                                if sv.get("xslg"): t.append(f"xSLG {sv['xslg']}%ile")
                                if sv.get("hardhit"): t.append(f"HardHit {sv['hardhit']}%ile")
                                if sv.get("xiso"): t.append(f"ISO {sv['xiso']}%ile")
                                if t: p["savant"] = ", ".join(t)
                    all_props.append(p)
    print(f"  Active: {', '.join(active) if active else 'NONE'}")
    return all_props

# ─── GEMINI (value-only) ───
def gemini_analyze(props):
    if not props or not GEMINI_KEYS: return None
    lines = []
    for p in props[:50]:
        ln = f"- {p['emoji']} {p['player']} ({p['game']}) {p['market']} @ {p['odds']}"
        extra = []
        if p.get("savant"): extra.append(f"STATCAST: {p['savant']}")
        if p.get("weather"): extra.append(f"WETTER: {p['weather']}")
        if extra: ln += "  [" + " | ".join(extra) + "]"
        lines.append(ln)
    props_text = "\n".join(lines)

    prompt = f"""You are an ELITE sharp sports betting analyst. Below are REAL player props with REAL odds for games in the next 12 hours. MLB includes STATCAST percentiles + WEATHER.

PROPS:
{props_text}

Select ONLY genuine VALUE picks - spots where data shows an edge the odds don't reflect. QUALITY OVER QUANTITY. If only 2 good spots exist, return 2. If 7, return 7. Never force picks.

VALUE CRITERIA:
- MLB HR: elite Barrel%/xSLG/ISO (top 15%) + good pitcher matchup + HR-friendly weather
- NBA: clear minutes/usage/matchup edge, or sell-high regression spot
- NFL: matchup advantage + form

For each: sharp 2-sentence analysis citing the data.
Build 2-leg combos only if you have 4+ value singles; 3-leg only if 5+.

Staking: high-confidence 1u, speculative high-odds 0.25u, 2-leg 0.5u, 3-leg 0.25u.

Include "team" = the player's team as short code + nickname for ALL sports:
- MLB: "ATL Braves", "PHI Phillies", "TB Rays", "LAD Dodgers"
- NBA: "OKC Thunder", "BOS Celtics", "LAL Lakers", "DEN Nuggets"
- NFL: "KC Chiefs", "BUF Bills", "DAL Cowboys", "SF 49ers"
Use the correct emoji per sport: ⚾ MLB, 🏀 NBA, 🏈 NFL.

Return ONLY valid JSON (no markdown). If NO value found, return []:
[
{{"type":"single","emoji":"⚾","player":"Acuna Jr.","team":"ATL Braves","market":"Home Run","odds":5.5,"stake":1,"analysis":"sharp reasoning citing data"}},
{{"type":"kombi2","legs":["ATL Acuna HR","PHI Schwarber HR"],"odds":12.0,"stake":0.5}},
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
            return json.loads(text[s:e])
        except Exception as ex:
            print(f"  warn gemini {ex}, next..."); continue
    return None

# ─── POST ───
def build_post(picks):
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    singles = [p for p in picks if p.get("type")=="single"]
    kombis = [p for p in picks if p.get("type")=="kombi2"]
    bigs = [p for p in picks if p.get("type")=="big"]
    post = f"🎯 PROP HUNTER — {today}\n\n"
    if singles:
        post += "📋 VALUE SINGLES:\n\n"
        for p in singles:
            team = p.get("team", "")
            post += f"{p.get('emoji','⚾')} {team} — {p['player']}\n"
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

def send_telegram(text):
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=30)
        print("  posted OK" if r.status_code==200 else f"  TG error: {r.text[:120]}")
    except Exception as e:
        print(f"  TG error: {e}")

def save_picks(picks):
    """Append today's picks to history for later evaluation."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history = []
    if os.path.exists("picks_history.json"):
        try:
            with open("picks_history.json") as f:
                history = json.load(f)
        except Exception:
            history = []
    # Only store singles + flatten for evaluation
    entry = {"date": today, "evaluated": False, "picks": []}
    for p in picks:
        if p.get("type") == "single":
            entry["picks"].append({
                "player": p.get("player", ""),
                "team": p.get("team", ""),
                "market": p.get("market", ""),
                "odds": p.get("odds", 0),
                "stake": p.get("stake", 1),
                "sport": "MLB" if p.get("emoji") == "⚾" else "NBA" if p.get("emoji") == "🏀" else "NFL",
                "result": None,
            })
    history.append(entry)
    with open("picks_history.json", "w") as f:
        json.dump(history, f, indent=2)
    print(f"  Saved {len(entry['picks'])} picks to history")

def main():
    print("PROP HUNTER starting...")
    print("Fetching games + odds + Statcast + weather (next 12h)...")
    props = gather()
    print(f"  Found {len(props)} props")
    if not props:
        print("  No games in window. Exiting."); return
    print("Gemini value analysis...")
    picks = gemini_analyze(props)
    if not picks:
        print("  No value found today. Exiting (no post).")
        return
    print(f"  {len(picks)} value picks")
    post = build_post(picks)
    print("\n"+"="*40+"\n"+post+"\n"+"="*40+"\n")
    send_telegram(post)
    save_picks(picks)
    print("Done!")

if __name__ == "__main__":
    main()
