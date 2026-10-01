#!/usr/bin/env python3
"""PROP HUNTER GitHub/source watcher.

Metadata-only discovery. It never clones or executes third-party repositories.
Designed for a cheap twice-monthly GitHub Actions run.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STATE_PATH = Path(os.getenv("PH_WATCHER_STATE", "prop_hunter_github_watch_state.json"))
REPORT_PATH = Path(os.getenv("PH_WATCHER_REPORT", "prop_hunter_github_watch_report.json"))
MIN_SCORE = int(os.getenv("PH_WATCHER_MIN_SCORE", "50"))
MAX_RESULTS_PER_QUERY = min(30, max(5, int(os.getenv("PH_WATCHER_MAX_PER_QUERY", "15"))))
MAX_ALERTS = min(20, max(1, int(os.getenv("PH_WATCHER_MAX_ALERTS", "10"))))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
TELEGRAM_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Broad enough to discover new projects, narrow enough to keep GitHub Search calls cheap.
KNOWN_INTEGRATED = {
    "proplineapi/propline-python",
}

SEARCHES: Tuple[str, ...] = (
    'sports betting player props API SDK language:Python',
    'sports betting odds player props language:Python',
    'sportsbook odds scraper player props language:Python',
    'NBA player props betting odds language:Python',
    'NFL player props betting odds language:Python',
    'MLB player props betting odds language:Python',
    'NHL player props betting odds language:Python',
    'sports betting Monte Carlo props language:Python',
    'sports betting CLV line movement language:Python',
    'sports odds API aggregator player props',
    'DraftKings FanDuel odds scraper props',
)

POSITIVE = {
    "player props": 16, "player-props": 16, "props": 8,
    "odds": 10, "sportsbook": 8, "betting": 7,
    "nba": 5, "wnba": 5, "nfl": 5, "mlb": 5, "nhl": 5,
    "ncaab": 5, "ncaaf": 5, "espn": 5, "draftkings": 7, "fanduel": 7,
    "monte carlo": 8, "clv": 8, "line movement": 9,
    "settlement": 7, "prediction": 5, "machine learning": 5,
    "api": 4, "scraper": 5, "analytics": 4,
}
NEGATIVE = {
    "casino": -10, "slot": -12, "poker": -8, "crypto": -5,
    "tutorial": -4, "course": -5, "frontend only": -5,
    "endpoints have been removed": -30, "api urls and endpoints have been removed": -30,
    "pay per row": -20, "apify actor": -15, "streamlit": -3,
    "educational and research purposes only": -4,
}
README_POSITIVE = {
    "official python client": 18,
    "player props api": 10,
    "real-time betting odds": 8,
    "1000 requests/day": 8,
    "1,000 requests/day": 8,
    "no credit card": 4,
    "no third party api key": 6,
}

@dataclass
class Candidate:
    full_name: str
    html_url: str
    description: str
    language: str
    stars: int
    forks: int
    open_issues: int
    pushed_at: str
    created_at: str
    archived: bool
    fork: bool
    topics: List[str]
    score: int
    reasons: List[str]
    first_seen: str
    seen_via: List[str]


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _request_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> Any:
    h = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "prop-hunter-github-watcher/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def github_search(query: str) -> List[Dict[str, Any]]:
    params = urllib.parse.urlencode({
        "q": query,
        "sort": "updated",
        "order": "desc",
        "per_page": MAX_RESULTS_PER_QUERY,
    })
    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    try:
        data = _request_json(f"https://api.github.com/search/repositories?{params}", headers=headers)
        return list(data.get("items") or [])
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")[:200]
        print(f"WARN GitHub search failed {exc.code}: {query!r} {body}")
    except Exception as exc:
        print(f"WARN GitHub search failed: {query!r}: {exc}")
    return []


def github_readme_text(full_name: str) -> str:
    if not full_name or "/" not in full_name:
        return ""
    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    try:
        data = _request_json(f"https://api.github.com/repos/{full_name}/readme", headers=headers, timeout=12)
        content = str(data.get("content") or "")
        if str(data.get("encoding") or "").lower() == "base64" and content:
            return base64.b64decode(content).decode("utf-8", "ignore")[:30000]
    except Exception:
        pass
    return ""

def score_repo(repo: Dict[str, Any], readme_text: str = "") -> Tuple[int, List[str]]:
    text = " ".join([
        str(repo.get("name") or ""),
        str(repo.get("full_name") or ""),
        str(repo.get("description") or ""),
        " ".join(repo.get("topics") or []),
        readme_text,
    ]).lower()
    score = 0
    reasons: List[str] = []
    for key, weight in POSITIVE.items():
        if key in text:
            score += weight
            reasons.append(f"{key}+{weight}")
    for key, weight in NEGATIVE.items():
        if key in text:
            score += weight
            reasons.append(f"{key}{weight}")
    for key, weight in README_POSITIVE.items():
        if key in text:
            score += weight
            reasons.append(f"{key}+{weight}")
    if str(repo.get("full_name") or "") in KNOWN_INTEGRATED:
        reasons.append("already_integrated")

    stars = int(repo.get("stargazers_count") or 0)
    forks = int(repo.get("forks_count") or 0)
    if stars >= 1000: score += 14; reasons.append("stars>=1000+14")
    elif stars >= 250: score += 11; reasons.append("stars>=250+11")
    elif stars >= 50: score += 8; reasons.append("stars>=50+8")
    elif stars >= 10: score += 5; reasons.append("stars>=10+5")
    elif stars >= 2: score += 2; reasons.append("stars>=2+2")
    if forks >= 10: score += 3; reasons.append("forks>=10+3")

    language = str(repo.get("language") or "")
    if language.lower() == "python": score += 6; reasons.append("python+6")
    elif language.lower() in {"typescript", "javascript"}: score += 2; reasons.append("js/ts+2")

    if repo.get("archived"): score -= 25; reasons.append("archived-25")
    if repo.get("fork"): score -= 4; reasons.append("fork-4")

    pushed = repo.get("pushed_at") or ""
    try:
        dt = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - dt).days
        if age_days <= 30: score += 12; reasons.append("updated<=30d+12")
        elif age_days <= 90: score += 8; reasons.append("updated<=90d+8")
        elif age_days <= 365: score += 4; reasons.append("updated<=365d+4")
        elif age_days > 1095: score -= 8; reasons.append("stale>3y-8")
    except Exception:
        pass

    return score, reasons


def load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"version": 1, "seen": {}, "last_run": None}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data.get("seen"), dict):
            data["seen"] = {}
        return data
    except Exception:
        return {"version": 1, "seen": {}, "last_run": None}


def telegram_send(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception as exc:
        print(f"WARN Telegram: {exc}")
        return False


def main() -> int:
    now = _utcnow()
    state = load_state()
    seen: Dict[str, Any] = state.setdefault("seen", {})
    found: Dict[str, Dict[str, Any]] = {}
    found_queries: Dict[str, List[str]] = {}

    for i, query in enumerate(SEARCHES, 1):
        rows = github_search(query)
        print(f"watch query {i}/{len(SEARCHES)}: {len(rows)} repos")
        for repo in rows:
            full_name = str(repo.get("full_name") or "").strip()
            if not full_name:
                continue
            found[full_name] = repo
            found_queries.setdefault(full_name, []).append(query)
        # Be friendly to Search API secondary limits.
        if i != len(SEARCHES):
            time.sleep(0.35)

    candidates: List[Candidate] = []
    new_candidates: List[Candidate] = []
    for full_name, repo in found.items():
        prelim_score, _ = score_repo(repo)
        readme = github_readme_text(full_name) if prelim_score >= (MIN_SCORE - 15) else ""
        score, reasons = score_repo(repo, readme)
        if score < MIN_SCORE:
            continue
        first_seen = str((seen.get(full_name) or {}).get("first_seen") or now)
        cand = Candidate(
            full_name=full_name,
            html_url=str(repo.get("html_url") or ""),
            description=str(repo.get("description") or "")[:500],
            language=str(repo.get("language") or ""),
            stars=int(repo.get("stargazers_count") or 0),
            forks=int(repo.get("forks_count") or 0),
            open_issues=int(repo.get("open_issues_count") or 0),
            pushed_at=str(repo.get("pushed_at") or ""),
            created_at=str(repo.get("created_at") or ""),
            archived=bool(repo.get("archived")),
            fork=bool(repo.get("fork")),
            topics=list(repo.get("topics") or []),
            score=score,
            reasons=reasons,
            first_seen=first_seen,
            seen_via=found_queries.get(full_name, []),
        )
        candidates.append(cand)
        if full_name not in seen and full_name not in KNOWN_INTEGRATED:
            new_candidates.append(cand)
        seen[full_name] = {
            "first_seen": first_seen,
            "last_seen": now,
            "score": score,
            "stars": cand.stars,
            "pushed_at": cand.pushed_at,
            "url": cand.html_url,
        }

    candidates.sort(key=lambda c: (c.score, c.stars, c.pushed_at), reverse=True)
    new_candidates.sort(key=lambda c: (c.score, c.stars, c.pushed_at), reverse=True)

    report = {
        "version": 1,
        "generated_at": now,
        "queries": list(SEARCHES),
        "min_score": MIN_SCORE,
        "repositories_scanned": len(found),
        "qualified": len(candidates),
        "new_qualified": len(new_candidates),
        "new_candidates": [asdict(c) for c in new_candidates[:50]],
        "top_candidates": [asdict(c) for c in candidates[:50]],
        "safety": "metadata_only_no_clone_no_execute",
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state["last_run"] = now
    state["last_counts"] = {
        "scanned": len(found), "qualified": len(candidates), "new_qualified": len(new_candidates)
    }
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"WATCHER scanned={len(found)} qualified={len(candidates)} new={len(new_candidates)}")
    for c in new_candidates[:MAX_ALERTS]:
        print(f"NEW score={c.score:3d} stars={c.stars:5d} {c.full_name} {c.html_url}")

    if new_candidates:
        lines = [f"🔭 PROP HUNTER SOURCE WATCHER — {len(new_candidates)} neu"]
        for c in new_candidates[:MAX_ALERTS]:
            lines.append(f"\n⭐ {c.full_name} | Score {c.score} | ★{c.stars}\n{c.html_url}")
        if len(new_candidates) > MAX_ALERTS:
            lines.append(f"\n+ {len(new_candidates) - MAX_ALERTS} weitere im Watcher-Report")
        telegram_send("\n".join(lines)[:4000])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
