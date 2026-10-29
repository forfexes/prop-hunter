#!/usr/bin/env python3
"""PROP HUNTER — autonomous learning update.

Turns settled results into market/source/bookmaker performance and conservative
weights. Existing Supabase tables are used; no migration is required.

It also learns conservative same-game pair factors from already-settled builder
legs in picks_history.json. Those factors are consumed by prop_hunter_builder_engine
on later cards, closing the builder settlement -> learning -> next-card loop.
"""
from __future__ import annotations
from prop_hunter_basketball_boxscore import unobserved_log
from collections import defaultdict
import itertools
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple
from prop_hunter_shared_utils import select_rows, upsert_rows, safe_json_write, hash_key, now_iso, log, norm_market, to_float
from prop_hunter_builder_learning import market_group, pair_key


def _base_market(value: Any) -> str:
    import re
    m = norm_market(value)
    m = re.sub(r"\b(over|under|o|u|plus)\b", " ", m)
    m = re.sub(r"\d+(?:\s+\d+)?", " ", m)
    return re.sub(r"\s+", " ", m).strip() or "unknown"


def _profit(result: str, odds: float, stake: float) -> float:
    if result == "win": return stake * max(0.0, odds - 1.0)
    if result == "loss": return -stake
    return 0.0


def _weight(roi: float, n: int) -> float:
    reliability = min(1.0, max(0.0, (n - 10) / 90.0))
    signal = math.tanh(roi / 0.18)
    return round(max(0.70, min(1.30, 1.0 + 0.30 * signal * reliability)), 3)


def _accumulate(groups, key: Tuple[str, str], result: str, profit: float, stake: float):
    g = groups[key]
    g["bets"] += 1; g["stake"] += stake; g["profit"] += profit
    if result == "win": g["wins"] += 1
    elif result == "loss": g["losses"] += 1
    elif result == "push": g["pushes"] += 1


def _builder_leg_direction(leg: Dict[str, Any]) -> str:
    raw = str(leg.get("direction") or leg.get("side") or "").lower()
    return "under" if "under" in raw else "over"


def _builder_leg_key(leg: Dict[str, Any], combo: Dict[str, Any]) -> str:
    sport = str(leg.get("sport") or combo.get("sport") or "UNKNOWN").upper()
    market = market_group(leg.get("market") or leg.get("market_family") or "")
    return f"{sport}:{market}:{_builder_leg_direction(leg)}"


def _builder_leg_probability(leg: Dict[str, Any]):
    p = to_float(leg.get("probability"))
    if p is None:
        return None
    if p > 1:
        p /= 100.0
    return max(0.01, min(0.99, p)) if 0 < p < 1 else None


def learn_builder_correlations(history: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Learn bounded pair factors plus profile performance from settled SGPs."""
    closed = {"win", "won", "loss", "lost", "push"}
    pair_stats = defaultdict(lambda: {"n": 0, "both_wins": 0, "expected_sum": 0.0})
    profiles = defaultdict(lambda: {"n": 0, "wins": 0, "losses": 0, "pushes": 0, "stake": 0.0, "profit": 0.0})

    for entry in history or []:
        for combo in entry.get("kombis") or []:
            if not isinstance(combo, dict):
                continue
            if combo.get("settlement_invalidated"):
                continue
            status = str(combo.get("result") or "").lower()
            features = combo.get("features") if isinstance(combo.get("features"), dict) else {}
            profile = str(combo.get("builder_profile") or features.get("builder_profile") or "").lower()
            if profile and status in closed:
                p = profiles[profile]
                p["n"] += 1
                if status in {"win", "won"}: p["wins"] += 1
                elif status in {"loss", "lost"}: p["losses"] += 1
                else: p["pushes"] += 1
                p["stake"] += to_float(combo.get("stake"), 0.0) or 0.0
                p["profit"] += to_float(combo.get("profit"), 0.0) or 0.0

            legs = combo.get("settlement_legs") or combo.get("leg_details") or []
            legs = [x for x in legs if isinstance(x, dict)]
            for a, b in itertools.combinations(legs, 2):
                sa = str(a.get("result") or "").lower()
                sb = str(b.get("result") or "").lower()
                if sa not in closed or sb not in closed or "push" in {sa, sb}:
                    continue
                pa, pb = _builder_leg_probability(a), _builder_leg_probability(b)
                if pa is None or pb is None:
                    continue
                key = pair_key(_builder_leg_key(a, combo), _builder_leg_key(b, combo))
                rec = pair_stats[key]
                rec["n"] += 1
                rec["both_wins"] += int(sa in {"win", "won"} and sb in {"win", "won"})
                rec["expected_sum"] += pa * pb

    pairs = {}
    for key, rec in pair_stats.items():
        n = rec["n"]
        if not n:
            continue
        expected = max(0.01, min(0.99, rec["expected_sum"] / n))
        observed = rec["both_wins"] / n
        raw_ratio = max(0.60, min(1.35, observed / expected if expected else 1.0))
        reliability = max(0.0, min(1.0, (n - 8) / 72.0))
        factor = 1.0 + (raw_ratio - 1.0) * reliability
        factor = max(0.85, min(1.12, factor))
        pairs[key] = {
            "factor": round(factor, 4),
            "n": n,
            "both_wins": rec["both_wins"],
            "observed_joint": round(observed, 5),
            "expected_joint": round(expected, 5),
            "raw_ratio": round(raw_ratio, 4),
        }

    profile_out = {}
    for name, p in profiles.items():
        decided = p["wins"] + p["losses"]
        profile_out[name] = {
            **p,
            "stake": round(p["stake"], 4),
            "profit": round(p["profit"], 4),
            "hit_rate": round(p["wins"] / decided, 5) if decided else None,
            "roi": round(p["profit"] / p["stake"], 5) if p["stake"] else 0.0,
        }
    return {"version": 2, "pairs": pairs, "profiles": profile_out, "updated_at": now_iso()}


def _update_builder_learning() -> Dict[str, Any]:
    path = Path("picks_history.json")
    try:
        history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except Exception:
        history = []
    if not isinstance(history, list):
        history = []
    learned = learn_builder_correlations(history)
    safe_json_write("prop_hunter_builder_correlations.json", learned)
    return learned


def unique_results(rows):
    """A migrated result_id must never count a pick twice in learning."""
    from prop_hunter_quote_incidents import evidence_for
    newest = {}
    for row in sorted(rows, key=lambda r: str(r.get("settled_at") or ""), reverse=True):
        pick = row.get("pick_raw") or {}
        raw = pick.get("raw") if isinstance(pick.get("raw"), dict) else {}
        quoted = dict(raw, **pick)
        if evidence_for(quoted, pick.get("sent_date") or pick.get("date")):
            continue
        if unobserved_log(row.get("result_raw") or {}):
            continue
        if str(row.get("result") or "").lower() not in {"win", "loss", "push"}:
            continue
        key = row.get("pick_id") or row.get("result_id")
        if key:
            newest.setdefault(key, row)
    return list(newest.values())


def main():
    results = unique_results(select_rows("prop_hunter_results", limit=20000, order_by="settled_at", desc=True))
    audits = select_rows("prop_hunter_source_audit", limit=10000)
    groups = defaultdict(lambda: {"bets":0,"wins":0,"losses":0,"pushes":0,"profit":0.0,"stake":0.0})
    source_perf = defaultdict(lambda: {"bets":0,"wins":0,"losses":0,"pushes":0,"profit":0.0,"stake":0.0})

    for row in results:
        result = str(row.get("result") or "").lower()
        if result not in {"win","loss","push"}: continue
        raw = row.get("pick_raw") if isinstance(row.get("pick_raw"), dict) else {}
        sport = str(row.get("sport") or raw.get("sport") or "UNKNOWN").upper()
        league = str(row.get("league") or raw.get("league") or sport).upper()
        market = _base_market(row.get("market") or raw.get("market") or raw.get("prop_type"))
        source = str(raw.get("source") or raw.get("bookmaker") or raw.get("book") or "unknown").strip().lower()
        book = str(raw.get("bookmaker") or raw.get("book") or source).strip().lower()
        odds = to_float(raw.get("odds") or raw.get("odds_decimal"), 2.0) or 2.0
        stake = to_float(raw.get("stake"), 1.0) or 1.0
        profit = to_float(row.get("profit"), None)
        if profit is None: profit = _profit(result, odds, stake)
        _accumulate(groups, ("market", f"{sport}|{sport}|{market}"), result, profit, stake)
        if league and league != sport:
            _accumulate(groups, ("league_market", f"{sport}|{league}|{market}"), result, profit, stake)
        _accumulate(groups, ("sport_market", f"{sport}|{market}"), result, profit, stake)
        _accumulate(groups, ("bookmaker", f"{sport}|{book}|{market}"), result, profit, stake)
        _accumulate(source_perf, (source, "all"), result, profit, stake)

    perf_rows=[]
    report={}
    for (gtype,gkey), g in groups.items():
        n=g["bets"]; decided=g["wins"]+g["losses"]
        hit=(g["wins"]/decided) if decided else None
        roi=(g["profit"]/g["stake"]) if g["stake"] else 0.0
        w=_weight(roi,n)
        row={
            "performance_id":hash_key(gtype,gkey), "rule_id":gkey, "group_type":gtype, "group_key":gkey,
            "bets":n,"sample_size":n,"wins":g["wins"],"losses":g["losses"],"pushes":g["pushes"],
            "profit":round(g["profit"],4),"stake":round(g["stake"],4),"roi":round(roi,5),
            "hit_rate":round(hit,5) if hit is not None else None,"learning_weight":w,"learned_weight":w,"updated_at":now_iso(),
        }
        perf_rows.append(row); report[f"{gtype}:{gkey}"]=row
    upsert_rows("prop_hunter_rule_performance", perf_rows, "performance_id")
    safe_json_write("prop_hunter_autolearn_report.json", report)

    audit_by_source=defaultdict(lambda:{"ok":0,"bad":0,"lat":[]})
    for a in audits:
        if str(a.get("check_type") or a.get("section") or "").lower() != "source_health":
            continue
        s=str(a.get("source_name") or a.get("item_key") or "").strip().lower()
        if not s: continue
        st=str(a.get("status") or "").lower()
        if st in {"ok","healthy","success","active","cached"}: audit_by_source[s]["ok"] += 1
        elif st in {"error","failed","missing","dead","timeout","blocked","empty"}: audit_by_source[s]["bad"] += 1
        lat=to_float(a.get("latency_ms"))
        if lat is not None: audit_by_source[s]["lat"].append(lat)

    trust_rows=[]; trust_json={}
    all_sources=set(audit_by_source) | {k[0] for k in source_perf}
    for source in sorted(all_sources):
        p=source_perf.get((source,"all"), {"bets":0,"wins":0,"losses":0,"pushes":0,"profit":0.0,"stake":0.0})
        a=audit_by_source[source]
        checks=a["ok"]+a["bad"]
        success=(a["ok"]/checks) if checks else 0.75
        n=p["bets"]; roi=(p["profit"]/p["stake"]) if p["stake"] else 0.0
        sample=min(1.0,n/80.0)
        roi_score=50.0 + 45.0*math.tanh(roi/0.20)
        health_score=100.0*success
        trust=(1-sample)*health_score + sample*(0.45*health_score+0.55*roi_score)
        trust=max(5.0,min(100.0,trust))
        avg_lat=(sum(a["lat"])/len(a["lat"])) if a["lat"] else None
        row={"source_name":source,"trust_score":round(trust,2),"success_rate":round(success,4),
             "avg_latency_ms":round(avg_lat,1) if avg_lat is not None else None,"roi_units":round(p["profit"],4),
             "notes":"auto-learned; conservative until sample grows",
             "raw":{"settled_samples":n,"roi":round(roi,5),"wins":p["wins"],"losses":p["losses"],"checks":checks},
             "updated_at":now_iso()}
        trust_rows.append(row); trust_json[source]=row
    upsert_rows("prop_hunter_source_trust", trust_rows, "source_name")
    safe_json_write("prop_hunter_source_trust.json", trust_json)

    builder_learning = _update_builder_learning()
    log(
        f"learning update: results={len(results)} groups={len(perf_rows)} "
        f"sources={len(trust_rows)} builder_pairs={len(builder_learning.get('pairs',{}))}"
    )

if __name__ == "__main__": main()
