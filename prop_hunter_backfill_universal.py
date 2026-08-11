#!/usr/bin/env python3
"""Obsolete compatibility stub.

The former file was a duplicate CLV engine, not a universal backfill.
Canonical CLV is implemented by prop_hunter_clv_engine.py.
"""


def main() -> int:
    print("SKIP prop_hunter_backfill_universal.py: obsolete duplicate disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
