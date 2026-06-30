#!/usr/bin/env python3
"""
PROP HUNTER AI MASTER V12 — ORCHESTRATOR
========================================

Eine Master-Datei für GitHub Actions.

Macht:
1) Datenquellen/Resultate/Features aktualisieren
2) Settlement + Learning + CLV
3) Finale v5 Telegram Card starten, falls prop_hunter_v5_patch.py vorhanden ist

Wichtig:
- prop_hunter_v5_patch.py ist nur noch ein optionales Modul.
- Workflow soll nur diese Datei starten:
    python prop_hunter_ai_master_v12.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# Daten-/Feature-Module
DATA_SCRIPTS = [
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

# Finale Telegram-Ausgabe / JK-Style / Builder
FINAL_CARD_SCRIPTS = [
    "prop_hunter_v5_patch.py",
]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def is_final_run() -> bool:
    """
    Final Run = Telegram Card senden.
    GitHub kann es explizit setzen:
      PROP_HUNTER_FINAL=1

    Ohne Variable: final ab 17:00 UTC.
    Das passt grob für Abend-/US-Sport-Karte.
    """
    if env_bool("PROP_HUNTER_FINAL", False):
        return True

    now_utc = datetime.now(timezone.utc)
    return now_utc.hour >= 17


def run_script(script: str, required: bool = False) -> int:
    path = Path(script)
    if not path.exists():
        msg = f"SKIP missing {script}"
        if required:
            print(f"ERROR {msg}", flush=True)
            return 1
        print(msg, flush=True)
        return 0

    print("=" * 70, flush=True)
    print(f"RUN {script}", flush=True)

    result = subprocess.run([sys.executable, script], text=True)

    if result.returncode != 0:
        print(f"WARNING {script} exit={result.returncode}", flush=True)

    return result.returncode


def main() -> int:
    warnings = 0

    print("=" * 70, flush=True)
    print("PROP HUNTER AI MASTER V12 START", flush=True)
    print(f"UTC: {datetime.now(timezone.utc).isoformat(timespec='seconds')}", flush=True)
    print(f"FINAL_RUN={is_final_run()}", flush=True)

    # 1) Datenpipeline immer laufen lassen
    for script in DATA_SCRIPTS:
        rc = run_script(script)
        if rc != 0:
            warnings += 1

    # 2) Finale Telegram-Karte nur beim Abend-/Final-Run
    if is_final_run():
        print("=" * 70, flush=True)
        print("FINAL CARD RUN", flush=True)

        ran_any_final = False
        for script in FINAL_CARD_SCRIPTS:
            if Path(script).exists():
                ran_any_final = True
            rc = run_script(script)
            if rc != 0:
                warnings += 1

        if not ran_any_final:
            print("WARNING no final card script found: prop_hunter_v5_patch.py", flush=True)
            warnings += 1
    else:
        print("=" * 70, flush=True)
        print("EARLY RUN only: data update done, no Telegram final card.", flush=True)

    print("=" * 70, flush=True)
    print(f"AI MASTER V12 done warnings={warnings}", flush=True)

    # Nicht hart abbrechen: Quellen können ohne Key fehlen.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
