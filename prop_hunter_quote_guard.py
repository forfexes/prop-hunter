#!/usr/bin/env python3
"""Central sanity guard for observed PROP HUNTER sportsbook rows.

NETRATTLER-style defensive checks, plus explicit threshold normalization for
keyless books. It never invents a sportsbook price. A line may only be repaired
when the market label itself explicitly states the threshold (for example
"4+ Hits" -> settlement line 3.5, or "A Triple" -> settlement line 0.5).
"""
from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, Optional

_GENERIC_PLAYER_RE = re.compile(
    r"^(?:over|under|higher|lower|yes|no)?\s*[+-]?\d+(?:[\.,]\d+)?(?:\s*[+]?\s*(?:points?|rebounds?|assists?|hits?|bases?|yards?|tds?|touchdowns?|goals?|shots?|saves?))?$",
    re.I,
)
_MULTI_PLAYER_TERMS = ("||", " either player", "both players", "any of ", " or ")
_BINARY_MARKET_TERMS = (
    "anytime td", "anytime touchdown", "to score a touchdown", "home run",
    "to hit a home run", "to score", "goal scorer", "goalscorer",
    "double double", "double-double", "triple double", "triple-double",
)
_FUTURES_TERMS = (
    "standings", "regular season", "season total", "season points", "season wins",
    "futures", "to win championship", "to win conference", "to win division",
    "make playoffs", "make the playoffs", "mvp", "award winner",
    "january standings", "february standings", "march standings", "april standings",
    "may standings", "june standings", "july standings", "august standings",
    "september standings", "october standings", "november standings", "december standings",
)

def _looks_futures(player: str, market: str, original_market: str = "", selection: str = "") -> bool:
    text = " ".join(_norm(x) for x in (player, market, original_market, selection) if x)
    return any(_norm(term) in text for term in _FUTURES_TERMS)

def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

def _f(value: Any) -> Optional[float]:
    try:
        x = float(str(value).replace(",", "."))
        return x if math.isfinite(x) else None
    except Exception:
        return None

def _looks_team_or_generic(player: str, home: str = "", away: str = "") -> bool:
    p = _norm(player)
    if not p or p in {"over", "under", "higher", "lower", "yes", "no", "home", "away", "draw", "player", "total"}:
        return True
    if _GENERIC_PLAYER_RE.match(str(player or "").strip()):
        return True
    if p.startswith(("over ", "under ", "higher ", "lower ")):
        return True
    padded = f" {p} "
    if any(term in padded for term in _MULTI_PLAYER_TERMS):
        return True
    h, a = _norm(home), _norm(away)
    # Strip ranking/seed numbers from team labels, e.g. "BYU (#10)" -> "byu".
    # This must work for short acronyms too, so do not gate it behind len(p) >= 5.
    h_team = re.sub(r"\b\d+\b", " ", h)
    a_team = re.sub(r"\b\d+\b", " ", a)
    h_team = re.sub(r"\s+", " ", h_team).strip()
    a_team = re.sub(r"\s+", " ", a_team).strip()
    if p and (p == h or p == a or p == h_team or p == a_team):
        return True
    if len(p) >= 3:
        if h_team and (p in h_team or h_team in p) and len(p.split()) <= max(2, len(h_team.split())):
            return True
        if a_team and (p in a_team or a_team in p) and len(p.split()) <= max(2, len(a_team.split())):
            return True
    return False

def _binary_market(market: str, selection: str = "") -> bool:
    text = f"{_norm(market)} {_norm(selection)}"
    if any(term in text for term in _BINARY_MARKET_TERMS):
        return True
    return _norm(selection) in {"yes", "no"}

def _explicit_threshold_line(label: str) -> Optional[float]:
    """Convert an explicit sportsbook threshold label to its settlement line."""
    text = _norm(label)
    m = re.search(r"\b(\d+)\s*(?:plus|\+)", str(label or "").lower())
    if not m:
        m = re.search(r"\b(\d+)\s+plus\b", text)
    if m:
        return max(0.5, float(int(m.group(1))) - 0.5)
    if re.search(
        r"\b(?:a|an)\s+(?:hit|single|home run|double|triple|rbi|run|stolen base|touchdown|goal)\b",
        text,
    ):
        return 0.5
    if any(x in text for x in ("anytime td", "anytime touchdown", "to score a touchdown")):
        return 0.5
    return None

def canonical_market(market: Any, original_market: Any = "") -> str:
    """Canonical market key used before any gamelog/stat matching."""
    raw = _norm(original_market) or _norm(market)
    cur = _norm(market)
    text = raw or cur

    if "triple double" in text:
        return "triple_double"
    if "double double" in text:
        return "double_double"
    if any(x in text for x in ("points rebounds assists", "points rebounds and assists")) or text == "pra":
        return "pra"
    if any(x in text for x in ("points rebounds", "points and rebounds")) and "assists" not in text:
        return "pr"
    if any(x in text for x in ("points assists", "points and assists")) and "rebounds" not in text:
        return "pa"
    if any(x in text for x in ("rebounds assists", "rebounds and assists")) and "points" not in text:
        return "ra"

    if re.search(r"\bsingles?\b", text):
        return "singles"
    if re.search(r"\btriples?\b", text):
        return "triples"
    if re.search(r"\bdoubles?\b", text):
        return "doubles"
    if "home run" in text or re.search(r"\bhrs?\b", text):
        return "home_runs"
    if "total bases" in text:
        return "total_bases"
    if "pitcher strikeout" in text:
        return "pitcher_strikeouts"
    if "stolen base" in text:
        return "stolen_bases"
    if re.search(r"\brbis?\b", text) or "runs batted in" in text:
        return "rbi"
    if re.search(r"\bhits?\b", text) and "hits allowed" not in text and "hit by pitch" not in text:
        return "hits"
    if re.search(r"\bruns?\b", text) and "home run" not in text and "runs batted" not in text:
        return "runs"

    aliases = (
        (("passing touchdowns", "pass tds", "pass td"), "passing_touchdowns"),
        (("passing yards", "pass yds"), "passing_yards"),
        (("passing attempts", "pass attempts"), "passing_attempts"),
        (("passing completions", "pass completions", "completions"), "passing_completions"),
        (("rushing attempts", "rush attempts", "carries"), "rushing_attempts"),
        (("rushing yards", "rush yds"), "rushing_yards"),
        (("receiving yards", "receiving yds", "reception yards"), "receiving_yards"),
        (("receiving targets", "targets"), "receiving_targets"),
        (("anytime td", "anytime touchdown", "touchdown scorer"), "anytime_td"),
        (("shots on goal",), "shots_on_goal"),
        (("goalie saves",), "goalie_saves"),
        (("three pointers", "3 pointers", "3pm", "threes"), "threes"),
        (("rebounds",), "rebounds"),
        (("assists",), "assists"),
        (("points",), "points"),
        (("receptions",), "receptions"),
        (("goals",), "goals"),
        (("blocks",), "blocks"),
        (("steals",), "steals"),
    )
    for needles, key in aliases:
        if any(n in text for n in needles):
            return key
    return re.sub(r"[^a-z0-9]+", "_", cur or text).strip("_") or "player_prop"

def sanitize_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a safe normalized copy or None when the row is not trustworthy."""
    if not isinstance(row, dict):
        return None
    out = dict(row)
    player = str(out.get("player_name") or out.get("player") or "").strip()
    market = str(out.get("market_key") or out.get("market") or "").strip()
    home = str(out.get("home_team") or "")
    away = str(out.get("away_team") or "")
    if not player or not market or _looks_team_or_generic(player, home, away):
        return None

    price = _f(out.get("odds_decimal") if out.get("odds_decimal") is not None else out.get("odds"))
    if price is None or not (1.001 < price <= float(os.getenv("PH_MAX_DECIMAL_ODDS", "75"))):
        return None

    direction = str(out.get("direction") or "").strip().lower()
    selection = str(out.get("selection") or "").strip()
    if direction in {"yes", "higher"}:
        direction = "over"
    elif direction in {"no", "lower"}:
        direction = "under"
    if direction not in {"over", "under"}:
        text = f" {_norm(selection)} {_norm(market)} "
        if re.search(r"\b(over|higher|yes)\b", text):
            direction = "over"
        elif re.search(r"\b(under|lower|no)\b", text):
            direction = "under"
        else:
            return None

    raw = out.get("raw") if isinstance(out.get("raw"), dict) else {}
    original_market = (
        raw.get("market_name") or raw.get("market_original") or raw.get("criterion")
        or out.get("market_original") or out.get("selection") or market
    )
    if _looks_futures(player, market, str(original_market or ""), selection):
        return None

    explicit_line = _explicit_threshold_line(str(original_market or ""))
    line = _f(out.get("line") if out.get("line") is not None else out.get("point"))
    if explicit_line is not None:
        line = explicit_line
    if line is None and _binary_market(market, selection):
        line = 0.5
    if line is None or line < 0:
        return None
    if line > float(os.getenv("PH_MAX_PROP_LINE", "1000")):
        return None

    canon = canonical_market(market, original_market)
    out["player_name"] = player
    out["market"] = canon
    out["market_key"] = canon
    out["direction"] = direction
    out["line"] = float(line)
    out["odds_decimal"] = round(float(price), 4)
    return out

def probability_sane(probability: Any, odds_decimal: Any) -> bool:
    """Reject implausible model/market gaps that usually indicate bad matching."""
    p = _f(probability)
    odds = _f(odds_decimal)
    if p is None or odds is None or odds <= 1.001:
        return False
    if p > 1:
        p /= 100.0
    if not (0 < p < 1):
        return False
    implied = 1.0 / odds
    max_gap = float(os.getenv("PH_MAX_MODEL_MARKET_GAP", "0.35"))
    max_ratio = float(os.getenv("PH_MAX_MODEL_MARKET_RATIO", "4.0"))
    if abs(p - implied) > max_gap:
        return False
    if implied > 0 and p / implied > max_ratio:
        return False
    return True

# Install the expanded 2-10 leg SGP builder wrapper first.
try:
    import prop_hunter_builder_engine as _builder_engine
    if not getattr(_builder_engine, "_ph_profiles_installed", False):
        from prop_hunter_builder_profiles import install as _install_builder_profiles
        _builder_engine.build_autonomous_extras = _install_builder_profiles(_builder_engine.build_autonomous_extras)
        _builder_engine._ph_profiles_installed = True
except Exception:
    pass

# Add cross-game ACCAs after the SGP wrapper so all existing ladder/SGP behavior
# remains untouched. This produces NFL TD, MLB HR/RBI/K and basketball prop ACCAs
# only from real positive-EV bookmaker legs at one book.
try:
    import prop_hunter_builder_engine as _builder_engine
    if not getattr(_builder_engine, "_ph_acca_installed", False):
        from prop_hunter_acca_engine import install as _install_acca_engine
        _builder_engine.build_autonomous_extras = _install_acca_engine(_builder_engine.build_autonomous_extras)
        _builder_engine._ph_acca_installed = True
except Exception:
    pass

# When quote_guard is imported from the card entrypoint, the core build_post
# function already exists. Replace only its Bet Builder presentation layer so
# settlement/persistence semantics stay unchanged while Telegram shows the new
# SAFE/VALUE/AGGRESSIVE/LONGSHOT structure.
try:
    import sys as _sys
    from prop_hunter_card_formatter import install as _install_card_formatter
    for _mod_name in ("prophunter", "__main__"):
        _mod = _sys.modules.get(_mod_name)
        if _mod is None or not hasattr(_mod, "build_post") or getattr(_mod, "_ph_card_formatter_installed", False):
            continue
        _mod.build_post = _install_card_formatter(_mod.build_post)
        _mod._ph_card_formatter_installed = True
except Exception:
    pass
