#!/usr/bin/env python3
"""
PROP HUNTER AI MASTER V11 — ORCHESTRATOR
========================================

Startet die V11-Datenbank-Module nacheinander.
Fehlende optionale Dateien werden übersprungen, damit der Workflow nicht unnötig abbricht.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS = [
    "prop_hunter_source_audit.py",
    "prop_hunter_odds_oddsapi_io.py",
    "prop_hunter_odds_sportsgameodds.py",
    "prop_hunter_odds_opticodds.py",
    "prop_hunter_results_nba.py",
    "prop_hunter_results_wnba.py",
    "prop_hunter_results_nfl.py",
    "prop_hunter_results_mlb.py",
    "espn_multisport_results.py",
    "prop_hunter_feature_builder.py",
    "prop_hunter_settler.py",
    "prop_hunter_clv_engine.py",
    "prop_hunter_learning_update.py",
    "prop_hunter_social_signals.py",
    "prop_hunter_github_source_scanner.py",
    "prop_hunter_source_reliability.py",
]


def run_script(script: str) -> int:
    path = Path(script)
    if not path.exists():
        print(f"SKIP missing {script}", flush=True)
        return 0

    print("=" * 60, flush=True)
    print(f"RUN {script}", flush=True)

    result = subprocess.run([sys.executable, script], text=True)
    if result.returncode != 0:
        print(f"WARNING {script} exit={result.returncode}", flush=True)

    return result.returncode


def main() -> int:
    warnings = 0

    for script in SCRIPTS:
        rc = run_script(script)
        if rc != 0:
            warnings += 1

    print("=" * 60, flush=True)
    print(f"AI MASTER V11 done warnings={warnings}", flush=True)

    # Nicht hart abbrechen, weil manche Quellen optional sind und ohne Key warnen können.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
