#!/usr/bin/env python3
"""PROP HUNTER — Results Evaluator
Wertet gestrige Picks aus und postet Ergebnisse auf Telegram.
"""
from __future__ import annotations
import json, logging, os, requests, time
from datetime import datetime, timedelta, timezone
from typing import Optional

# ─── Config ───
TG_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN","")
TG_CHAT   = os.environ.get("TELEGRAM_CHAT_ID","")
BDL_KEY   = os.environ.get("BALLDONTLIE_API_KEY","")
HISTORY   = "picks_history.json"
TIMEOUT   = 30

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(message)s",datefmt="%H:%M:%S")
log = logging.getLogger("results")

# ─── Telegram ───
def send(text):
    if not TG_TOKEN or not TG_CHAT: log.warning("Telegram not configured"); return
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id":TG_CHAT,"text":text,"disable_web_page_preview":True},timeout=TIMEOUT)
        log.info("Telegram: %d", r.status_code)
    except Exception as e: log.error("Telegram: %s", e)

# ─── History ───
def load():
    if not os.path.exists(HISTORY): return []
    try: return json.load(open(HISTORY))
    except: return []
def save(h):
    try: json.dump(h, open(HISTORY,"w"), indent=2, default=str)
    except Exception as e: log.warning("save: %s", e)

# ─── NBA Results via balldontlie ───
def bdl_get(path, params):
    h = {"Accept":"application/json"}
    if BDL_KEY: h["Authorization"] = BDL_KEY
    try:
        r = requests.get(f"https://api.balldontlie.io/v1{path}",
            params=params, headers=h, timeout=TIMEOUT)
        return r.json() if r.status_code==200 else None
    except: return None

def get_nba_stats_yesterday(player_name: str) -> Optional[dict]:
    """Get yesterday's game stats for NBA player."""
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    # Find player
    d = bdl_get("/players", {"search": player_name, "per_page": 5})
    if not d: return None
    players = d.get("data", [])
    if not players: return None
    nl = player_name.lower()
    player = next((p for p in players
        if f"{p.get('first_name','')} {p.get('last_name','')}".lower().strip()==nl), players[0])
    pid = player.get("id")
    if not pid: return None
    # Get stats
    d2 = bdl_get("/stats", {"player_ids[]":pid, "dates[]":yesterday, "per_page":1})
    if not d2: return None
    rows = d2.get("data",[])
    if not rows: return None
    s = rows[0]
    return {
        "pts": float(s.get("pts") or 0),
        "reb": float(s.get("reb") or 0),
        "ast": float(s.get("ast") or 0),
        "blk": float(s.get("blk") or 0),
        "stl": float(s.get("stl") or 0),
        "fg3m": float(s.get("fg3m") or 0),
        "min": s.get("min","0"),
    }

# ─── MLB Results via MLB-StatsAPI ───
def get_mlb_stats_yesterday(player_name: str, market: str) -> Optional[dict]:
    try:
        import statsapi
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        schedule = statsapi.schedule(date=yesterday)
        for game in schedule:
            try:
                box = statsapi.boxscore_data(game.get("game_id"))
                for side in ("home","away"):
                    for bid in box.get(side,{}).get("batters",[]) + box.get(side,{}).get("pitchers",[]):
                        info = box.get(side,{}).get("players",{}).get(f"ID{bid}",{})
                        name = info.get("person",{}).get("fullName","")
                        if player_name.lower() not in name.lower(): continue
                        s = info.get("stats",{}).get("batting",{})
                        sp = info.get("stats",{}).get("pitching",{})
                        return {
                            "hits": int(s.get("hits",0)),
                            "hr": int(s.get("homeRuns",0)),
                            "tb": int(s.get("totalBases",0)),
                            "rbi": int(s.get("rbi",0)),
                            "sb": int(s.get("stolenBases",0)),
                            "k": int(sp.get("strikeOuts",0)),
                            "outs": int(sp.get("outs",0)),
                            "er": int(sp.get("earnedRuns",0)),
                        }
            except: continue
    except: pass
    return None

# ─── Grade a single pick ───
def grade(pick: dict) -> Optional[str]:
    market = (pick.get("market") or "").lower()
    direction = (pick.get("direction") or "over").lower()
    point = pick.get("point") or pick.get("odds")  # fallback
    sport = (pick.get("sport") or "").upper()
    player = pick.get("player","")

    # Extract line from market string if point not stored
    line = None
    import re
    m = re.search(r"(\d+\.?\d*)\+?", market)
    if m: line = float(m.group(1))

    if sport in ("NBA","WNBA"):
        stats = get_nba_stats_yesterday(player)
        if not stats: return None
        if "rebounds+assists" in market or "reb+ast" in market:
            val = stats["reb"] + stats["ast"]
        elif "pra" in market or ("points" in market and "rebounds" in market and "assists" in market):
            val = stats["pts"] + stats["reb"] + stats["ast"]
        elif "points+rebounds" in market and "assists" not in market:
            val = stats["pts"] + stats["reb"]
        elif "points+assists" in market and "rebounds" not in market:
            val = stats["pts"] + stats["ast"]
        elif "points" in market:
            val = stats["pts"]
        elif "rebounds" in market:
            val = stats["reb"]
        elif "assists" in market:
            val = stats["ast"]
        elif "3pm" in market or "three" in market:
            val = stats["fg3m"]
        elif "blocks" in market:
            val = stats["blk"]
        elif "steals" in market:
            val = stats["stl"]
        else:
            return None
    elif sport == "MLB":
        stats = get_mlb_stats_yesterday(player, market)
        if not stats: return None
        if "home run" in market or "hr" in market:
            val = stats["hr"]; line = 0.5  # yes/no
        elif "hits" in market:
            val = stats["hits"]
        elif "total bases" in market:
            val = stats["tb"]
        elif "stolen base" in market:
            val = stats["sb"]; line = 0.5
        elif "rbi" in market:
            val = stats["rbi"]
        elif "pitcher k" in market or "strikeout" in market:
            val = stats["k"]
        elif "outs recorded" in market:
            val = stats["outs"]
        elif "earned runs" in market:
            val = stats["er"]
        else:
            return None
    else:
        return None

    if line is None: return None
    if direction == "under":
        return "win" if val < line else "loss"
    else:
        return "win" if val > line else "loss"

# ─── Main ───
def main():
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    today     = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.info("Grading picks for %s", yesterday)

    history = load()
    entry = next((e for e in history if e.get("date")==yesterday), None)
    if not entry:
        log.info("No picks found for %s", yesterday)
        return

    picks = entry.get("picks",[])
    pending = [p for p in picks if p.get("result","pending")=="pending"]
    log.info("%d pending picks to grade", len(pending))

    wins=0; losses=0; total_profit=0.0; results=[]
    for p in pending:
        result = grade(p)
        if result is None:
            log.warning("Could not grade: %s %s", p.get("player"), p.get("market"))
            results.append(("❓", p))
            continue
        stake = float(p.get("stake",1))
        odds  = float(p.get("odds",2))
        profit = round((odds-1)*stake if result=="win" else -stake, 2)
        p["result"] = result
        p["profit"] = profit
        total_profit += profit
        if result=="win":
            wins += 1
            results.append(("✅",p))
        else:
            losses += 1
            results.append(("❌",p))
        time.sleep(0.3)

    save(history)

    # ─── Build Telegram message ───
    total = wins+losses
    roi = round(100*total_profit/sum(float(p.get("stake",1)) for _,p in results if p.get("result") in ("win","loss")),1) if total>0 else 0
    lines = [f"📊 PROP HUNTER — Auswertung {yesterday}", ""]
    for icon,p in results:
        odds = float(p.get("odds",0))
        stake = float(p.get("stake",0))
        profit = p.get("profit")
        profit_str = f"+{profit:.2f}u" if (profit or 0)>0 else f"{profit:.2f}u" if profit is not None else ""
        lines.append(f"{icon} {p.get('emoji','🎯')} {p.get('team','')} — {p.get('player','')} @{odds:.2f} → {profit_str}")

    lines += [
        "",
        "━━━━━━━━━━",
        f"{'🟢' if total_profit>=0 else '🔴'} {'Gewinn' if total_profit>=0 else 'Verlust'}: {total_profit:+.2f}u",
        f"📊 Heute: {wins}/{total} ({round(100*wins/total) if total else 0}%)",
    ]

    # Monthly stats
    monthly_wins=0; monthly_total=0; monthly_profit=0.0
    month = today[:7]
    for e in history:
        if not e.get("date","").startswith(month): continue
        for p in e.get("picks",[]):
            if p.get("result") in ("win","loss"):
                monthly_total+=1
                if p["result"]=="win": monthly_wins+=1
                monthly_profit+=float(p.get("profit",0))
    if monthly_total:
        monthly_roi=round(100*monthly_profit/monthly_total,1)
        lines.append(f"📅 {month}: {monthly_wins}/{monthly_total} ({round(100*monthly_wins/monthly_total)}%) · ROI {monthly_roi}%")

    lines.append("@prophunter")
    msg = "\n".join(lines)
    print("\n"+msg+"\n")
    send(msg)

if __name__=="__main__":
    main()
