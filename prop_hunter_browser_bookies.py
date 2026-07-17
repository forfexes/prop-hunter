#!/usr/bin/env python3
"""Public-browser sportsbook fallback for PROP HUNTER.

This module opens normal public league pages and listens for JSON network responses.
It does not bypass logins, CAPTCHAs, geo restrictions or access controls. When a
bookmaker is blocked it returns no rows and the orchestrator marks it accordingly.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from prop_hunter_shared_utils import hash_key, norm_market, norm_name, now_iso, safe_json_write, to_float, warn

SPORT_SLUGS = {
    "MLB": ("baseball", "mlb"),
    "NBA": ("basketball", "nba"),
    "WNBA": ("basketball", "wnba"),
    "NFL": ("football", "nfl"),
    "NHL": ("hockey", "nhl"),
}

BOOKIE_PAGES = {
    "betmgm": "https://sports.betmgm.com/en/sports/{sport}",
    "caesars": "https://sportsbook.caesars.com/us/az/bet/{sport}",
    "betrivers": "https://az.betrivers.com/?page=sportsbook&group={sport}",
    "superbook": "https://co.superbook.com/sports/{sport}",
    "fanatics": "https://sportsbook.fanatics.com/sports/{sport}",
    "hardrock": "https://www.hardrock.bet/sports/{sport}",
    "thescore": "https://www.thescore.bet/sports/{sport}",
    "bet365": "https://www.bet365.com/#/AC/B{sport}",
    "action_network": "https://www.actionnetwork.com/{sport}",
    "betr": "https://www.betr.app/",
    "dabble": "https://dabble.com/",
    "chalkboard": "https://chalkboard.io/",
    "parlayplay": "https://parlayplay.io/",
}

PLAYER_KEYS = ("playerName", "player_name", "participant", "participantName", "runnerName", "subject", "name")
MARKET_KEYS = ("marketName", "market_name", "market", "statType", "stat_type", "label", "displayName", "betOfferType")
LINE_KEYS = ("line", "handicap", "points", "point", "statValue", "stat_value", "threshold", "value")
ODDS_KEYS = ("decimalOdds", "oddsDecimal", "decimal_odds", "odds", "price", "trueOdds")
SIDE_KEYS = ("side", "direction", "outcome", "resultType", "label", "name")
EVENT_KEYS = ("eventId", "event_id", "fixtureId", "fixture_id", "gameId", "game_id", "id")
TIME_KEYS = ("startTime", "start_time", "startDate", "commence_time", "fixtureDate")


def _first(d: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = d.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _decimal_odds(raw: Any) -> Optional[float]:
    value = to_float(raw)
    if value is None:
        return None
    # American odds are normally outside the plausible decimal range.
    if value >= 100:
        return round(1.0 + value / 100.0, 4)
    if value <= -100:
        return round(1.0 + 100.0 / abs(value), 4)
    if 1.001 < value < 1000:
        return value
    return None


def _direction(raw: Any) -> str:
    text = str(raw or "").lower()
    if any(x in text for x in ("under", "less", "lower")):
        return "under"
    if any(x in text for x in ("no", "not to")):
        return "no"
    if any(x in text for x in ("yes", "to score", "anytime")):
        return "yes"
    return "over"


def _looks_like_player(value: Any) -> bool:
    text = str(value or "").strip()
    if not 3 <= len(text) <= 80 or len(text.split()) < 2:
        return False
    reject = ("over", "under", "team", "game", "total", "moneyline", "spread", "league", "draw")
    lower = text.lower()
    return not any(x == lower or lower.startswith(x + " ") for x in reject)


def _context_value(stack: List[Dict[str, Any]], keys: Iterable[str]) -> Any:
    for d in reversed(stack):
        value = _first(d, keys)
        if value not in (None, ""):
            return value
    return None


def _normalise_candidate(book: str, sport: str, d: Dict[str, Any], stack: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    player = _first(d, PLAYER_KEYS)
    # Many feeds place the player in a nested participant object.
    if isinstance(player, dict):
        player = _first(player, PLAYER_KEYS)
    market = _first(d, MARKET_KEYS) or _context_value(stack, MARKET_KEYS)
    line = _first(d, LINE_KEYS)
    odds = _decimal_odds(_first(d, ODDS_KEYS))

    # Outcomes frequently inherit market/line from their parent.
    if line is None:
        line = _context_value(stack, LINE_KEYS)
    if player is None:
        label = _first(d, ("label", "name", "description", "outcomeName"))
        if _looks_like_player(label):
            player = label
    if not (_looks_like_player(player) and market and line is not None):
        return None

    line_f = to_float(line)
    if line_f is None:
        return None
    side = _direction(_first(d, SIDE_KEYS))
    event_id = _first(d, EVENT_KEYS) or _context_value(stack, EVENT_KEYS) or ""
    commence = _first(d, TIME_KEYS) or _context_value(stack, TIME_KEYS)
    home = _context_value(stack, ("homeTeam", "home_team", "team2"))
    away = _context_value(stack, ("awayTeam", "away_team", "team1"))
    if isinstance(home, dict): home = _first(home, ("name", "displayName"))
    if isinstance(away, dict): away = _first(away, ("name", "displayName"))

    market_text = str(market).strip()
    return {
        "snapshot_id": hash_key(book, sport, event_id, player, market_text, line_f, side, odds),
        "source": book,
        "bookmaker": book,
        "sport": sport,
        "league": sport,
        "source_sport_key": f"browser_{book}_{sport.lower()}",
        "source_event_id": str(event_id),
        "game_id": str(event_id),
        "commence_time": commence,
        "player_name": str(player).strip(),
        "normalized_name": norm_name(player),
        "market": f"{market_text} {side}",
        "market_key": norm_market(market_text),
        "direction": side,
        "line": line_f,
        "odds_decimal": odds,
        "home_team": home,
        "away_team": away,
        "raw": {"browser_capture": True},
        "created_at": now_iso(),
    }


def parse_payload(book: str, sport: str, payload: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen = set()

    def walk(node: Any, stack: List[Dict[str, Any]], depth: int = 0) -> None:
        if depth > 18:
            return
        if isinstance(node, dict):
            row = _normalise_candidate(book, sport, node, stack)
            if row:
                key = row["snapshot_id"]
                if key not in seen:
                    seen.add(key); rows.append(row)
            new_stack = (stack + [node])[-7:]
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value, new_stack, depth + 1)
        elif isinstance(node, list):
            for value in node[:20000]:
                walk(value, stack, depth + 1)

    walk(payload, [])
    return rows


async def _capture(book: str, sport: str, timeout_ms: int = 30000) -> Tuple[List[Dict[str, Any]], str]:
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        return [], f"playwright unavailable: {exc}"

    sport_slug, league_slug = SPORT_SLUGS.get(sport, (sport.lower(), sport.lower()))
    template = BOOKIE_PAGES.get(book)
    if not template:
        return [], "unknown book"
    page_url = template.format(sport=sport_slug, league=league_slug)
    payloads: List[Any] = []
    errors: List[str] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = await context.new_page()

        async def handle_response(response):
            try:
                content_type = (response.headers.get("content-type") or "").lower()
                url = response.url.lower()
                if "json" not in content_type and not any(x in url for x in ("api", "offer", "event", "market", "line", "fixture", "projection")):
                    return
                if response.status != 200:
                    return
                body = await response.body()
                if not body or len(body) > 12_000_000:
                    return
                text = body.decode("utf-8", errors="ignore").strip()
                if not text or text[0] not in "[{":
                    return
                payloads.append(json.loads(text))
            except Exception:
                return

        page.on("response", handle_response)
        try:
            await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(5500)
            # Scroll once to trigger lazy-loaded market calls.
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2500)
        except Exception as exc:
            errors.append(str(exc))
        finally:
            await browser.close()

    rows: List[Dict[str, Any]] = []
    for payload in payloads:
        rows.extend(parse_payload(book, sport, payload))
    dedup = {r["snapshot_id"]: r for r in rows}
    status = "ok" if dedup else (errors[0][:180] if errors else "no normalizable public JSON")
    return list(dedup.values()), status


def fetch_browser_source(book: str, sport: str, timeout_ms: int = 30000) -> Tuple[List[Dict[str, Any]], str]:
    try:
        return asyncio.run(_capture(book, sport.upper(), timeout_ms=timeout_ms))
    except RuntimeError:
        # A nested event loop is rare in CLI use; create a private loop as fallback.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_capture(book, sport.upper(), timeout_ms=timeout_ms))
        finally:
            loop.close()
    except Exception as exc:
        warn(f"browser source {book}/{sport}: {exc}")
        return [], str(exc)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=sorted(BOOKIE_PAGES), required=True)
    parser.add_argument("--sport", choices=sorted(SPORT_SLUGS), required=True)
    parser.add_argument("--out", default="prop_hunter_browser_source.json")
    args = parser.parse_args()
    rows, status = fetch_browser_source(args.book, args.sport)
    safe_json_write(args.out, {"book": args.book, "sport": args.sport, "status": status, "rows": rows})
    print(f"{args.book}/{args.sport}: {len(rows)} rows | {status}")


if __name__ == "__main__":
    main()
