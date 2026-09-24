#!/usr/bin/env python3
"""Shared stable keys for PROP HUNTER builder-correlation learning.

The actual empirical factors live in prop_hunter_builder_correlations.json and are
consumed by prop_hunter_builder_engine. Keeping key generation in one module avoids
fallback drift between training and card generation.
"""
from __future__ import annotations

import re
from typing import Any


def market_group(market: Any) -> str:
    s = str(market or "").lower().strip()
    s = re.sub(r"\s+(over|under)\s+[-+]?\d+(?:\.\d+)?", "", s).strip()
    s = re.sub(r"^player\s+", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    aliases = {
        "3-pt made": "three_pointers_made",
        "3pm": "three_pointers_made",
        "home run": "home_runs",
        "pass tds": "passing_touchdowns",
        "passing tds": "passing_touchdowns",
    }
    return aliases.get(s, s.replace(" ", "_"))


def pair_key(a: Any, b: Any) -> str:
    return "|".join(sorted((str(a), str(b))))
