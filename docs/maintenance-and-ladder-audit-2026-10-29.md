# Maintenance and ladder accounting — 2026-10-29

## Baseline failures and evidence

Daily Control #161 (40862939027) stopped before integrity/retention because the conflict scanner matched literal grep patterns in valid workflow commands. Upstream commit 1ec6f7a already restricted detection to conflict lines; this repair additionally corrects its escaped whitespace pattern so a real bare separator is detected. Tests cover literal grep text, opening/closing conflict markers and bare/whitespace separators.

Shadow Data #37 (40866714295) passed regressions but its snapshot-retention DELETE hit PostgreSQL error 57014, statement timeout. The former implementation deleted every stale snapshot in one transaction. The replacement selects at most 250 expired snapshot IDs and deletes that primary-key batch with the same cutoff predicate. It stops when empty or after 100 batches, explicitly logging deferred backlog at the budget. Errors still propagate. A direct database probe deleted exactly 250 expired snapshots successfully; the seven-day retention predicate remains enforced.

The current retained history has 88 closed, valid ladder tickets and 279 settled rungs. Every rung lacked its own profit field. The newly added performance summary counted rungs but treated that absent value as zero, despite nonzero parent profits. The report now derives missing rung P/L from actual stake, odds and result using the same settlement rounding, and inherits parent sport metadata when missing. It counts each rung once. Source evidence is not mutated. The retained sample sums to +0.29 units both by parent tickets and by repaired rung accounting: 94 winning and 185 losing rungs, +0.6% ROI. This describes the loaded retained history rather than lifetime performance.

## Changes and checks

Commit 27f94468ebc575df5ecb0276b54dddc8e49aa381 contains the fixes, behavioral regressions and CI coverage. Local checks passed: settlement/backlog and rung P/L consistency; bounded retention, its cutoff predicate, write-failure propagation and batch budget; conflict detection; 14 expansion cases; whitespace checks.

Results now runs snapshot-retention tests and the static workflow check. Snapshot-retention changes trigger the Shadow Data workflow. A dedicated daily-control trigger permits verification of its full offline integrity gate; its existing destructive-retention step remains scheduled/manual only.

Live verification:
- Results #238: https://github.com/forfexes/prop-hunter/actions/runs/40873651825
- Daily Control #162: https://github.com/forfexes/prop-hunter/actions/runs/40873651823
- Shadow Data #38: https://github.com/forfexes/prop-hunter/actions/runs/40873651847

Results #238 completed successfully. Its regression step passed the bounded-retention and workflow-conflict checks, and settlement reporter merged 19 retained singles and edited 26 original cards. The live retained-history ladder report now shows 106 wins, 188 losses, +3.49 units and +6.8% ROI; this includes newly merged results, so it is a different snapshot from the baseline example above. No lifetime profitability claim is made. Final database source pending counts: 64 canonical plus 31 legacy = 95; duplicate result pick IDs remain zero. The audit contains 177 cases including historical legs and combo parents: 70 awaiting completion, 84 without a unique game, eight parent ticket market labels, seven season/fantasy/standings, three team/game totals, five ambiguous lines. No ready-to-settle or missing-stat case remained.

Shadow Data #38 completed successfully. It requested deletion of 25,000 expired snapshots through bounded batches, then reached the explicit maintenance budget. Remaining stale rows are deferred; this is not a claim that the entire retention backlog is empty. Shadow collection itself returned zero rows across six leagues.

Daily Control #162 passed workflow validation, then exposed a stale hard-test database fixture: the current snapshot loader calls `lte`, `order` and `range`, but the fixture did not implement those methods. The fixture now models bounded paging. All seven hardtest suites pass locally; market, EuroLeague, event-market and ACCA regressions also pass. Replacement Daily Control #163 (40874108186) verifies the complete offline gate.

[Daily Control #163](https://github.com/forfexes/prop-hunter/actions/runs/40874108186) completed successfully, including safe workflow checks, the complete offline integrity gate and safe-repair save. Its database retention step was correctly skipped for a push-triggered verification; live retention was exercised separately by Shadow Data #38. Results #238, Shadow Data #38 and replacement Daily Control #163 are all green.
