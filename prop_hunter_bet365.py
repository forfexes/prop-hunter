#!/usr/bin/env python3
"""bet365 public-browser player-prop adapter for PROP HUNTER.

Supported leagues:
- MLB
- NBA
- WNBA
- NFL

The adapter uses an ordinary Playwright browser and public page/network data only.
It does not bypass login, CAPTCHA, geo restrictions or access controls. When the
site is unavailable, it returns no live rows and the orchestrator uses its normal
health/cache logic.

The market catalogue is also used offline to normalize captured JSON/DOM payloads.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from prop_hunter_shared_utils import hash_key, norm_name, now_iso, to_float


@dataclass(frozen=True)
class MarketSpec:
    key: str
    label: str
    aliases: Tuple[str, ...]
    binary: bool = False
    card_eligible: bool = True
    risk_class: str = "standard"


MARKETS: Dict[str, Tuple[MarketSpec, ...]] = {
    "MLB": (
        MarketSpec("pitcher_strikeouts", "Pitcher Strikeouts", ("pitcher strikeouts", "pitcher strikeout", "strikeouts thrown")),
        MarketSpec("pitcher_outs", "Pitcher Outs Recorded", ("pitcher outs", "outs recorded", "pitching outs")),
        MarketSpec("pitcher_hits_allowed", "Pitcher Hits Allowed", ("pitcher hits allowed", "hits allowed")),
        MarketSpec("pitcher_earned_runs", "Pitcher Earned Runs", ("pitcher earned runs", "earned runs allowed")),
        MarketSpec("pitcher_walks", "Pitcher Walks", ("pitcher walks", "walks allowed")),
        MarketSpec("pitcher_win", "Pitcher to Record Win", ("pitcher to record the win", "pitcher win"), binary=True),
        MarketSpec("batter_home_runs", "Home Runs", ("home runs", "home run"), binary=True, risk_class="risk"),
        MarketSpec("batter_total_bases", "Total Bases", ("total bases",)),
        MarketSpec("batter_hits_runs_rbis", "Hits + Runs + RBIs", (
            "total hits runs and rbis", "total hits, runs and rbis",
            "hits runs and rbis", "hits runs rbis", "hrr"
        )),
        MarketSpec("batter_hits", "Hits", ("player hits", "batter hits", "hits")),
        MarketSpec("batter_rbis", "RBIs", ("runs batted in", "rbis", "rbi")),
        MarketSpec("batter_runs", "Runs", ("player runs", "runs scored", "runs")),
        MarketSpec("batter_stolen_bases", "Stolen Bases", ("stolen bases", "stolen base"), binary=True, risk_class="risk"),
        MarketSpec("batter_strikeouts", "Batter Strikeouts", ("batter strikeouts", "batter to strikeout")),
        MarketSpec("batter_walks", "Batter Walks", ("batter walks", "player walks")),
        MarketSpec("player_first_hit", "First Hit", ("player to record first hit", "first hit"), binary=True, card_eligible=False, risk_class="lottery"),
        MarketSpec("player_first_home_run", "First Home Run", ("player to hit first home run", "first home run"), binary=True, card_eligible=False, risk_class="lottery"),
        MarketSpec("player_first_run", "First Run", ("player to score first run", "first run"), binary=True, card_eligible=False, risk_class="lottery"),
        MarketSpec("player_first_rbi", "First RBI", ("player to record first rbi", "first rbi"), binary=True, card_eligible=False, risk_class="lottery"),
        MarketSpec("pitcher_first_strikeout", "First Strikeout", ("pitcher to record first strikeout", "first strikeout"), binary=True, card_eligible=False, risk_class="lottery"),
        MarketSpec("pitch_velocity", "Pitch Velocity", ("pitch velocity",), card_eligible=False, risk_class="live"),
    ),
    "NBA": (),
    "WNBA": (),
    "NFL": (),
}

_BASKETBALL = (
    MarketSpec("player_points", "Points", ("player points", "points")),
    MarketSpec("player_rebounds", "Rebounds", ("player rebounds", "rebounds")),
    MarketSpec("player_assists", "Assists", ("player assists", "assists")),
    MarketSpec("player_threes_made", "3-Pointers Made", (
        "3 pointers made", "3-pointers made", "three pointers made",
        "three-pointers made", "3pt made", "3pm"
    )),
    MarketSpec("player_turnovers", "Turnovers", ("player turnovers", "turnovers")),
    MarketSpec("player_steals", "Steals", ("player steals", "steals")),
    MarketSpec("player_blocks", "Blocks", ("player blocks", "blocked shots", "blocks")),
    MarketSpec("player_free_throws_made", "Free Throws Made", ("free throws made", "player free throws")),
    MarketSpec("player_points_rebounds_assists", "Points + Rebounds + Assists", (
        "points rebounds and assists", "points, rebounds and assists",
        "points rebounds assists", "pts rebs asts", "pra"
    )),
    MarketSpec("player_points_rebounds", "Points + Rebounds", (
        "points and rebounds", "points rebounds", "pts rebs"
    )),
    MarketSpec("player_points_assists", "Points + Assists", (
        "points and assists", "points assists", "pts asts"
    )),
    MarketSpec("player_rebounds_assists", "Rebounds + Assists", (
        "rebounds and assists", "rebounds assists", "rebs asts"
    )),
    MarketSpec("player_steals_blocks", "Steals + Blocks", (
        "steals and blocks", "steals blocks", "stocks"
    )),
    MarketSpec("player_double_double", "Double Double", ("double double", "double-double"), binary=True, risk_class="risk"),
    MarketSpec("player_triple_double", "Triple Double", ("triple double", "triple-double"), binary=True, risk_class="lottery"),
    MarketSpec("player_first_basket", "First Basket", (
        "player to score first basket", "first basket exact", "first basket"
    ), binary=True, card_eligible=False, risk_class="lottery"),
    MarketSpec("player_first_assist", "First Assist", (
        "player to record first assist", "first assist"
    ), binary=True, card_eligible=False, risk_class="lottery"),
    MarketSpec("player_first_rebound", "First Rebound", (
        "player to record first rebound", "first rebound"
    ), binary=True, card_eligible=False, risk_class="lottery"),
)

MARKETS["NBA"] = _BASKETBALL
MARKETS["WNBA"] = _BASKETBALL

MARKETS["NFL"] = (
    MarketSpec("player_passing_yards", "Passing Yards", ("passing yards", "pass yards")),
    MarketSpec("player_passing_completions", "Passing Completions", ("passing completions", "pass completions", "completions")),
    MarketSpec("player_passing_attempts", "Passing Attempts", ("passing attempts", "pass attempts")),
    MarketSpec("player_passing_touchdowns", "Passing Touchdowns", ("passing touchdowns", "pass touchdowns", "passing tds", "pass tds")),
    MarketSpec("player_interceptions_thrown", "Interceptions Thrown", ("interceptions thrown", "passing interceptions")),
    MarketSpec("player_rushing_yards", "Rushing Yards", ("rushing yards", "rush yards")),
    MarketSpec("player_rushing_attempts", "Rushing Attempts", ("rushing attempts", "rush attempts", "carries")),
    MarketSpec("player_receiving_yards", "Receiving Yards", ("receiving yards", "reception yards")),
    MarketSpec("player_receptions", "Receptions", ("player receptions", "receptions")),
    MarketSpec("player_longest_reception", "Longest Reception", ("longest reception",)),
    MarketSpec("player_rush_receiving_yards", "Rushing + Receiving Yards", (
        "rushing and receiving yards", "rushing receiving yards", "rush rec yards"
    )),
    MarketSpec("player_anytime_touchdown", "Anytime Touchdown", (
        "anytime touchdown scorer", "anytime touchdown", "to score a touchdown"
    ), binary=True, risk_class="risk"),
    MarketSpec("player_first_touchdown", "First Touchdown", (
        "first touchdown scorer", "first touchdown"
    ), binary=True, card_eligible=False, risk_class="lottery"),
    MarketSpec("player_last_touchdown", "Last Touchdown", (
        "last touchdown scorer", "last touchdown"
    ), binary=True, card_eligible=False, risk_class="lottery"),
    MarketSpec("player_2plus_touchdowns", "2+ Touchdowns", (
        "2+ touchdowns", "2 or more touchdowns", "multiple touchdowns"
    ), binary=True, risk_class="lottery"),
    MarketSpec("player_defensive_sacks", "Defensive Sacks", (
        "defensive sacks", "player sacks", "to record a defensive sack"
    )),
    MarketSpec("player_tackles", "Tackles", ("player tackles", "tackles")),
    MarketSpec("player_tackle_assists", "Tackle Assists", ("tackle assists", "assisted tackles")),
    MarketSpec("player_tackles_assists", "Tackles + Assists", (
        "tackles and assists", "tackles assists", "combined tackles"
    )),
    MarketSpec("player_kicking_points", "Kicking Points", ("kicking points",)),
    MarketSpec("player_field_goals_made", "Field Goals Made", ("field goals made",)),
    MarketSpec("player_longest_field_goal", "Longest Field Goal", ("longest field goal",)),
    MarketSpec("player_longest_punt", "Longest Punt", ("longest punt",)),
    MarketSpec("player_catch_in_drive", "Catch a Pass in Drive", (
        "player to catch a pass in drive", "catch a pass in drive"
    ), binary=True, card_eligible=False, risk_class="live"),
    MarketSpec("player_next_pass", "Next Pass", ("player next pass", "next pass"), card_eligible=False, risk_class="live"),
)

HUB_URLS = {
    "MLB": "https://www.bet365.com/hub/en-us/baseball/mlb",
    "NBA": "https://www.bet365.com/hub/en-us/basketball/nba",
    "WNBA": "https://www.bet365.com/hub/en-us/basketball/wnba",
    "NFL": "https://www.bet365.com/hub/en-us/american-football/nfl",
}

COMPACT_NAME_KEYS = (
    "NA", "name", "label", "displayName", "description", "outcomeName",
    "participantName", "playerName", "player_name", "runnerName",
)
COMPACT_MARKET_KEYS = (
    "marketName", "market_name", "market", "groupName", "betOfferType",
    "statType", "stat_type", "MG", "MA",
)
COMPACT_ODDS_KEYS = (
    "OD", "decimalOdds", "oddsDecimal", "decimal_odds", "odds", "price",
    "trueOdds", "fractionalOdds",
)
COMPACT_LINE_KEYS = (
    "HA", "HD", "line", "handicap", "points", "point", "statValue",
    "stat_value", "threshold",
)
COMPACT_EVENT_KEYS = (
    "FI", "eventId", "event_id", "fixtureId", "fixture_id", "gameId",
    "game_id", "id",
)
COMPACT_TIME_KEYS = (
    "startTime", "start_time", "startDate", "commence_time", "fixtureDate",
)


def _clean(value: Any) -> str:
    text = str(value or "").lower().replace("&", " and ").replace("+", " plus ")
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _first(mapping: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _decimal_odds(raw: Any) -> Optional[float]:
    if raw in (None, ""):
        return None
    text = str(raw).strip()
    frac = re.fullmatch(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", text)
    if frac:
        den = float(frac.group(2))
        return round(1.0 + float(frac.group(1)) / den, 4) if den else None
    value = to_float(text)
    if value is None:
        return None
    if value >= 100:
        return round(1.0 + value / 100.0, 4)
    if value <= -100:
        return round(1.0 + 100.0 / abs(value), 4)
    if 1.001 < value < 1000:
        return round(value, 4)
    return None


def market_spec(sport: str, market_text: Any) -> Optional[MarketSpec]:
    sport = str(sport or "").upper()
    text = _clean(market_text)
    if not text:
        return None

    best: Optional[Tuple[int, MarketSpec]] = None
    for spec in MARKETS.get(sport, ()):
        for alias in spec.aliases:
            alias_clean = _clean(alias)
            if alias_clean and alias_clean in text:
                score = len(alias_clean)
                if best is None or score > best[0]:
                    best = (score, spec)
    return best[1] if best else None


def infer_period(text: Any) -> str:
    value = _clean(text)
    if any(token in value for token in ("1st quarter", "first quarter", "q1")):
        return "q1"
    if any(token in value for token in ("2nd quarter", "second quarter", "q2")):
        return "q2"
    if any(token in value for token in ("3rd quarter", "third quarter", "q3")):
        return "q3"
    if any(token in value for token in ("4th quarter", "fourth quarter", "q4")):
        return "q4"
    if "1st half" in value or "first half" in value:
        return "h1"
    if "2nd half" in value or "second half" in value:
        return "h2"
    if "drive" in value:
        return "drive"
    if "plate appearance" in value:
        return "plate_appearance"
    return "game"


def infer_live(text: Any) -> bool:
    value = _clean(text)
    return any(token in value for token in (
        "live", "in play", "in-play", "current drive", "next drive",
        "next pass", "next possession", "current half inning",
        "next half inning", "plate appearance",
    ))


def infer_bet_builder(*values: Any) -> bool:
    text = " ".join(str(value or "") for value in values).lower()
    return any(token in text for token in (
        "bet builder", "betbuilder", "same game parlay", "same-game parlay",
        "sgp", " bb ", "[bb]", "bb eligible",
    ))


def _threshold_line(text: str) -> Optional[float]:
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*\+", text)
    if not match:
        return None
    # 20+ is equivalent to Over 19.5 for settlement.
    return float(match.group(1)) - 0.5


def _direction_line(text: str, explicit_line: Any, binary: bool) -> Tuple[str, Optional[float], bool]:
    cleaned = str(text or "")
    direction = "over"
    alternate = False

    if re.search(r"\bunder\b|\bless\b|\blower\b", cleaned, re.I):
        direction = "under"
    elif re.search(r"\bno\b|\bnot to\b", cleaned, re.I):
        direction = "no"
    elif re.search(r"\byes\b|\banytime\b|\bto score\b", cleaned, re.I):
        direction = "yes"

    line = to_float(explicit_line)
    threshold = _threshold_line(cleaned)
    if threshold is not None:
        line = threshold
        direction = "over"
        alternate = True

    if line is None:
        patterns = (
            r"\b(?:over|under|more|less)\s*([+-]?\d+(?:\.\d+)?)",
            r"([+-]?\d+(?:\.\d+)?)\s*(?:over|under)\b",
        )
        for pattern in patterns:
            match = re.search(pattern, cleaned, re.I)
            if match:
                line = to_float(match.group(1))
                break

    if binary and line is None:
        line = 0.5
        if direction == "over":
            direction = "yes"

    return direction, line, alternate


def _looks_like_player(value: Any) -> bool:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" -|")
    if not 3 <= len(text) <= 90:
        return False
    words = text.split()
    if len(words) < 2:
        return False
    lowered = _clean(text)
    reject = (
        "over", "under", "yes", "no", "total", "team", "game",
        "moneyline", "spread", "draw", "bet builder",
    )
    return not any(lowered == token or lowered.startswith(token + " ") for token in reject)


def _strip_selection_to_player(
    selection_text: str,
    market_text: str,
    spec: MarketSpec,
    odds_raw: Any = None,
) -> str:
    text = re.sub(r"\s+", " ", str(selection_text or "")).strip()
    if odds_raw not in (None, ""):
        text = text.replace(str(odds_raw), " ")

    # Remove decimal/fractional price at the end.
    text = re.sub(r"\s+(?:\d+\.\d{2,4}|\d+\s*/\s*\d+)\s*$", " ", text)
    text = re.sub(r"\b(?:over|under|more|less|yes|no)\b\s*[+-]?\d*(?:\.\d+)?", " ", text, flags=re.I)
    text = re.sub(r"(?<!\d)\d+(?:\.\d+)?\s*\+", " ", text)
    text = re.sub(r"\bBB\b|\bBet Builder\b|\bSGP\b", " ", text, flags=re.I)

    # Remove a repeated market name from participant labels.
    for phrase in sorted((*spec.aliases, spec.label, market_text), key=lambda x: len(str(x)), reverse=True):
        if phrase:
            text = re.sub(re.escape(str(phrase)), " ", text, flags=re.I)

    text = re.sub(r"\s+[+-]?\d+(?:\.\d+)?\s*$", " ", text)
    text = re.sub(r"^[\s\-|:]+|[\s\-|:]+$", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_selection(
    sport: str,
    market_text: str,
    selection_text: str,
    *,
    odds_raw: Any = None,
    line_raw: Any = None,
    player_raw: Any = None,
    bet_builder: bool = False,
    is_live: bool = False,
    event_id: Any = "",
    commence_time: Any = None,
    home_team: Any = None,
    away_team: Any = None,
    source_url: str = "",
    capture_kind: str = "dom",
) -> Optional[Dict[str, Any]]:
    sport = str(sport or "").upper()
    spec = market_spec(sport, market_text)
    if spec is None:
        return None

    odds = _decimal_odds(odds_raw)
    if odds is None:
        # No displayed price means it is not a bookable sportsbook row.
        return None

    combined = f"{market_text} {selection_text}"
    direction, line, alternate = _direction_line(combined, line_raw, spec.binary)
    if line is None:
        return None

    player = str(player_raw or "").strip()
    if not _looks_like_player(player):
        player = _strip_selection_to_player(selection_text, market_text, spec, odds_raw)
    if not _looks_like_player(player):
        return None

    period = infer_period(combined)
    live = bool(is_live or infer_live(combined))
    alternate = bool(alternate or "alternate" in _clean(combined))
    bb = bool(bet_builder or infer_bet_builder(combined))

    card_eligible = bool(spec.card_eligible and not live and period == "game")
    if spec.key in {"player_first_touchdown", "player_first_basket", "player_first_assist",
                    "player_first_rebound", "player_first_hit", "player_first_home_run",
                    "player_first_run", "player_first_rbi", "pitcher_first_strikeout"}:
        card_eligible = False

    market_display = spec.label
    if spec.binary:
        market_display = f"{spec.label} {'Yes' if direction in ('yes', 'over') else 'No'}"
    else:
        market_display = f"{spec.label} {'Under' if direction == 'under' else 'Over'} {line:g}"

    event_id = str(event_id or "")
    snapshot_id = hash_key(
        "bet365", sport, event_id, norm_name(player), spec.key,
        direction, line, odds, period, live,
    )

    return {
        "snapshot_id": snapshot_id,
        "source": "bet365",
        "bookmaker": "bet365",
        "sport": sport,
        "league": sport,
        "source_sport_key": f"browser_bet365_{sport.lower()}",
        "source_event_id": event_id,
        "game_id": event_id,
        "commence_time": commence_time,
        "player_name": player,
        "normalized_name": norm_name(player),
        "market_original": str(market_text).strip(),
        "market": market_display,
        "market_key": spec.key,
        "direction": direction,
        "line": float(line),
        "odds_decimal": float(odds),
        "home_team": home_team,
        "away_team": away_team,
        "period": period,
        "alternate_line": alternate,
        "bet_builder": bb,
        "is_live": live,
        "card_eligible": card_eligible,
        "settlement_supported": spec.card_eligible,
        "risk_class": spec.risk_class,
        "price_type": "bookmaker",
        "odds_observed": True,
        "source_url": source_url,
        "raw": {
            "capture_kind": capture_kind,
            "selection_text": selection_text,
            "market_text": market_text,
            "bet_builder": bb,
        },
        "created_at": now_iso(),
    }


def parse_dom_groups(
    sport: str,
    groups: Sequence[Dict[str, Any]],
    *,
    source_url: str = "",
) -> List[Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    for group in groups or []:
        if not isinstance(group, dict):
            continue
        title = str(group.get("title") or "").strip()
        if market_spec(sport, title) is None:
            continue
        group_bb = bool(group.get("bet_builder") or infer_bet_builder(title, group.get("class_name")))
        group_live = bool(group.get("is_live") or infer_live(f"{title} {source_url}"))
        for participant in group.get("participants") or []:
            if isinstance(participant, str):
                participant = {"text": participant}
            if not isinstance(participant, dict):
                continue
            text = str(participant.get("text") or participant.get("aria_label") or "").strip()
            if not text:
                continue

            odds_raw = participant.get("odds")
            if odds_raw in (None, ""):
                # Last token is commonly the decimal/fractional price.
                matches = re.findall(r"(?:\d+\.\d{2,4}|\d+\s*/\s*\d+)", text)
                odds_raw = matches[-1] if matches else None

            row = parse_selection(
                sport,
                title,
                text,
                odds_raw=odds_raw,
                line_raw=participant.get("line"),
                player_raw=participant.get("player"),
                bet_builder=bool(group_bb or participant.get("bet_builder")),
                is_live=group_live,
                event_id=group.get("event_id") or participant.get("event_id") or "",
                commence_time=group.get("commence_time"),
                home_team=group.get("home_team"),
                away_team=group.get("away_team"),
                source_url=source_url,
                capture_kind="dom",
            )
            if row:
                rows[row["snapshot_id"]] = row
    return list(rows.values())


def _stack_value(stack: Sequence[Dict[str, Any]], keys: Iterable[str]) -> Any:
    for item in reversed(stack):
        value = _first(item, keys)
        if value not in (None, ""):
            return value
    return None


def _context_market(sport: str, node: Dict[str, Any], stack: Sequence[Dict[str, Any]]) -> Optional[str]:
    direct = _first(node, COMPACT_MARKET_KEYS)
    if direct and market_spec(sport, direct):
        return str(direct)
    for item in reversed(stack):
        for key in (*COMPACT_MARKET_KEYS, *COMPACT_NAME_KEYS):
            value = item.get(key)
            if value and market_spec(sport, value):
                return str(value)
    current_name = _first(node, COMPACT_NAME_KEYS)
    if current_name and market_spec(sport, current_name):
        return str(current_name)
    return None


def _context_player(node: Dict[str, Any], stack: Sequence[Dict[str, Any]], market_text: str) -> Optional[str]:
    direct = _first(node, ("playerName", "player_name", "participantName", "runnerName"))
    if isinstance(direct, dict):
        direct = _first(direct, COMPACT_NAME_KEYS)
    if direct and _looks_like_player(direct):
        return str(direct)

    market_clean = _clean(market_text)
    for item in reversed(stack):
        value = _first(item, COMPACT_NAME_KEYS)
        if value and _looks_like_player(value) and _clean(value) != market_clean:
            return str(value)
    return None


def parse_payload(sport: str, payload: Any, *, source_url: str = "") -> List[Dict[str, Any]]:
    """Parse descriptive JSON and common compact bet365-style fields.

    Compact examples often use:
    - NA: name
    - OD: odds
    - HA/HD: handicap/line
    - FI: fixture id
    """
    rows: Dict[str, Dict[str, Any]] = {}

    def walk(node: Any, stack: List[Dict[str, Any]], depth: int = 0) -> None:
        if depth > 22:
            return
        if isinstance(node, dict):
            market_text = _context_market(sport, node, stack)
            odds_raw = _first(node, COMPACT_ODDS_KEYS)
            if market_text and odds_raw not in (None, ""):
                name = _first(node, COMPACT_NAME_KEYS)
                player = _context_player(node, stack, market_text)
                line = _first(node, COMPACT_LINE_KEYS)
                event_id = _first(node, COMPACT_EVENT_KEYS) or _stack_value(stack, COMPACT_EVENT_KEYS)
                commence = _first(node, COMPACT_TIME_KEYS) or _stack_value(stack, COMPACT_TIME_KEYS)
                bb_value = _first(node, ("BB", "betBuilder", "bet_builder", "isBetBuilder", "sgp"))
                if bb_value in (None, ""):
                    bb_value = _stack_value(stack, ("BB", "betBuilder", "bet_builder", "isBetBuilder", "sgp"))

                selection_text = str(name or "")
                if player and _clean(selection_text) in {"over", "under", "yes", "no"}:
                    selection_text = f"{player} {selection_text}"

                row = parse_selection(
                    sport,
                    market_text,
                    selection_text,
                    odds_raw=odds_raw,
                    line_raw=line,
                    player_raw=player,
                    bet_builder=bool(bb_value),
                    is_live=bool(_first(node, ("live", "isLive", "inPlay")) or _stack_value(stack, ("live", "isLive", "inPlay"))),
                    event_id=event_id or "",
                    commence_time=commence,
                    home_team=_stack_value(stack, ("homeTeam", "home_team")),
                    away_team=_stack_value(stack, ("awayTeam", "away_team")),
                    source_url=source_url,
                    capture_kind="json",
                )
                if row:
                    rows[row["snapshot_id"]] = row

            new_stack = (stack + [node])[-10:]
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value, new_stack, depth + 1)
        elif isinstance(node, list):
            for value in node[:30000]:
                walk(value, stack, depth + 1)

    walk(payload, [])
    return list(rows.values())


def page_candidates(sport: str) -> List[str]:
    sport = sport.upper()
    env_url = os.getenv(f"PH_BET365_URL_{sport}", "").strip()
    urls = []
    if env_url:
        urls.append(env_url)
    if sport in HUB_URLS:
        urls.append(HUB_URLS[sport])
    urls.append("https://www.bet365.com/")
    return list(dict.fromkeys(urls))


async def _accept_cookies(page: Any) -> None:
    for label in (
        "Accept All Cookies", "Accept All", "Allow All", "I Accept",
    ):
        try:
            locator = page.get_by_text(label, exact=True)
            if await locator.count():
                await locator.first.click(timeout=1500)
                await page.wait_for_timeout(500)
                return
        except Exception:
            continue


async def _expand_markets(page: Any, sport: str, max_groups: int = 36) -> None:
    aliases = []
    for spec in MARKETS.get(sport, ()):
        aliases.extend(spec.aliases)
    alias_pattern = re.compile("|".join(re.escape(x) for x in sorted(set(aliases), key=len, reverse=True)), re.I)

    selectors = (
        '[aria-expanded="false"]',
        '[class*="MarketGroupButton"]',
        '[class*="MarketGroup_Header"]',
        '[data-testid*="market"] button',
        'button',
    )
    clicked = 0
    for selector in selectors:
        try:
            elements = page.locator(selector)
            count = min(await elements.count(), 250)
            for index in range(count):
                if clicked >= max_groups:
                    return
                element = elements.nth(index)
                try:
                    text = (await element.inner_text(timeout=500)).strip()
                    aria = await element.get_attribute("aria-label")
                    combined = f"{text} {aria or ''}"
                    if not alias_pattern.search(combined):
                        continue
                    await element.click(timeout=1000)
                    clicked += 1
                    await page.wait_for_timeout(120)
                except Exception:
                    continue
        except Exception:
            continue


async def _extract_dom_groups(page: Any) -> List[Dict[str, Any]]:
    script = r"""
    () => {
      const roots = Array.from(document.querySelectorAll(
        '[class*="MarketGroup"], [data-testid*="market-group"], [role="region"]'
      )).slice(0, 160);
      const out = [];
      for (const root of roots) {
        const titleNode = root.querySelector(
          '[class*="MarketGroupButton"], [class*="MarketGroup_Header"], ' +
          '[class*="MarketGroupTitle"], [data-testid*="market-title"], h2, h3'
        );
        const title = (titleNode?.innerText || '').trim();
        if (!title) continue;

        const participantNodes = Array.from(root.querySelectorAll(
          '[class*="Participant"], [class*="Selection"], ' +
          '[data-testid*="selection"], button'
        )).slice(0, 300);
        const participants = [];
        for (const node of participantNodes) {
          const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
          if (!text || text.length < 4 || text.length > 220) continue;
          const cls = String(node.className || '');
          const aria = node.getAttribute?.('aria-label') || '';
          participants.push({
            text,
            aria_label: aria,
            class_name: cls,
            bet_builder: /bet.?builder|\bBB\b|sgp/i.test(text + ' ' + aria + ' ' + cls),
          });
        }
        if (!participants.length) continue;
        const rootText = (root.innerText || '').slice(0, 600);
        out.push({
          title,
          participants,
          class_name: String(root.className || ''),
          bet_builder: /bet.?builder|\bBB\b|sgp/i.test(rootText + ' ' + String(root.className || '')),
          is_live: /live|in.?play/i.test(rootText),
        });
      }
      return out;
    }
    """
    try:
        result = await page.evaluate(script)
        return result if isinstance(result, list) else []
    except Exception:
        return []


async def capture_bet365(sport: str, timeout_ms: int = 30000) -> Tuple[List[Dict[str, Any]], str]:
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        return [], f"playwright unavailable: {exc}"

    sport = sport.upper()
    if sport not in MARKETS:
        return [], f"unsupported sport {sport}"

    payloads: List[Tuple[Any, str]] = []
    websocket_payloads: List[Tuple[Any, str]] = []
    dom_groups: List[Dict[str, Any]] = []
    errors: List[str] = []
    visited: List[str] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-GB",
            timezone_id="Europe/Zurich",
            viewport={"width": 1440, "height": 1100},
        )
        page = await context.new_page()

        async def on_response(response: Any) -> None:
            try:
                if response.status != 200:
                    return
                url = response.url
                content_type = (response.headers.get("content-type") or "").lower()
                lowered = url.lower()
                if (
                    "json" not in content_type
                    and not any(token in lowered for token in (
                        "api", "event", "market", "offer", "fixture", "coupon",
                        "sportsbook", "participant", "line",
                    ))
                ):
                    return
                body = await response.body()
                if not body or len(body) > 15_000_000:
                    return
                text = body.decode("utf-8", errors="ignore").strip()
                if not text or text[0] not in "[{":
                    return
                payloads.append((json.loads(text), url))
            except Exception:
                return

        def on_websocket(ws: Any) -> None:
            def frame_received(payload: Any) -> None:
                try:
                    if isinstance(payload, bytes):
                        text = payload.decode("utf-8", errors="ignore").strip()
                    else:
                        text = str(payload or "").strip()
                    if text and text[0] in "[{" and len(text) <= 15_000_000:
                        websocket_payloads.append((json.loads(text), ws.url))
                except Exception:
                    return
            ws.on("framereceived", frame_received)

        page.on("response", on_response)
        page.on("websocket", on_websocket)

        urls = page_candidates(sport)
        discovered: List[str] = []
        for url in urls:
            try:
                visited.append(url)
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                await _accept_cookies(page)
                await page.wait_for_timeout(2500)

                # Editorial hub pages sometimes expose a normal sportsbook hash link.
                try:
                    hrefs = await page.eval_on_selector_all(
                        "a[href]",
                        "(els) => els.map(e => e.href).filter(Boolean)"
                    )
                    for href in hrefs or []:
                        if "bet365.com" in href and ("#/AC/" in href or "/sports/" in href):
                            discovered.append(href)
                except Exception:
                    pass

                await _expand_markets(
                    page,
                    sport,
                    max_groups=int(os.getenv("PH_BET365_MAX_GROUPS", "36")),
                )
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1800)
                dom_groups.extend(await _extract_dom_groups(page))
            except Exception as exc:
                errors.append(f"{url}: {exc}")

        for href in list(dict.fromkeys(discovered))[:2]:
            if href in visited:
                continue
            try:
                visited.append(href)
                await page.goto(href, wait_until="domcontentloaded", timeout=timeout_ms)
                await _accept_cookies(page)
                await page.wait_for_timeout(2200)
                await _expand_markets(page, sport)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1600)
                dom_groups.extend(await _extract_dom_groups(page))
            except Exception as exc:
                errors.append(f"{href}: {exc}")

        await browser.close()

    rows: Dict[str, Dict[str, Any]] = {}
    for payload, url in payloads + websocket_payloads:
        for row in parse_payload(sport, payload, source_url=url):
            rows[row["snapshot_id"]] = row
    for row in parse_dom_groups(sport, dom_groups, source_url=visited[-1] if visited else ""):
        rows[row["snapshot_id"]] = row

    status = (
        f"ok rows={len(rows)} json={len(payloads)} ws={len(websocket_payloads)} dom_groups={len(dom_groups)}"
        if rows
        else (
            f"no bookable public rows; json={len(payloads)} ws={len(websocket_payloads)} "
            f"dom_groups={len(dom_groups)}"
        )
    )
    if not rows and errors:
        status += f"; {errors[0][:180]}"
    return list(rows.values()), status
