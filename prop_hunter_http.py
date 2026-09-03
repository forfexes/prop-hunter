#!/usr/bin/env python3
"""Lightweight HTTP helper for PROP HUNTER.

Order:
1) requests for normal public APIs/pages
2) curl_cffi with ``impersonate='chrome'`` for public endpoints that reject a
   plain Python TLS/browser fingerprint

This helper deliberately does not retry HTTP 429 with browser impersonation and
is not a CAPTCHA/login/geo-bypass mechanism. Playwright remains a source-local
last fallback where the existing collector already supports it.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import requests as _requests

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def get(
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 25,
    allow_curl_fallback: bool = True,
):
    """GET a public resource, falling back to curl_cffi on browser-style denial.

    We only fall back for statuses commonly caused by client/fingerprint policy
    (401/403/406) or transport exceptions. A 429 is returned untouched so the
    caller respects the upstream rate limit.
    """
    hdr = dict(DEFAULT_HEADERS)
    if headers:
        hdr.update(headers)
    first_exc = None
    try:
        resp = _requests.get(url, params=params, headers=hdr, timeout=timeout)
        if resp.status_code not in {401, 403, 406} or not allow_curl_fallback:
            return resp
    except Exception as exc:  # network/TLS path; try browser-like transport
        first_exc = exc
        if not allow_curl_fallback:
            raise

    try:
        from curl_cffi import requests as curl_requests
        return curl_requests.get(
            url,
            params=params,
            headers=hdr,
            timeout=timeout,
            impersonate="chrome",
        )
    except Exception:
        if first_exc is not None:
            raise first_exc
        raise


def get_json(url: str, **kwargs):
    resp = get(url, **kwargs)
    if getattr(resp, "status_code", 0) != 200:
        return None
    try:
        return resp.json()
    except Exception:
        return None


__all__ = ["get", "get_json", "DEFAULT_HEADERS"]
