"""Gemini API client (key rotation + retry on 429/5xx)."""
from __future__ import annotations

import time
from typing import Optional

import requests

from ..config import AI_MAX_TOKENS, AI_TEMPERATURE, GEMINI_KEYS, GEMINI_MODEL, REQUEST_TIMEOUT
from ..logging_setup import get_logger

log = get_logger(__name__)


def call_gemini(prompt: str) -> Optional[str]:
    if not GEMINI_KEYS:
        log.warning("no Gemini keys configured")
        return None
    for i, key in enumerate(GEMINI_KEYS):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
        try:
            r = requests.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": AI_TEMPERATURE,
                        "maxOutputTokens": AI_MAX_TOKENS,
                    },
                },
                timeout=REQUEST_TIMEOUT * 2,
            )
        except requests.RequestException as e:
            log.warning("gemini %d HTTP err: %s", i, e)
            continue
        if r.status_code == 429:
            log.info("gemini key %d rate-limited, switching", i + 1)
            time.sleep(2)
            continue
        if r.status_code != 200:
            log.warning("gemini %d -> %d %s", i, r.status_code, r.text[:140])
            continue
        try:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            log.warning("gemini parse: %s", e)
            continue
    return None
