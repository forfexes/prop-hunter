#!/usr/bin/env python3
"""
PROP HUNTER DATA+ SCORING
Optional enrichment used by prophunter.py. Reads prop_hunter_data_cache.json.
Never crashes the main bot: all functions are defensive.
"""
from __future__ import annotations

import json, re, math
from pathlib import Path
from typing import Any, Dict, Optional


def load_data_cache(cache_file: str = "prop_hunter_data_cache.json") -> Dict[str, Any]:
    try:
        p = Path(cache_file)
        if not p.exists():
            return {}
        return json.loads(p.read_text())
    except Exception:
        return {}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def fuzzy_get(name: str, data: Dict[str, Any]) -> Optional[dict]:
    n = norm(name)
    if not n or not data:
        return None
    if n in data:
        return data[n]
    # cheap token match, no dependency
    n_tokens = set(n.split())
    best, score = None, 0.0
    for k, v in data.items():
        kt = set(norm(k).split())
        if not kt:
            continue
        inter = len(n_tokens & kt)
        union = len(n_tokens | kt)
        s = inter / union if union else 0
        if s > score:
            best, score = v, s
    return best if score >= 0.55 else None


def pct(x):
    try:
        return round(float(x) * 100, 1)
    except Exception:
        return None


def get_line_from_prop(prop) -> Optional[float]:
    try:
        if getattr(prop, "point", None) is not None:
            return float(prop.point)
    except Exception:
        pass
    text = f"{getattr(prop,'market','') or ''} {getattr(prop,'analysis','') or ''}"
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None


def market_kind(prop) -> str:
    m = (getattr(prop, "market", "") or "").lower()
    if "home run" in m or m == "hr" or " hr" in m:
        return "mlb_hr"
    if "hit" in m:
        return "mlb_hits"
    if "total base" in m:
        return "mlb_tb"
    if "strikeout" in m or "pitcher k" in m:
        return "mlb_k"
    if "rebounds+assists" in m or "reb+ast" in m:
        return "basket_ra"
    if "pra" in m or "points rebounds assists" in m:
        return "basket_pra"
    if "points" in m:
        return "basket_pts"
    return "other"


def mlb_data_probability(prop, cache: Dict[str, Any]) -> Optional[float]:
    batter = fuzzy_get(getattr(prop, "player", ""), cache.get("mlb_batting", {}))
    pitcher = None
    market = market_kind(prop)
    if not batter:
        return None
    line = get_line_from_prop(prop)
    if market == "mlb_hits":
        # conservative season hit chance proxy, adjusted for 1.5 hits lines
        avg = float(batter.get("avg") or 0)
        if line and line >= 1.5:
            # two-hit probability proxy; avoid overconfidence
            return max(0.20, min(0.62, avg * 1.55))
        return max(0.35, min(0.75, avg * 2.2))
    if market == "mlb_hr":
        hr_pa = float(batter.get("hr_per_pa") or 0)
        # HR prop usually yes/no; cap realistically
        return max(0.03, min(0.24, hr_pa * 4.5))
    if market == "mlb_tb":
        tb_ab = float(batter.get("tb_per_ab") or 0)
        if line and line >= 1.5:
            return max(0.25, min(0.65, tb_ab / 2.3))
        return max(0.35, min(0.72, tb_ab / 1.8))
    return None


def confidence_from(prob: Optional[float], edge: Optional[float], enrichment: str = "") -> Optional[int]:
    if prob is None:
        return None
    e = max(0.0, float(edge or 0.0))
    conf = 45 + prob * 45 + min(e, 12) * 1.3
    if enrichment:
        conf += min(8, len(enrichment.split("|")) * 1.5)
    return int(max(1, min(99, round(conf))))


def apply_data_plus_to_props(props, cache_file: str = "prop_hunter_data_cache.json"):
    cache = load_data_cache(cache_file)
    if not cache:
        return props
    for p in props:
        try:
            sport = (getattr(p, "sport", "") or "").upper()
            tags = []
            if sport == "MLB":
                b = fuzzy_get(getattr(p, "player", ""), cache.get("mlb_batting", {}))
                if b:
                    if b.get("avg") is not None: tags.append(f"AVG{b['avg']}")
                    if b.get("ops") is not None: tags.append(f"OPS{b['ops']}")
                    if b.get("hr") is not None: tags.append(f"HR{b['hr']}")
                    data_prob = mlb_data_probability(p, cache)
                    if data_prob is not None:
                        tags.append(f"DATA+{round(data_prob*100)}%")
                        old = getattr(p, "probability", None)
                        if old is None:
                            p.probability = data_prob
                        else:
                            # Blend AI probability with data proxy
                            p.probability = max(0.01, min(0.99, round(old * 0.65 + data_prob * 0.35, 3)))
                team = (getattr(p, "team", "") or "").lower()
                tc = fuzzy_get(team, cache.get("mlb_team_context", {})) if team else None
                if tc and tc.get("probable_pitcher"):
                    tags.append(f"vsSP {tc['probable_pitcher']}")
            elif sport in ("NBA", "WNBA", "NFL"):
                inj = fuzzy_get(getattr(p, "player", ""), cache.get(f"{sport.lower()}_injuries", {}))
                if inj and inj.get("status"):
                    tags.append(f"INJ:{inj.get('status')}")
                team = (getattr(p, "team", "") or "").lower()
                tc = fuzzy_get(team, cache.get(f"{sport.lower()}_team_context", {})) if team else None
                if tc:
                    if tc.get("opponent"): tags.append(f"vs {tc['opponent']}")
                    if tc.get("total"): tags.append(f"ESPN O/U{tc['total']}")
            if tags:
                existing = getattr(p, "enrichment", None) or ""
                p.enrichment = (existing + " | " if existing else "") + " | ".join(tags[:5])
            # update confidence if available
            prob = getattr(p, "probability", None)
            edge = getattr(p, "edge_pct", None)
            conf = confidence_from(prob, edge, getattr(p, "enrichment", "") or "")
            if conf is not None:
                p.features = getattr(p, "features", {}) or {}
                p.features["data_plus_confidence"] = conf
        except Exception:
            continue
    return props
