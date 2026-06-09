"""Groq API fallback (multi-model + multi-key rotation)."""
from __future__ import annotations

from typing import Optional

import requests

from ..config import AI_MAX_TOKENS, AI_TEMPERATURE, GROQ_KEYS, GROQ_MODELS, REQUEST_TIMEOUT
from ..logging_setup import get_logger

log = get_logger(__name__)


def call_groq(prompt: str) -> Optional[str]:
    if not GROQ_KEYS:
        return None
    for key in GROQ_KEYS:
        for model in GROQ_MODELS:
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": AI_MAX_TOKENS,
                        "temperature": AI_TEMPERATURE,
                    },
                    timeout=REQUEST_TIMEOUT * 2,
                )
            except requests.RequestException as e:
                log.warning("groq %s HTTP: %s", model, e)
                continue
            if r.status_code == 200:
                try:
                    return r.json()["choices"][0]["message"]["content"]
                except (KeyError, IndexError):
                    continue
            if r.status_code == 429:
                log.info("groq %s 429, next model", model)
                continue
            log.warning("groq %s -> %d", model, r.status_code)
    return None
