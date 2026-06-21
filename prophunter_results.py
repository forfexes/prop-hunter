#!/usr/bin/env python3
"""PROP HUNTER — Results Evaluator v2 Style"""
import json, os, requests, time, re
from datetime import datetime, timedelta, timezone

# ─── Day-level cache (1 API call covers all picks of that day) ───
_NBA_DAY_CACHE = {}
_MLB_DAY_CACHE = {}
_ESPN_NBA_DAY_CACHE = {}
_ESPN_MLB_DAY_CACHE = {}

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN","")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID","")
BDL_KEY  = os.environ.get("BALLDONTLIE_API_KEY","")
HISTORY  = "picks_history.json"
TIMEOUT  = 30

def send(text):
    if not TG_TOKEN or not TG_CHAT: print(text); return
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id":TG_CHAT,"text":text,"disable_web_page_preview":True},timeout=TIMEOUT)
        print(f"Telegram: {r.status_code}")
    except Exception as e: print(f"Telegram: {e}")

def load():
    if not os.path.exists(HISTORY): return []
    try: return json.load(open(HISTORY))
    except: return []

def save(h):
    try: json.dump(h, open(HISTORY,"w"), indent=2, default=str)
    except Exception as e: print(f"save: {e}")

# ─── NBA via balldontlie ───
def nba_stats_yesterday(player):
    yesterday = (datetime.now(timezone.utc)-timedelta(days=1)).strftime("%Y-%m-%d")
    h = {"Accept":"application/json"}
    if BDL_KEY: h["Authorization"] = BDL_KEY
    try:
        r = requests.get("https://api.balldontlie.io/v1/players",
            params={"search":player,"per_page":5},headers=h,timeout=TIMEOUT)
        if r.status_code != 200: return None
        players = r.json().get("data",[])
        if not players: return None
        nl = player.lower()
        p = next((x for x in players if f"{x.get('first_name','')} {x.get('last_name','')}".lower().strip()==nl),players[0])
        pid = p.get("id")
        r2 = requests.get("https://api.balldontlie.io/v1/stats",
            params={"player_ids[]":pid,"dates[]":yesterday,"per_page":1},headers=h,timeout=TIMEOUT)
        if r2.status_code != 200: return None
        rows = r2.json().get("data",[])
        if not rows: return None
        s = rows[0]
        return {"pts":float(s.get("pts") or 0),"reb":float(s.get("reb") or 0),
                "ast":float(s.get("ast") or 0),"blk":float(s.get("blk") or 0),
                "stl":float(s.get("stl") or 0),"fg3m":float(s.get("fg3m") or 0)}
    except: return None

# ─── MLB via statsapi ───
def mlb_stats_yesterday(player):
    try:
        import statsapi
        yesterday = (datetime.now(timezone.utc)-timedelta(days=1)).strftime("%Y-%m-%d")
        for game in statsapi.schedule(date=yesterday):
            try:
                box = statsapi.boxscore_data(game.get("game_id"))
                for side in ("home","away"):
                    for bid in box.get(side,{}).get("batters",[])+box.get(side,{}).get("pitchers",[]):
                        info = box.get(side,{}).get("players",{}).get(f"ID{bid}",{})
                        name = info.get("person",{}).get("fullName","")
                        if player.lower() not in name.lower(): continue
                        b = info.get("stats",{}).get("batting",{})
                        p = info.get("stats",{}).get("pitching",{})
                        return {"hits":int(b.get("hits",0)),"hr":int(b.get("homeRuns",0)),
                                "tb":int(b.get("totalBases",0)),"rbi":int(b.get("rbi",0)),
                                "sb":int(b.get("stolenBases",0)),"k":int(p.get("strikeOuts",0)),
                                "outs":int(p.get("outs",0)),"er":int(p.get("earnedRuns",0))}
            except: continue
    except: pass
    return None

# ─── ESPN Fallback ───
def espn_nba_scoreboard(date_str):
    """ESPN NBA scoreboard for a given date (YYYYMMDD), cached per day."""
    if date_str in _ESPN_NBA_DAY_CACHE:
        return _ESPN_NBA_DAY_CACHE[date_str]
    games = []
    try:
        d = date_str.replace("-", "")
        r = requests.get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
            params={"dates": d}, timeout=TIMEOUT)
        if r.status_code == 200:
            games = r.json().get("events", [])
    except Exception:
        pass
    _ESPN_NBA_DAY_CACHE[date_str] = games
    return games

def espn_mlb_scoreboard(date_str):
    """ESPN MLB scoreboard for a given date (YYYYMMDD), cached per day."""
    if date_str in _ESPN_MLB_DAY_CACHE:
        return _ESPN_MLB_DAY_CACHE[date_str]
    games = []
    try:
        d = date_str.replace("-", "")
        r = requests.get("https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
            params={"dates": d}, timeout=TIMEOUT)
        if r.status_code == 200:
            games = r.json().get("events", [])
    except Exception:
        pass
    _ESPN_MLB_DAY_CACHE[date_str] = games
    return games

def espn_nba_player_stats(player_name, date_str):
    """Fallback: find NBA player boxscore stats via ESPN scoreboard summary."""
    games = espn_nba_scoreboard(date_str)
    pl = player_name.lower()
    for ev in games:
        try:
            comp = ev.get("competitions", [{}])[0]
            event_id = ev.get("id")
            if not event_id:
                continue
            r = requests.get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary",
                params={"event": event_id}, timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            box = r.json().get("boxscore", {})
            for team in box.get("players", []):
                for stat_group in team.get("statistics", []):
                    labels = stat_group.get("labels", [])
                    for athlete in stat_group.get("athletes", []):
                        name = (athlete.get("athlete", {}) or {}).get("displayName", "")
                        if pl not in name.lower():
                            continue
                        vals = athlete.get("stats", [])
                        stat_map = dict(zip(labels, vals))
                        def gi(k):
                            try: return float(stat_map.get(k, 0) or 0)
                            except: return 0.0
                        return {
                            "pts": gi("PTS"), "reb": gi("REB"), "ast": gi("AST"),
                            "blk": gi("BLK"), "stl": gi("STL"), "fg3m": gi("3PM"),
                        }
        except Exception:
            continue
    return None

def espn_mlb_player_stats(player_name, date_str):
    """Fallback: find MLB player boxscore stats via ESPN scoreboard summary."""
    games = espn_mlb_scoreboard(date_str)
    pl = player_name.lower()
    for ev in games:
        try:
            event_id = ev.get("id")
            if not event_id:
                continue
            r = requests.get("https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/summary",
                params={"event": event_id}, timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            box = r.json().get("boxscore", {})
            for team in box.get("players", []):
                for stat_group in team.get("statistics", []):
                    labels = stat_group.get("labels", [])
                    for athlete in stat_group.get("athletes", []):
                        name = (athlete.get("athlete", {}) or {}).get("displayName", "")
                        if pl not in name.lower():
                            continue
                        vals = athlete.get("stats", [])
                        stat_map = dict(zip(labels, vals))
                        def gi(k):
                            try: return int(float(stat_map.get(k, 0) or 0))
                            except: return 0
                        return {
                            "hits": gi("H"), "hr": gi("HR"), "tb": gi("TB"),
                            "rbi": gi("RBI"), "sb": gi("SB"),
                            "k": gi("K"), "outs": gi("IP") * 3 if "IP" in stat_map else 0,
                            "er": gi("ER"),
                        }
        except Exception:
            continue
    return None


# ─── Grade single pick ───
def grade(pick):
    market = (pick.get("market") or "").lower()
    direction = (pick.get("direction") or "over").lower()
    sport = (pick.get("sport") or "").upper()
    player = pick.get("player","")

    # Extract line
    line = None
    m = re.search(r"(\d+\.?\d*)", market)
    if m: line = float(m.group(1))

    stats = None
    if sport in ("NBA","WNBA"):
        stats = nba_stats_yesterday(player)
        if not stats: return None
        if "rebounds+assists" in market: val = stats["reb"]+stats["ast"]
        elif "pra" in market or ("points" in market and "rebounds" in market and "assists" in market):
            val = stats["pts"]+stats["reb"]+stats["ast"]
        elif "points+rebounds" in market and "assists" not in market: val = stats["pts"]+stats["reb"]
        elif "points+assists" in market and "rebounds" not in market: val = stats["pts"]+stats["ast"]
        elif "points" in market: val = stats["pts"]
        elif "rebounds" in market: val = stats["reb"]
        elif "assists" in market: val = stats["ast"]
        elif "3pm" in market or "three" in market: val = stats["fg3m"]
        elif "blocks" in market: val = stats["blk"]
        elif "steals" in market: val = stats["stl"]
        else: return None
    elif sport == "MLB":
        stats = mlb_stats_yesterday(player)
        if not stats:
            yesterday = (datetime.now(timezone.utc)-timedelta(days=1)).strftime("%Y%m%d")
            stats = espn_mlb_player_stats(player, yesterday)
        if not stats: return None
        if "home run" in market or "hr" in market: val = stats["hr"]; line = line or 0.5
        elif "hits" in market: val = stats["hits"]
        elif "total bases" in market: val = stats["tb"]
        elif "stolen base" in market: val = stats["sb"]; line = line or 0.5
        elif "rbi" in market: val = stats["rbi"]
        elif "pitcher k" in market or "strikeout" in market: val = stats["k"]
        elif "outs recorded" in market: val = stats["outs"]
        elif "earned runs" in market: val = stats["er"]
        else: return None
    else:
        return None

    if line is None: return None
    if direction == "under": return "win" if val < line else "loss"
    return "win" if val > line else "loss"

# ─── Main ───
def main():
    yesterday = (datetime.now(timezone.utc)-timedelta(days=1)).strftime("%Y-%m-%d")
    today     = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month     = today[:7]
    print(f"Grading: {yesterday}")

    history = load()
    entry = next((e for e in history if e.get("date")==yesterday), None)
    if not entry:
        print(f"No picks for {yesterday}")
        # Still post empty summary
        send(f"📊 PROP HUNTER — Auswertung {yesterday}\n\n❕ Keine Picks gestern\n\n@prophunter")
        return

    picks = entry.get("picks",[])
    pending = [p for p in picks if p.get("result","pending")=="pending"]
    print(f"{len(pending)} pending picks")

    results = []
    for p in pending:
        result = grade(p)
        stake  = float(p.get("stake",1))
        odds   = float(p.get("odds",2))
        if result is None:
            results.append(("❓",p,0))
            continue
        profit = round((odds-1)*stake if result=="win" else -stake, 2)
        p["result"] = result
        p["profit"] = profit
        results.append(("✅" if result=="win" else "❌", p, profit))
        time.sleep(0.3)

    save(history)

    # ─── Build post (V2 style) ───
    wins   = sum(1 for ic,_,_ in results if ic=="✅")
    losses = sum(1 for ic,_,_ in results if ic=="❌")
    total  = wins+losses
    total_profit = sum(profit for _,_,profit in results if profit!=0)

    stakes_settled = sum(float(p.get("stake",1)) for _,p,_ in results if p.get("result") in ("win","loss"))
    roi = round(100*total_profit/stakes_settled,1) if stakes_settled>0 else 0

    lines = [f"📊 PROP HUNTER — Auswertung {yesterday}", ""]
    for icon,p,profit in results:
        odds = float(p.get("odds",0)); stake = float(p.get("stake",0))
        ps = f"+{profit:.2f}u" if profit>0 else f"{profit:.2f}u" if profit!=0 else ""
        lines.append(f"{icon} {p.get('emoji','🎯')} {p.get('team','')} — {p.get('player','')}")
        lines.append(f"   └ {p.get('market','')} @{odds:.2f} → {stake}u  {ps}")

    # Monthly stats
    m_wins=m_total=0; m_profit=0.0
    for e in history:
        if not e.get("date","").startswith(month): continue
        for p in e.get("picks",[]):
            if p.get("result") in ("win","loss"):
                m_total+=1
                if p["result"]=="win": m_wins+=1
                m_profit+=float(p.get("profit",0))
    m_roi = round(100*m_profit/m_total,1) if m_total else 0

    lines += [
        "",
        "━━━━━━━━━━",
        f"{'🟢' if total_profit>=0 else '🔴'} {'Gewinn' if total_profit>=0 else 'Verlust'}: {total_profit:+.2f}u",
        f"📊 Heute: {wins}/{total} ({round(100*wins/total) if total else 0}%)",
    ]
    if m_total:
        lines.append(f"📅 {month}: {m_wins}/{m_total} ({round(100*m_wins/m_total)}%) · ROI {m_roi}%")
    lines.append("@prophunter")

    msg = "\n".join(lines)
    print("\n"+msg+"\n")
    send(msg)

if __name__=="__main__":
    main()
