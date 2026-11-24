"""Bounded source-image discovery for exact Swiss National League players.

Read-only, no login, no SIHF /api bypass, no Telegram and no image redistribution.
Metadata is not a license. Returns image candidates for human/rights review only.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse

from prop_hunter_hockey_source_candidates import CANDIDATES, _norm

MAX_HTML = 1_500_000
ALLOWED_SCHEMES = {"https"}


class _MediaTags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = []
        self.in_title = False
        self.meta = {}
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key in {"og:title", "og:image", "twitter:title", "twitter:image"}:
                self.meta[key] = attrs.get("content") or ""
        elif tag == "img":
            self.images.append({"src": attrs.get("src") or attrs.get("data-src") or "",
                                "alt": attrs.get("alt") or ""})

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)


def page_candidates(page_url, html, expected_player):
    """Only select explicitly named images; generic team headers are not photos."""
    if not isinstance(html, str):
        raise ValueError("Expected HTML source")
    parser = _MediaTags()
    parser.feed(html[:MAX_HTML])
    title = parser.meta.get("og:title") or " ".join(parser.title)
    identity = _norm(expected_player)
    if not identity or identity not in _norm(title):
        return {"status": "page_identity_unconfirmed", "page_title": title[:150],
                "image_candidates": []}
    urls = []
    name_tokens = [_norm(x) for x in re.split(r"\s+", str(expected_player)) if len(_norm(x)) >= 4]
    for item in parser.images:
        link = item.get("src") or ""
        alt = _norm(item.get("alt"))
        joined = urljoin(page_url, link)
        parsed = urlparse(joined)
        if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
            continue
        # Require full player name in the supplied alt text, or a URL
        # path containing BOTH a recognizable first and last name token.
        path = _norm(parsed.path)
        exact_alt = identity in alt
        path_match = len(name_tokens) >= 2 and all(t in path for t in name_tokens)
        if (exact_alt or path_match) and joined not in urls:
            urls.append(joined)
    # OpenGraph pictures are candidate leads only if the URL visibly
    # identifies the actual athlete; never assign a team's banner by default.
    og = parser.meta.get("og:image") or ""
    if og:
        joined = urljoin(page_url, og)
        parsed = urlparse(joined)
        path = _norm(parsed.path)
        if parsed.scheme == "https" and len(name_tokens) >= 2 and all(t in path for t in name_tokens):
            if joined not in urls:
                urls.append(joined)
    return {"status": "named_candidate_found" if urls else "identity_verified_image_unresolved",
            "page_title": title[:150], "image_candidates": urls[:6]}


def scan(max_profiles=10):
    import requests
    session = requests.Session()
    session.headers.update({"User-Agent": "PROP-HUNTER-public-source-audit/1.0 (read-only)",
                            "Accept": "text/html"})
    rows = []
    for rec in CANDIDATES[:max_profiles]:
        entry = {"player": rec.player, "club": rec.team, "competition": rec.league,
                 "source_page": rec.url, "image_license": "unverified",
                 "telegram_approved": False}
        try:
            response = session.get(rec.url, timeout=9, allow_redirects=True, stream=True)
            if response.status_code != 200:
                entry["status"] = f"source_http_{response.status_code}"
            elif "text/html" not in response.headers.get("content-type", "").lower():
                entry["status"] = "non_html_source"
            else:
                chunks = bytearray()
                for part in response.iter_content(16384):
                    chunks.extend(part)
                    if len(chunks) > MAX_HTML:
                        break
                if len(chunks) > MAX_HTML:
                    entry["status"] = "source_html_too_large"
                else:
                    data = page_candidates(rec.url, chunks.decode("utf-8", errors="replace"),
                                           rec.player)
                    entry.update(data)
        except requests.RequestException:
            entry["status"] = "source_network_error"
        finally:
            try:
                response.close()
            except (NameError, AttributeError):
                pass
        rows.append(entry)
    return {"verified_player_club_links": len(rows),
            "named_image_source_candidates": sum(x.get("status") == "named_candidate_found" for x in rows),
            "all_image_rights_unverified": True,
            "status": "read_only_offline_review",
            "records": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-profiles", type=int, default=10)
    parser.add_argument("--out", type=Path,
                        default=Path("diagnostics/swiss_nl_official_image_sources.json"))
    args = parser.parse_args()
    report = scan(max(1, min(args.max_profiles, 10)))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print("SWISS_NL_SOURCE_SCAN", json.dumps({k:v for k,v in report.items() if k != "records"},
                                              ensure_ascii=False))


if __name__ == "__main__":
    main()
