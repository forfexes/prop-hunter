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


## MLB identity and quoted event dates

The primary MLB StatsAPI people search for `Max Muncy` returns two distinct player IDs: 571970 and 691777. The collector previously returned the first exact-name match and also permitted substring matches. Commit `81ca19c6160b0029a4780ca89eac9e184abb439c` now requires exactly one distinct official ID with the full normalized name; accent normalization remains supported. Ambiguous searches produce a warning and no new collected rows. This does not retroactively establish that stored LAD rows belong to the wrong player, and no historic result is withdrawn on that assumption.

Historical MLB fetch targeting now prioritizes the stored event kickoff (including raw kickoff), then game date, then sent/created dates. Previously it used sent dates first, potentially omitting an older target event outside the recent-game window. The existing previous-US-gameday lookup is preserved.

Behavioral tests cover both real same-name IDs, a unique accented name, rejection of substring-only names, event date precedence, nested kickoff, and fallback from malformed kickoff. Settlement identity/date and historical backlog regressions pass. Results #230 stopped in offline tests before any collection or settlement. A concurrently added Over/Under assertion block referenced undefined module-level `core`. Commit `b72f94954a9cb24bc2bced63382f09cea4dc215d` moves those assertions into a named test with explicit core source loading. All 13 expansion cases pass locally; the Over/Under implementation itself is preserved. [Replacement Results #231](https://github.com/forfexes/prop-hunter/actions/runs/40786657004) completed successfully. Live logs confirm ambiguous IDs are rejected for both Max Muncy (571970/691777) and Sean Murphy (595340/669221). MLB emitted 482 player-game rows for 21 pending names; features were rebuilt for 9,535 players. The pending audit remained 158 and reporter edits were zero. This validates identity safeguards without claiming additional source settlements.


### WNBA empty-hint rejection

An additional concrete blocker was reproduced: `_game_text` joined absent metadata into whitespace, so the documented no-matchup fallback was never entered. Legacy picks with all team/game fields null were rejected by candidate matching. Earlier #228 logs showed 24 pending WNBA picks but only three candidate events and zero parsed rows.

The official ESPN scoreboard lists Minnesota at Golden State as event 401857157 with kickoff `2026-08-20T02:00Z`, official US gameday August 19. Its final summary explicitly contains played rows for Courtney Williams, Kayla McBride and Olivia Miles; stored backfill rows for the same ID retained the UTC date August 20. The corrected existing parser can normalize those dates, once the whitespace candidate rejection is removed.

The WNBA fix strips joined metadata before matching. Behavioral tests cover empty dictionaries, null metadata, whitespace-only hints, valid one-team hints and contradictory explicit matchups. Exact requested player presence, completed event status, and explicit two-team matchup checks remain required. A full serialized Results run verifies collection and settlement; no nearby-game date is manually substituted.


During #232, database verification confirms event 401857157 was recollected with official date 2026-08-19 and retained raw kickoff `2026-08-20T02:00Z`. Three exact pending pick IDs are now graded from that event: Courtney Williams 1 three-pointer (win over 0.5), Kayla McBride 3 three-pointers (win over 1.5), Olivia Miles 5 rebounds (win over 2.5). [Results #232](https://github.com/forfexes/prop-hunter/actions/runs/40787005802) completed successfully. WNBA collection examined 55 candidate events and emitted 17 observed player-game rows. Eleven previously pending legacy source picks closed: WNBA pending fell from 24 to 13, total source pending from 85 to 74 (43 canonical, 31 legacy). No duplicate result pick IDs and no closed empty-ESPN-stat results were found.

The final audit fell from 158 to 147: 86 awaiting completion, 46 without unique official-game evidence, seven season/fantasy/standings, three team/game totals and five ambiguous lines. No ready-to-settle or missing-stat case remained. Features were rebuilt for 9,535 players; learning used 1,368 observed deduplicated result rows. The reporter made zero card edits. This pass does not establish that the old Telegram messages for these legacy picks were updated. The WNBA whitespace fix is commit `b8778cf8a5d8cf16515ad445f81a45c6b1a0ec31`.
