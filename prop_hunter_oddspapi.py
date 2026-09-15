#!/usr/bin/env python3
"""OddsPapi v4 player-prop collector for PROP HUNTER.

Design goals
------------
* ODDSPAPI_KEY is the canonical secret (legacy aliases still work).
* Discover sport IDs and market IDs from the live v4 catalog; never guess them.
* Follow the proven NETRATTLER pattern for fixtures: /fixtures by sport + date,
  then filter the league/tournament locally. This avoids brittle tournament IDs
  and undocumented fixture query parameters.
* Player props are identified primarily by a non-empty ``playerName`` in the
  live /odds payload. ``playerProp=true`` from /markets is used as validation,
  not as a single point of failure.
* Every line/price is an observed sportsbook value. No synthetic ladders.
* Keep API use bounded and cached within the process.
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

TARGETS: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    "baseball_mlb": (("baseball",), ("mlb", "major league baseball")),
    "basketball_nba": (("basketball",), ("nba", "national basketball association")),
    "basketball_wnba": (("basketball",), ("wnba", "women's national basketball association", "womens national basketball association")),
    "americanfootball_nfl": (("american football", "americanfootball", "gridiron"), ("nfl", "national football league")),
    "icehockey_nhl": (("ice hockey", "icehockey", "hockey"), ("nhl", "national hockey league")),
}
PREPARED_TARGETS: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    "basketball_ncaab": (("basketball",), ("ncaab", "ncaa", "college basketball")),
    "americanfootball_ncaaf": (("american football", "americanfootball", "gridiron"), ("ncaaf", "ncaa", "college football")),
    "basketball_euroleague": (("basketball",), ("euroleague",)),
    "icehockey_swiss_nl": (("ice hockey", "icehockey", "hockey"), ("swiss national league", "switzerland national league", "national league")),
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
    "basketball_ncaab": "NCAAB",
    "americanfootball_ncaaf": "NCAAF",
    "basketball_euroleague": "EUROLEAGUE",
    "icehockey_swiss_nl": "SWISS_NL",
    "icehockey_ahl": "AHL",
    "icehockey_shl": "SHL",
    "icehockey_liiga": "LIIGA",
    "icehockey_del": "DEL",
}

_PREFERRED_BOOKS = [
    "pinnacle", "bet365", "hardrockbet", "fanduel", "draftkings", "thescore",
    "betrivers", "caesars", "betmgm", "williamhill", "betano", "bwin", "unibet",
]

_CACHE: Dict[str, Any] = {
    "sports": None,
    "markets_all": None,
    "fixtures_by_sport": {},
    "odds": {},
}
_CALL_COUNT = {"sports": 0, "markets": 0, "fixtures": 0, "odds": 0}
_LAST_HTTP: Dict[str, Any] = {}


def _debug_enabled() -> bool:
    return str(os.getenv("PH_ODDSPAPI_DEBUG", "1")).strip().lower() not in {"0", "false", "no", "off"}


def _diag(message: str) -> None:
    if _debug_enabled():
        print(f"   🍋 OddsPapi: {message}", flush=True)


def call_stats() -> Dict[str, int]:
    return dict(_CALL_COUNT)


def last_http() -> Dict[str, Any]:
    return dict(_LAST_HTTP)


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
    global _RATE_LIMITED_FOR_RUN
    if _RATE_LIMITED_FOR_RUN:
        return {"_rate_limited": True, "_http_error": 429, "_skipped": True}
    if not _key():
        _LAST_HTTP[path] = {"status": "no_key"}
        return None
    payload = dict(params or {})
    payload["apiKey"] = _key()
    try:
        response = requests.get(
            f"{BASE_URL}/{path}",
            params=payload,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        _LAST_HTTP[path] = {"status": int(response.status_code), "url": response.url.split("apiKey=")[0]}
        if response.status_code == 429:
            _RATE_LIMITED_FOR_RUN = True
            _diag("HTTP 429: OddsPapi disabled for the remainder of this run")
            return {"_rate_limited": True, "_http_error": 429}
        if not response.ok:
            return {"_http_error": int(response.status_code), "_body": response.text[:200]}
        return response.json()
    except Exception as exc:
        _LAST_HTTP[path] = {"status": "exception", "error": f"{type(exc).__name__}: {exc}"[:200]}
        return {"_error": f"{type(exc).__name__}: {exc}"}


def get_sports(force: bool = False) -> List[Dict[str, Any]]:
    if _CACHE["sports"] is not None and not force:
        return _CACHE["sports"]
    data = _api_get("sports", {"language": "en"})
    _CALL_COUNT["sports"] += 1
    rows = data if isinstance(data, list) else []
    _CACHE["sports"] = rows
    if not rows:
        _diag(f"/sports leer ({_LAST_HTTP.get('sports')})")
    else:
        _diag(f"/sports OK: {len(rows)} Sportarten")
    return rows


def _score_alias(value: str, aliases: Iterable[str]) -> int:
    v = _norm(value)
    if not v:
        return 0
    best = 0
    for alias in aliases:
        a = _norm(alias)
        if not a:
            continue
        if v == a:
            best = max(best, 100)
        elif len(a) <= 5 and a in v.split():
            best = max(best, 90)
        elif len(a) > 5 and (a in v or v in a):
            best = max(best, 80)
        elif set(a.split()).issubset(set(v.split())):
            best = max(best, 70)
    return best


def resolve_sport_id(sport_key: str) -> Optional[int]:
    spec = TARGETS.get(sport_key) or PREPARED_TARGETS.get(sport_key)
    if not spec:
        return None
    sport_aliases, _ = spec
    candidates: List[Tuple[int, Any, str]] = []
    for row in get_sports():
        label = f"{row.get('slug', '')} {row.get('sportName', '')}"
        score = _score_alias(label, sport_aliases)
        if score:
            candidates.append((score, row.get("sportId"), str(row.get("sportName") or row.get("slug") or "")))
    candidates.sort(reverse=True, key=lambda x: x[0])
    if not candidates:
        _diag(f"{sport_key}: sportId nicht gefunden")
        return None
    try:
        sid = int(candidates[0][1])
    except Exception:
        return None
    _diag(f"{sport_key}: sportId={sid} ({candidates[0][2]})")
    return sid


def get_all_markets(force: bool = False) -> List[Dict[str, Any]]:
    if _CACHE["markets_all"] is not None and not force:
        return _CACHE["markets_all"]
    # v4 docs specify only language for /markets. Fetch once and filter locally.
    data = _api_get("markets", {"language": "en"})
    _CALL_COUNT["markets"] += 1
    rows = data if isinstance(data, list) else []
    _CACHE["markets_all"] = rows
    if not rows:
        _diag(f"/markets leer ({_LAST_HTTP.get('markets')})")
    else:
        _diag(f"/markets OK: {len(rows)} Märkte")
    return rows


def get_markets(sport_id: int) -> List[Dict[str, Any]]:
    return [m for m in get_all_markets() if str(m.get("sportId")) == str(sport_id)]


def market_catalog(sport_id: int) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for market in get_markets(sport_id):
        try:
            out[int(market["marketId"])] = market
        except Exception:
            continue
    return out


def player_market_catalog(sport_id: int) -> Dict[int, Dict[str, Any]]:
    return {mid: m for mid, m in market_catalog(sport_id).items() if m.get("playerProp") is True}


def get_tournaments(sport_id: int) -> List[Dict[str, Any]]:
    """Compatibility helper. Not used in the main fetch path."""
    data = _api_get("tournaments", {"sportId": sport_id, "language": "en"})
    return data if isinstance(data, list) else []


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
        if score:
            scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored else None


def _fixture_matches_league(fixture: Dict[str, Any], sport_key: str) -> bool:
    spec = TARGETS.get(sport_key) or PREPARED_TARGETS.get(sport_key)
    if not spec:
        return False
    _, aliases = spec
    fields = " ".join(str(fixture.get(k) or "") for k in (
        "tournamentName", "tournamentSlug", "categoryName", "categorySlug", "leagueName", "competitionName"
    ))
    # Some fixture responses omit tournament labels. In that case do not throw
    # the fixture away; the sport itself is still authoritative and /odds will
    # tell us whether actual player props exist.
    if not _norm(fields):
        return True
    return _score_alias(fields, aliases) > 0


def _sport_fixtures(sport_id: int, lookahead_hours: int) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    # Match the known-good NETRATTLER pattern: date-bounded /fixtures using only
    # documented core fields. Use whole UTC dates so late games are not missed.
    start = now.date().isoformat()
    end = (now + timedelta(hours=max(24, lookahead_hours))).date().isoformat()
    cache_key = (sport_id, start, end)
    if cache_key in _CACHE["fixtures_by_sport"]:
        return _CACHE["fixtures_by_sport"][cache_key]
    data = _api_get("fixtures", {"sportId": sport_id, "from": start, "to": end, "language": "en"})
    _CALL_COUNT["fixtures"] += 1
    rows = [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []
    _CACHE["fixtures_by_sport"][cache_key] = rows
    if not rows:
        _diag(f"sportId={sport_id}: /fixtures leer ({_LAST_HTTP.get('fixtures')})")
    else:
        _diag(f"sportId={sport_id}: /fixtures {len(rows)} gesamt")
    return rows


def get_fixtures(sport_key: str, lookahead_hours: int = 36) -> List[Dict[str, Any]]:
    sid = resolve_sport_id(sport_key)
    if sid is None:
        return []
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=max(6, lookahead_hours))
    rows: List[Dict[str, Any]] = []
    for fixture in _sport_fixtures(sid, lookahead_hours):
        if not fixture.get("hasOdds"):
            continue
        if not _fixture_matches_league(fixture, sport_key):
            continue
        try:
            start_raw = str(fixture.get("startTime") or "").replace("Z", "+00:00")
            start_dt = datetime.fromisoformat(start_raw)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            if start_dt < now - timedelta(hours=4) or start_dt > cutoff:
                continue
        except Exception:
            pass
        rows.append(fixture)
    _diag(f"{sport_key}: {len(rows)} Fixtures mit Odds im Fenster")
    return rows


def _outcome_name(catalog_market: Dict[str, Any], outcome_id: Any, raw_outcome: Dict[str, Any]) -> str:
    if raw_outcome.get("outcomeName"):
        return str(raw_outcome.get("outcomeName"))
    oid = str(outcome_id)
    for item in (catalog_market or {}).get("outcomes") or []:
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
        if not isinstance(book_data, dict) or book_data.get("suspended") is True:
            continue
        for mid_raw, market_data in (book_data.get("markets") or {}).items():
            if not isinstance(market_data, dict) or market_data.get("marketActive") is False:
                continue
            try:
                mid = int(mid_raw)
            except Exception:
                continue
            cat = catalog.get(mid) or {}
            market_name = str(cat.get("marketName") or market_data.get("marketName") or f"market_{mid}")
            line = cat.get("handicap")
            for oid, outcome_data in (market_data.get("outcomes") or {}).items():
                if not isinstance(outcome_data, dict):
                    continue
                outcome_name = _outcome_name(cat, oid, outcome_data)
                direction = _direction(outcome_name)
                for player_id, pdata in (outcome_data.get("players") or {}).items():
                    if str(player_id) == "0" or not isinstance(pdata, dict):
                        continue
                    # Live /odds is the ground truth for player props: playerName
                    # is populated for props. This also protects us if a catalog
                    # entry is missing/stale or playerProp metadata is wrong.
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
                        "event_id": fid,
                        "game_id": fid,
                        "commence_time": fixture.get("startTime") or data.get("startTime"),
                        "home_team": fixture.get("participant1Name") or data.get("participant1Name"),
                        "away_team": fixture.get("participant2Name") or data.get("participant2Name"),
                        "bookmaker": str(book).lower(),
                        "market": market_name,
                        "market_original": market_name,
                        "market_key": _norm(market_name).replace(" ", "_"),
                        "market_id": mid,
                        "outcome_id": str(oid),
                        "selection": outcome_name,
                        "direction": direction,
                        "player_id": str(player_id),
                        "player_name": player_name,
                        "normalized_name": _norm(player_name),
                        "line": line,
                        "odds": round(price, 4),
                        "odds_decimal": round(price, 4),
                        "decimal_odds": round(price, 4),
                        "implied_probability": round(1.0 / price, 6),
                        "period": cat.get("period"),
                        "price_type": "sportsbook_observed",
                        "source_payload_observed": True,
                        "active": True,
                        "changed_at": pdata.get("changedAt"),
                        "raw": {
                            "market_id": mid,
                            "outcome_id": oid,
                            "player_id": player_id,
                            "catalog_player_prop": cat.get("playerProp"),
                            "bookmaker_outcome_id": pdata.get("bookmakerOutcomeId"),
                            "betslip": pdata.get("betslip"),
                            "price_american": pdata.get("priceAmerican"),
                            "price_fractional": pdata.get("priceFractional"),
                            "main_line": pdata.get("mainLine"),
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
    lookahead_hours: int = 36,
    max_events: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if not configured():
        _diag("KEIN KEY gefunden (ODDSPAPI_KEY Secret?)")
        return []
    sid = resolve_sport_id(sport_key)
    if sid is None:
        return []
    catalog = market_catalog(sid)
    prop_catalog = {mid: m for mid, m in catalog.items() if m.get("playerProp") is True}
    _diag(f"{sport_key}: markets={len(catalog)}, playerProp={len(prop_catalog)}")

    fixtures = sorted(get_fixtures(sport_key, lookahead_hours), key=lambda x: str(x.get("startTime") or ""))
    limit = max_events if max_events is not None else int(os.getenv("PH_ODDSPAPI_MAX_EVENTS", "2"))
    # This is deliberately global for the process to protect the free tier.
    odds_cap = int(os.getenv("PH_ODDSPAPI_MAX_ODDS_CALLS", "6"))
    out: List[Dict[str, Any]] = []
    checked = 0
    for fixture in fixtures[:max(0, limit)]:
        if _CALL_COUNT["odds"] >= odds_cap:
            _diag(f"Odds-call cap erreicht ({odds_cap})")
            break
        fid = str(fixture.get("fixtureId") or "")
        if not fid:
            continue
        checked += 1
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
            time.sleep(float(os.getenv("PH_ODDSPAPI_COOLDOWN", "0.55")))
        if not isinstance(data, dict) or data.get("_rate_limited") or data.get("_http_error") or data.get("_error"):
            _diag(f"{sport_key}: /odds {fid} Fehler {data if isinstance(data, dict) else type(data).__name__}")
            continue
        parsed = parse_odds_payload(sport_key, fixture, data, catalog)
        books = len(data.get("bookmakerOdds") or {})
        _diag(f"{sport_key}: fixture {fid} books={books}, player-quotes={len(parsed)}")
        out.extend(parsed)

    # Deduplicate only exact observations. Alternate lines remain intact.
    uniq: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for row in out:
        key = (
            row.get("source_event_id"), row.get("bookmaker"), row.get("player_id"),
            row.get("market_id"), row.get("outcome_id"), row.get("line"), row.get("odds_decimal"),
        )
        uniq[key] = row
    result = list(uniq.values())
    result.sort(key=lambda r: (_book_rank(r.get("bookmaker", "")), r.get("player_name", ""), r.get("market", ""), str(r.get("line")), r.get("selection", "")))
    _diag(f"{sport_key}: FINAL {len(result)} Quotes aus {checked} Fixture(s); calls={call_stats()}")
    return result


def fetch_for_league(league: str) -> List[Dict[str, Any]]:
    rev = {v: k for k, v in SPORT_LABELS.items()}
    key = rev.get(str(league).upper())
    return fetch_oddspapi_props(key) if key else []


__all__ = [
    "TARGETS", "PREPARED_TARGETS", "SPORT_LABELS", "configured", "call_stats", "last_http",
    "get_sports", "resolve_sport_id", "get_all_markets", "get_markets", "market_catalog",
    "player_market_catalog", "get_tournaments", "resolve_tournament", "get_fixtures",
    "parse_odds_payload", "fetch_oddspapi_props", "fetch_for_league",
]
