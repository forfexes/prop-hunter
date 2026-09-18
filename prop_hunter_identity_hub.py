#!/usr/bin/env python3
"""PROP HUNTER — lightweight player identity hub.

Keeps settlement/source matching deterministic across providers without adding
network calls to the card run. Aliases are learned from rows already stored in
Supabase and from local cache updates.
"""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

CACHE = Path("prop_hunter_identity_cache.json")


def normalize_name(value: Any) -> str:
    s = str(value or "").strip().lower()
    s = s.replace("’", "'").replace("`", "'")
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\.?$", "", s).strip()
    s = re.sub(r"[^a-z0-9\s\-\.']", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def compact_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize_name(value))


def _load() -> Dict[str, str]:
    try:
        raw = json.loads(CACHE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def canonical_name(value: Any, aliases: Optional[Dict[str, str]] = None) -> str:
    n = normalize_name(value)
    amap = aliases if aliases is not None else _load()
    return normalize_name(amap.get(n) or n)


def identity_match(a: Any, b: Any, threshold: int = 94, aliases: Optional[Dict[str, str]] = None) -> bool:
    aa, bb = canonical_name(a, aliases), canonical_name(b, aliases)
    if not aa or not bb:
        return False
    if aa == bb or compact_name(aa) == compact_name(bb):
        return True
    try:
        from rapidfuzz.fuzz import ratio
        return ratio(aa, bb) >= threshold
    except Exception:
        # conservative fallback; avoids false matches
        return False


def learn_aliases(rows: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    aliases = _load()
    changed = 0
    for row in rows or []:
        names = [row.get(k) for k in ("player_name", "player", "selection", "normalized_name") if row.get(k)]
        names = [normalize_name(x) for x in names if normalize_name(x)]
        if not names:
            continue
        canonical = normalize_name(row.get("normalized_name") or names[0])
        for n in names:
            if aliases.get(n) != canonical:
                aliases[n] = canonical
                changed += 1
    if changed:
        CACHE.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")
    return aliases


def best_match(name: Any, candidates: Iterable[Any], threshold: int = 94) -> Optional[Tuple[Any, float]]:
    n = canonical_name(name)
    best = None
    best_score = 0.0
    for candidate in candidates:
        c = canonical_name(candidate)
        if not c:
            continue
        if n == c or compact_name(n) == compact_name(c):
            return candidate, 100.0
        try:
            from rapidfuzz.fuzz import ratio
            score = float(ratio(n, c))
        except Exception:
            score = 0.0
        if score > best_score:
            best, best_score = candidate, score
    return (best, best_score) if best is not None and best_score >= threshold else None
