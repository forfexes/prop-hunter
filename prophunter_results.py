#!/usr/bin/env python3
"""
PROP HUNTER — Results Evaluator
Checks yesterday's picks against real game results, posts Auswertung to Telegram.
Runs morning via GitHub Actions.

Data sources (free, no key):
- MLB Stats API (statsapi.mlb.com) for HR results
"""

import os
import json
import requests
from datetime import datetime, timedelta, timezone

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
UA = {"User-Agent": "Mozilla/5.0"}

# ─── MLB: get HR hitters for a date ───
def mlb_hr_hitters(date_str):
    """Return set of player names who hit a HR on date_str (YYYY-MM-DD)."""
    hitters = {}
    try:
        sched = requests.get("https://statsapi.mlb.com/api/v1/schedule",
            params={"sportId": 1, "date": date_str, "hydrate": "none"}, timeout=30).json()
        game_ids = []
        for d in sched.get("dates", []):
            for g in d.get("games", []):
                game_ids.append(g["gamePk"])
        for gid in game_ids:
            try:
                box = requests.get(f"https://statsapi.mlb.com/api/v1/game/{gid}/boxscore", timeout=30).json()
                for side in ("home", "away"):
                    players = box.get("teams", {}).get(side, {}).get("players", {})
                    for pdata in players.values():
                        name = pdata.get("person", {}).get("fullName", "")
                        hr = pdata.get("stats", {}).get("batting", {}).get("homeRuns", 0)
                        if name and hr and int(hr) > 0:
                            hitters[name.lower()] = int(hr)
            except Exception:
                continue
    except Exception as e:
        print(f"  warn mlb results: {e}")
    return hitters

def name_match(player, hitters):
    pl = player.lower()
    if pl in hitters:
        return True
    last = pl.split()[-1] if pl.split() else pl
    for name in hitters:
        if name.split() and name.split()[-1] == last and pl.split()[0][:3] in name:
            return True
    return False

# ─── EVALUATE ───
def evaluate():
    if not os.path.exists("picks_history.json"):
        print("No picks history."); return None
    with open("picks_history.json") as f:
        history = json.load(f)

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    target = None
    for entry in history:
        if entry["date"] == yesterday and not entry.get("evaluated"):
            target = entry
            break
    if not target:
        print(f"No unevaluated picks for {yesterday}"); return None

    # Get MLB HR results for that date
    hr_hitters = mlb_hr_hitters(yesterday)
    print(f"  MLB HR hitters {yesterday}: {len(hr_hitters)}")

    results = []
    for p in target["picks"]:
        if p["sport"] == "MLB" and "Home Run" in p["market"]:
            won = name_match(p["player"], hr_hitters)
            p["result"] = "won" if won else "lost"
        else:
            # NBA/NFL evaluation not yet automated -> mark pending
            p["result"] = "pending"
        results.append(p)

    target["evaluated"] = True
    with open("picks_history.json", "w") as f:
        json.dump(history, f, indent=2)
    return target

# ─── BUILD RESULTS POST ───
def build_results_post(entry, history):
    date_disp = datetime.strptime(entry["date"], "%Y-%m-%d").strftime("%d.%m.%Y")
    picks = [p for p in entry["picks"] if p["result"] in ("won", "lost")]
    if not picks:
        return None

    won = [p for p in picks if p["result"] == "won"]
    lost = [p for p in picks if p["result"] == "lost"]
    net = sum((p["odds"] - 1) * p["stake"] for p in won) - sum(p["stake"] for p in lost)

    post = f"📊 PROP HUNTER — Auswertung {date_disp}\n\n"
    for p in picks:
        emoji = "⚾" if p["sport"] == "MLB" else "🏀" if p["sport"] == "NBA" else "🏈"
        if p["result"] == "won":
            pl = f"+{(p['odds']-1)*p['stake']:.2f}u"
            post += f"✅ {emoji} {p['team']} — {p['player']} @{p['odds']:.2f} → {pl}\n"
        else:
            post += f"❌ {emoji} {p['team']} — {p['player']} @{p['odds']:.2f} → -{p['stake']}u\n"

    post += "\n━━━━━━━━━━\n"
    post += f"📊 Heute: {len(won)}/{len(picks)} ({round(len(won)/len(picks)*100)}%) · {'+' if net>=0 else ''}{net:.2f}u\n"

    # Monthly + all-time stats
    this_month = entry["date"][:7]  # YYYY-MM
    m_won = m_lost = 0; m_net = m_staked = 0.0
    a_won = a_lost = 0; a_net = a_staked = 0.0
    for e in history:
        is_month = e["date"][:7] == this_month
        for p in e.get("picks", []):
            r = p.get("result")
            if r == "won":
                gain = (p["odds"]-1)*p["stake"]
                a_won += 1; a_net += gain; a_staked += p["stake"]
                if is_month: m_won += 1; m_net += gain; m_staked += p["stake"]
            elif r == "lost":
                a_lost += 1; a_net -= p["stake"]; a_staked += p["stake"]
                if is_month: m_lost += 1; m_net -= p["stake"]; m_staked += p["stake"]

    month_name = datetime.strptime(entry["date"], "%Y-%m-%d").strftime("%B")
    de_months = {"January":"Januar","February":"Februar","March":"März","April":"April","May":"Mai","June":"Juni","July":"Juli","August":"August","September":"September","October":"Oktober","November":"November","December":"Dezember"}
    month_de = de_months.get(month_name, month_name)

    m_total = m_won + m_lost
    if m_total:
        m_roi = m_net/m_staked*100 if m_staked else 0
        post += f"📅 {month_de}: {m_won}/{m_total} ({round(m_won/m_total*100)}%) · ROI {m_roi:+.1f}%\n"
    a_total = a_won + a_lost
    if a_total:
        a_roi = a_net/a_staked*100 if a_staked else 0
        post += f"🏆 Gesamt: {a_won}/{a_total} ({round(a_won/a_total*100)}%) · ROI {a_roi:+.1f}%\n"

    post += "\n@prophunter"
    return post

def send_telegram(text):
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=30)
        print("  posted OK" if r.status_code == 200 else f"  TG error: {r.text[:120]}")
    except Exception as e:
        print(f"  TG error: {e}")

def main():
    print("PROP HUNTER Results...")
    entry = evaluate()
    if not entry:
        print("Nothing to evaluate."); return
    with open("picks_history.json") as f:
        history = json.load(f)
    post = build_results_post(entry, history)
    if not post:
        print("No MLB results to post."); return
    print("\n" + "="*40 + "\n" + post + "\n" + "="*40 + "\n")
    send_telegram(post)
    print("Done!")

if __name__ == "__main__":
    main()
