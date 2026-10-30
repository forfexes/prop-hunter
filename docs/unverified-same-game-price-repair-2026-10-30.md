# Unverified same-game prices — 30 October 2026

## Trigger and verified fault

The published Edey/Morant/Holiday lottery quoted 537.60 for one Memphis–Portland game. The stored FanDuel selections were 14+ rebounds at 12.00, 10+ assists at 7.00 and 20+ points at 6.40. The combined price was exactly their product. No observed combined sportsbook quote was stored.

The legacy `_make_builder` marked such multiplied same-game products as `odds_observed=True` and `price_type=bookmaker`. The newer profile engine marked derived prices, but the delivery and performance paths still allowed them through.

## Repair

- A shared price-scope check rejects unpublished/unconfirmed SGPs, including repeated-game components in mixed-game tickets.
- Both the extras assembly and the final delivery boundary apply the check. The final boundary covers analysis/rescue output too.
- Confirmed combined quotes require explicit combined-price evidence and a quote reference. The old generic observed-leg flag is insufficient.
- Singles, independent ladder rungs and distinct-game combinations retain their existing handling.
- Historical demonstrably derived same-game tickets are retracted rather than graded as actual bookmaker wins, losses or refunds. Original recorded outcome and profit are retained in audit fields.
- Telegram retractions name the combined-price problem and remove the EV/probability claims.
- Performance accounting excludes these tickets. Profile ROI learning does not use their hypothetical combined profit.

## L10/L15 findings for the trigger

The retained sample before the quoted game showed Edey 14+ rebounds in 2/10 and 4/13, Morant 10+ assists in 3/10 and 5/15, Holiday 20+ points in 3/10 and 5/15. Their six stored October games showed 0/6, 0/6 and 1/6 respectively. Longer windows include older-season games, and Edey has only 13 retained games. These are descriptive stored-game counts, not calibrated joint probabilities or proof of the displayed +461.4% EV.

This change addresses the unverified combined price. It does not claim to resolve all sample recency, completeness or role-change issues in probability estimation.

## Verification

Regression tests cover the exact 537.60 failure, explicit confirmed quotes, independent cross-game tickets, mixed-ticket SGP components, ladders, singles, invalid historical profit accounting and the actual production assembly/final-delivery AST blocks. Existing 14 expansion suites and settlement backlog regressions passed. Diagnostic #8 completed successfully; its network-heavy full-card dry run was explicitly skipped in offline-only mode.

## Production outcome

Results #250 completed successfully. It retracted 193 retained unverified SGP tickets and edited 164 original Telegram cards (142 now contain the SGP-specific warning; 22 earlier period-market warnings were also refreshed). Some older cards contain more than one combo. Telegram rate limits were retried successfully; no exhausted retries or permanent edit failures were reported.

The exact Edey/Morant/Holiday lottery is source pick 575, now `withdrawn`, and original Telegram message 1200 now explicitly retracts the unconfirmed 537.60 combined quote. Its +461.4% EV claim is absent from the corrected text.

Final delivery-fence regression passed in Diagnostic #8. The remaining pending source backlog is 85 rows; the broader audit includes virtual legs and reports 133 unresolved items. This remediation is not completion of that backlog.
