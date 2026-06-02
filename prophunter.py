#!/usr/bin/env python3
"""
PROP HUNTER — Automated MLB/NBA Player Props Tipster Bot
Runs via GitHub Actions, posts to Telegram automatically.

Workflow:
1. Fetch today's games (next 12h) from the-odds-api.com
2. Fetch player props odds (Betfair/Pinnacle)
3. AI analysis (Anthropic) picks best value spots
4. Post to Telegram @prophunter

Secrets needed (GitHub Settings > Secrets):
- ODDS_API_KEY
- ANTHROPIC_API_KEY
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
"""

import os
import json
import requests
from datetime import datetime, timedelta, timezone

# ─── CONFIG ───
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

INCLUDE_NBA = os.environ.get("INCLUDE_NBA", "false").lower() == "true"

ODDS_BASE = "https://api.the-odds-api.com/v4"
BOOKMAKERS = "betfair_ex_eu,betfair_ex_uk,pinnacle"

# ─── TIME WINDOW (next 12h) ───
def time_window():
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=12)
    return now, end

# ─── FETCH GAMES IN NEXT 12H ───
def fetch_events(sport):
    now, end = time_window()
    url = f"{ODDS_BASE}/sports/{sport}/events"
    params = {
        "apiKey": ODDS_API_KEY,
        "dateFormat": "iso",
        "commenceTimeFrom": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commenceTimeTo": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  ⚠️ Events fetch error ({sport}): {e}")
        return []

# ─── FETCH PLAYER PROPS FOR AN EVENT ───
def fetch_props(sport, event_id, markets):
    url = f"{ODDS_BASE}/sports/{sport}/events/{event_id}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu,uk",
        "markets": markets,
        "oddsFormat": "decimal",
        "bookmakers": BOOKMAKERS,
    }
    try:
        r = requests.get(url, params=params, timeout=30)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as e:
        print(f"  ⚠️ Props fetch error: {e}")
        return None

# ─── EXTRACT BEST ODDS PER PLAYER ───
def extract_props(data, market_key, label, min_odds=3.5, min_point=None):
    """Returns list of {player, odds, market} for Over outcomes."""
    out = {}
    for bm in (data.get("bookmakers") or []):
        for mkt in (bm.get("markets") or []):
            if mkt.get("key") != market_key:
                continue
            for o in (mkt.get("outcomes") or []):
                desc = o.get("description", "")
                point = o.get("point")
                # Only "Over" outcomes (or yes for DD/TD)
                if market_key.endswith("_alternate") or "points" in market_key:
                    if desc and desc != "Over":
                        continue
                    if min_point and point and point < min_point:
                        continue
                name = o.get("name") or o.get("participant", "")
                if not name:
                    continue
                price = o.get("price", 0)
                key = f"{name}|{point or ''}"
                if key not in out:
                    out[key] = {"player": name, "point": point, "prices": []}
                out[key]["prices"].append(price)
    results = []
    for v in out.values():
        avg = sum(v["prices"]) / len(v["prices"])
        if avg >= min_odds:
            mkt_label = label
            if v["point"] and "Points" in label:
                mkt_label = f"{int(v['point'])}+ {label}"
            results.append({
                "player": v["player"],
                "odds": round(avg, 2),
                "market": mkt_label,
            })
    return results

# ─── GATHER ALL PROPS ───
def gather_props():
    props = {"mlb": [], "nba": []}

    # MLB Home Runs
    mlb_events = fetch_events("baseball_mlb")
    print(f"  ⚾ MLB events in window: {len(mlb_events)}")
    for ev in mlb_events[:8]:
        data = fetch_props("baseball_mlb", ev["id"], "batter_home_runs")
        if data:
            hr = extract_props(data, "batter_home_runs", "Home Run", min_odds=3.5)
            for p in hr:
                p["sport"] = "MLB"
                p["game"] = f"{ev['away_team']} @ {ev['home_team']}"
                p["commence"] = ev["commence_time"]
            props["mlb"].extend(hr)

    # NBA (optional)
    if INCLUDE_NBA:
        nba_events = fetch_events("basketball_nba")
        print(f"  🏀 NBA events in window: {len(nba_events)}")
        for ev in nba_events[:4]:
            for mkt, label, mp in [
                ("player_points_alternate", "Points", 25),
                ("player_double_double", "Double Double", None),
                ("player_triple_double", "Triple Double", None),
            ]:
                data = fetch_props("basketball_nba", ev["id"], mkt)
                if data:
                    pp = extract_props(data, mkt, label, min_odds=3.5, min_point=mp)
                    for p in pp:
                        p["sport"] = "NBA"
                        p["game"] = f"{ev['away_team']} @ {ev['home_team']}"
                        p["commence"] = ev["commence_time"]
                    props["nba"].extend(pp)

    return props

# ─── AI ANALYSIS ───
def ai_analyze(props):
    all_props = props["mlb"] + props["nba"]
    if not all_props:
        return None

    props_text = "\n".join([
        f"- {p['player']} ({p['game']}) {p['market']} @ {p['odds']}"
        for p in all_props[:40]
    ])

    prompt = f"""You are a sharp sports betting analyst. Below are REAL player props with REAL odds for games in the next 12 hours.

AVAILABLE PROPS (real odds from Betfair/Pinnacle):
{props_text}

Pick the 5 BEST VALUE singles from this list. Consider:
- Recent form, matchup, ballpark factors (Coors Field = HR boost)
- For NBA: minutes, usage, defensive matchup, sell-high/regression spots
- Mix of confidence levels

Then build 3 two-leg combos and 2 three-leg combos from your singles.

Staking (confidence-based):
- High-confidence singles: 1u
- Speculative high-odds singles: 0.25u
- 2-leg combos: 0.5u
- 3-leg combos: 0.25u

Return ONLY JSON (no markdown):
[
  {{"type":"single","player":"Name","game":"Game","market":"Market","odds":5.5,"stake":1,"analysis":"2-sentence sharp reasoning"}},
  {{"type":"kombi2","legs":["Player1 Market1","Player2 Market2"],"odds":12.0,"stake":0.5}},
  {{"type":"big","legs":["P1 M1","P2 M2","P3 M3"],"odds":40.0,"stake":0.25}}
]"""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        text = "".join([b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"])
        text = text.replace("```json", "").replace("```", "").strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        return json.loads(text[start:end])
    except Exception as e:
        print(f"  ⚠️ AI error: {e}")
        return None

# ─── BUILD TELEGRAM POST ───
def build_post(picks):
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    singles = [p for p in picks if p["type"] == "single"]
    kombis = [p for p in picks if p["type"] == "kombi2"]
    bigs = [p for p in picks if p["type"] == "big"]

    post = f"🎯 PROP HUNTER — {today}\n\n"
    post += "📋 SINGLES:\n"
    for p in singles:
        icon = "🏀" if "NBA" in p.get("game", "") else "⚾"
        post += f"{icon} {p['player']} {p['market']} @{p['odds']:.2f} → {p['stake']}u\n"
        if p.get("analysis"):
            post += f"   💡 {p['analysis']}\n"
    if kombis:
        post += "\n🔥 2-LEG KOMBIS:\n"
        for p in kombis:
            post += f"• {' + '.join(p['legs'])} @{p['odds']:.2f} → {p['stake']}u\n"
    if bigs:
        post += "\n💣 BIG KOMBIS:\n"
        for p in bigs:
            post += f"• {' + '.join(p['legs'])} @{p['odds']:.2f} → {p['stake']}u\n"
    post += "\n📊 ANALYZE. TARGET. CASH. 🎯\n@prophunter"
    return post

# ─── SEND TO TELEGRAM ───
def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=30)
        if r.status_code == 200:
            print("  ✅ Posted to Telegram")
        else:
            print(f"  ❌ Telegram error: {r.text[:100]}")
    except Exception as e:
        print(f"  ❌ Telegram send error: {e}")

# ─── MAIN ───
def main():
    print("🎯 PROP HUNTER starting...")
    print(f"  NBA included: {INCLUDE_NBA}")

    print("📡 Fetching games + odds...")
    props = gather_props()
    total = len(props["mlb"]) + len(props["nba"])
    print(f"  Found {total} props ({len(props['mlb'])} MLB, {len(props['nba'])} NBA)")

    if total == 0:
        print("  No games in next 12h window. Exiting.")
        return

    print("🤖 AI analysis...")
    picks = ai_analyze(props)
    if not picks:
        print("  AI returned no picks. Exiting.")
        return

    print(f"  Generated {len(picks)} picks")

    post = build_post(picks)
    print("\n" + "=" * 40)
    print(post)
    print("=" * 40 + "\n")

    send_telegram(post)
    print("✅ Done!")

if __name__ == "__main__":
    main()
