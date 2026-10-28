# Settlement audit — 2026-10-28

## Verified starting point

Results #212 (40619049684), #213 (40619234471), and #214 (40619527713) all completed successfully. Their logs showed successful jobs but incomplete historical settlement. Before this audit's new results run, source tables had 57 canonical and 198 legacy pending rows.

## Repairs

- Removed 53 duplicate result rows left by the transition to one result ID per pick; retained the canonical result ID. The duplicate closed outcomes agreed.
- Synchronized five legacy `status=pending` rows whose `result` was already closed. This left 250 source pendings before #215.
- Moved gamelog retention after both settlers, preserving freshly fetched historical official stats until grading finishes.
- Removed MLB's default four-day exclusion and preserved exact historical pending dates alongside recent gamelogs.
- Included retained ladder/builder/longshot legs in collector and settlement reads, even when no standalone single exists.
- Persist results successfully before mirroring source status. Supplemental settlement uses the same persistence path.
- Exclude `no_result` from new result writes. Learning counts each pick ID once.
- Normalize PA/PR, basketball compound markets, legacy `Pass Yds`, `3-PT Made`, and goalie `total_saves` aliases. Season/fantasy markets and contradictory repeated over/under thresholds fail closed.
- Resolve MLB accent variants against official player names while preserving the queried identity in targeted gamelog reads and retaining the official name/ID in raw evidence.
- Grade ladder thresholds against canonical stat families, preserve per-rung stakes, and merge all retained historical cards. Cross-game push legs use surviving observed prices; same-game repricing remains unresolved without a bookmaker price.
- Serialize EuroLeague's data/retention workflow with the shared results/history writer group for future runs.

## Historical data corrections

- Recalculated 20 Rebounds+Assists result rows from the stored official rebounds and assists, correcting seven outcomes. Mirrored 19 distinct legacy source rows. Original stat/value/outcome is retained under `pick_raw.settlement_repair`.
- Corrected two Hits+Runs+RBIS stat keys and totals; their outcomes did not change.
- Withdrew seven result rows with conflicting duplicate over/under thresholds from closed-result learning and reopened five distinct legacy source picks. Original outcomes are preserved in repair metadata. No arbitrary void or loss was assigned.

## Validation

Seven offline programs passed: settlement backlog, settler identity/date, L15 retention, expansion (11 suites), EuroLeague, market mapping, and ACCA. All Python files compiled and `git diff --check` passed. Local tests used the existing runtime's vendored Requests library without installing packages; CI uses the workflow's normal dependencies.

`prop_hunter_pending_audit.py` produces `prop_hunter_pending_audit.json` after every results run. It lists every unresolved source pick and virtual leg with its reason, including future/incomplete games, missing unique official games, ambiguous league, unsupported season/fantasy market, conflicting thresholds, and missing stats/lines.

## L15 verification

After the rebuild, all 9,595 player-feature rows across nine leagues had a populated `last_15` object; none had an empty L15 window. 5,608 players had at least 15 real games. Remaining windows use the actual available games rather than filling missing observations.

| League | Players | At least 15 games |
| --- | ---: | ---: |
| AHL | 834 | 641 |
| EuroLeague | 438 | 285 |
| MLB | 1,790 | 1,355 |
| NBA | 895 | 555 |
| NFL | 2,332 | 944 |
| NHL | 1,884 | 906 |
| SHL | 517 | 338 |
| Swiss NL | 495 | 344 |
| WNBA | 410 | 240 |

## Commits and verification runs

- `a5dc9f40e06c8bf1196d91a0dfec14d41306f466`: historical debt, virtual legs, safe persistence, ladder grading; verified by Results #215 (40629761222).
- `f44eb2794bb9307cffc698cca64b9c90fe7c4118`: compound/stat aliases, accent identity, unresolved-pick audit; verification Results #216 (40630423708), serialized behind #215.

- `49e1dffa61e382321681822d2214efeec905aea6`: enforce kickoff/completion checks on virtual legs and reporter merges, restore pending card text after premature grading; verification Results #217 (40631165580).

## Live verification correction

The #215 live output exposed 26 current-day virtual-leg results whose historical leg records lacked kickoff context. These provisional result rows were withdrawn from closed-result learning, with prior evidence preserved in repair metadata. Six prematurely mirrored canonical statuses were reopened. The follow-up fix inherits unique matching source-pick kickoff context and refuses same-day grading when kickoff is absent. The reporter also checks readiness before merging a result, resets premature combos, and can restore the original card text with an explicit pending count. Regression cases cover all four paths.

Results #215 completed successfully: 416 primary and 34 supplemental result rows processed; 25 retained singles merged; 95 original Telegram cards edited in place. EuroLeague Data #33 also completed successfully.

## Repeated-quote context

The residual audit identified historical NBA legs whose source singles carried multiple market thresholds for one player. A strict one-row-only context check discarded an otherwise unique kickoff, losing the actual UTC gameday. `inherit_leg_context` now accepts repeated quotes sharing a unique kickoff, prefers exact stored matchup text, preserves existing kickoff metadata, and leaves conflicting kickoff candidates unresolved. The reporter uses the same helper. Tests cover identical starts, conflicting starts, and two different matchups.

Commit `964cc36850e17f8cf0933b5ef98ee1167f194465` introduced this repair. Its queued Results #218 (40632067396) was superseded; the refined implementation was verified by #219–#221. Its explicit `[settlement-replay]` marker reuses the official logs and L15 features rebuilt by the preceding full runs; normal runs continue to collect and rebuild. Compilation, offline tests, settlement, in-place evaluation, audit, and learning remain enabled.

Results #216 completed successfully: 319 primary and 34 supplemental results processed, 19 retained singles merged, and 82 original cards edited. Telegram returned four 429 responses; the reporter honored the supplied retry delays and completed successfully.

Results #217 completed successfully: 121 primary and 10 supplemental result rows processed, 14 original cards corrected in place. The audit had **zero ready-to-settle leftovers**: 244 unresolved source picks/legs comprised 25 awaiting game completion, 202 without a unique official game, five ambiguous leagues, one missing stat/line, five contradictory market lines, and six unsupported season/fantasy markets.

The repeated-quote regression was extended to differing teammate feed times and explicit matchup scope. Final commits `a2b22c326b2d4803f5d6fd99a02ebcf12ad1c5cf` and `2dee705dd28055eb4557a1354cf42d25497849e5` refine that priority. Queued #218 was superseded before execution; #219 (40632337151) and #220 (40632426169) replay the stored official evidence in sequence.

Results #219 completed successfully: 169 primary and 11 supplemental result rows processed, another 25 original cards edited. The remaining audit fell to 218 unresolved items (49 awaiting completion, 152 without a unique official game, five ambiguous leagues, one missing stat/line, five conflicting lines, six season/fantasy markets); zero ready-to-settle items remained.

## Reporter pagination

The #219 log showed exactly 1,000 reporter results although the database contained more recent evidence. The reporter now reads stable 1,000-row pages ordered by settlement timestamp and unique result ID until the final short page. It fails explicitly on incomplete/error responses. A regression verifies 1,002 results across two HTTP pages and the expected offsets. Commit `f50d3b266ea30fb6ff6bba88476abdd8c6d132fa` is the final reporter fix.

Results #220 completed successfully: 167 primary and 11 supplemental result rows processed, 23 original cards edited. Its report had 195 unresolved items and zero ready-to-settle leftovers.

A database verification after #220 found:

- 25 canonical and 123 legacy pending source picks.
- Zero duplicate result pick IDs.
- Zero prematurely closed source picks by their recorded kickoff/completion window.
- Zero closed current-day virtual results lacking kickoff metadata.
- Zero closed Rebounds+Assists results with an incorrect stat key.

## Final verification

Results **#221 (40632740319) completed successfully**, including compilation, all configured offline regressions, settlement, in-place reporting, audit, learning, and runtime-state commit. It replayed stored official evidence: 33 primary and two supplemental result rows processed. The reporter read **1,028 recent results** across all pages. It found no additional card changes (`cards_edited=0`), confirming idempotent evaluation at the final state.

Final audit generated at **2026-10-28 04:32:20 UTC (05:32:20 Europe/Zurich)**:

| Unresolved reason | Source picks and virtual legs |
| --- | ---: |
| Awaiting game completion / current-day kickoff context | 49 |
| No unique official game available | 153 |
| Ambiguous league | 5 |
| Missing stat or line | 1 |
| Conflicting duplicated market thresholds | 5 |
| Unsupported season or fantasy market | 6 |
| **Total unresolved** | **219** |
| **Ready to settle but left unprocessed** | **0** |

The 219 cases comprise **25 canonical source picks, 123 legacy source picks, and 71 virtual legs**. Source pendings fell from 250 immediately before #215 to 148; the remaining cases were inspected and classified, not arbitrarily voided or graded as losses. Details are in `prop_hunter_pending_audit.json`.

Final database checks reconfirmed zero duplicate result pick IDs, zero source status conflicts, and zero closed Rebounds+Assists rows with an incorrect stat key. All eleven current-day canonical source picks remained pending under their recorded completion windows.

Successful verification runs: #212, #213, #214, #215, #216, #217, #219, #220, #221; EuroLeague Data #33 also succeeded. #218 was superseded while pending and did not execute. The final code fix is `f50d3b266ea30fb6ff6bba88476abdd8c6d132fa`; normal scheduled runs continue the full collection/retention/L15 cycle.
