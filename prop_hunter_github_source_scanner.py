#!/usr/bin/env python3
"""Discovers and ranks public GitHub data/scraper projects for PROP HUNTER.

Security rule: discovered repositories are never executed automatically. The scanner
collects metadata, classifies likely coverage and stores candidates for later review.
"""
from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

from prop_hunter_shared_utils import hash_key, now_iso, safe_json_write, upsert_rows

QUERIES = (
    'sportsbook odds scraper language:Python stars:>0',
    'player props scraper language:Python stars:>0',
    'DraftKings FanDuel BetMGM Caesars scraper language:Python',
    'PrizePicks Underdog Sleeper scraper language:Python',
    'OddsPortal odds history Playwright language:Python',
    'NBA player props model probability calibration',
    'MLB player props Statcast model',
    'NFL player props nflverse model',
    'sports betting line movement tracker language:Python',
)

BOOK_TERMS = {
    "draftkings": ("draftkings", "draft kings"), "fanduel": ("fanduel", "fan duel"),
    "betmgm": ("betmgm", "bet mgm"), "caesars": ("caesars", "william hill"),
    "betrivers": ("betrivers", "kambi", "sugarhouse"), "bovada": ("bovada",),
    "prizepicks": ("prizepicks", "prize picks"), "underdog": ("underdog",),
    "sleeper": ("sleeper",), "oddsportal": ("oddsportal", "odds portal"),
    "bet365": ("bet365",), "superbook": ("superbook",),
}


def _classify(text: str) -> Dict[str, Any]:
    lower = text.lower()
    books = sorted(k for k, terms in BOOK_TERMS.items() if any(t in lower for t in terms))
    purpose = []
    for needle, label in (("scrap", "scraper"), ("odd", "odds"), ("prop", "player_props"),
                          ("calibrat", "calibration"), ("model", "model"),
                          ("histor", "historical"), ("line movement", "line_movement")):
        if needle in lower: purpose.append(label)
    return {"bookies": books, "purpose": sorted(set(purpose))}


def _score(item: Dict[str, Any]) -> float:
    stars = int(item.get("stargazers_count") or 0)
    forks = int(item.get("forks_count") or 0)
    archived = bool(item.get("archived"))
    pushed = str(item.get("pushed_at") or "")
    try:
        age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days
    except Exception:
        age_days = 9999
    recency = max(0.0, 30.0 - age_days / 12.0)
    score = min(30.0, stars ** 0.5 * 4.0) + min(12.0, forks ** 0.5 * 2.0) + recency
    if archived: score -= 40
    if item.get("license"): score += 6
    return round(max(0.0, min(100.0, score)), 2)


def scan() -> List[Dict[str, Any]]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "PropHunter-SourceScanner/2"}
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token: headers["Authorization"] = f"Bearer {token}"
    found: Dict[str, Dict[str, Any]] = {}
    for query in QUERIES:
        try:
            response = requests.get("https://api.github.com/search/repositories", params={"q": query, "sort": "updated", "per_page": 30}, headers=headers, timeout=30)
            if response.status_code != 200:
                print(f"GitHub query failed {response.status_code}: {query}")
                continue
            for item in (response.json() or {}).get("items", []) or []:
                full_name = item.get("full_name")
                if not full_name: continue
                text = " ".join(str(item.get(k) or "") for k in ("name", "description", "topics"))
                cls = _classify(text)
                row = {
                    "repo_id": hash_key("github", full_name), "full_name": full_name,
                    "html_url": item.get("html_url"), "description": item.get("description"),
                    "stars": item.get("stargazers_count", 0), "forks": item.get("forks_count", 0),
                    "language": item.get("language"), "license": ((item.get("license") or {}).get("spdx_id")),
                    "archived": bool(item.get("archived")), "pushed_at": item.get("pushed_at"),
                    "bookies": cls["bookies"], "purpose": cls["purpose"], "score": _score(item),
                    "status": "candidate", "auto_execute": False,
                    "discovered_at": now_iso(), "updated_at": now_iso(),
                }
                current = found.get(full_name)
                if not current or row["score"] > current["score"]: found[full_name] = row
        except Exception as exc:
            print(f"GitHub query error: {query}: {exc}")
    rows = sorted(found.values(), key=lambda x: x["score"], reverse=True)
    safe_json_write("prop_hunter_github_sources.json", rows)
    print(f"GitHub source scanner: {len(rows)} candidates; no repository executed")
    return rows


if __name__ == "__main__":
    scan()
