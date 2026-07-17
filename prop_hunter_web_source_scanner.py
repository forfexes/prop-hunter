#!/usr/bin/env python3
"""Searches the public web for new sports-data and bookie connector candidates.

It uses ordinary search-result HTML only. Results are metadata candidates and are
never scraped/executed automatically until a dedicated adapter passes validation.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from prop_hunter_shared_utils import hash_key, now_iso, safe_json_write, upsert_rows

QUERIES = (
    'player props sportsbook public JSON API scraper',
    'DraftKings FanDuel BetMGM Caesars player props endpoint',
    'PrizePicks Underdog Sleeper projections API scraper',
    'MLB Statcast player prop model open source',
    'NBA WNBA player prop model calibrated probability open source',
    'NFL nflverse player props model open source',
    'sportsbook opening closing odds historical scraper Playwright',
    'same game parlay correlation player props model',
)


def _clean_url(raw: str) -> str:
    if not raw: return ""
    if raw.startswith("//"): raw = "https:" + raw
    parsed = urlparse(raw)
    if "duckduckgo.com" in parsed.netloc:
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        raw = unquote(target) if target else raw
    return raw.split("#", 1)[0]


def _classify(url: str, title: str, snippet: str) -> Dict[str, Any]:
    text = f"{url} {title} {snippet}".lower()
    category = "research"
    if "github.com" in url: category = "github"
    elif any(x in text for x in ("sportsbook", "betmgm", "draftkings", "fanduel", "caesars", "bovada")): category = "bookie"
    elif any(x in text for x in ("api", "stats", "statcast", "nflverse")): category = "data_api"
    elif any(x in text for x in ("model", "calibration", "machine learning")): category = "model"
    return {"category": category, "mentions_props": "prop" in text, "mentions_odds": "odd" in text}


def scan() -> List[Dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; PropHunterSourceResearch/1.0)"}
    found: Dict[str, Dict[str, Any]] = {}
    for query in QUERIES:
        try:
            r = requests.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=headers, timeout=30)
            if r.status_code != 200:
                print(f"web search {r.status_code}: {query}"); continue
            soup = BeautifulSoup(r.text, "html.parser")
            for result in soup.select(".result")[:15]:
                a = result.select_one("a.result__a")
                if not a: continue
                url = _clean_url(a.get("href") or "")
                if not url.startswith("http"): continue
                title = a.get_text(" ", strip=True)
                sn = result.select_one(".result__snippet")
                snippet = sn.get_text(" ", strip=True) if sn else ""
                cls = _classify(url, title, snippet)
                row = {
                    "candidate_id": hash_key("web", url), "url": url, "title": title[:250],
                    "snippet": snippet[:1000], "query": query, **cls,
                    "status": "candidate", "auto_execute": False,
                    "discovered_at": now_iso(), "updated_at": now_iso(),
                }
                found[url] = row
            time.sleep(1.0)
        except Exception as exc:
            print(f"web search error {query}: {exc}")
    rows = list(found.values())
    safe_json_write("prop_hunter_web_sources.json", rows)
    print(f"Web source scanner: {len(rows)} candidates; no candidate executed")
    return rows


if __name__ == "__main__":
    scan()
