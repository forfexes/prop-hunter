# Results follow-up — 2026-10-28

## Trigger and verified baseline

After the earlier #221 verification, subsequent card/enrichment changes introduced a regression in the test module. Results #222 failed before collection or settlement: the newly appended DD/TD assertions referenced undefined `core`, `ROOT`, and `builder` variables. At the start of this follow-up, the database had 63 canonical and 123 legacy pending source picks (186 total), with zero duplicate result pick IDs.

## Changes and observed evidence

### Results regression and DD/TD

The added assertions now run as a named expansion test with explicit source paths. The expansion suite has 12 cases. A separate behavioral test executes the production enrichment function against 15 observed-game fixtures: binary Double Double and Triple Double props with no numeric line receive the expected rates; an older sixteenth observation is excluded; a numeric prop without a line remains unenriched.

### ESPN basketball dates and DNP rows

A primary ESPN summary for WNBA game `401857136` starts at `2026-08-12T02:00Z`, which is official US gameday `2026-08-11`. The old summary/backfill code truncated the UTC date. Fifty-two pending WNBA source picks had a candidate stored one UTC day later than their pick date. NBA/WNBA ESPN collectors and the historical importer now use the same North-American gameday convention, retaining the original start timestamp in raw evidence. The settler's protection against borrowing a later unrelated game remains in place.

The same official summary explicitly lists non-playing athletes with `didNotPlay=true` and an empty stats array. The importer previously turned empty maps into `points=rebounds=assists=0`. Repairs:

- Removed 3,290 ESPN gamelog placeholders with an explicit empty stat map, no minutes, zero P/R/A, and no threes/steals/blocks. These were not observed zero-stat performances.
- Withdrew 12 closed result rows based on empty maps; reopened two canonical and six legacy source picks. Original outcomes/values remain in `pick_raw.boxscore_repair`.
- Invalidated 69 feature rows with no remaining stored observed history after that cleanup. They explicitly carry zero observed games and empty windows rather than invented observations. Later verified data can rebuild those features normally.
- New parsers skip DNP/empty observations and preserve missing stats as missing. Genuine played, observed all-zero performances remain valid.
- The settler rejects empty-map evidence, the reporter retracts its previous card evaluation, and learning ignores withdrawn result evidence and invalidated builder correlations. A later fully verified settlement clears the invalidation flag.

### WNBA legacy team hints

A legacy pick may contain a player and one team, without a quoted two-team matchup. The old candidate selector required two team matches even in that case, preventing the summary lookup. Team-only records now permit candidate inspection when that one team matches. Final game status and exact player presence in the official boxscore remain mandatory. Explicit quoted matchups still require both teams; tests reject a contradictory second team.

### EuroLeague identity and league evidence

The official EuroLeague E2026 game list, UTC starts, player rosters, and stats verified all five `NBA/WNBA`-labelled records as EuroLeague and provided a sixth missing result for Antonio Blakeney. Native names use forms such as `ZIZIC, ANTE` and `LAWSON, A.J.`. The native fallback now compares a strict normalized surname-first/initials key, preserves the requested pick identity, and stores the official name/start in raw evidence. It only accepts played games and positive playing time.

| Source pick | Official game | Official gameday | Verified stat for stored market |
| --- | --- | --- | ---: |
| A. J. Lawson, canonical 11 | E2026_27 | 2026-10-02 | 3 rebounds |
| Ante Zizic, canonical 12 | E2026_25 | 2026-10-02 | 9 rebounds |
| Armoni Brooks, canonical 13 | E2026_26 | 2026-10-02 | 6 rebounds |
| Isaac Bonga, canonical 14 | E2026_30 | 2026-10-02 | 4 rebounds |
| Scottie Wilbekin, canonical 15 | E2026_25 | 2026-10-02 | 3 assists |
| Antonio Blakeney, legacy 1117 | E2026_22 | 2026-10-01 | 12 points |

Six exact official rows were stored. The five league updates additionally required matching the original recorded kickoff to the official UTC kickoff. The sixth legacy pick's recorded kickoff is October 1 even though its sent date is October 2; settlement uses its recorded kickoff. All six source rows were verified closed by #224's settlement phase.

Results-collector changes now trigger the Results workflow, without redundantly launching the separate league-wide EuroLeague backfill (which does not execute that collector).

## Validation and commits

Nine offline programs passed, including the 12-case expansion suite, real production DD/TD L15 enrichment, observed basketball boxscores and DST/gameday handling, withdrawn-card/learning invalidation, native EuroLeague names/final-game checks, settlement identity/date guards, L15 retention, market mapping, and cross-game ACCA behavior. All Python files compiled and whitespace checks passed.

- `ae2393836dc3996fc614b20635e0d4c80320018d`: restore regressions, observed basketball stats, official gameday, DNP protection.
- `1a02a1288ee86e856877ecd84a125aecad4552ff`: official EuroLeague identity, withdrawal propagation into builder learning.
- `3fb11e5ee4bc722efaf3318eccc2cf688021af6e`: safe legacy WNBA team-only candidate lookup.

Results #223 (40778917789) completed successfully: 68 primary and six supplemental result rows processed, 13 retained singles merged, 23 original cards edited in place. Its six then-ready cases were the freshly verified EuroLeague rows inserted after its settler phase; the next serialized run consumes them.

Results #224 (40779872614) and #225 (40780241646) both completed successfully. #224 consumed all six official EuroLeague rows. #225 fetched 50 genuine WNBA player-game rows after the team-hint fix, processed 104 primary and two supplemental settlements, and rebuilt features for 9,535 players. These are processed result rows, not a count of distinct newly closed source picks.

#225 left 171 unresolved audit records: 48 canonical source picks, 43 legacy source picks, and 80 retained historical legs. Reasons: 86 awaiting game completion, 72 without a unique official game, two missing stat/line, five ambiguous double-threshold markets, and six unsupported season/fantasy markets. There were no ready-to-settle cases or ambiguous league labels. This is a reduction from #224's 247 unresolved audit records. Source counts and virtual legs must not be summed with earlier raw database counts as if they represented the same population.

## Serialized runtime freshness

Both history-writing workflows previously checked out the triggering SHA. A run waiting for the shared writer slot could therefore read history older than the preceding run's saved runtime, despite serialized writes. Both Results and card generation now check out current `main` after obtaining the workflow concurrency slot. Tests and processing execute that checked-out revision. Commit `f2a5e896e1ed9cc606bd9e184f5a9e4e35e5557c` includes a short settlement replay to verify this behavior without repeating official collection or L15 rebuilding.

Database verification after #225: 48 canonical plus 43 legacy pending source picks (91 total, down from 186); no duplicate result pick IDs; no closed results backed by empty ESPN stat maps; no stored ESPN rows with empty stat maps. Legacy WNBA pending fell from 100 before its candidate fix to 24. Two of those remaining WNBA markets have contradictory embedded thresholds and remain unresolved deliberately.

The remaining missing-stat cases are Adin Hill total saves and Joey Slye points. Five malformed markets contain two thresholds; six season/fantasy markets require a separate data/settlement model. The 72 no-unique-game cases lack sufficient uniquely matched official evidence in the loaded history. Future or live games remain pending. These cases are not converted into artificial losses, voids, or zero-stat observations.

Results #226 (40781527720) completed successfully. Logs confirm `ref: main` and checked-out revision `f2a5e896e1ed9cc606bd9e184f5a9e4e35e5557c`. Tests, settlement, learning, and runtime save passed. The reporter was idempotent: `merged=0`, `cards_ready=254`, `cards_edited=0`. The audit stayed at 171 with the same reason counts and no ready-to-settle case. Learning retained 1,344 deduplicated observed result records, 206 market groups, 124 source groups, and 179 builder pairs. Reprocessed result upserts are not new settlements.

Run links:
- [#223](https://github.com/forfexes/prop-hunter/actions/runs/40778917789)
- [#224](https://github.com/forfexes/prop-hunter/actions/runs/40779872614)
- [#225](https://github.com/forfexes/prop-hunter/actions/runs/40780241646)
- [#226](https://github.com/forfexes/prop-hunter/actions/runs/40781527720)

The earlier ladders/legs, HR/longshots, historical settlement, and pending audit protections remain covered by the offline regressions. This follow-up does not assert that every retained historical record has sufficient official evidence, or that every player has 15 observed games. Missing observations remain missing.


## Continuation: observed NHL saves and NFL kicking points

The two remaining missing-stat cases had a concrete parser gap. Official NHL goalie logs store `shotsAgainst` and `goalsAgainst` without a direct `saves` field (Adin Hill: 26 minus 1 = 25). The NHL collector now derives saves only from complete, nonnegative integer counts with shots at least goals. Existing official raw rows can be read by settlement without rewriting historical evidence; explicit saves, including zero, retain precedence.

NFL weekly raw rows already contain kicker position, `fg_made` and `pat_made`. The collector now preserves field goals made, longest field goal, and kicking points. Generic NFL player points are interpreted as kicking points only for a row explicitly marked position K. Missing components remain unknown. Neither touchdowns nor fantasy points are substituted.

Commit `0372b60cfad7d908c92e344d5bb5c80781adac99` includes collector and settlement fixes with behavioral tests for both production collector parsing and existing-row fallback. Valid zero, partial data, contradictory goals/shots, and non-kicker/non-NHL controls pass. Existing settlement/backlog, basketball, binary L15, 12 expansion cases, EuroLeague, and retention tests pass. Tests use their own processes in CI; expansion fixtures must not leak mocked modules into another test process.

[Results #227](https://github.com/forfexes/prop-hunter/actions/runs/40782062647) completed successfully, including tests, settlement, learning and runtime save. Database verification confirms Adin Hill: 25 saves, win; Joey Slye: four kicking points, loss. Slye's stored kickoff is October 4, matching official game `2026_04_TEN_BAL`, despite the October 1 sent date. Reporter merged one retained single and edited one card in place. Audit: 169 unresolved (86 awaiting completion, 72 no unique game, five ambiguous lines, six season/fantasy); zero missing-stat or ready-to-settle cases. Pending source picks fell from 91 to 89; duplicate result pick IDs remain zero. Learning now has 1,346 observed deduplicated result rows.

This was a settlement replay: it verified existing official raw evidence and did not recollect all leagues or rebuild features. New collector fields will be populated during the next full results run.

