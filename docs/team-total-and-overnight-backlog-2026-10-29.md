# Team totals and overnight data refresh — 2026-10-29

## Baseline

The live database contained 89 pending source picks: 48 issued October 29 and 41 older (ten canonical, 31 legacy). Sent date is not the event date: three October 28 NHL picks quote October 29 UTC starts. The last full official NHL collector run was Results #237 at 03:37 UTC; subsequent settlement replays reused those existing gamelogs. Three overnight picks consequently lacked October 28 official US-gameday rows.

## Verified old team-total case

Source pick 37 is BYU team points Under 27.5, odds 1.77, stake 0.33, for BYU (#10) at TCU on October 3, 23:00 UTC. It was passed through the player-gamelog settler although BYU is a team. Primary event evidence confirms the matchup, final score BYU 17–TCU 10 and the quoted 18:00 Central kickoff:
- https://gofrogs.com/game-center/20099
- https://byucougars.com/news/2026/09/28/byu-football-game-week-2026-at-tcu
- ESPN final scoreboard event 401856818, October 3 23:00Z.

## Change and safeguards

Commit ff509ea8426a554c59d0de6772f37be369cfdec5 adds a dedicated team/game-total settlement path. It requires an explicit team/whole-game selection, supported score stat, positive unambiguous line, quoted two-team matchup and aware kickoff. Both competitor identities must match complete ESPN team aliases; shared city tokens alone cannot match. Only completed events with numeric integer scores and kickoff within 15 minutes are eligible. Exactly one official event ID must match across the narrow date window. The result records full event evidence and a per-event source URL. Team scores are not inserted into player L15 gamelogs.

Tests verify the actual BYU event fixture, reject a player selection, incomplete events, a different date/opponent, missing score, malformed thresholds and a Lakers/Clippers city collision. Existing settlement/backlog and workflow checks pass locally. The full run includes fresh league collection as well as the new team settler.

## Unresolved evidence kept separate

MLB officially identifies Sean Murphy as player 669221 (the other equal-name search ID has no postseason batting logs). His nearby official game 849822 was played October 7 at 22:00 UTC, not the October 6 22:10 UTC quoted by the pending pick. No rescheduling evidence was present in the inspected schedule payload. That later game is therefore not substituted.

[Full Results #241](https://github.com/forfexes/prop-hunter/actions/runs/40881380800) completed successfully. NHL collected 191 player-game rows for 17 resolved player names. The exact team/game path settled three source picks. Reporter merged 12 retained singles and edited 26 original cards. Final database source pending count fell from 89 to 59: four older canonical, 29 older legacy, and 26 issued October 29. Thus eight older source picks and 22 issued October 29 closed in this pass. These are source-row outcomes, not a count of newly completed sporting events.

The audit fell from 171 to 120 records including retained legs: 57 awaiting completion, 50 no unique official game, seven season/fantasy/standings, one unsupported team/game market and five ambiguous lines. No ready-to-settle, missing-stat or unmapped-market case was left by the audit. The remaining source picks are not described as fully settled.


## Verified individual outcomes during the full run

Direct database verification confirms all four targeted old source picks have closed, with matching official event IDs:

| Source ID | Selection | Actual | Result | Official event |
| --- | --- | ---: | --- | --- |
| 37 | BYU team points Under 27.5 | 17 | Win | ESPN 401856818 |
| 388 | Nathan MacKinnon points Over 0.5 | 1 | Win | NHL 2026020201 |
| 389 | Jack Hughes points Over 0.5 | 0 | Loss | NHL 2026020201 |
| 391 | Joel Farabee assists Over 0.5 | 0 | Loss | NHL 2026020200 |

The three native NHL player gamelogs now have official US gameday October 28. The source outcomes were checked in both picks and results. A result was not inferred solely from a web recap or an absent player name.


The new team/game path also settled two October 1 legacy NHL picks from exact final ESPN event 401891780: Colorado Avalanche team goals Over 1.5 (8 goals, win) and whole-game goals Over 0.5 (12 goals, win). All three team-score result rows retain the final event payload. A further scope guard requires an explicit full-game score label; first-half, quarter, regulation-only and handicap labels are rejected, including partial-market suffixes after the numeric threshold. That guard and its behavioral regression are commit 98233642acbb2bfcf865b02ea8d7fd9b3d162bc2.


[Scope replay #242](https://github.com/forfexes/prop-hunter/actions/runs/40882592171) completed successfully, including the full-game-only regression. It found zero eligible pending team-score records to re-settle and zero new card edits or single merges. Audit remains 120 with the same reasons. Final direct database verification: 59 pending source picks, zero duplicate result pick IDs. The 33 older source rows remain a real unresolved backlog; no unsupported line, unknown player participation, season future or differently dated game was forced into a win/loss/void.
