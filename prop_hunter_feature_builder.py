from collections import defaultdict
from statistics import mean
from prop_hunter_shared_utils import select_rows, upsert_rows, safe_json_write, log, norm_name, to_float, hash_key, now_iso

OUT="prop_hunter_player_features.json"
FEATURE_WRITE_BATCH=max(100,int(__import__("os").getenv("PH_FEATURE_WRITE_BATCH","500")))
STATS=["points","rebounds","assists","pra","ra","pa","pr","threes_made","double_double","triple_double","hits","doubles","triples","total_bases","home_runs","rbi","runs","stolen_bases","hits_runs_rbis","pitcher_strikeouts","receptions","receiving_yards","receiving_touchdowns","rushing_touchdowns","rushing_yards","passing_yards","passing_touchdowns","touchdowns","anytime_td","two_plus_td","three_plus_td","goals","assists_hockey","hockey_points","shots_on_goal","goalie_saves","blocked_shots","power_play_points"]
LINES={"pra":[24.5,29.5,34.5,39.5,44.5],"ra":[9.5,11.5,13.5,15.5,17.5],"pa":[14.5,19.5,24.5,29.5,34.5],"pr":[14.5,19.5,24.5,29.5,34.5],"points":[14.5,19.5,24.5,29.5],"rebounds":[5.5,7.5,9.5,11.5],"assists":[3.5,5.5,7.5,9.5],"threes_made":[0.5,1.5,2.5,3.5],"hits":[0.5,1.5],"doubles":[0.5],"triples":[0.5],"total_bases":[1.5,2.5,3.5],"home_runs":[0.5],"stolen_bases":[0.5],"hits_runs_rbis":[0.5,1.5,2.5,3.5],"pitcher_strikeouts":[3.5,4.5,5.5,6.5,7.5],"receiving_yards":[24.5,39.5,49.5,59.5,69.5],"rushing_yards":[24.5,39.5,49.5,59.5],"passing_yards":[199.5,224.5,249.5,274.5],"receptions":[2.5,3.5,4.5,5.5],"touchdowns":[0.5,1.5,2.5],"receiving_touchdowns":[0.5,1.5],"rushing_touchdowns":[0.5,1.5],"passing_touchdowns":[0.5,1.5,2.5,3.5],"goals":[0.5],"assists_hockey":[0.5],"hockey_points":[0.5,1.5],"shots_on_goal":[1.5,2.5,3.5,4.5],"goalie_saves":[19.5,24.5,29.5,34.5],"blocked_shots":[0.5,1.5,2.5],"power_play_points":[0.5]}

def _raw_mlb_stat(r,k):
    raw=r.get("raw") if isinstance(r.get("raw"),dict) else {}
    candidates=[raw]
    candidates.extend(v for v in raw.values() if isinstance(v,dict))
    for item in candidates:
        split=item.get("split") if isinstance(item.get("split"),dict) else {}
        stat=split.get("stat") if isinstance(split.get("stat"),dict) else {}
        x=to_float(stat.get(k))
        if x is not None:return x
    return None

def val(r,k):
    if k in {"touchdowns","anytime_td","two_plus_td","three_plus_td"}:
        rec=to_float(r.get("receiving_touchdowns"),0.0) or 0.0
        rush=to_float(r.get("rushing_touchdowns"),0.0) or 0.0
        total=rec+rush
        if k == "touchdowns": return total
        if k == "anytime_td": return 1.0 if total >= 1 else 0.0
        if k == "two_plus_td": return 1.0 if total >= 2 else 0.0
        if k == "three_plus_td": return 1.0 if total >= 3 else 0.0
    if k == "pa":
        a,b=to_float(r.get("points")),to_float(r.get("assists"))
        return None if a is None or b is None else a+b
    if k == "pr":
        a,b=to_float(r.get("points")),to_float(r.get("rebounds"))
        return None if a is None or b is None else a+b
    if k == "hits_runs_rbis":
        xs=[to_float(r.get(x)) for x in ("hits","runs","rbi")]
        return None if any(x is None for x in xs) else sum(xs)
    if k in {"doubles","triples"}:
        direct=to_float(r.get(k))
        return direct if direct is not None else _raw_mlb_stat(r,k)
    x=r.get(k)
    if isinstance(x,bool): return 1.0 if x else 0.0
    return to_float(x)
def avg(rs,k):
    vs=[val(r,k) for r in rs if val(r,k) is not None]
    return round(mean(vs),4) if vs else None
def hit(rs,k,line):
    vs=[val(r,k) for r in rs if val(r,k) is not None]
    return round(sum(v>line for v in vs)/len(vs),4) if vs else None

def main():
    # Read the full retained history with deterministic paging. The retention job
    # caps each sport/league/player at 15 games, so L5/L10/L15 stay complete.
    logs=select_rows("prop_hunter_player_gamelogs",limit=None,order_by="id")
    g=defaultdict(list)
    for r in logs:
        nk=norm_name(r.get("player_name"))
        if nk: g[(str(r.get("sport") or "").upper(),str(r.get("league") or "").upper(),nk)].append(r)
    rows=[]
    for (sport,league,nk),items in g.items():
        items.sort(key=lambda x:str(x.get("game_date") or x.get("created_at") or ""), reverse=True)
        feat={"games_total":len(items),"last_game_date":items[0].get("game_date")}
        for n in [5,10,15]:
            sub=items[:n]; feat[f"last_{n}"]={}
            for st in STATS:
                a=avg(sub,st)
                if a is not None: feat[f"last_{n}"][f"{st}_avg"]=a
                for line in LINES.get(st,[]):
                    h=hit(sub,st,line)
                    if h is not None: feat[f"last_{n}"][f"{st}_over_{str(line).replace('.','_')}_hit_rate"]=h
        rows.append({"feature_id":hash_key(sport,league,nk),"sport":sport,"league":league,"player_name":items[0].get("player_name"),"normalized_name":nk,"games_total":len(items),"features":feat,"updated_at":now_iso()})
    safe_json_write(OUT,rows)
    for start in range(0,len(rows),FEATURE_WRITE_BATCH):
        batch=rows[start:start+FEATURE_WRITE_BATCH]
        upsert_rows("prop_hunter_player_features",batch,"feature_id")
        log(f"feature builder saved batch={start//FEATURE_WRITE_BATCH+1} rows={len(batch)} progress={min(start+len(batch),len(rows))}/{len(rows)}")
    log(f"feature builder done players={len(rows)}")
if __name__=="__main__": main()
