# WNBA current-game scan repair — 30 October 2026

## Fault

The WNBA collector sorted pending scoreboard dates oldest-first and took only 18. Permanently unresolved July/August picks occupied the window repeatedly. The completed Golden State Valkyries at Atlanta Dream event on 29 October (ESPN 401918310, 16:30 UTC) could therefore remain unfetched even though it had final player stats.

The NBA fallback similarly sliced the first dates from insertion order. Neither bounded strategy guaranteed current-game coverage.

## Fix

`select_scan_dates` reserves the most recent completed/current calendar dates, then uses remaining slots for a daily rotating historical window. Future dates are last. This preserves a bounded number of requests while preventing unresolved legacy dates from monopolizing every run.

Both basketball collectors use the helper. Final-game, player-name and quoted-matchup guards remain active. A targeted WNBA refresh mode supports repair without re-fetching every sport. Targeted refreshes now also rebuild retained L15 features after settlement. The dedicated feature-rebuild workflow uses the intended 15-game retention setting.

## Tests

- More than 30 old dates ahead of the current date do not hide the current game.
- Historical rotation eventually visits every old date.
- Scan budget, unique dates, associated picks and future-date priority are preserved.
- Production WNBA main is exercised with a stubbed scoreboard and fixed UTC clock.
- Existing 14 expansion suites and native NBA collector regression pass.

## Official evidence

- https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates=20261029
- https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary?event=401918310

Observed final values: Gabby Williams 26 points; Kaila Charles 5 rebounds; Allisha Gray 23 points; Rhyne Howard 21 points; Angel Reese 14 rebounds; Jordin Canada 2 assists. No DNP or missing stat map was converted into zero.

## Verified production outcome

Results #248 succeeded: 14 player gamelogs loaded, 16 original Telegram cards edited, 21 source picks closed. Remaining pending sources fell from 107 to 86 (57 canonical and 29 legacy). The broader audit, which also includes virtual combo legs, fell from 220 to 167. No unmatched or ambiguous league classifications remain in that audit snapshot.

Dedicated Feature Rebuild #7 was started with 15-game retention. Direct database checks confirm that Allisha Gray, Angel Reese, Gabby Williams, Jordin Canada, Kaila Charles and Rhyne Howard each retain 15 games and now have `last_game_date=2026-10-29` rather than October 24.

The remaining source backlog is not complete. Older cases still include missing official participation/event evidence, season/fantasy markets and contradictory thresholds; current overnight NBA/NHL/NFL games also remain pending.
