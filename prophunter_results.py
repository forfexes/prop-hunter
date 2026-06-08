#!/usr/bin/env python3
"""
PROP HUNTER — Results Evaluator (Fixed)
- Evaluates ALL picks from yesterday (multiple daily runs)
- MLB: HR, Hits, Total Bases via MLB Stats API
- NBA/WNBA: Points, Assists, Rebounds via ESPN API
- Combos: auto-evaluated from single results
"""

import os, json, re, requests
from datetime import datetime, timedelta, timezone

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
SB_URL   = os.environ.get("SUPABASE_URL", "")
SB_KEY   = os.environ.get("SUPABASE_KEY", "")

# ─── MLB: full box stats (HR, Hits, Total Bases) ───
def mlb_player_stats(date_str):
    """Returns {player_name_lower: {hr, hits, total_bases, strikeouts}}"""
    out = {}
    try:
        sched = requests.get("https://statsapi.mlb.com/api/v1/schedule",
            params={"sportId":1,"date":date_str,"hydrate":"none"}, timeout=30).json()
        for d in sched.get("dates",[]):
            for g in d.get("games",[]):
                try:
                    box = requests.get(
                        f"https://statsapi.mlb.com/api/v1/game/{g['gamePk']}/boxscore",
                        timeout=30).json()
                    for side in ("home","away"):
                        players = box.get("teams",{}).get(side,{}).get("players",{})
                        for pdata in players.values():
                            name = pdata.get("person",{}).get("fullName","").lower()
                            bat  = pdata.get("stats",{}).get("batting",{})
                            pit  = pdata.get("stats",{}).get("pitching",{})
                            if name:
                                out[name] = {
                                    "hr":          int(bat.get("homeRuns",0) or 0),
                                    "hits":        int(bat.get("hits",0) or 0),
                                    "total_bases": int(bat.get("totalBases",0) or 0),
                                    "strikeouts_p":int(pit.get("strikeOuts",0) or 0),
                                }
                except Exception: continue
    except Exception as e:
        print(f"  warn mlb stats: {e}")
    print(f"  MLB players: {len(out)}")
    return out

# ─── NBA/WNBA: player stats via ESPN ───
def espn_player_stats(date_str, league="nba"):
    """Returns {player_name_lower: {pts, reb, ast, blk}}"""
    out = {}
    try:
        date_fmt = date_str.replace("-","")
        sched = requests.get(
            f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/scoreboard",
            params={"dates":date_fmt}, timeout=30).json()
        for ev in sched.get("events",[]):
            gid = ev.get("id")
            if not gid: continue
            try:
                summ = requests.get(
                    f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/summary",
                    params={"event":gid}, timeout=30).json()
                for team in summ.get("boxscore",{}).get("players",[]):
                    for sg in team.get("statistics",[]):
                        keys = sg.get("keys",[])
                        def idx(k): return keys.index(k) if k in keys else None
                        pts_i = idx("PTS"); reb_i = idx("REB")
                        ast_i = idx("AST"); blk_i = idx("BLK")
                        for ath in sg.get("athletes",[]):
                            name = ath.get("athlete",{}).get("displayName","").lower()
                            st   = ath.get("stats",[])
                            if name:
                                def gv(i): return float(st[i]) if i is not None and i<len(st) else 0
                                out[name] = {
                                    "pts": gv(pts_i), "reb": gv(reb_i),
                                    "ast": gv(ast_i), "blk": gv(blk_i),
                                }
            except Exception: continue
    except Exception as e:
        print(f"  warn espn {league}: {e}")
    print(f"  {league.upper()} players: {len(out)}")
    return out

# ─── NAME MATCHING ───
def name_match(player, result_dict):
    pl = player.lower()
    if pl in result_dict: return pl
    parts = pl.split()
    last = parts[-1] if parts else pl
    first3 = parts[0][:3] if parts else ""
    for name in result_dict:
        nparts = name.split()
        if nparts and nparts[-1] == last:
            if not first3 or any(first3 in np for np in nparts): return name
    # fuzzy: last name only
    for name in result_dict:
        if last in name: return name
    return None

# ─── EVALUATE SINGLE PICK ───
def eval_pick(p, mlb, nba, wnba):
    sport  = p.get("sport","")
    player = p.get("player","")
    market = p.get("market","")

    if sport == "MLB":
        key = name_match(player, mlb)
        if key is None: return "pending"
        stats = mlb[key]
        if "Home Run" in market:
            return "won" if stats["hr"] >= 1 else "lost"
        elif "Hits" in market:
            # "Hits Over 1.5" → need 2+ hits
            m = re.search(r'(\d+\.?\d*)', market)
            thresh = float(m.group(1)) if m else 1.5
            return "won" if stats["hits"] > thresh else "lost"
        elif "Total Bases" in market:
            m = re.search(r'(\d+\.?\d*)', market)
            thresh = float(m.group(1)) if m else 2.5
            return "won" if stats["total_bases"] > thresh else "lost"
        elif "Pitcher K" in market or "Strikeout" in market:
            m = re.search(r'(\d+\.?\d*)', market)
            thresh = float(m.group(1)) if m else 5.5
            return "won" if stats["strikeouts_p"] > thresh else "lost"

    elif sport in ("NBA","WNBA"):
        db = nba if sport=="NBA" else wnba
        key = name_match(player, db)
        if key is None: return "pending"
        stats = db[key]
        m = re.search(r'(\d+)', market)
        thresh = float(m.group(1)) if m else 20
        if "PRA" in market:
            val = stats["pts"] + stats["reb"] + stats["ast"]
        elif "PR" in market and "Punkte+Rebounds" in market:
            val = stats["pts"] + stats["reb"]
        elif "PA" in market or "Punkte+Assists" in market:
            val = stats["pts"] + stats["ast"]
        elif "Rebounds+Assists" in market or "RA" in market:
            val = stats["reb"] + stats["ast"]
        elif "Rebounds" in market or "Reb" in market:
            val = stats["reb"]
        elif "Assists" in market or "Ast" in market:
            val = stats["ast"]
        elif "Blocks" in market or "Blk" in market:
            val = stats["blk"]
        elif "Double Double" in market:
            doubles = sum(1 for v in [stats["pts"],stats["reb"],stats["ast"]] if v >= 10)
            return "won" if doubles >= 2 else "lost"
        elif "Triple Double" in market:
            doubles = sum(1 for v in [stats["pts"],stats["reb"],stats["ast"]] if v >= 10)
            return "won" if doubles >= 3 else "lost"
        else:  # Points
            val = stats["pts"]
        direction = p.get("direction","over") if isinstance(p, dict) else "over"
        if direction == "under":
            return "won" if val < thresh else "lost"
        return "won" if val > thresh else "lost"

    return "pending"

# ─── EVALUATE ALL ENTRIES FOR DATE ───
def evaluate():
    if not os.path.exists("picks_history.json"):
        print("No history."); return None
    history = json.load(open("picks_history.json"))
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    # Get ALL unevaluated entries from yesterday
    targets = [e for e in history if e["date"]==yesterday and not e.get("evaluated")]
    if not targets:
        print(f"Nothing to evaluate for {yesterday}"); return None
    print(f"  Evaluating {len(targets)} entries from {yesterday}")

    # Fetch results once
    mlb  = mlb_player_stats(yesterday)
    nba  = espn_player_stats(yesterday, "nba")
    wnba = espn_player_stats(yesterday, "wnba")

    # Collect all won player names for combo evaluation
    won_set = set()

    # Evaluate ALL entries
    all_picks  = []
    all_kombis = []
    for entry in targets:
        for p in entry.get("picks",[]):
            p["result"] = eval_pick(p, mlb, nba, wnba)
            if p["result"] == "won":
                won_set.add(p["player"].lower())
            all_picks.append(p)
        for k in entry.get("kombis",[]):
            all_kombis.append(k)
        entry["evaluated"] = True

    # Evaluate combos
    for k in all_kombis:
        legs = k.get("legs",[])
        results = []
        for leg in legs:
            # Extract player name from leg (e.g. "PHI Harper HR" → check "harper")
            words = [w.lower() for w in leg.split()]
            hit = any(any(w in wp for w in words[1:] if len(w)>3) for wp in won_set)
            results.append("won" if hit else "lost")
        if all(r == "won" for r in results):
            k["result"] = "won"
        elif any(r == "lost" for r in results):
            k["result"] = "lost"
        else:
            k["result"] = "pending"

    json.dump(history, open("picks_history.json","w"), indent=2)

    # Update Supabase
    if SB_URL and SB_KEY:
        try:
            from supabase import create_client
            sb = create_client(SB_URL, SB_KEY)
            for p in all_picks:
                if p.get("result") in ("won","lost"):
                    profit = round((p["odds"]-1)*p["stake"],2) if p["result"]=="won" else round(-p["stake"],2)
                    sb.table("prop_picks").update({
                        "result":p["result"],"profit":profit
                    }).eq("player",p["player"]).eq("date",yesterday).eq("result","pending").execute()
            print("  Supabase updated")
        except Exception as e:
            print(f"  warn supabase: {e}")

    return all_picks, all_kombis

# ─── BUILD POST ───
def build_post(all_picks, all_kombis, history):
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    date_disp = datetime.strptime(yesterday,"%Y-%m-%d").strftime("%d.%m.%Y")

    picks  = [p for p in all_picks  if p["result"] in ("won","lost")]
    kombis = [k for k in all_kombis if k["result"] in ("won","lost")]
    if not picks and not kombis: return None

    won  = [p for p in picks if p["result"]=="won"]
    lost = [p for p in picks if p["result"]=="lost"]
    kwon = [k for k in kombis if k["result"]=="won"]
    klost= [k for k in kombis if k["result"]=="lost"]

    net  = sum((p["odds"]-1)*p["stake"] for p in won)
    net -= sum(p["stake"] for p in lost)
    net += sum((k["odds"]-1)*k["stake"] for k in kwon)
    net -= sum(k["stake"] for k in klost)

    post = f"📊 PROP HUNTER — Auswertung {date_disp}\n\n"
    for p in picks:
        icon = "⚾" if p["sport"]=="MLB" else "🏀" if p["sport"] in ("NBA","WNBA") else "🏈"
        team = p.get("team","")
        if p["result"]=="won":
            post += f"✅ {icon} {team} — {p['player']} @{p['odds']:.2f} → +{(p['odds']-1)*p['stake']:.2f}u\n"
        else:
            post += f"❌ {icon} {team} — {p['player']} @{p['odds']:.2f} → -{p['stake']}u\n"

    if kombis:
        post += "\n"
        for k in kombis:
            legs_str = " + ".join(k["legs"][:2]) + ("..." if len(k["legs"])>2 else "")
            if k["result"]=="won":
                post += f"✅ 🔥 {legs_str} @{k['odds']:.1f} → +{(k['odds']-1)*k['stake']:.2f}u\n"
            else:
                post += f"❌ 🔥 {legs_str} → -{k['stake']}u\n"

    total_w = len(won)+len(kwon)
    total_l = len(lost)+len(klost)
    total   = total_w + total_l

    post += "\n━━━━━━━━━━\n"
    post += f"{'🟢' if net>=0 else '🔴'} {'Profit' if net>=0 else 'Verlust'}: {'+' if net>=0 else ''}{net:.2f}u\n"
    if total: post += f"📊 Heute: {total_w}/{total} ({round(total_w/total*100)}%)\n"

    this_month = yesterday[:7]
    de_months  = {"January":"Januar","February":"Februar","March":"März","April":"April","May":"Mai","June":"Juni","July":"Juli","August":"August","September":"September","October":"Oktober","November":"November","December":"Dezember"}
    month_de   = de_months.get(datetime.strptime(yesterday,"%Y-%m-%d").strftime("%B"),"")

    def calc(entries):
        w=l=0; net_v=staked=0.0
        for e in entries:
            for p in e.get("picks",[]):
                r=p.get("result")
                if r=="won":   w+=1; net_v+=(p["odds"]-1)*p["stake"]; staked+=p["stake"]
                elif r=="lost":l+=1; net_v-=p["stake"]; staked+=p["stake"]
            for k in e.get("kombis",[]):
                r=k.get("result")
                if r=="won":   w+=1; net_v+=(k["odds"]-1)*k["stake"]; staked+=k["stake"]
                elif r=="lost":l+=1; net_v-=k["stake"]; staked+=k["stake"]
        return w,l,net_v,staked

    mw,ml,mn,ms = calc([e for e in history if e["date"][:7]==this_month])
    mt = mw+ml
    if mt and ms: post += f"📅 {month_de}: {mw}/{mt} ({round(mw/mt*100)}%) · ROI {mn/ms*100:+.1f}%\n"

    aw,al,an,as_ = calc(history)
    at = aw+al
    if at and as_: post += f"🏆 Gesamt: {aw}/{at} ({round(aw/at*100)}%) · ROI {an/as_*100:+.1f}%\n"

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
    result = evaluate()
    if not result: print("Nothing to post."); return
    all_picks, all_kombis = result
    evaluated = [p for p in all_picks if p["result"] in ("won","lost")]
    print(f"  Evaluated: {len(evaluated)} picks, {len([k for k in all_kombis if k['result'] in ('won','lost')])} kombis")
    history = json.load(open("picks_history.json"))
    post = build_post(all_picks, all_kombis, history)
    if not post: print("No results to post."); return
    print("\n"+post+"\n")
    send_telegram(post)
    print("Done!")

if __name__ == "__main__":
    main()
