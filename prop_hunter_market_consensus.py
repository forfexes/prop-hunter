#!/usr/bin/env python3
"""Cross-source/book market consensus and no-vig fair probabilities."""
from __future__ import annotations
import statistics,re
from collections import defaultdict
from datetime import datetime
from typing import Any,Dict,Iterable,Tuple
def _f(v):
    try:return float(v)
    except Exception:return None
def _norm(v):return re.sub(r"[^a-z0-9]+"," ",str(v or "").lower()).strip()
def _canon_market(v:Any)->str:
    s=_norm(v);checks=[(("points rebounds assists","points rebounds and assists","pra"),"pra"),(("total bases",),"total_bases"),(("home run","home runs"),"home_runs"),(("pitcher strikeout","pitcher strikeouts"),"pitcher_strikeouts"),(("strikeout","strikeouts"),"strikeouts"),(("rbi","rbis"),"rbi"),(("passing touchdown","pass tds","pass td"),"passing_touchdowns"),(("passing yards","pass yds"),"passing_yards"),(("rushing yards","rush yds"),"rushing_yards"),(("receiving yards","reception yds","receiving yds"),"receiving_yards"),(("receptions",),"receptions"),(("anytime td","anytime touchdown","touchdown scorer"),"anytime_td"),(("shots on goal","player shots"),"shots_on_goal"),(("goalie saves","player saves"),"goalie_saves"),(("three pointers","threes","3 pointers","3pm"),"threes"),(("rebounds",),"rebounds"),(("assists",),"assists"),(("points",),"points"),(("hits",),"hits"),(("goals",),"goals"),(("runs",),"runs")]
    for needles,out in checks:
        if any(n in s for n in needles):return out
    return s.replace(" ","_")
def _event_key(row:Dict[str,Any])->str:
    home=_norm(row.get("home_team"));away=_norm(row.get("away_team"));start=str(row.get("commence_time") or "");hour=""
    if start:
        try:hour=datetime.fromisoformat(start.replace("Z","+00:00")).strftime("%Y-%m-%dT%H")
        except Exception:hour=start[:13]
    if home or away:return f"{away}@{home}|{hour}"
    return str(row.get("source_event_id") or row.get("event_id") or row.get("game_id") or "")
def _base_key(row:Dict[str,Any])->Tuple[str,str,str,str,str]:
    line=_f(row.get("line"));return (str(row.get("sport") or row.get("league") or "").upper(),_event_key(row),_norm(row.get("player_name")),_canon_market(row.get("market_key") or row.get("market")),"" if line is None else f"{line:.4f}")
def _side(row):
    s=str(row.get("direction") or "").lower().strip();return "over" if s in {"yes","over","higher"} else "under" if s in {"no","under","lower"} else s
def _novig(o,u):
    try:a,b=1/float(o),1/float(u);t=a+b;return (a/t,b/t) if t>0 else (None,None)
    except Exception:return (None,None)
def enrich(rows:Iterable[Dict[str,Any]]):
    out=[dict(r) for r in (rows or []) if isinstance(r,dict)];groups=defaultdict(list)
    for r in out:
        d=_f(r.get("odds_decimal") or r.get("odds"));s=_side(r)
        if d and d>1 and s in {"over","under"}:groups[_base_key(r)].append((r,d,s))
    summaries={}
    for key,items in groups.items():
        books=defaultdict(dict);alls={"over":[],"under":[]};sources=set();quote_books=set();raw_pairs=[]
        for r,d,s in items:
            bk=str(r.get("bookmaker") or r.get("source") or "").lower().strip();src=str(r.get("source") or "").lower().strip()
            if src:sources.add(src)
            if bk:quote_books.add(bk);books[bk][s]=max(d,books[bk].get(s,0))
            alls[s].append(d);raw=r.get("raw") if isinstance(r.get("raw"),dict) else {};fp=_f(raw.get("paired_fair_prob"))
            if fp is not None and 0<fp<1:raw_pairs.append(fp if s=="over" else 1-fp)
        paired=[]
        for bk,pair in books.items():
            if pair.get("over") and pair.get("under"):
                po,pu=_novig(pair["over"],pair["under"])
                if po is not None:paired.append((bk,po,pu))
        if paired:fair_over=float(statistics.median([x[1] for x in paired]));method="paired_books"
        elif raw_pairs:fair_over=float(statistics.median(raw_pairs));method="provider_paired"
        elif alls["over"] and alls["under"]:
            a=float(statistics.median([1/x for x in alls["over"]]));b=float(statistics.median([1/x for x in alls["under"]]));t=a+b;fair_over=a/t if t>0 else None;method="cross_book_median"
        else:fair_over=None;method="unpaired"
        prices=[x[1] for x in items];summaries[key]={"quote_count":len(prices),"book_count":len(quote_books),"source_count":len(sources),"books":sorted(quote_books),"sources":sorted(sources),"paired_book_count":len(paired),"best_decimal":round(max(prices),4),"median_decimal":round(float(statistics.median(prices)),4),"fair_over":round(fair_over,6) if fair_over is not None else None,"fair_method":method}
    for r in out:
        sm=summaries.get(_base_key(r))
        if not sm:continue
        fair_over=sm.get("fair_over");side=_side(r);fair=fair_over if side=="over" else 1-fair_over if side=="under" and fair_over is not None else None;raw=dict(r.get("raw") or {}) if isinstance(r.get("raw"),dict) else {};cons=dict(sm);cons["fair_prob"]=round(float(fair),6) if fair is not None else None;raw["consensus"]=cons;r["raw"]=raw
    return out
def fair_prob_for(row):
    raw=row.get("raw") if isinstance(row.get("raw"),dict) else {};cons=raw.get("consensus") if isinstance(raw.get("consensus"),dict) else {};fp=_f(cons.get("fair_prob"));return fp if fp is not None and 0<fp<1 else None
