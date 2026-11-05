# NBA USG% source policy (PROP HUNTER)

## Source order
1. NBA.com/stats advanced player season stats: authoritative season USG%; currently times out from GitHub Actions (verified 2026-11-05).
2. NBA.com/stats advanced box scores: authoritative **game-specific** USG%; do not confuse with season totals.
3. Basketball-Reference: independent historical season USG% and plausibility cross-check. Verify access and usage terms before automated collection.
4. NBAstuffer: optional supplemental season comparison; verify accessibility and licensing.
5. Databallr: optional contextual analysis; verify availability and licensing.

AthletePath is a formula reference, **not** a source of measured player observations.

## Quality gates
- Never label season USG% as L5/L10/L15.
- Calculate player L5/L10/L15 usage only from **observed game-level** usage rows, with explicit date, game ID, NBA player ID, sample count and source.
- Missing, timed-out, blocked, malformed or unmatched data must remain missing; never fill with averages or invented values.
- Official NBA player IDs are canonical; no automatic fuzzy player-name joins for production.
- Source failure must not block settlement or unrelated league data collection.
- No live model use until real source retrieval, storage mapping, freshness, feature parity and offline validation are verified.
- An Actions job success after a graceful unavailable fallback does **not** imply the source returned data.

## Current state
The optional `prop_hunter_nba_usage.py` adapter fetches official season snapshots but has not been wired to production storage or prediction features. GitHub-hosted live requests to stats.nba.com have timed out. The on-demand smoke workflow reports UNAVAILABLE rather than claiming data were ingested.
