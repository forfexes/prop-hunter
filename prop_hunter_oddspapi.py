#!/usr/bin/env python3
"""OddsPapi player-prop collector for PROP HUNTER.

Key properties:
- Uses ODDSPAPI_KEY (legacy ODDSPAPI/ODDSPAPI_API_KEY are accepted).
- Discovers sport IDs and player-prop market IDs from OddsPapi itself.
- Never guesses/hardcodes American-sport IDs or prop market IDs.
- Parses every active player quote across bookmakers.
- Preserves real observed lines and decimal prices; never synthesizes ladders.
- Small in-process discovery/odds caches and a strict per-run call budget.

OddsPapi v4 model:
  /sports -> sportId discovery
  /markets -> playerProp + handicap catalog
  /tournaments -> league/tournament discovery
  /fixtures -> upcoming league fixtures
  /odds -> bookmakerOdds[book].markets[mid].outcomes[oid].players[playerId]
"""
from __future__ import annotations

import os
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

BASE_URL = "https://api.oddspapi.io/v4"

# Internal sport key -> (sport aliases, tournament aliases)
TARGETS: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    "baseball_mlb": (
        ("baseball",),
        ("mlb", "major league baseball"),
    ),
    "basketball_nba": (
        ("basketball",),
        ("nba", "national basketball association"),
    ),
    "basketball_wnba": (
        ("basketball",),
        ("wnba", "women's national basketball association", "womens national basketball association"),
    ),
    "americanfootball_nfl": (
        ("american football", "americanfootball", "gridiron"),
        ("nfl", "national football league"),
    ),
    "icehockey_nhl": (
        ("ice hockey", "icehockey", "hockey"),
        ("nhl", "national hockey league"),
    ),
}

# Extra prepared leagues can use the same discovery engine later without changing
# the parser. They are not activated by the main card until their settlement and
# history paths are explicitly enabled.
PREPARED_TARGETS: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    "basketball_ncaab": (("basketball",), ("ncaa", "ncaab", "college basketball")),
    "americanfootball_ncaaf": (("american football", "americanfootball", "gridiron"), ("ncaa", "ncaaf", "college football")),
    "basketball_euroleague": (("basketball",), ("euroleague",)),
    "icehockey_swiss_nl": (("ice hockey", "icehockey", "hockey"), ("national league", "switzerland national league", "swiss national league")),
    "icehockey_ahl": (("ice hockey", "icehockey", "hockey"), ("ahl", "american hockey league")),
    "icehockey_shl": (("ice hockey", "icehockey", "hockey"), ("shl", "swedish hockey league")),
    "icehockey_liiga": (("ice hockey", "icehockey", "hockey"), ("liiga",)),
    "icehockey_del": (("ice hockey", "icehockey", "hockey"), ("del", "deutsche eishockey liga")),
}

SPORT_LABELS = {
    "baseball_mlb": "MLB",
    "basketball_nba": "NBA",
    "basketball_wnba": "WNBA",
    "americanfootball_nfl": "NFL",
    "icehockey_nhl": "NHL",
}

_PREFERRED_BOOKS = [
    "pinnacle", "bet365", "fanduel", "draftkings", "caesars", "hardrockbet",
    "betrivers", "betmgm", "williamhill", "betano", "bwin", "unibet",
]

_CACHE: Dict[str, Any] = {"sports": None, "markets": {}, "tournaments": {}, "fixtures": {}, "odds": {}}
_CALL_COUNT = {"sports": 0, "markets": 0, "tournaments": 0, "fixtures": 0, "odds": 0}


def call_stats() -> Dict[str, int]:
    return dict(_CALL_COUNT)


def _key() -> str:
    return (
        os.getenv("ODDSPAPI_KEY", "")
        or os.getenv("ODDSPAPI", "")
        or os.getenv("ODDSPAPI_API_KEY", "")
    ).strip()


def configured() -> bool:
    return bool(_key())


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower().strip())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _api_get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 25):
    if not _key():
        return None
    payload = dict(params or {})
    payload["apiKey"] = _key()
    try:
        response = requests.get(
            f"{BASE_URL}/{path}",
            params=payload,
            timeout=timeout,
            headers={"User-Agent": "PROP-HUNTER/13.6", "Accept": "application/json"},
        )
        if response.status_code == 429:
            return {"_rate_limited": True}
        if not response.ok:
            return {"_http_error": response.status_code}
        return response.json()
    except Exception as exc:
        return {"_error": f"{type(exc).__name__}: {exc}"}


def get_sports(force: bool = False) -> List[Dict[str, Any]]:
    if _CACHE["sports"] is not None and not force:
        return _CACHE["sports"]
    data = _api_get("sports", {"language": "en"})
    _CALL_COUNT["sports"] += 1
    rows = data if isinstance(data, list) else []
    _CACHE["sports"] = rows
    return rows


def _score_alias(value: str, aliases: Iterable[str]) -> int:
    v = _norm(value)
    best = 0
    for alias in aliases:
        a = _norm(alias)
        if not a:
            continue
        if v == a:
            best = max(best, 100)
        elif len(a) <= 4 and a in v.split():
            best = max(best, 90)
        elif len(a) > 4 and (a in v or v in a):
            best = max(best, 80)
        elif set(a.split()) and set(a.split()).issubset(set(v.split())):
            best = max(best, 70)
    return best


def resolve_sport_id(sport_key: str) -> Optional[int]:
    spec = TARGETS.get(sport_key) or PREPARED_TARGETS.get(sport_key)
    if not spec:
        return None
    sport_aliases, _ = spec
    candidates = []
    for row in get_sports():
        score = max(_score_alias(row.get("slug", ""), sport_aliases), _score_alias(row.get("sportName", ""), sport_aliases))
        if score:
            candidates.append((score, row.get("sportId")))
    candidates.sort(reverse=True, key=lambda x: x[0])
    try:
        return int(candidates[0][1]) if candidates else None
    except Exception:
        return None


def get_markets(sport_id: int) -> List[Dict[str, Any]]:
    if sport_id in _CACHE["markets"]:
        return _CACHE["markets"][sport_id]
    # Docs accept sportId and this avoids loading irrelevant market catalogs.
    data = _api_get("markets", {"sportId": sport_id, "language": "en"})
    _CALL_COUNT["markets"] += 1
    rows = data if isinstance(data, list) else []
    _CACHE["markets"][sport_id] = rows
    return rows


def player_market_catalog(sport_id: int) -> Dict[int, Dict[str, Any]]:
    result = {}
    for market in get_markets(sport_id):
        if market.get("playerProp") is not True:
            continue
        try:
            result[int(market["marketId"])] = market
        except Exception:
            continue
    return result


def get_tournaments(sport_id: int) -> List[Dict[str, Any]]:
    if sport_id in _CACHE["tournaments"]:
        return _CACHE["tournaments"][sport_id]
    data = _api_get("tournaments", {"sportId": sport_id, "language": "en"})
    _CALL_COUNT["tournaments"] += 1
    rows = data if isinstance(data, list) else []
    _CACHE["tournaments"][sport_id] = rows
    return rows


def resolve_tournament(sport_key: str, sport_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    spec = TARGETS.get(sport_key) or PREPARED_TARGETS.get(sport_key)
    if not spec:
        return None
    _, aliases = spec
    sid = sport_id or resolve_sport_id(sport_key)
    if sid is None:
        return None
    scored = []
    for row in get_tournaments(sid):
        hay = " ".join(str(row.get(k) or "") for k in ("tournamentSlug", "tournamentName", "categorySlug", "categoryName"))
        score = _score_alias(hay, aliases)
        # Exact short league token in name/slug gets priority over broad category matches.
        tn = _norm(row.get("tournamentName"))
        ts = _norm(row.get("tournamentSlug"))
        if any(tn == _norm(a) or ts == _norm(a) for a in aliases):
            score = max(score, 110)
        if score:
            scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored else None


def get_fixtures(sport_key: str, lookahead_hours: int = 18) -> List[Dict[str, Any]]:
    cache_key = (sport_key, int(lookahead_hours))
    if cache_key in _CACHE["fixtures"]:
        return _CACHE["fixtures"][cache_key]
    sid = resolve_sport_id(sport_key)
    tournament = resolve_tournament(sport_key, sid)
    if sid is None or not tournament or not tournament.get("tournamentId"):
        _CACHE["fixtures"][cache_key] = []
        return []
    now = datetime.now(timezone.utc)
    data = _api_get("fixtures", {
        "sportId": sid,
        "tournamentId": tournament["tournamentId"],
        "from": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": (now + timedelta(hours=lookahead_hours)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "statusId": 0,
        "hasOdds": "true",
        "language": "en",
    })
    _CALL_COUNT["fixtures"] += 1
    rows = [x for x in data if isinstance(x, dict) and x.get("hasOdds")] if isinstance(data, list) else []
    _CACHE["fixtures"][cache_key] = rows
    return rows


def _outcome_name(catalog_market: Dict[str, Any], outcome_id: Any, raw_outcome: Dict[str, Any]) -> str:
    if raw_outcome.get("outcomeName"):
        return str(raw_outcome.get("outcomeName"))
    oid = str(outcome_id)
    for item in catalog_market.get("outcomes") or []:
        if str(item.get("outcomeId")) == oid:
            return str(item.get("outcomeName") or oid)
    return oid


def _direction(outcome: str) -> Optional[str]:
    val = _norm(outcome)
    if val.startswith("over") or val in {"higher", "more"}:
        return "over"
    if val.startswith("under") or val in {"lower", "less"}:
        return "under"
    return None


def _clean_player_name(name: Any) -> str:
    value = str(name or "").strip()
    if "," in value:
        last, first = [x.strip() for x in value.split(",", 1)]
        if first and last:
            return f"{first} {last}"
    return value


def parse_odds_payload(
    sport_key: str,
    fixture: Dict[str, Any],
    data: Dict[str, Any],
    catalog: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    label = SPORT_LABELS.get(sport_key, sport_key.upper())
    fid = str(fixture.get("fixtureId") or data.get("fixtureId") or "")
    for book, book_data in (data.get("bookmakerOdds") or {}).items():
        if not isinstance(book_data, dict):
            continue
        for mid_raw, market_data in (book_data.get("markets") or {}).items():
            try:
                mid = int(mid_raw)
            except Exception:
                continue
            cat = catalog.get(mid)
            if not cat or cat.get("playerProp") is not True:
                continue
            market_name = str(cat.get("marketName") or market_data.get("marketName") or mid)
            line = cat.get("handicap")
            for oid, outcome_data in (market_data.get("outcomes") or {}).items():
                if not isinstance(outcome_data, dict):
                    continue
                outcome_name = _outcome_name(cat, oid, outcome_data)
                direction = _direction(outcome_name)
                for player_id, pdata in (outcome_data.get("players") or {}).items():
                    if str(player_id) == "0" or not isinstance(pdata, dict):
                        continue
                    player_name = _clean_player_name(pdata.get("playerName"))
                    if not player_name or pdata.get("active") is False:
                        continue
                    try:
                        price = float(pdata.get("price"))
                    except Exception:
                        continue
                    if price <= 1.0:
                        continue
                    rows.append({
                        "source": "oddspapi",
                        "sport": label,
                        "league": label,
                        "source_sport_key": sport_key,
                        "source_event_id": fid,
                        "game_id": fid,
                        "commence_time": fixture.get("startTime") or data.get("startTime"),
                        "home_team": fixture.get("participant1Name") or data.get("participant1Name"),
                        "away_team": fixture.get("participant2Name") or data.get("participant2Name"),
                        "bookmaker": str(book).lower(),
                        "market": market_name,
                        "market_original": market_name,
                        "market_key": _norm(market_name),
                        "market_id": mid,
                        "outcome_id": str(oid),
                        "selection": outcome_name,
                        "direction": direction,
                        "player_id": str(player_id),
                        "player_name": player_name,
                        "normalized_name": _norm(player_name),
                        "line": line,
                        "odds_decimal": round(price, 4),
                        "decimal_odds": round(price, 4),
                        "implied_probability": round(1.0 / price, 6),
                        "price_type": "sportsbook_observed",
                        "source_payload_observed": True,
                        "active": True,
                        "changed_at": pdata.get("changedAt"),
                        "raw": {
                            "market_id": mid,
                            "outcome_id": oid,
                            "player_id": player_id,
                            "bookmaker_outcome_id": pdata.get("bookmakerOutcomeId"),
                            "betslip": pdata.get("betslip"),
                            "price_american": pdata.get("priceAmerican"),
                            "price_fractional": pdata.get("priceFractional"),
                            "selection": outcome_name,
                            "direction": direction,
                            "changed_at": pdata.get("changedAt"),
                            "active": pdata.get("active", True),
                        },
                    })
    return rows


def _book_rank(book: str) -> int:
    try:
        return _PREFERRED_BOOKS.index(str(book).lower())
    except ValueError:
        return 999


def fetch_oddspapi_props(
    sport_key: str,
    *,
    lookahead_hours: int = 18,
    max_events: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch real player-prop quotes for one PROP HUNTER sport key.

    ``max_events`` defaults to PH_ODDSPAPI_MAX_EVENTS (2). This intentionally
    keeps the free-tier call budget tight. Fixture ordering is by start time.
    """
    if not configured():
        return []
    sid = resolve_sport_id(sport_key)
    if sid is None:
        return []
    catalog = player_market_catalog(sid)
    if not catalog:
        return []
    fixtures = get_fixtures(sport_key, lookahead_hours)
    fixtures = sorted(fixtures, key=lambda x: str(x.get("startTime") or ""))
    limit = max_events if max_events is not None else int(os.getenv("PH_ODDSPAPI_MAX_EVENTS", "2"))
    odds_cap = int(os.getenv("PH_ODDSPAPI_MAX_ODDS_CALLS", "6"))
    out: List[Dict[str, Any]] = []
    for fixture in fixtures[:max(0, limit)]:
        if _CALL_COUNT["odds"] >= odds_cap:
            break
        fid = str(fixture.get("fixtureId") or "")
        if not fid:
            continue
        if fid in _CACHE["odds"]:
            data = _CACHE["odds"][fid]
        else:
            data = _api_get("odds", {
                "fixtureId": fid,
                "oddsFormat": "decimal",
                "language": "en",
                "verbosity": 3,
            })
            _CALL_COUNT["odds"] += 1
            _CACHE["odds"][fid] = data
            # Documented cooldowns are sub-second; stay conservative.
            time.sleep(float(os.getenv("PH_ODDSPAPI_COOLDOWN", "0.9")))
        if not isinstance(data, dict) or data.get("_rate_limited") or data.get("_http_error") or data.get("_error"):
            continue
        out.extend(parse_odds_payload(sport_key, fixture, data, catalog))
    # Deterministic order: favored books first, then player/market/line/outcome.
    out.sort(key=lambda r: (_book_rank(r.get("bookmaker", "")), r.get("player_name", ""), r.get("market", ""), str(r.get("line")), r.get("selection", "")))
    return out


def fetch_for_league(league: str) -> List[Dict[str, Any]]:
    rev = {v: k for k, v in SPORT_LABELS.items()}
    key = rev.get(str(league).upper())
    return fetch_oddspapi_props(key) if key else []


__all__ = [
    "TARGETS", "PREPARED_TARGETS", "SPORT_LABELS", "configured", "call_stats",
    "get_sports", "resolve_sport_id", "get_markets", "player_market_catalog",
    "get_tournaments", "resolve_tournament", "get_fixtures", "parse_odds_payload",
    "fetch_oddspapi_props", "fetch_for_league",
]
