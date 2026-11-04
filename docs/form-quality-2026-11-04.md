# Player form selection — 4 November 2026

Current-season enrichment now records actual L5/L10/L15 counts, hits and averages at the exact offered line and side, plus the preceding 5–10 observations. The raw gamelog model estimate is connected to builder candidates only after sample, line and side validation. Existing Wilson lower-bound ladder sizing remains in place.

Singles must carry at least six observed games and matching line evidence before extras are assembled. Final delivery checks the evidence for every leg of ladders and combinations; unsupported legacy combinations without leg evidence are rejected. Form snapshots are retained on historical singles and combo legs for later audits; this does not backfill historical ML features.

A conservative deterioration policy rejects 0–1 hits in the last five observations when at least five preceding observations had >=60% hits. It does not raise probabilities for a hot streak and is not a validated profitability claim. Under pushes are excluded from hits. Binary DD/TD form is checked at the 0.5 indicator threshold. Exact observed sample sizes are retained; fewer than 15 games are not labelled as 15 observations.

The existing quote-confirmation gates still control publication. No inferred SGP price was reinstated. Automatic stale-data voids are disabled in Results; prior automatic voids need a separate evidence review and were not rewritten by this change.

Tests cover chronological reversal with identical total hit counts, Under deterioration, integer pushes, small samples, mismatched lines/sides, builder wiring and final filtering across singles, ladders and combinations. Existing 13 ladder regressions, form enrichment, quote delivery and quality guards pass locally. Results workflow runs the new regression before collection/settlement.

Limits: this change does not add injury, rotation or opponent feeds, nor certify that every historical game was regular-season rather than preseason. Those require separate verified data. It does not establish improved ROI; that needs prospective evaluation.
