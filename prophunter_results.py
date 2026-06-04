#!/usr/bin/env python3
"""
PROP HUNTER — Results Evaluator
Checks yesterday's picks (singles + kombis) against real results.
MLB: MLB Stats API | NBA/WNBA: ESPN API | Combos: auto-evaluated
Posts Auswertung to Telegram with Heute/Monat/Gesamt stats.
"""

import os, json, requests
from datetime import datetime, timedelta, timezone

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")

# ─── MLB: HR results via MLB Stats API ───
def mlb_hr_hitters(date_str):
    out = {}
    try:
        sched = requests.get("https://statsapi.mlb.com/api/v1/schedule",
            params={"sportId":1,"date":date_str,"hydrate":"none"}, timeout=30).json()
        for d in sched.get("dates",[]):
            for g in d.get("games",[]):
                try:
                    box = requests.get(f"https://statsapi.mlb.com/api/v1/game/{g['gamePk']}/boxscore", timeout=30).json()
                    for side in ("home","away"):
                        for pdata in box.get("teams",{}).get(side,{}).get("players",{}).values():
                            name = pdata.get("person",{}).get("fullName","")
                            hr = pdata.get("stats",{}).get("batting",{}).get("homeRuns",0)
                            if name and int(hr or 0) > 0:
                                out[name.lower()] = int(hr)
                except Exception: continue
    except Exception as e:
        print(f"  warn mlb results: {e}")
    return out

# ─── NBA/WNBA: player points via ESPN API ───
def espn_player_stats(date_str, league="nba"):
    """Returns {player_name_lower: points_scored}"""
    out = {}
    try:
        date_fmt = date_str.replace("-","")
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/scoreboard"
        sched = requests.get(url, params={"dates":date_fmt}, timeout=30).json()
        for ev in sched.get("events",[]):
            gid = ev.get("id")
            if not gid: continue
            try:
                summ = requests.get(
                    f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/summary",
                    params={"event":gid}, timeout=30).json()
                for team in summ.get("boxscore",{}).get("players",[]):
                    for stat_group in team.get("statistics",[]):
                        keys = stat_group.get("keys",[])
                        pts_idx = keys.index("PTS") if "PTS" in keys else None
                        if pts_idx is None: continue
                        for ath in stat_group.get("athletes",[]):
                            name = ath.get("athlete",{}).get("displayName","").lower()
                            stats = ath.get("stats",[])
                            if name and pts_idx < len(stats):
                                try: out[name] = int(stats[pts_idx])
                                except: pass
            except Exception: continue
    except Exception as e:
        print(f"  warn espn {league}: {e}")
    return out

def name_match(player, result_dict):
    pl = player.lower()
    if pl in result_dict: return True
    last = pl.split()[-1] if pl.split() else pl
    first3 = pl.split()[0][:3] if pl.split() else ""
    for name in result_dict:
        parts = name.split()
        if parts and parts[-1] == last:
            if not first3 or first3 in name: return True
    return False

def get_result_for_pick(p, mlb_hrs, nba_pts, wnba_pts):
    sport = p.get("sport","")
    player = p.get("player","")
    market = p.get("market","")
    if sport == "MLB" and "Home Run" in market:
        return "won" if name_match(player, mlb_hrs) else "lost"
    elif sport in ("NBA","WNBA"):
        pts_data = nba_pts if sport=="NBA" else wnba_pts
        if pts_data:
            # Extract threshold from market e.g. "30+ Points" → 30
            import re
            m = re.search(r'(\d+)\+', market)
            threshold = int(m.group(1)) if m else 25
            for name, pts in pts_data.items():
                if name_match(player, {name: pts}):
                    return "won" if pts >= threshold else "lost"
        return "pending"
    return "pending"

# ─── COMBO EVALUATION ───
def eval_kombis(kombis, won_players):
    """Mark combo as won/lost based on whether all legs hit."""
    for k in kombis:
        legs = k.get("legs",[])
        all_won = True
        any_lost = False
        for leg in legs:
            # Extract player name from leg string e.g. "MIN Buxton HR" → "Buxton"
            words = leg.split()
            matched = False
            for i in range(len(words)):
                partial = " ".join(words[i:])
                for wp in won_players:
                    if words[-2] in wp if len(words) >= 2 else False:
                        matched = True; break
                    if any(w.lower() in wp for w in words[1:-1] if len(w) > 3):
                        matched = True; break
                if matched: break
            if not matched:
                all_won = False
                any_lost = True
        if any_lost:
            k["result"] = "lost"
        elif all_won:
            k["result"] = "won"
        else:
            k["result"] = "pending"
    return kombis

# ─── EVALUATE ───
def evaluate():
    if not os.path.exists("picks_history.json"):
        print("No history."); return None
    history = json.load(open("picks_history.json"))
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    target = next((e for e in history if e["date"]==yesterday and not e.get("evaluated")), None)
    if not target:
        print(f"Nothing to evaluate for {yesterday}"); return None

    mlb_hrs  = mlb_hr_hitters(yesterday)
    nba_pts  = espn_player_stats(yesterday, "nba")
    wnba_pts = espn_player_stats(yesterday, "wnba")
    print(f"  MLB HR hitters: {len(mlb_hrs)} | NBA players: {len(nba_pts)} | WNBA: {len(wnba_pts)}")

    won_players = set()
    for p in target.get("picks",[]):
        p["result"] = get_result_for_pick(p, mlb_hrs, nba_pts, wnba_pts)
        if p["result"] == "won":
            won_players.add(p["player"].lower())

    # Evaluate combos
    target["kombis"] = eval_kombis(target.get("kombis",[]), won_players)
    target["evaluated"] = True

    json.dump(history, open("picks_history.json","w"), indent=2)
    return target

# ─── BUILD POST ───
def build_post(entry, history):
    date_disp = datetime.strptime(entry["date"],"%Y-%m-%d").strftime("%d.%m.%Y")
    picks  = [p for p in entry.get("picks",[]) if p["result"] in ("won","lost")]
    kombis = [k for k in entry.get("kombis",[]) if k["result"] in ("won","lost")]
    if not picks and not kombis: return None

    # Singles
    won = [p for p in picks if p["result"]=="won"]
    lost = [p for p in picks if p["result"]=="lost"]
    net = sum((p["odds"]-1)*p["stake"] for p in won) - sum(p["stake"] for p in lost)

    post = f"📊 PROP HUNTER — Auswertung {date_disp}\n\n"
    for p in picks:
        icon = "⚾" if p["sport"]=="MLB" else "🏀" if p["sport"] in ("NBA","WNBA") else "🏈"
        if p["result"]=="won":
            post += f"✅ {icon} {p.get('team','')} — {p['player']} @{p['odds']:.2f} → +{(p['odds']-1)*p['stake']:.2f}u\n"
        else:
            post += f"❌ {icon} {p.get('team','')} — {p['player']} @{p['odds']:.2f} → -{p['stake']}u\n"

    # Combos
    if kombis:
        post += "\n"
        k_won = [k for k in kombis if k["result"]=="won"]
        k_lost = [k for k in kombis if k["result"]=="lost"]
        for k in kombis:
            legs_str = " + ".join(k["legs"][:2]) + ("..." if len(k["legs"])>2 else "")
            if k["result"]=="won":
                profit = (k["odds"]-1)*k["stake"]
                post += f"✅ 🔥 {legs_str} @{k['odds']:.1f} → +{profit:.2f}u\n"
                net += profit
            else:
                post += f"❌ 🔥 {legs_str} @{k['odds']:.1f} → -{k['stake']}u\n"
                net -= k["stake"]

    # Stats
    post += "\n━━━━━━━━━━\n"
    total_today = len(won) + len(lost) + len(k_won) + len(k_lost)
    won_today = len(won) + len(k_won)
    post += f"📊 Heute: {won_today}/{total_today} ({round(won_today/total_today*100) if total_today else 0}%) · {'+' if net>=0 else ''}{net:.2f}u\n"

    # Monthly + all-time
    this_month = entry["date"][:7]
    de_months = {"January":"Januar","February":"Februar","March":"März","April":"April","May":"Mai","June":"Juni","July":"Juli","August":"August","September":"September","October":"Oktober","November":"November","December":"Dezember"}
    month_de = de_months.get(datetime.strptime(entry["date"],"%Y-%m-%d").strftime("%B"),"")

    def calc_stats(entries):
        w = l = 0; net_val = staked = 0.0
        for e in entries:
            for p in e.get("picks",[]):
                r = p.get("result")
                if r == "won":   w += 1; net_val += (p["odds"]-1)*p["stake"]; staked += p["stake"]
                elif r == "lost": l += 1; net_val -= p["stake"]; staked += p["stake"]
            for k in e.get("kombis",[]):
                r = k.get("result")
                if r == "won":   w += 1; net_val += (k["odds"]-1)*k["stake"]; staked += k["stake"]
                elif r == "lost": l += 1; net_val -= k["stake"]; staked += k["stake"]
        return w, l, net_val, staked

    m_entries = [e for e in history if e["date"][:7]==this_month]
    mw,ml,mn,ms = calc_stats(m_entries)
    mt = mw+ml
    if mt: post += f"📅 {month_de}: {mw}/{mt} ({round(mw/mt*100)}%) · ROI {mn/ms*100:+.1f}%\n"

    aw,al,an,as_ = calc_stats(history)
    at = aw+al
    if at: post += f"🏆 Gesamt: {aw}/{at} ({round(aw/at*100)}%) · ROI {an/as_*100:+.1f}%\n"

    post += "\n@prophunter"
    return post

def send_telegram(text):
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id":TG_CHAT,"text":text}, timeout=30)
        print("  posted OK" if r.status_code==200 else f"  TG error: {r.text[:120]}")
    except Exception as e: print(f"  TG error: {e}")

def main():
    print("PROP HUNTER Results...")
    entry = evaluate()
    if not entry: print("Nothing to post."); return
    history = json.load(open("picks_history.json"))
    post = build_post(entry, history)
    if not post: print("No results to post."); return
    print("\n"+post+"\n")
    send_telegram(post)
    print("Done!")

if __name__ == "__main__":
    main()
