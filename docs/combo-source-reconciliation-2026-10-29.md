# Closed combo source reconciliation — 2026-10-29

## Verified defect

Canonical source pick 424 (`6-Leg AGGRESSIVE ACCA`, October 28) remained pending although its complete retained-history ticket was settled as loss, profit -0.07. The source's stored quote and the settled history have the same creation timestamp, stake, total price and six exact player/market/game/book/line/side/price legs. The settled history entry lacked the original source dedup key. Existing source-key reconstruction only runs for pending history tickets and depends on mutable leg details, so it did not repair already-closed legacy tickets.

## Repair

Commit 18db95ad103c5084d18d247f77d404b0c9867420 builds an immutable complete-quote fingerprint for retained closed combos and pending source snapshots. It requires the original timestamp, ticket economics, and at least two complete player legs. Enriched result/actual fields are excluded from identity. Only a single matching closed, non-invalidated history ticket with all legs closed can provide the source status/profit. The actual stored source dedup key and date are used for the existing date-filtered source updater. Newly associated keys are retained in history for later corrections. No name-only, market-only or nearest-date update is used.

Source combo parents with explicit raw ticket type and leg details are now audited as awaiting combo legs rather than unsupported individual stat markets. This is classification, not automatic grading of unresolved parents.

## Verification

Behavioral tests cover an enriched closed ticket against its original source quote, mismatched game, changed stake, different date, duplicate history candidates and invalidated evidence. Existing settlement, source-write, rung accounting, identity/date and workflow checks pass locally.

The replay uses existing official result evidence; no new league-wide collection is required for this source-mirroring repair. Live outcome follows after completion.


## Live verification, first replay

[Results #239](https://github.com/forfexes/prop-hunter/actions/runs/40876099155) completed successfully. Six pending source tickets matched unique closed history tickets and were synchronized. Database pick 424 is now `status=result=loss`, profit -0.07, verified directly. Canonical pending source picks fell from 64 to 58 without new official-game collection; these are recovered source mirrors of existing settlements, not six newly decided games. Reporter edits and single merges were zero. Audit fell from 177 to 171. Two legacy Lottery/Risk parents use raw type `big`, outside the audit's explicit parent-type set, and remain classified unmapped. This label limitation does not authorize grading incomplete tickets.

Additional commit daad5fc31518693cc3d48f4c5a286da17669773b includes each ladder rung's individual stake in the quote identity and rejects closed parent records with unknown profit. Its regression covers equal total stake with different rung allocation and missing P/L. The follow-up replay checks that reconciliation is idempotent.


[Follow-up Results #240](https://github.com/forfexes/prop-hunter/actions/runs/40876330916) completed successfully. Reconciliation requested zero further updates; reporter merged zero singles and edited zero cards. Audit remained 171 (70 awaiting completion, 84 no unique official game, two legacy parent labels, seven season/fantasy/standings, three team/game totals and five ambiguous lines). No ready-to-settle or missing-stat case remained. Database pending source total is 89 (58 canonical plus 31 legacy); duplicate result pick IDs remain zero. Both replays saved runtime state successfully.
