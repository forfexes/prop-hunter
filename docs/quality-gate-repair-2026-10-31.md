# Quality gate repair — 2026-10-31

## Changes on main

- Removed the MLB HR probability floor that converted HR-rate / DATA+ profile signals into a synthetic 12%–30% per-game probability. HR candidates now require an explicit finite model/fair probability and a real observed bookmaker price.
- Removed the general source-probability fallback that derived probability from decimal odds plus narrative markers and DATA+ score. Missing model probability now fails closed.
- Builder probability no longer blends implied bookmaker probability back into a model estimate. It excludes fair_prob-only inputs and requires at least six actual gamelog observations before a builder candidate can produce EV.
- Results collector failures are no longer silently swallowed. Each collector still runs so successful sources can contribute, but any nonzero collector exit is recorded and makes the overall workflow visibly fail after settlement/save.
- Results workflow now triggers when the core probability or builder engine changes and runs the new quality-gate regression test.

## Supabase consistency repair

- Paige Bueckers PRA Over 27.5 and Jessica Shepard RA Over 14.5: source result fields were reconciled to the already stored official loss rows (actual values 24 and 14).
- Austin Wells Home Run: no auditable result row existed, so the source row was reopened as pending and the unsupported loss profit marker cleared.
- Post-repair check: zero status/result conflicts in both pick tables.
- Current pending rows: 29 in prop_hunter_picks and 29 in prop_picks. These are separate source populations and must not be added without identity-level deduplication.

## Important data limitation

The current-season feature table is still sparse for recently started leagues. Among the 9,627 feature rows checked:
- American football: 647 with no current-season games; 990 with 1–5; 694 with 6–9; 1 with 10–14; none with 15+.
- Baseball: 319 with none; 189 with 1–5; 127 with 6–9; 80 with 10–14; 1,075 with 15+.
- Basketball: 532 with none; 513 with 1–5; 545 with 6–9; 85 with 10–14; 79 with 15+.
- Ice hockey: 270 with none; 547 with 1–5; 330 with 6–9; 457 with 10–14; 253 with 15+.
- NHL: 496 with none; 651 with 1–5; 142 with 6–9; 496 with 10–14; 109 with 15+.

The feature builder retains actual available sample counts; it must not label a short sample as a full L15. The new builder EV gate requires at least six games. Further tightening of all singles should be driven by market-specific backtests, not a blanket cutoff that would eliminate legitimate early-season markets.

## Verification status

The new regression test is wired into the Results workflow. The workflow was updated on main and should run from the push trigger. The connected GitHub tool did not expose a workflow-run listing/dispatch action in this session, and the latest commit had no reported status checks at the time of inspection; therefore a green CI run is **not yet claimed**.
