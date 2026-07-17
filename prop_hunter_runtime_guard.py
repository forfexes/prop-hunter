#!/usr/bin/env python3
"""Fail-fast deployment guard for PROP HUNTER V12.2."""

from __future__ import annotations

from pathlib import Path
import inspect
import sys

import prophunter

EXPECTED = "12.3-HR-RISK-LOTTERY"


def fail(message: str) -> None:
    print(f"RUNTIME GUARD FAILED: {message}", file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    if getattr(prophunter, "PH_RUNTIME_VERSION", None) != EXPECTED:
        fail(
            f"wrong prophunter.py version: "
            f"{getattr(prophunter, 'PH_RUNTIME_VERSION', None)!r}; expected {EXPECTED!r}"
        )

    for name in (
        "_has_observed_odds",
        "enforce_final_verified_market_gate",
        "_conservative_live_probability",
    ):
        if not hasattr(prophunter, name):
            fail(f"prophunter.py missing {name}")

    ph_source = inspect.getsource(prophunter)
    builder_path = Path(__file__).with_name("prop_hunter_builder_engine.py")
    if not builder_path.exists():
        fail("prop_hunter_builder_engine.py missing")
    builder_source = builder_path.read_text(encoding="utf-8")

    for marker in (
        "V12.2 final verified-market gate",
        "HOME-RUN RISK",
        "RISK BUILDER",
        "no verified bookmaker prices matched",
        'rejected["unverified_odds"]',
        '"odds_observed": False',
        "Configured Odds API keys exhausted",
    ):
        if marker not in ph_source:
            fail(f"prophunter.py missing marker: {marker}")

    for marker in (
        'return len(books) == 1 and "" not in books',
        "Echte Alt-Linien",
        "if not _real_price(anchor)",
    ):
        if marker not in builder_source:
            fail(f"builder missing marker: {marker}")

    synthetic = prophunter.Prop(
        player="Synthetic Player",
        market="Pitcher Strikeouts",
        odds=1.83,
        point=2.5,
        sport="MLB",
        direction="over",
        features={
            "source": "propcruncher",
            "odds_observed": False,
            "price_type": "synthetic",
        },
    )
    if prophunter._has_observed_odds(synthetic):
        fail("synthetic ProCruncher price was accepted")

    real = prophunter.Prop(
        player="Real Player",
        market="Pitcher Strikeouts",
        odds=1.91,
        point=4.5,
        sport="MLB",
        direction="over",
        features={
            "source": "betmgm",
            "bookmaker": "betmgm",
            "odds_observed": True,
            "price_type": "bookmaker",
        },
    )
    if not prophunter._has_observed_odds(real):
        fail("observed bookmaker price was rejected")

    print(f"RUNTIME GUARD OK: {EXPECTED}")
    print("Synthetic odds rejected: OK")
    print("Observed bookmaker odds accepted: OK")
    print("Same-book builder/ladders required: OK")
    print("Verified HR/Risk/Lottery engine present: OK")


if __name__ == "__main__":
    main()
