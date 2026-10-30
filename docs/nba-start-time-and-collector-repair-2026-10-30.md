# NBA settlement repair — 30 October 2026

## Verified faults and fixes

- `nba_api_player_logs` referenced `observed` without defining it. It now builds the observed stat map before deriving PRA, RA, double-double and triple-double, retaining missing values rather than manufacturing zeros. Zero-minute rows are skipped.
- Native NBA API dates such as `OCT 28, 2026` were truncated rather than parsed. Valid source formats now become ISO dates; invalid dates are skipped.
- Two Stephon Castle logs shared the local official date 2026-10-28. Only event 401909890 carried the quoted UTC start, 2026-10-29 01:00. The date fallback now prefers a unique observed official start within 15 minutes and rejects known conflicting starts. Ambiguous duplicates and later official dates remain unresolved.
- Verified overnight NJD/COL period-price withdrawals now cover both October 28 and October 29 sent-date records. This prevents the reporter from reopening the previous-day Hughes record.

## Production verification

Results #246 completed successfully: the Castle single was settled as a loss, actual assists 8, official event 401909890. The dependent SAFE ticket became a loss and the six-leg SGP became a win. Three original Telegram cards were edited. These are recorded tip outcomes, not evidence that a derived SGP quote was obtainable from a bookmaker.

Sources inspected directly:

- https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20261028
- https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401909890

## Older unresolved picks

Direct ESPN checks found explicit `didNotPlay=true` for Kawhi Leonard in event 401909864 and Andrew Nembhard in event 401909872. Keegan Murray was absent from the inspected boxscore for event 401909867; absence alone does not prove DNP or establish a betting outcome. None was assigned a fabricated zero-stat win/loss. Bookmaker-specific settlement evidence is still required for automatic refunds.

No fresh sports-data collection was performed in these replay runs. Current overnight games must finish and their official logs must be fetched before settlement.

## Tests

Production NBA collector executed with a stubbed native API frame: observed totals, DD/TD, native date format, zero-minute and malformed-date guards. Existing fast settlement, historical backlog, observed basketball boxscore, and quote incident regressions passed locally and in Results CI.

Results #247 completed successfully. Final pending source rows: 107 (78 canonical, 29 legacy), down from 110 before this repair. This count excludes virtual legs and must not be compared directly with the broader pending audit total.
