#!/usr/bin/env python3
"""
PROP HUNTER — MULTI-SOURCE HUB
==============================

Ein gemeinsamer, ausfallsicherer Einstieg für vorhandene Odds-/Line-Quellen.

Priorität:
1. SportsGameOdds
2. OddsAPI.io
3. PrizePicks
4. Underdog
5. Sleeper
6. DraftKings
7. FanDuel
8. Bovada
9. ESPN Bet

Jede Quelle ist optional. Ein Fehler beendet den Bot nicht.
Playwright-Fallbacks bleiben in den jeweiligen Connectoren aktiv.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

log = logging.getLogger("prop_hunter_source_hub")

SPORTS = ("MLB", "WNBA", "NBA", "NFL")


def _wanted_sports(sport_filter: Optional[str]) -> List[str]:
    if not sport_filter:
        return list(SPORTS)
    needle = str(sport_filter).strip().upper()
    aliases = {
        "BASEBALL_MLB": "MLB",
        "BASKETBALL_WNBA": "WNBA",
        "BASKETBALL_NBA": "NBA",
        "AMERICANFOOTBALL_NFL": "NFL",
        "FOOTBALL_NFL": "NFL",
    }
    needle = aliases.get(needle, needle)
    return [needle] if needle in SPORTS else []


def _safe(name: str, fn: Callable[[], Any]) -> List[Dict[str, Any]]:
    try:
        data = fn()
        if isinstance(data, list):
            rows = [r for r in data if isinstance(r, dict)]
            log.info("source hub %s: %d rows", name, len(rows))
            return rows
        log.info("source hub %s: no list result", name)
    except Exception as exc:
        log.warning("source hub %s failed: %s", name, exc)
    return []


def _dedupe(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        key = (
            str(row.get("source") or ""),
            str(row.get("sport") or row.get("league") or ""),
            str(row.get("game_id") or row.get("source_event_id") or ""),
            str(row.get("player_name") or "").lower(),
            str(row.get("market_key") or row.get("market") or "").lower(),
            str(row.get("line") or ""),
            str(row.get("odds_decimal") or ""),
            str(row.get("bookmaker") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def collect(sport_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    sports = _wanted_sports(sport_filter)
    if not sports:
        return []

    rows: List[Dict[str, Any]] = []

    # Key-basierte Quellen
    try:
        import prop_hunter_odds_sportsgameodds as sgo
        for sport in sports:
            rows.extend(_safe(f"sportsgameodds:{sport}", lambda s=sport: sgo.fetch_sport(s)))
    except Exception as exc:
        log.warning("source hub SportsGameOdds import failed: %s", exc)

    try:
        import prop_hunter_odds_oddsapi_io as oio
        for sport in sports:
            rows.extend(_safe(f"oddsapi_io:{sport}", lambda s=sport: oio.fetch_for_sport(s)))
    except Exception as exc:
        log.warning("source hub OddsAPI.io import failed: %s", exc)

    # Keylose / Browser-Fallback-Quellen
    try:
        import prop_hunter_odds_pp_ud as ppud

        for sport in sports:
            rows.extend(_safe(f"prizepicks:{sport}", lambda s=sport: ppud.fetch_prizepicks(s)))

        # Underdog und Sleeper liefern mehrere Sportarten auf einmal.
        ud_rows = _safe("underdog", ppud.fetch_underdog)
        sl_rows = _safe("sleeper", ppud.fetch_sleeper)
        rows.extend(r for r in ud_rows if str(r.get("sport") or r.get("league") or "").upper() in sports)
        rows.extend(r for r in sl_rows if str(r.get("sport") or r.get("league") or "").upper() in sports)

        for sport in sports:
            rows.extend(_safe(f"draftkings:{sport}", lambda s=sport: ppud.fetch_draftkings(s)))
            rows.extend(_safe(f"fanduel:{sport}", lambda s=sport: ppud.fetch_fanduel(s)))
            rows.extend(_safe(f"bovada:{sport}", lambda s=sport: ppud.fetch_bovada(s)))
            rows.extend(_safe(f"espn_bet:{sport}", lambda s=sport: ppud.fetch_espn_bet(s)))
    except Exception as exc:
        log.warning("source hub PP/UD import failed: %s", exc)

    result = _dedupe(rows)

    try:
        Path("prop_hunter_source_hub_cache.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception:
        pass

    log.info("source hub total: %d rows", len(result))
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    data = collect()
    print(f"PROP HUNTER source hub rows={len(data)}")
