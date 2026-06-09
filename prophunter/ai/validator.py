"""Robust LLM-output validator with auto-retry."""
from __future__ import annotations

import json
import re
from typing import Callable, List, Optional, Tuple

from pydantic import ValidationError

from ..config import AI_RETRY_ON_INVALID_JSON
from ..logging_setup import get_logger
from ..models import Pick

log = get_logger(__name__)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def strip_code_fence(text: str) -> str:
    return _FENCE_RE.sub("", text or "").strip()


def extract_json_array(text: str) -> Optional[str]:
    text = strip_code_fence(text)
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start:end + 1]


def parse_picks(raw_text: str) -> Tuple[List[Pick], Optional[str]]:
    body = extract_json_array(raw_text)
    if not body:
        return [], "no JSON array found in response"
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        return [], f"json.JSONDecodeError: {e}"
    if not isinstance(data, list):
        return [], "expected a JSON list at top level"
    picks: List[Pick] = []
    errors: List[str] = []
    for i, raw in enumerate(data):
        try:
            picks.append(Pick.model_validate(raw))
        except ValidationError as e:
            errors.append(f"pick[{i}] {e.errors()[0]['msg']}")
    if not picks and errors:
        return [], "; ".join(errors[:3])
    if errors:
        log.warning("dropped %d invalid picks: %s", len(errors), errors[:2])
    return picks, None


def call_with_validation(
    prompt: str,
    llm_call: Callable[[str], Optional[str]],
    max_retries: int = AI_RETRY_ON_INVALID_JSON,
) -> List[Pick]:
    attempt = 0
    current_prompt = prompt
    while True:
        raw = llm_call(current_prompt)
        if not raw:
            return []
        picks, err = parse_picks(raw)
        if picks or attempt >= max_retries:
            return picks
        log.warning("LLM validation failed (attempt %d): %s", attempt + 1, err)
        attempt += 1
        current_prompt = (
            prompt
            + f"\n\nDeine letzte Antwort war ungültig: {err}\n"
            "Gib JETZT NUR den valide JSON-Array zurück, ohne Erklärung, ohne ```."
        )
    return []
