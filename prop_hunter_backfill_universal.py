from prop_hunter_shared_utils import select_rows, upsert_rows, safe_json_write, log, norm_name, norm_market, to_float, hash_key, now_iso, pick_id

OUT="prop_hunter_clv_report.json"

def same(p,s):
    pn=norm_name(p.get("player_name") or p.get("player") or p.get("selection"))
    sn=norm_name(s.get("player_name"))
    if pn and sn and pn!=sn: return False
    pm=norm_market(p.get("market") or p.get("prop_type") or p.get("selection"))
    sm=norm_market(s.get("market") or s.get("market_key"))
    if pm and sm and not (pm in sm or sm in pm): return False
    gid=str(p.get("game_id") or p.get("source_game_id") or "")
    sg=str(s.get("game_id") or s.get("source_event_id") or "")
    return not (gid and sg and gid!=sg)

def side(p):
    t=str(p.get("side") or p.get("direction") or p.get("selection") or p.get("market") or "").lower()
    return "under" if "under" in t else "over"

def line_clv(pick_line, close_line, sd):
    pl=to_float(pick_line); cl=to_float(close_line)
    if pl is None or cl is None: return None
    return pl-cl if sd=="under" else cl-pl

def odds_clv(pick_odds, close_odds):
    po=to_float(pick_odds); co=to_float(close_odds)
    if not po or not co: return None
    return (1/co)-(1/po)

def main():
    picks=select_rows("prop_hunter_picks",limit=5000) or select_rows("prop_picks",limit=5000)
    snaps=select_rows("prop_hunter_prop_snapshots",limit=50000)
    rows=[]
    for p in picks:
        cand=[s for s in snaps if same(p,s)]
        if not cand: continue
        cand.sort(key=lambda x:str(x.get("created_at") or ""))
        op,cl=cand[0],cand[-1]; sd=side(p)
        po=p.get("odds_decimal") or p.get("odds") or p.get("price") or op.get("odds_decimal")
        pl=p.get("line") or p.get("prop_line") or p.get("points") or op.get("line")
        rows.append({"clv_id":hash_key(pick_id(p),cl.get("snapshot_id")),"pick_id":pick_id(p),"source":cl.get("source"),
        "bookmaker":cl.get("bookmaker"),"sport":p.get("sport") or cl.get("sport"),"league":p.get("league") or cl.get("league"),
        "player_name":p.get("player_name") or p.get("player") or cl.get("player_name"),"normalized_name":norm_name(p.get("player_name") or p.get("player") or cl.get("player_name")),
        "market":p.get("market") or cl.get("market"),"side":sd,"pick_line":to_float(pl),"closing_line":to_float(cl.get("line")),
        "line_clv":line_clv(pl,cl.get("line"),sd),"pick_odds_decimal":to_float(po),"closing_odds_decimal":to_float(cl.get("odds_decimal")),
        "odds_clv":odds_clv(po,cl.get("odds_decimal")),"opening_snapshot_id":op.get("snapshot_id"),"closing_snapshot_id":cl.get("snapshot_id"),
        "computed_at":now_iso(),"pick_raw":p,"opening_raw":op,"closing_raw":cl})
    safe_json_write(OUT,rows); upsert_rows("prop_hunter_clv",rows,"clv_id")
    log(f"clv done rows={len(rows)}")
if __name__=="__main__": main()
