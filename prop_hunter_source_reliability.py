from collections import defaultdict
from prop_hunter_shared_utils import select_rows, upsert_rows, safe_json_write, log, to_float, hash_key, now_iso

OUT="prop_hunter_source_trust.json"
def clamp(x): return max(0,min(100,x))
def main():
    snaps=select_rows("prop_hunter_prop_snapshots",limit=50000)
    res=select_rows("prop_hunter_results",limit=20000)
    clv=select_rows("prop_hunter_clv",limit=20000)
    st=defaultdict(lambda:{"snapshots":0,"results":0,"wins":0,"losses":0,"pushes":0,"clv_rows":0,"positive_clv":0})
    for s in snaps: st[s.get("source") or "unknown"]["snapshots"]+=1
    for r in res:
        src=(r.get("pick_raw") or {}).get("source") or (r.get("pick_raw") or {}).get("odds_source") or "unknown"
        st[src]["results"]+=1
        rr=str(r.get("result") or "").lower()
        if rr=="win": st[src]["wins"]+=1
        elif rr=="loss": st[src]["losses"]+=1
        elif rr=="push": st[src]["pushes"]+=1
    for c in clv:
        src=c.get("source") or "unknown"; st[src]["clv_rows"]+=1
        if (to_float(c.get("line_clv"),0) or 0)>0 or (to_float(c.get("odds_clv"),0) or 0)>0: st[src]["positive_clv"]+=1
    rows=[]
    for src,s in st.items():
        score=50+min(15,s["snapshots"]/1000*15)
        if s["results"]>=20:
            score+=(s["wins"]/max(1,s["results"]-s["pushes"])-.5)*30
        if s["clv_rows"]>=10:
            score+=(s["positive_clv"]/max(1,s["clv_rows"])-.5)*20
        rows.append({"trust_id":hash_key("trust",src),"source":src,"trust_score":round(clamp(score),2),**s,"updated_at":now_iso()})
    safe_json_write(OUT,rows); upsert_rows("prop_hunter_source_trust",rows,"trust_id")
    log(f"source trust done sources={len(rows)}")
if __name__=="__main__": main()
