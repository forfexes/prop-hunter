"""CLI entrypoint:  python -m prophunter [flags]"""
from __future__ import annotations

import argparse
import sys

from .betting.backtest import backtest
from .betting.clv import update_closing_lines
from .logging_setup import setup_logging
from .pipeline import run


def main() -> int:
    parser = argparse.ArgumentParser(description="PROP HUNTER v3")
    parser.add_argument("--dry-run", action="store_true",
                        help="run pipeline but do NOT post to Telegram nor persist")
    parser.add_argument("--sport", choices=["mlb", "nba", "wnba", "nfl", "euroleague"],
                        help="restrict to a single sport")
    parser.add_argument("--backtest", type=int, metavar="DAYS",
                        help="print a backtest report for the last N days and exit")
    parser.add_argument("--update-clv", action="store_true",
                        help="snapshot closing odds for pending CLV rows")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    import logging
    setup_logging(logging.DEBUG if args.verbose else logging.INFO)

    if args.backtest:
        print(backtest(args.backtest))
        return 0
    if args.update_clv:
        n = update_closing_lines()
        print(f"Updated {n} CLV rows.")
        return 0
    run(dry_run=args.dry_run, sport_filter=args.sport)
    return 0


if __name__ == "__main__":
    sys.exit(main())
