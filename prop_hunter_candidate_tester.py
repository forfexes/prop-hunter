#!/usr/bin/env python3
"""Non-invasive reachability tester for known and newly discovered sources."""
from __future__ import annotations

import time
from typing import Any, Dict, List

import requests

from prop_hunter_shared_utils import hash_key, now_iso, safe_json_load, safe_json_write, upsert_rows
from prop_hunter_source_catalog import SOURCES


def _candidate_urls() -> List[Dict[str, str]]:
    rows = [{"key": x.key, "url": x.homepage, "kind": x.category} for x in SOURCES]
    for filename in ("prop_hunter_web_sources.json", "prop_hunter_github_sources.json"):
        for item in safe_json_load(filename, []) or []:
            url = item.get("url") or item.get("html_url")
            key = item.get("candidate_id") or item.get("repo_id") or hash_key(url)
            if url: rows.append({"key": str(key), "url": str(url), "kind": "discovered"})
    seen = set(); out = []
    for row in rows:
        if row["url"] in seen: continue
        seen.add(row["url"]); out.append(row)
    return out


def test(max_urls: int = 80) -> List[Dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; PropHunterHealthCheck/1.0)", "Accept": "text/html,application/json,*/*"}
    results = []
    for item in _candidate_urls()[:max_urls]:
        started = time.monotonic(); status = "error"; code = 0; content_type = ""; error = ""
        try:
            response = requests.get(item["url"], headers=headers, timeout=15, allow_redirects=True, stream=True)
            code = response.status_code; content_type = response.headers.get("content-type", "")[:120]
            status = "reachable" if code < 400 else ("blocked" if code in {401, 403, 429, 451} else "http_error")
            response.close()
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:400]
        results.append({
            "audit_id": hash_key("candidate", item["key"]), "section": "candidate_reachability",
            "item_key": item["key"], "status": status,
            "message": error, "payload": {"url": item["url"], "kind": item["kind"], "http_status": code,
                "content_type": content_type, "elapsed_s": round(time.monotonic() - started, 3)},
            "updated_at": now_iso(),
        })
    safe_json_write("prop_hunter_candidate_health.json", results)
    db_rows = [{
        "source_name": r.get("item_key"), "sport": None, "check_type": "candidate_reachability",
        "status": r.get("status"), "message": r.get("message"),
        "latency_ms": int(float((r.get("payload") or {}).get("elapsed_s", 0)) * 1000),
        "raw": r.get("payload") or {},
    } for r in results]
    upsert_rows("prop_hunter_source_audit", db_rows)
    print(f"Candidate tester: {len(results)} URLs")
    return results


if __name__ == "__main__":
    test()
