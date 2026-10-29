#!/usr/bin/env python3
"""Real-line autonomous ladder and builder engine.

Unlike the former fallback, this engine never invents alternate lines or odds.
Ladders are built only from independently observed source rows. Builders use the
learned empirical pair factors and require positive joint EV.
"""
from __future__ import annotations

import itertools
import math
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from prop_hunter_builder_learning import market_group, pair_key
except Exception:
    def market_group(market):
        s = re.sub(r"\s+(over|under)\s+[-+]?\d+(?:\.\d+)?", "", str(market or "").lower()).strip()
        aliases = {"3-pt made":"three_pointers_made","3pm":"three_pointers_made","home run":"home_runs"}
        return aliases.get(s, s.replace(" ", "_"))
    def pair_key(a, b):
        return "|".join(sorted((str(a), str(b))))
from prop_hunter_shared_utils import safe_json_load, to_float

CORR_FILE = "prop_hunter_builder_correlations.json"


def _prob(p: Any) -> float:
    value = to_float(getattr(p, "probability", None), 0.0) or 0.0
    return max(0.01, min(0.99, value))


def _odds(p: Any) -> float:
    return to_float(getattr(p, "odds", None), 0.0) or 0.0


def _features(obj: Any) -> Dict[str, Any]:
    value = getattr(obj, "features", None)
    return value if isinstance(value, dict) else {}


def _real_price(obj: Any) -> bool:
    feats = _features(obj)
    explicit = feats.get("odds_observed")
    if explicit is not None:
        return bool(explicit)
    return str(feats.get("price_type") or "").lower() in {"bookmaker", "observed", "exchange"}


def _book(obj: Any) -> str:
    feats = _features(obj)
    return str(
        feats.get("bookmaker") or feats.get("book") or
        getattr(obj, "bookmaker", None) or ""
    ).strip().lower()


def _point(obj: Any) -> Optional[float]:
    value = getattr(obj, "point", None)
    if value is None:
        value = getattr(obj, "line", None)
    parsed = to_float(value)
    if parsed is not None:
        return parsed

    # Some books expose TD ladders as separate yes/no markets instead of a numeric
    # handicap (Anytime TD, 2+ TD, 3+ TD). Convert only those explicit thresholds
    # to settlement-equivalent half-lines; no price or missing rung is invented.
    feats = _features(obj)
    text = " ".join(str(x or "") for x in (
        getattr(obj, "market", None), getattr(obj, "selection", None),
        feats.get("selection"), feats.get("market_original"),
    )).lower()
    if "td" in text or "touchdown" in text:
        if "anytime" in text:
            return 0.5
        m = re.search(r"\b(\d+)\s*(?:\+|plus\b|or\s+more\b)", text)
        if not m:
            m = re.search(r"\b(\d+)\s*(?:tds?|touchdowns?)\b", text)
        if m:
            return max(0.5, float(m.group(1)) - 0.5)
    return None


def _direction(obj: Any) -> str:
    explicit = getattr(obj, "direction", None)
    if explicit: return str(explicit).lower()
    return "under" if "under" in str(getattr(obj, "market", "")).lower() else "over"


def _base_market(text: Any) -> str:
    s = str(text or "").lower()
    s = s.replace("+", " plus ")
    s = re.sub(r"\b(over|under|more|less|yes|no)\b", " ", s)
    s = re.sub(r"\b\d+(?:\.\d+)?\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    # Canonicalize touchdown ladders so Anytime TD / 1+ TD / 2+ TD / 3+ TD
    # can be grouped for the same player, while pass/rush/receiving TDs remain separate.
    if re.search(r"\b(pass|passing)\b", s) and re.search(r"\b(td|tds|touchdown|touchdowns)\b", s):
        return "passing touchdowns"
    if re.search(r"\b(receiv|receiving)\w*\b", s) and re.search(r"\b(td|tds|touchdown|touchdowns)\b", s):
        return "receiving touchdowns"
    if re.search(r"\b(rush|rushing)\w*\b", s) and re.search(r"\b(td|tds|touchdown|touchdowns)\b", s):
        return "rushing touchdowns"
    if "anytime td" in s or "anytime touchdown" in s or re.search(r"\b(td|tds|touchdown|touchdowns)\b", s):
        return "touchdowns"
    return s.replace(" plus ", " ").strip()


def _player(obj: Any) -> str:
    return str(getattr(obj, "player", None) or getattr(obj, "player_name", None) or "").strip()


def _game(obj: Any) -> str:
    return str(getattr(obj, "game", None) or getattr(obj, "game_id", None) or getattr(obj, "source_event_id", None) or "").strip()


def _sport(obj: Any) -> str:
    feats = _features(obj)
    return str(
        getattr(obj, "sport", None)
        or getattr(obj, "source_sport", None)
        or getattr(obj, "league", None)
        or feats.get("sport")
        or feats.get("source_sport")
        or feats.get("league")
        or "UNKNOWN"
    ).upper()


def _is_hr(obj: Any) -> bool:
    market = _base_market(getattr(obj, "market", ""))
    return "home run" in market or bool(re.search(r"\bhr\b", market))


def _plausible_ladder_line(obj: Any) -> bool:
    """Reject feed-misaligned alternate lines before ladder construction."""
    point = _point(obj)
    if point is None or point < 0:
        return False
    market = _base_market(getattr(obj, "market", ""))
    caps = (
        (("passing yards",), 450.5),
        (("rushing yards", "receiving yards"), 200.5),
        (("receptions",), 15.5),
        (("passing touchdowns",), 5.5),
        (("rushing touchdowns", "receiving touchdowns", "touchdowns"), 3.5),
        (("shots on goal",), 12.5),
        (("goalie saves",), 60.5),
        (("home run",), 2.5),
        (("hits",), 4.5),
        (("total bases",), 10.5),
        (("rbi",), 6.5),
        (("pitcher strikeouts",), 15.5),
        (("rebounds",), 30.5),
        (("assists",), 25.5),
        (("three pointers", "threes"), 15.5),
        (("points",), 65.5),
    )
    for needles, cap in caps:
        if any(n in market for n in needles):
            return point <= cap
    return point <= 500.5


def _candidate_probability(obj: Any) -> Optional[float]:
    """Return a conservative calibrated probability for a real bookmaker row."""
    odds = _odds(obj)
    if odds <= 1.01 or not _real_price(obj):
        return None

    feats = _features(obj)
    raw_prob = None
    for key in (
        "calibrated_prob", "fair_prob", "model_prob", "hit_prob",
        "proj_prob", "probability", "gamelog_fair_prob",
    ):
        value = feats.get(key)
        if value is not None:
            raw_prob = to_float(value)
            if raw_prob is not None:
                break
    if raw_prob is None:
        raw_prob = to_float(getattr(obj, "probability", None))
    if raw_prob is None:
        return None

    raw_prob = max(0.01, min(0.99, raw_prob))
    implied = max(0.01, min(0.99, 1.0 / odds))
    sample = int(to_float(feats.get("gamelog_n") or feats.get("sample_size"), 0) or 0)
    consensus = int(to_float(feats.get("consensus_sources"), 0) or 0)

    weight = min(0.68, 0.30 + sample / 80.0 + min(consensus, 4) * 0.04)
    probability = implied * (1.0 - weight) + raw_prob * weight
    probability = min(0.40 if _is_hr(obj) else 0.86, probability)
    return round(max(0.01, probability), 4)


def _candidate_key(obj: Any) -> Tuple[str, str, str, str, str]:
    point = _point(obj)
    return (
        _player(obj).lower(),
        _base_market(getattr(obj, "market", "")),
        _direction(obj),
        f"{point:g}" if point is not None else "",
        _book(obj),
    )


def _candidate_from_prop(prop: Any, PickCls: Any) -> Optional[Any]:
    """Create a positive-EV candidate only from a verified bookmaker row."""
    probability = _candidate_probability(prop)
    odds = _odds(prop)
    if probability is None or odds <= 1.01:
        return None

    edge = probability * odds - 1.0
    minimum_edge = 0.04 if _is_hr(prop) else 0.018
    if edge < minimum_edge:
        return None

    category = "hr_risk" if _is_hr(prop) else "verified_pool"
    fraction = 0.08 if _is_hr(prop) else 0.16
    cap = 0.18 if _is_hr(prop) else 0.35
    stake = _kelly(probability, odds, fraction, cap)
    if stake <= 0:
        stake = 0.05 if _is_hr(prop) else 0.10
    if _is_hr(prop):
        stake = max(0.05, stake)

    point = _point(prop)
    direction = _direction(prop)
    market = _base_market(getattr(prop, "market", "")).title()
    if point is not None and not _is_hr(prop):
        market = f"{market} {direction.title()} {point:g}"
    elif _is_hr(prop):
        if point is not None and float(point) > 0.5:
            frac = abs(float(point) - math.floor(float(point)))
            market = (
                f"{int(math.floor(float(point)) + 1)}+ Home Runs"
                if abs(frac - 0.5) < 1e-9
                else f"Home Runs {direction.title()} {float(point):g}"
            )
        else:
            market = "Home Run"

    features = dict(_features(prop))
    features["odds_observed"] = True
    features["price_type"] = "bookmaker"

    pick = PickCls(
        type="single",
        category=category,
        tier=1,
        player=_player(prop),
        team=getattr(prop, "team", "") or "",
        emoji=getattr(prop, "emoji", "⚾" if _is_hr(prop) else "🎯") or "🎯",
        market=market,
        direction="over" if _is_hr(prop) else direction,
        odds=round(odds, 2),
        stake=round(stake, 2),
        probability=probability,
        edge_pct=round(edge * 100.0, 1),
        ev=round(edge, 4),
        game=_game(prop),
        analysis=(
            f"Verifizierte {_book(prop)} Quote · "
            f"kalibrierte Modellprob {probability*100:.1f}%"
        ),
    )
    pick.point = point
    pick.features = features
    pick.odds_observed = True
    pick.sport = _sport(prop)
    return pick


def _leg_text(p: Any) -> str:
    line = _point(p)
    direction = _direction(p).title()
    market = _base_market(getattr(p, "market", "")).title()
    suffix = f" {direction} {line:g}" if line is not None else ""
    return f"{_player(p)} {market}{suffix} @{_odds(p):.2f}".strip()


def _kelly(prob: float, odds: float, fraction: float, cap: float) -> float:
    if odds <= 1: return 0.0
    full = (prob * odds - 1) / (odds - 1)
    return max(0.0, min(cap, full * fraction))


def _pair_factor(a: Any, b: Any, pairs: Dict[str, Any]) -> Tuple[float, int]:
    sport = _sport(a) if _sport(a) != "UNKNOWN" else _sport(b)
    ka = f"{sport}:{market_group(getattr(a, 'market', ''))}:{_direction(a)}"
    kb = f"{sport}:{market_group(getattr(b, 'market', ''))}:{_direction(b)}"
    info = pairs.get(pair_key(ka, kb)) or {}
    return float(info.get("factor", 1.0)), int(info.get("n", 0))


def _joint_probability(legs: Sequence[Any], pairs: Dict[str, Any]) -> Tuple[float, float, int]:
    independent = math.prod(_prob(x) for x in legs)
    factors, samples = [], []
    for a, b in itertools.combinations(legs, 2):
        factor, n = _pair_factor(a, b, pairs)
        factors.append(factor); samples.append(n)
    corr = math.prod(factors) ** (1 / len(factors)) if factors else 1.0
    # Conservative: learned positive correlation receives only half weight.
    adjusted = independent * (1.0 + (corr - 1.0) * 0.5)
    return max(0.002, min(0.97, adjusted)), corr, min(samples) if samples else 0


def _valid_combo(legs: Sequence[Any]) -> bool:
    # Temporary product rule: builders are OVER-only until explicitly re-enabled.
    # Singles/ladders keep their normal observed-side logic.
    if any(_direction(x) != "over" for x in legs):
        return False
    players = [_player(x).lower() for x in legs]
    if len(set(players)) != len(players):
        return False
    keys = [(_player(x).lower(), _base_market(getattr(x, "market", "")), _direction(x)) for x in legs]
    if len(set(keys)) != len(keys):
        return False
    if not all(_odds(x) > 1 and _prob(x) > 0 and _real_price(x) for x in legs):
        return False
    # A displayed builder must be placeable at one bookmaker.
    books = {_book(x) for x in legs}
    if len(books) != 1 or "" in books:
        return False

    games = {_game(x) for x in legs if _game(x)}
    same_game = len(games) == 1
    book = next(iter(books))
    if same_game and book == "bet365":
        # Bet365 builders are strict observed-selection only. A generic/API bet365
        # quote is not proof that the same side is selectable in Bet Builder.
        # The public bet365 adapter marks an actually observed BB selection.
        if not all(
            bool(_features(x).get("bet_builder"))
            and str(_features(x).get("source") or "").lower() in {"bet365","browser_bet365","bet365_browser"}
            for x in legs
        ):
            return False
    return True


def _display_line(base: str, direction: str, point: float, original_market: str = "") -> str:
    """Human-friendly ladder label without changing settlement semantics."""
    low = str(original_market or "").lower()
    if direction == "over":
        # A half-point over is exactly equivalent to the next integer threshold,
        # e.g. O9.5 == 10+. Keep integer lines as O10 unless source itself says 10+.
        frac = abs(float(point) - int(float(point)))
        if abs(frac - 0.5) < 1e-9:
            return f"{int(math.floor(float(point)) + 1)}+ {base.title()}"
        if "+" in low:
            return f"{int(point) if float(point).is_integer() else point:g}+ {base.title()}"
    return f"{base.title()} {direction.title()} {point:g}"


def _wilson_l15_lower_bound(hits: int, games: int) -> float:
    """One-sided 90% Wilson lower bound on observed line-specific hit probability."""
    if games <= 0 or hits < 0 or hits > games:
        return 0.0
    z = 1.2815515655446004
    rate = hits / games
    z2 = z * z
    denominator = 1.0 + z2 / games
    center = rate + z2 / (2.0 * games)
    margin = z * math.sqrt(rate * (1.0 - rate) / games + z2 / (4.0 * games * games))
    return max(0.0, (center - margin) / denominator)


def _ladder_leg_candidate(prop: Any) -> Optional[Dict[str, Any]]:
    """Fail-closed ladder leg with independent exact-L15 evidence and conservative EV."""
    if not _real_price(prop) or not _plausible_ladder_line(prop):
        return None
    point, odds = _point(prop), _odds(prop)
    if point is None or odds <= 1.01 or _direction(prop) not in {"over", "under"}:
        return None
    feats = _features(prop)
    if feats.get("gamelog_prob_rejected"):
        return None

    # The old gamelog_l15_rate is smoothed/clipped, NOT a real hit count.
    # Never use bookmaker implied probability as a substitute for missing games.
    n_raw = to_float(feats.get("gamelog_l15_n"))
    hits_raw = to_float(feats.get("gamelog_l15_hits"))
    verified_line = to_float(feats.get("gamelog_l15_line"))
    verified_side = str(feats.get("gamelog_l15_direction") or "").lower()
    if any(x is None or not math.isfinite(x) for x in (n_raw, hits_raw, verified_line)):
        return None
    n, hits = int(n_raw), int(hits_raw)
    if (n_raw != n or hits_raw != hits or n < 10 or n > 15
            or hits < 2 or hits > n or abs(point - verified_line) > 1e-6
            or verified_side != _direction(prop)):
        return None

    model_probability = _candidate_probability(prop)
    if model_probability is None:
        return None
    # The model can mix bookmaker price and smoothed estimates. A price-independent
    # confidence lower bound caps the estimate used for EV/staking.
    conservative_probability = _wilson_l15_lower_bound(hits, n)
    probability = min(model_probability, conservative_probability)
    edge = probability * odds - 1.0
    if edge < 0.03:
        return None

    fraction = 0.15 if odds < 4 else 0.10 if odds < 8 else 0.06
    cap = 0.40 if odds < 3 else 0.25 if odds < 6 else 0.12
    # No forced minimum stake: a marginal or longshot estimate is never
    # upgraded into a large position just to make the Telegram ticket visible.
    stake = _kelly(probability, odds, fraction, cap)
    if stake < 0.005:
        return None
    return {
        "prop": prop, "point": point, "odds": odds,
        "probability": round(probability, 4),
        "edge": round(edge, 6),
        "stake": round(min(stake, 1.0), 2),
        "gamelog_l15_hits": hits, "gamelog_l15_n": n,
    }

def _real_ladders(props: Iterable[Any], PickCls: Any, LadderLegCls: Any, selected: Sequence[Any] = ()) -> List[Any]:
    """Build every verified same-player/same-book ladder with >=2 +EV rungs.

    Important: exact alternate lines remain distinct. We do not collapse 10+/15+/20+
    into one pick and we do not invent missing rungs or prices.
    """
    selected_keys = {
        (_player(p).lower(), _base_market(getattr(p, "market", "")), _direction(p))
        for p in (selected or [])
        if _player(p) and _base_market(getattr(p, "market", ""))
    }
    grouped: Dict[Tuple[str, str, str, str, str], List[Any]] = {}
    for p in props or []:
        if not _real_price(p):
            continue
        player = _player(p).lower()
        book = _book(p)
        base = _base_market(getattr(p, "market", ""))
        direction = _direction(p)
        game = _game(p)
        if not player or not book or not base or _point(p) is None:
            continue
        # NHL/NFL alternate lines are dedicated ladder lanes. A strong ladder
        # must not disappear merely because another market won the player's Single slot.
        sport = _sport(p)
        dedicated_ladder = (
            sport == "NHL" and any(x in base for x in ("shots on goal", "goalie saves", "points", "assists", "goals"))
        ) or (
            sport == "NFL" and any(x in base for x in (
                "passing yards", "rushing yards", "receiving yards", "receptions",
                "passing touchdowns", "rushing touchdowns", "receiving touchdowns", "touchdowns"
            ))
        )
        if selected_keys and (player, base, direction) not in selected_keys and not dedicated_ladder:
            continue
        grouped.setdefault((player, base, direction, book, game), []).append(p)

    ladders: List[Any] = []
    for (_player_key, base, direction, book, game), rows in grouped.items():
        # Same line at same book: retain best observed price, but never merge different lines.
        unique: Dict[float, Any] = {}
        for row in rows:
            point = _point(row)
            if point is None:
                continue
            prev = unique.get(float(point))
            if prev is None or _odds(row) > _odds(prev):
                unique[float(point)] = row

        legs = []
        for point, row in unique.items():
            candidate = _ladder_leg_candidate(row)
            if candidate:
                legs.append(candidate)
        if len(legs) < 2:
            continue

        # Natural ladder order: safer threshold first for overs, reverse for unders.
        legs.sort(key=lambda x: x["point"], reverse=(direction == "under"))

        # A harder rung must not become materially shorter-priced than the easier rung.
        # Tiny feed/rounding noise is tolerated; obvious inversions are dropped.
        monotonic = []
        for item in legs:
            if monotonic and item["odds"] < monotonic[-1]["odds"] * 0.95:
                continue
            monotonic.append(item)
        legs = monotonic
        if len(legs) < 2:
            continue

        # Keep ladders readable and actionable. Every rung is still a real observed
        # bookmaker line, but dozens of alt-lines for one player add noise rather
        # than a distinct betting idea. Preserve easy/hard endpoints plus the best
        # intermediate +EV rungs.
        max_rungs = max(2, min(6, int(os.getenv("PH_MAX_LADDER_RUNGS", "4"))))
        if len(legs) > max_rungs:
            endpoints = [legs[0], legs[-1]]
            middle = sorted(
                legs[1:-1],
                key=lambda x: (x["edge"], x["probability"]),
                reverse=True,
            )[:max_rungs-2]
            keep_ids = {id(x) for x in endpoints + middle}
            legs = [x for x in legs if id(x) in keep_ids]

        ladder_legs = []
        leg_details = []
        for item in legs:
            row = item["prop"]
            label = _display_line(base, direction, item["point"], getattr(row, "market", ""))
            ladder_legs.append(LadderLegCls(
                market=label, odds=round(item["odds"], 2), stake=item["stake"],
                point=item["point"], direction=direction,
                probability=item["probability"], edge_pct=round(item["edge"] * 100, 1),
                bookmaker=book,
            ))
            leg_details.append({
                "player": _player(row), "sport": _sport(row), "market": label,
                "source_market": getattr(row, "market", ""), "direction": direction,
                "point": item["point"], "odds": item["odds"],
                "probability": item["probability"], "edge_pct": round(item["edge"] * 100, 1),
                "gamelog_l15_hits": item["gamelog_l15_hits"],
                "gamelog_l15_n": item["gamelog_l15_n"],
                "probability_method": "min(model,one_sided_90pct_wilson_l15)",
                "bookmaker": book, "game": game,
            })

        first = legs[0]
        total_stake = round(sum(x["stake"] for x in legs), 2)
        anchor = first["prop"]
        built = PickCls(
            type="ladder", category="ladder", player=_player(anchor),
            team=getattr(anchor, "team", "") or "", emoji=getattr(anchor, "emoji", "🎯") or "🎯",
            market=f"{base.title()} Ladder", direction=direction,
            odds=round(first["odds"], 2), stake=min(total_stake, 5.0),
            probability=first["probability"], edge_pct=round(first["edge"] * 100, 1),
            ev=round(first["edge"], 4), game=game,
            analysis=f"{len(legs)} echte +EV Alt-Linien bei {book}; jede Stufe separat geprueft.",
            picks=ladder_legs,
        )
        built.sport = _sport(anchor)
        built.point = first["point"]
        built.features = {"odds_observed": True, "price_type": "bookmaker", "bookmaker": book, "ladder_rungs": len(legs)}
        built.leg_details = leg_details
        ladders.append(built)

    ladders.sort(key=lambda p: (
        max((getattr(x, "edge_pct", 0) or 0) for x in (getattr(p, "picks", None) or [])),
        len(getattr(p, "picks", None) or []),
    ), reverse=True)

    # Different feeds/books can expose the exact same ladder. Show it only once.
    deduped = []
    seen = set()
    for ladder in ladders:
        sig = (
            str(getattr(ladder, "player", "") or "").strip().lower(),
            str(getattr(ladder, "market", "") or "").strip().lower(),
            str(getattr(ladder, "direction", "") or "").strip().lower(),
            _game(ladder),
            tuple(
                (round(float(getattr(leg, "point", 0) or 0), 4), round(float(getattr(leg, "odds", 0) or 0), 4))
                for leg in (getattr(ladder, "picks", None) or [])
            ),
        )
        # NHL feed aliases (e.g. CGY @ EDM versus Calgary @ Edmonton)
        # must not create multiple exposure to the same player's ladder
        # across two sportsbooks during one card-generation window.
        # Never mix rung prices from different books within one ladder.
        if _sport(ladder) == "NHL":
            sig = ("nhl_player_ladder", sig[0], sig[1], sig[2])
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append(ladder)
    max_ladders = max(0, min(12, int(os.getenv("PH_MAX_LADDERS", "6"))))
    return deduped[:max_ladders]

def _make_builder(legs: Sequence[Any], label: str, PickCls: Any, pairs: Dict[str, Any]) -> Optional[Any]:
    if not _valid_combo(legs):
        return None

    odds = math.prod(_odds(x) for x in legs)
    prob, corr, corr_n = _joint_probability(legs, pairs)
    edge = prob * odds - 1.0

    thresholds = {"SAFE": 0.012, "VALUE": 0.025, "RISK": 0.045, "LOTTERY": 0.07}
    probability_floors = {"SAFE": 0.30, "VALUE": 0.16, "RISK": 0.055, "LOTTERY": 0.008}
    if edge < thresholds[label] or prob < probability_floors[label]:
        return None

    caps = {"SAFE": 0.35, "VALUE": 0.26, "RISK": 0.14, "LOTTERY": 0.06}
    fractions = {"SAFE": 0.24, "VALUE": 0.18, "RISK": 0.10, "LOTTERY": 0.04}
    stake = _kelly(prob, odds, fractions[label], caps[label])
    if stake <= 0:
        return None
    # High-odds positive-EV tickets often have a tiny fractional-Kelly stake.
    # Preserve them at a small explicit unit floor instead of rounding to zero.
    stake = max({"SAFE":0.10,"VALUE":0.10,"RISK":0.05,"LOTTERY":0.05}[label], stake)

    same_game = bool(_game(legs[0])) and len({_game(x) for x in legs}) == 1
    all_hr = all(_is_hr(x) for x in legs)
    category = "hr_lottery" if all_hr and label in {"RISK", "LOTTERY"} else label.lower()
    ptype = "betbuilder" if same_game and label in {"SAFE", "VALUE"} else (
        "big" if label in {"RISK", "LOTTERY"} else ("kombi2" if len(legs) == 2 else "kombi3")
    )

    analysis = (
        f"{'HR LOTTERY' if all_hr else label} · gemeinsame Prob {prob*100:.1f}% "
        f"· Korrelation {corr:.2f} · {_book(legs[0])}"
    )
    if corr_n:
        analysis += f" ({corr_n}+ Settlements)"

    built = PickCls(
        type=ptype,
        category=category,
        player=" + ".join(_player(x) for x in legs),
        emoji="⚾" if all_hr else "🎯",
        team="",
        market=f"{len(legs)}-Leg {'HR Lottery' if all_hr else label}",
        direction="over",
        odds=round(odds, 2),
        stake=stake,
        probability=round(prob, 4),
        edge_pct=round(edge * 100, 1),
        ev=round(edge, 4),
        game=_game(legs[0]) if same_game else label,
        analysis=analysis,
        legs=[_leg_text(x) for x in legs],
    )
    built.leg_details = [{
        "player": _player(x), "sport": _sport(x), "market": getattr(x, "market", ""),
        "direction": _direction(x), "point": _point(x), "odds": _odds(x),
        "bookmaker": _book(x), "game": _game(x),
    } for x in legs]
    built.features = {"odds_observed": True, "price_type": "bookmaker", "bookmaker": _book(legs[0])}
    return built


def build_autonomous_extras(picks: Sequence[Any], props: Iterable[Any], PickCls: Any, LadderLegCls: Any) -> List[Any]:
    """Build HR singles and all risk buckets from the complete verified pool."""
    selected = [
        p for p in picks
        if getattr(p, "type", None) == "single"
        and _prob(p) >= 0.50 and _odds(p) > 1 and _real_price(p)
    ]

    pool: List[Any] = list(selected)
    seen = {_candidate_key(p) for p in selected}

    for prop in props or []:
        candidate = _candidate_from_prop(prop, PickCls)
        if candidate is None:
            continue
        key = _candidate_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        pool.append(candidate)

    if not pool:
        return []

    pool = sorted(
        pool,
        key=lambda x: ((_prob(x) * _odds(x) - 1.0), _prob(x)),
        reverse=True,
    )[:28]

    corr = safe_json_load(CORR_FILE, {}) or {}
    pairs = corr.get("pairs", {}) if isinstance(corr, dict) else {}
    extras: List[Any] = []

    # Dedicated verified Home Run lane.
    selected_keys = {_candidate_key(p) for p in selected}
    hr_candidates = [
        p for p in pool
        if _is_hr(p) and _candidate_key(p) not in selected_keys
    ]
    hr_candidates.sort(
        key=lambda p: ((getattr(p, "ev", 0) or 0), _prob(p)),
        reverse=True,
    )
    extras.extend(hr_candidates[:3])

    # All genuine same-book ladders whose individual rungs are independently +EV.
    # Same player + same market at 10+/15+/20+ (or TD 1+/2+/3+) must survive.
    extras.extend(_real_ladders(props, PickCls, LadderLegCls, selected=selected))

    candidates: Dict[str, List[Any]] = {
        "SAFE": [], "VALUE": [], "RISK": [], "LOTTERY": []
    }
    same_game_candidates: Dict[Tuple[str, str], List[Any]] = {}

    by_book: Dict[str, List[Any]] = {}
    for candidate in pool:
        book = _book(candidate)
        if book:
            by_book.setdefault(book, []).append(candidate)

    for book_pool in by_book.values():
        book_pool = sorted(
            book_pool,
            key=lambda x: ((_prob(x) * _odds(x) - 1.0), _prob(x)),
            reverse=True,
        )[:14]

        for size in (2, 3, 4):
            for legs in itertools.combinations(book_pool, size):
                odds = math.prod(_odds(x) for x in legs)
                min_prob = min(_prob(x) for x in legs)
                all_hr = all(_is_hr(x) for x in legs)

                if all_hr:
                    label = "RISK" if size == 2 and odds < 25 else "LOTTERY"
                elif size == 2:
                    if min_prob >= 0.60 and odds <= 4.5:
                        label = "SAFE"
                    elif odds <= 7.5:
                        label = "VALUE"
                    else:
                        label = "RISK"
                elif size == 3:
                    if min_prob >= 0.52 and odds <= 9.0:
                        label = "VALUE"
                    elif odds <= 22.0:
                        label = "RISK"
                    else:
                        label = "LOTTERY"
                else:
                    label = "LOTTERY"

                built = _make_builder(legs, label, PickCls, pairs)
                if built:
                    candidates[label].append(built)
                    if getattr(built, "type", None) == "betbuilder":
                        same_game_candidates.setdefault((_book(legs[0]), _game(legs[0])), []).append(built)

    # Guarantee a dedicated same-game builder lane. The general risk buckets may
    # otherwise select a cross-game combo with slightly higher EV and hide a valid SGB.
    for (_book_key, _game_key), items in same_game_candidates.items():
        items.sort(key=lambda p: (
            getattr(p, "ev", 0) or 0,
            getattr(p, "probability", 0) or 0,
            len(getattr(p, "legs", None) or []),
        ), reverse=True)
        best = items[0]
        sig = tuple(getattr(best, "legs", []) or [])
        if not any(tuple(getattr(x, "legs", []) or []) == sig for x in extras):
            extras.append(best)

    for label in ("SAFE", "VALUE", "RISK", "LOTTERY"):
        if candidates[label]:
            candidates[label].sort(
                key=lambda p: (
                    getattr(p, "ev", 0) or 0,
                    getattr(p, "probability", 0) or 0,
                ),
                reverse=True,
            )
            extras.append(candidates[label][0])

    # Preserve one dedicated HR lottery in addition to the general buckets.
    hr_tickets = [
        item for item in candidates["RISK"] + candidates["LOTTERY"]
        if getattr(item, "category", "") == "hr_lottery"
    ]
    if hr_tickets:
        hr_tickets.sort(
            key=lambda p: (
                getattr(p, "ev", 0) or 0,
                getattr(p, "probability", 0) or 0,
            ),
            reverse=True,
        )
        best_hr = hr_tickets[0]
        signature = tuple(getattr(best_hr, "legs", []) or [])
        if not any(
            tuple(getattr(existing, "legs", []) or []) == signature
            for existing in extras
        ):
            extras.append(best_hr)

    return extras

