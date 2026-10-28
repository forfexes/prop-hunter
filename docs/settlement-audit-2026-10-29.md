# Results continuation — 2026-10-29 (Europe/Zurich)

## Confirmed cause and fix

The NFL collector applied `df.head(NFL_RESULT_ROW_CAP)` to the entire league frame before matching pending player names. Thus late weeks or players later in source ordering could never be reached even when their own result rows fit the budget. Database baseline: ordinary `nflreadpy` rows stopped at 2026-10-11 (936 retained rows), whereas historical backfill rows extended to 2026-10-25. This is evidence of incomplete ordinary collection; it does not establish that every missing pick has a final eligible game.

Commit `9c313d12a217957dc117ec54e544b907cfcd46b1` scans the full source iterator and applies the row cap only after appending a matching player result. The cap is clamped to at least one. Only pending-player rows are emitted. The previous goalie-save and kicker-stat parsing fixes are retained.

## Tests

The behavioral regression places requested kicker rows after six unrelated league rows with output cap two. It verifies that weeks six and seven are collected, scheduled game dates are retained, kicking points are parsed, and a third matching row is excluded. Existing settlement identity/date, official goalie saves, kicker-only points, and historical backlog regressions pass locally. The full Results workflow runs the wider regression set before collection.

## Live run

Full Results #228: https://github.com/forfexes/prop-hunter/actions/runs/40784459507

Unlike the preceding short replays, this run collects official logs, settles eligible picks, applies L15 retention, rebuilds features, updates original cards, learns, and saves runtime state. Baseline: 89 pending source picks and 169 audit cases including retained legs; no duplicate result pick IDs. During #228, the ordinary NFL source advanced to 2026-10-26, verified directly in the database. It now includes the requested late-week rows for Saquon Barkley, Darius Cooper, Marquise Brown and Dameon Pierce. This confirms that the row-budget fix reaches data previously excluded by input truncation. Results #228 completed successfully, including collection, regression tests, settlement, retention, feature rebuild, card updates, learning, and runtime save. NFL collection emitted 43 dated rows for nine pending player names. The feature builder rebuilt 9,535 player feature records. Reporter merged four retained singles and edited six original cards. Learning used 1,357 observed deduplicated result records and 185 builder pairs.

Final audit: 158 unresolved cases (down from 169): 86 awaiting completion, 61 without uniquely matched official game evidence, five ambiguous lines and six season/fantasy markets. No ready-to-settle or missing-stat case remains. Database: 43 canonical plus 42 legacy pending source picks (85, down from 89); zero duplicate result pick IDs and zero closed empty-ESPN-stat results. Historical legs account for additional audit cases; processed upserts are not counted as new source settlements.


The four previously unmatched canonical NFL picks are now verified closed from official-date 2026-10-26 weekly rows:

| Player | Market | Actual | Result |
| --- | --- | ---: | --- |
| Saquon Barkley | Receptions Under 2.5 | 2 | Win |
| Darius Cooper | Receiving yards Under 33.5 | 17 | Win |
| Marquise Brown | Receiving yards Over 19.5 | 30 | Win |
| Dameon Pierce | Rushing yards Under 19.5 | 47 | Loss |

These four observations describe the repaired cohort, not overall strategy profitability.


## Pending evidence audit, Results #229

Commit `10e477a79fe16e3b0635583f83dbc677c8d6314c` adds explicit non-player scope classification and per-pick diagnostic context (quoted game/kickoff/ID, loaded player-row count, loaded official game dates). The diagnostics describe the loaded audit window, not an exhaustive external schedule. They do not relax settlement matching or infer a loss/void from missing observations.

Explicit `GAME`, `Total Goals`, and `Total Goals by ...` selections now have the unsupported team/game reason. Standings in the selection name are classified alongside season/fantasy markets, even when their market label only says points. A behavioral test verifies league-scoped evidence and that a player with nearby but unmatched dates remains unresolved.

[Results #229](https://github.com/forfexes/prop-hunter/actions/runs/40785688368) completed successfully. Total unresolved stays 158: 86 awaiting completion, 57 no unique official game, seven season/fantasy/standings, three team/game totals, five ambiguous lines. The reduction from 61 to 57 in the no-unique-game category is reclassification of four existing cases, not four new settlements. Reporter `merged=0`, `cards_edited=0`; this replay produced no new source-pick grading.

The loaded context confirms that remaining cases need individual evidence: some have other dates for the same player, while BYU and Mitchell Bratt have no loaded player rows. An unrelated nearby or later game is not substituted. Original legacy metadata can also be inconsistent (for example Sabrina Ionescu carries a Connecticut team hint in one migrated record); identity/team corrections need independent event evidence.
