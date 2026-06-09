"""Telegram notification client."""
from __future__ import annotations

import requests

from .config import REQUEST_TIMEOUT, TG_CHAT, TG_TOKEN
from .logging_setup import get_logger

log = get_logger(__name__)


def send_telegram(text: str, dry_run: bool = False) -> bool:
    if dry_run:
        log.info("DRY-RUN — would send Telegram message (%d chars)", len(text))
        return True
    if not TG_TOKEN or not TG_CHAT:
        log.warning("Telegram not configured")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": text, "disable_web_page_preview": True},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        log.error("telegram HTTP: %s", e)
        return False
    if r.status_code == 200:
        log.info("Telegram OK")
        return True
    log.error("Telegram failed: %s", r.text[:160])
    return False
