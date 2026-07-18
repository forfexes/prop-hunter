#!/usr/bin/env python3
"""
PROP HUNTER — DATA+ SCORING
===========================

Kompatible Zusatzdatei für prophunter.py.

Ziel:
- DATA+ Cache aus prop_hunter_data_cache.json nutzen
- MLB HR Picks besser bewerten
- MLB Hits / Total Bases leicht verbessern
- WNBA/NBA Props nicht zerstören, nur Features ergänzen
- Kein Crash, wenn Felder fehlen

Wichtig:
Diese Datei ersetzt/ergänzt nur prop_hunter_scoring.py.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional


def _norm_name(name: Any) -> str:
    s = str(name or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s\.\-']", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _to_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        if isinstance(x, str) and not x.strip():
            return default
        return float(x)
    except Exception:
        return default


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _set_feature(prop: Any, key: str, value: Any) -> None:
    try:
        feats = getattr(prop, "features", None)
        if feats is None:
            setattr(prop, "features", {})
            feats = getattr(prop, "features")
        if isinstance(feats, dict):
            feats[key] = value
    except Exception:
        pass


def _get_features(prop: Any) -> Dict[str, Any]:
    feats = _get(prop, "features", {}) or {}
    return feats if isinstance(feats, dict) else {}


def _player(prop: Any) -> str:
    return _norm_name(_get(prop, "player", ""))


def _market(prop: Any) -> str:
    return str(_get(prop, "market", "") or "").lower()


def _sport(prop: Any) -> str:
    return str(_get(prop, "sport", "") or "").upper()


def _odds_to_implied_prob(odds: Any) -> Optional[float]:
    o = _to_float(odds)
    if not o or o <= 1.01:
        return None
    return 1.0 / o


def _safe_prob(p: Optional[float]) -> Optional[float]:
    if p is None:
        return None
    return max(0.01, min(0.98, float(p)))


def _score_to_prob_delta(score: float, scale: float = 0.018, cap: float = 0.08) -> float:
    return max(-cap, min(cap, score * scale))


def _find_player_stats(player_name: str, data_map: Dict[str, Any]) -> Dict[str, Any]:
    if not player_name or not isinstance(data_map, dict):
        return {}
    n = _norm_name(player_name)
    if n in data_map and isinstance(data_map[n], dict):
        return data_map[n]

    # fuzzy-light: exact last name + first initial fallback
    parts = n.split()
    if not parts:
        return {}
    last = parts[-1]
    first_initial = parts[0][:1]
    for k, v in data_map.items():
        kk = _norm_name(k)
        kp = kk.split()
        if not kp:
            continue
        if kp[-1] == last and kp[0][:1] == first_initial and isinstance(v, dict):
            return v
    return {}


def _extract_mlb_maps(data_plus: Dict[str, Any]) -> Dict[str, Any]:
    mlb = (data_plus or {}).get("mlb", {}) if isinstance(data_plus, dict) else {}
    if not isinstance(mlb, dict):
        mlb = {}
    return {
        "batters": mlb.get("batters_basic", {}) or {},
        "pitchers": mlb.get("pitchers_basic", {}) or {},
        "team_k": mlb.get("team_k_rates", {}) or {},
    }


def _mlb_hr_score(prop: Any, data_plus: Dict[str, Any]) -> Dict[str, Any]:
    maps = _extract_mlb_maps(data_plus)
    batter = _find_player_stats(_player(prop), maps["batters"])

    # Batter metrics from scraper may vary by key names.
    ab = _to_float(batter.get("ab") or batter.get("AB") or batter.get("at_bats"), 0) or 0
    hr = _to_float(batter.get("hr") or batter.get("HR") or batter.get("home_runs"), 0) or 0
    slg = _to_float(batter.get("slg") or batter.get("SLG") or batter.get("slugging"), None)
    ops = _to_float(batter.get("ops") or batter.get("OPS"), None)

    hr_rate = (hr / ab) if ab and ab > 0 else None

    # Start neutral. Positive score means HR profile fits.
    score = 0.0
    reasons = []

    if hr_rate is not None:
        if hr_rate >= 0.075:
            score += 3.0
            reasons.append(f"starker HR/AB {hr_rate:.1%}")
        elif hr_rate >= 0.055:
            score += 2.0
            reasons.append(f"guter HR/AB {hr_rate:.1%}")
        elif hr_rate >= 0.040:
            score += 1.0
            reasons.append(f"okay HR/AB {hr_rate:.1%}")
        elif ab >= 40:
            score -= 1.2
            reasons.append(f"niedriger HR/AB {hr_rate:.1%}")

    if slg is not None:
        if slg >= 0.560:
            score += 2.0
            reasons.append(f"starke SLG {slg:.3f}")
        elif slg >= 0.480:
            score += 1.0
            reasons.append(f"solide SLG {slg:.3f}")
        elif slg < 0.380 and ab >= 40:
            score -= 1.0
            reasons.append(f"schwache SLG {slg:.3f}")

    if ops is not None:
        if ops >= 0.900:
            score += 1.2
            reasons.append(f"starke OPS {ops:.3f}")
        elif ops < 0.650 and ab >= 40:
            score -= 0.8
            reasons.append(f"tiefe OPS {ops:.3f}")

    # Odds context: HR odds 4.0+ need lower raw probability but positive profile.
    implied = _odds_to_implied_prob(_get(prop, "odds"))
    base_prob = implied
    if base_prob is not None:
        # Add model delta but don't create impossible probabilities.
        prob = _safe_prob(base_prob + _score_to_prob_delta(score, scale=0.012, cap=0.07))
    else:
        # Fallback from HR rate.
        if hr_rate is not None:
            prob = _safe_prob(min(0.30, max(0.08, hr_rate * 2.2)))
        else:
            prob = None

    return {
        "score": round(score, 3),
        "prob": prob,
        "hr_rate": hr_rate,
        "slg": slg,
        "ops": ops,
        "reasons": reasons[:4],
    }


def _mlb_hit_score(prop: Any, data_plus: Dict[str, Any]) -> Dict[str, Any]:
    maps = _extract_mlb_maps(data_plus)
    batter = _find_player_stats(_player(prop), maps["batters"])

    ab = _to_float(batter.get("ab") or batter.get("AB") or batter.get("at_bats"), 0) or 0
    hits = _to_float(batter.get("h") or batter.get("H") or batter.get("hits"), 0) or 0
    avg = _to_float(batter.get("avg") or batter.get("AVG") or batter.get("batting_avg"), None)
    obp = _to_float(batter.get("obp") or batter.get("OBP"), None)

    hit_rate = (hits / ab) if ab and ab > 0 else avg

    score = 0.0
    reasons = []

    if hit_rate is not None:
        if hit_rate >= 0.310:
            score += 2.0
            reasons.append(f"starker Hit-Rate {hit_rate:.3f}")
        elif hit_rate >= 0.270:
            score += 1.0
            reasons.append(f"solider Hit-Rate {hit_rate:.3f}")
        elif hit_rate < 0.220 and ab >= 40:
            score -= 1.0
            reasons.append(f"tiefer Hit-Rate {hit_rate:.3f}")

    if obp is not None:
        if obp >= 0.370:
            score += 1.0
            reasons.append(f"starke OBP {obp:.3f}")
        elif obp < 0.290 and ab >= 40:
            score -= 0.6
            reasons.append(f"tiefe OBP {obp:.3f}")

    implied = _odds_to_implied_prob(_get(prop, "odds"))
    if implied is not None:
        prob = _safe_prob(implied + _score_to_prob_delta(score, scale=0.015, cap=0.05))
    else:
        prob = None

    return {
        "score": round(score, 3),
        "prob": prob,
        "hit_rate": hit_rate,
        "reasons": reasons[:4],
    }



def _is_direct_underdog(prop: Any) -> bool:
    feats = _get_features(prop)
    source = str(feats.get("source") or _get(prop, "source", "") or "").lower()
    bookmaker = str(feats.get("bookmaker") or _get(prop, "bookmaker", "") or source).lower()
    return (
        source == "underdog"
        and bookmaker == "underdog"
        and feats.get("direct_source_line") is True
        and feats.get("source_payload_observed") is True
        and str(feats.get("price_type") or "").lower() == "fantasy_fixed"
    )


def _poisson_cdf(k: int, mean: float) -> float:
    """P(X <= k) without scipy; stable for the prop-size means used here."""
    if k < 0:
        return 0.0
    mean = max(0.000001, float(mean))
    term = math.exp(-mean)
    total = term
    for i in range(1, int(k) + 1):
        term *= mean / i
        total += term
    return max(0.0, min(1.0, total))


def _poisson_sides(mean: float, line: float) -> Dict[str, float]:
    line = float(line)
    over_min = math.floor(line) + 1
    under_max = math.ceil(line) - 1
    over = 1.0 - _poisson_cdf(over_min - 1, mean)
    under = _poisson_cdf(under_max, mean)
    return {"over": max(0.0, min(1.0, over)), "under": max(0.0, min(1.0, under))}


def _mlb_pickem_season_score(prop: Any, data_plus: Dict[str, Any]) -> Dict[str, Any]:
    """Conservative season-rate fallback for direct Underdog MLB lines.

    It never treats the configured 1.85 card reference as a sportsbook quote.
    The estimate comes only from official MLB season totals in DATA+.
    """
    if not _is_direct_underdog(prop) or _sport(prop) != "MLB":
        return {"score": 0.0, "prob": None, "reasons": []}

    line = _to_float(_get(prop, "point", None), None)
    if line is None:
        return {"score": 0.0, "prob": None, "reasons": []}

    maps = _extract_mlb_maps(data_plus)
    batter = _find_player_stats(_player(prop), maps["batters"])
    pitcher = _find_player_stats(_player(prop), maps["pitchers"])
    market = _market(prop)

    # Period/fantasy-only lines cannot be derived honestly from season box-score totals.
    if any(token in market for token in (
        "fantasy point", "1st inning", "first inning", "first 5", "first five",
        "first plate appearance", "plate appearance result",
    )):
        return {"score": 0.0, "prob": None, "reasons": []}

    mean = None
    sample = 0
    label = ""

    pitcher_market = bool(
        pitcher and (
            "pitcher" in market or "pitching" in market or "allowed" in market
            or "outs recorded" in market or "earned run" in market
        )
    )
    if pitcher_market:
        sample = int(_to_float(pitcher.get("starts"), 0) or _to_float(pitcher.get("games"), 0) or 0)
        denom = float(sample or 0)
        if denom > 0:
            if "strikeout" in market or re.search(r"\bks?\b", market):
                mean = (_to_float(pitcher.get("strikeouts"), 0) or 0) / denom
                label = "Pitcher K"
            elif "outs" in market:
                innings = _to_float(pitcher.get("innings"), None)
                if innings is not None:
                    mean = (innings * 3.0) / denom
                    label = "Pitching Outs"
            elif "hits allowed" in market:
                mean = (_to_float(pitcher.get("hits_allowed"), 0) or 0) / denom
                label = "Hits Allowed"
            elif "earned run" in market:
                mean = (_to_float(pitcher.get("earned_runs"), 0) or 0) / denom
                label = "Earned Runs"
            elif "walk" in market:
                mean = (_to_float(pitcher.get("walks"), 0) or 0) / denom
                label = "Pitcher Walks"
    elif batter:
        sample = int(_to_float(batter.get("games"), 0) or 0)
        denom = float(sample or 0)
        if denom > 0:
            hits = _to_float(batter.get("hits") or batter.get("h"), 0) or 0
            total_bases = _to_float(batter.get("total_bases"), 0) or 0
            home_runs = _to_float(batter.get("hr") or batter.get("home_runs"), 0) or 0
            runs = _to_float(batter.get("runs"), 0) or 0
            rbi = _to_float(batter.get("rbi"), 0) or 0
            walks = _to_float(batter.get("walks"), 0) or 0
            strikeouts = _to_float(batter.get("strikeouts"), 0) or 0
            stolen = _to_float(batter.get("stolen_bases"), 0) or 0
            if "hits plus runs plus rbi" in market or "hits runs rbi" in market or "h+r+rbi" in market:
                mean = (hits + runs + rbi) / denom
                label = "H+R+RBI"
            elif "total base" in market:
                mean = total_bases / denom
                label = "Total Bases"
            elif "home run" in market or re.search(r"\bhrs?\b", market):
                mean = home_runs / denom
                label = "Home Runs"
            elif "batter strikeout" in market or ("strikeout" in market and not pitcher):
                mean = strikeouts / denom
                label = "Batter K"
            elif "walk" in market:
                mean = walks / denom
                label = "Batter Walks"
            elif "stolen base" in market:
                mean = stolen / denom
                label = "Stolen Bases"
            elif re.search(r"\brbis?\b", market) or "runs batted" in market:
                mean = rbi / denom
                label = "RBI"
            elif "hit" in market:
                mean = hits / denom
                label = "Hits"
            elif "run" in market:
                mean = runs / denom
                label = "Runs"

    min_sample = 5 if pitcher_market else 12
    if mean is None or mean < 0 or sample < min_sample:
        return {"score": 0.0, "prob": None, "reasons": []}

    sides = _poisson_sides(mean, line)
    direction = "over" if sides["over"] >= sides["under"] else "under"
    raw = sides[direction]

    # Season-only evidence is useful but deliberately shrunk and capped.
    if pitcher_market:
        model_weight = min(0.68, 0.34 + sample * 0.035)
    else:
        model_weight = min(0.72, 0.30 + sample * 0.005)
    prob = 0.50 + (raw - 0.50) * model_weight
    prob = max(0.01, min(0.68, prob))

    return {
        "score": round((prob - 0.50) * 100.0, 3),
        "prob": round(prob, 4),
        "direction": direction,
        "sample": sample,
        "mean": round(mean, 4),
        "raw_probability": round(raw, 4),
        "reasons": [f"{label} Saison Ø {mean:.2f} über {sample} Spiele/Starts"],
    }

def _basket_context_score(prop: Any, data_plus: Dict[str, Any]) -> Dict[str, Any]:
    # Aktuell bewusst konservativ: nur Marker, keine aggressiven Änderungen.
    sport = _sport(prop)
    m = _market(prop)
    reasons = []
    score = 0.0

    # Lines are important for WNBA/NBA picks.
    point = _get(prop, "point", None)
    if sport in ("NBA", "WNBA"):
        if point is None:
            score -= 2.0
            reasons.append("Basket ohne Line")
        else:
            score += 0.3
            reasons.append("Basket Line vorhanden")

    return {
        "score": round(score, 3),
        "prob": None,
        "reasons": reasons[:3],
    }


def _apply_prob_if_better(prop: Any, new_prob: Optional[float], tag: str) -> None:
    if new_prob is None:
        return
    feats = _get_features(prop)
    old = feats.get("fair_prob")
    oldf = _to_float(old, None)
    if oldf is None:
        _set_feature(prop, "fair_prob", round(new_prob, 4))
        _set_feature(prop, "fair_prob_source", tag)
        return

    # Blend instead of overwrite. This avoids one DATA+ metric dominating odds/model.
    blended = (oldf * 0.70) + (new_prob * 0.30)
    _set_feature(prop, "fair_prob", round(_safe_prob(blended), 4))
    _set_feature(prop, "fair_prob_source", f"{feats.get('fair_prob_source','base')}+{tag}")


def apply_data_plus_to_props(props: List[Any], data_plus: Optional[Dict[str, Any]] = None) -> List[Any]:
    """
    Hauptfunktion, die von prophunter.py importiert wird.

    Gibt die gleiche props-Liste zurück, ergänzt aber Features:
    - data_plus_score
    - data_plus_reasons
    - fair_prob / fair_prob_source
    - market-specific tags
    """
    data_plus = data_plus or {}
    out = []

    for p in props or []:
        try:
            sport = _sport(p)
            market = _market(p)
            result = {"score": 0.0, "prob": None, "reasons": []}
            tag = "data_plus"

            if sport == "MLB" and _is_direct_underdog(p):
                result = _mlb_pickem_season_score(p, data_plus)
                tag = "mlb_season_poisson"
                if result.get("direction"):
                    try:
                        setattr(p, "direction", result["direction"])
                    except Exception:
                        pass
                    _set_feature(p, "pickem_direction", result["direction"])
                _set_feature(p, "model_sample", result.get("sample"))
                _set_feature(p, "sample_size", result.get("sample"))
                _set_feature(p, "season_mean", result.get("mean"))
                _set_feature(p, "season_raw_probability", result.get("raw_probability"))
            elif sport == "MLB" and ("home run" in market or re.search(r"\bhr\b", market)):
                result = _mlb_hr_score(p, data_plus)
                tag = "mlb_hr_data_plus"
                _set_feature(p, "mlb_hr_score", result.get("score"))
                _set_feature(p, "mlb_hr_rate", result.get("hr_rate"))
                _set_feature(p, "mlb_slg", result.get("slg"))
                _set_feature(p, "mlb_ops", result.get("ops"))
            elif sport == "MLB" and ("hit" in market or "total base" in market or "bases" in market):
                result = _mlb_hit_score(p, data_plus)
                tag = "mlb_hit_data_plus"
                _set_feature(p, "mlb_hit_score", result.get("score"))
                _set_feature(p, "mlb_hit_rate", result.get("hit_rate"))
            elif sport in ("NBA", "WNBA"):
                result = _basket_context_score(p, data_plus)
                tag = "basket_data_plus"

            _set_feature(p, "data_plus_score", result.get("score", 0.0))
            _set_feature(p, "data_plus_reasons", result.get("reasons", []))
            _apply_prob_if_better(p, result.get("prob"), tag)

            # Short enrichment text for Telegram analysis fallback.
            reasons = result.get("reasons") or []
            if reasons:
                old_enrich = _get(p, "enrichment", "") or ""
                msg = "DATA+: " + "; ".join(reasons[:3])
                if not old_enrich:
                    try:
                        setattr(p, "enrichment", msg)
                    except Exception:
                        pass
                elif "DATA+:" not in str(old_enrich):
                    try:
                        setattr(p, "enrichment", (str(old_enrich) + " | " + msg)[:240])
                    except Exception:
                        pass

        except Exception as e:
            try:
                _set_feature(p, "data_plus_error", str(e)[:120])
            except Exception:
                pass

        out.append(p)

    return out
