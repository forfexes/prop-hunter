# Current-season form and overnight settlement — 30 October 2026

## Verified faults

- The enrichment cache used player/stat but omitted league and reference season/date. It could combine rows across seasons or leagues and label the result current L15.
- The fallback queries did not consistently retain date/league context.
- With fewer than six games, the code multiplied an unpaired bookmaker implied probability by 1.04 and called that a no-vig estimate. That manufactured a positive edge without independent probability evidence.
- `gamelog_l10_rate` was an alias of the same smoothed L15 model value. Neither label necessarily represented the actual historical hit fraction.
- Under rates used `1 - over_rate`, counting equal-to-line pushes as Under successes.
- Conflicting same-day basketball rows could count as multiple games.
- The ESPN NBA collector did not require final event status before fetching player statistics.

## Implemented policy

The common form selector filters by league, reference date and a calendar-aligned current-season boundary: September for NBA/NHL/European winter leagues, July for NFL/NCAAF, and January for MLB/WNBA. Dates beyond the reference date are excluded. These boundaries distinguish seasons; they do not independently classify preseason versus regular-season phases.

Older retained gamelogs are not deleted by this form policy. The feature table stores a separate `historical_last_15` comparison and `retained_games_total`. Current-window `games_total` and `form_games_available` report the actual available sample, including zero, rather than pretending every player has 15 current games.

Same-day NBA/WNBA rows count once when observations agree or one record has uniquely observed official start context. Unresolved conflicting duplicates are omitted instead of selected by arbitrary game ID.

Both fast and fallback enrichment use the selector. Cache identities include league and reference date. Small samples retain independent existing evidence but receive no fabricated market-probability uplift. L10/L15 rates are actual strict-threshold hit fractions; smoothing/Monte Carlo values are separately identified as model estimates.

NBA ESPN collection accepts completed events only. Scheduled, live, absent and contradictory final-status evidence is rejected.

EuroLeague and AHL feature rebuilds are scoped to their own leagues. EuroLeague data collection no longer occupies the shared history-writer concurrency group, which could evict a pending Results run despite `cancel-in-progress: false`.

## Regression coverage

Production enrichment is executed through its actual AST with current/old-season, cross-league and future rows, both batched and fallback reads, conflicting duplicates, insufficient samples, distinct L10/L15 outcomes and integer-line pushes. Feature rebuilding is tested with preserved historical comparison, actual current counts and league-scoped writes. NBA collection is tested to avoid requesting live boxscores. Existing 14 expansion suites, 13 ladder tests, retention tests, DD/TD enrichment and combined-price delivery regressions pass.

## Run tracking

Results #251 and #252 were replaced while pending; they are not successful verification runs. Full collection #253 contains the form and final-status changes. A further Results run was queued by the subsequent feature-scope regression update. Final production findings are appended after verification.

## Production verification

Full Results [#253](https://github.com/forfexes/prop-hunter/actions/runs/41014073450) and [#254](https://github.com/forfexes/prop-hunter/actions/runs/41014327890) completed successfully. #253 merged 34 reporter records and edited 50 cards. #254 refreshed 9,554 player feature records; its following settlement pass was idempotent (zero merges, zero card edits). Replay [#255](https://github.com/forfexes/prop-hunter/actions/runs/41015501822) also passed with zero merges and zero card edits.

A database cross-check after #253 still showed older feature dates for the three example players; #254 brought all three through 29 October. The feature reader additionally now uses an immutable-id cursor rather than offsets, preventing concurrent deletion of earlier rows from shifting subsequent pages. A regression explicitly deletes an earlier page row between reads and verifies no later row is skipped. This is a pagination vulnerability demonstrated by regression, not a claim that a particular deletion was traced as the sole cause of every stale row. Missing database connectivity fails the rebuild instead of silently publishing an empty rebuild.

Stored current-season observations at 06:45 UTC:

| Player / line | Available games | Hits | Latest game |
|---|---:|---:|---|
| Zach Edey rebounds >13.5 | 7 | 0 | 2026-10-29 |
| Ja Morant assists >9.5 | 7 | 0 | 2026-10-29 |
| Jrue Holiday points >19.5 | 7 | 1 | 2026-10-29 |

These are seven-game observations, not ten or fifteen games. The 29 October rows record Morant 1 minute / 0 assists, Edey 1 minute / 2 rebounds, Holiday 24 minutes / 6 points; the observed short appearances are not fabricated DNP zeros. The original Lottery ticket remains withdrawn because its combined quote was unverified.

Source-table pending rows are now 39 (10 canonical, 29 legacy), versus 85 before this refresh sequence. The separate history/leg audit reports 48 unresolved items; its population includes virtual/history legs and must not be confused with source-row counts. Remaining cases include missing or mismatched official event context, unproven DNP/void handling, unsupported both-team totals, five contradictory market lines and seven unsupported season/fantasy markets. No arbitrary losses, wins or voids were assigned to erase that backlog.

A dedicated feature rebuild [#8](https://github.com/forfexes/prop-hunter/actions/runs/41015844796) was started after the full Results job to validate the new cursor reader in production. Final result follows below.

Feature rebuild #8 completed successfully: regression suite passed, 3,980 rows beyond the existing 15-game retention limit were pruned, and 9,554 player features rebuilt. The final database read confirmed all three examples have `games_total=7`, `last_game_date=2026-10-29`, `form_window_policy=current_season`, and new rebuild timestamps at 06:46 UTC. Cursor fix commit: `4de8934917b011a83e3378200a7e4f38f6be08c9`.
