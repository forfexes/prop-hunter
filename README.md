# PROP HUNTER

Current production runtime: **13.9.2-HARDENED-SOURCES-SETTLEMENT**.

PROP HUNTER collects observed player-prop prices, enriches them with sports data,
creates +EV singles/ladders/builders, settles picks from official/result feeds and
updates the original Telegram card in place. The production path is intentionally
small: expensive discovery/backfill/browser work is kept out of normal card runs.

## Production schedule

- Card: 16:30 UTC and 21:00 UTC, 8-minute hard timeout.
- Results: 10:15 UTC, separate from card generation.
- Self-maintenance: Sunday 03:15 UTC.
- GitHub source watcher: twice monthly; metadata-only, no third-party repo execution.

## Live prop source order

The active collector prefers real sportsbook/API prices and stops unnecessary
fallbacks when earlier sources already provide sufficient coverage:

1. The Odds API (event-level player props)
2. SportsGameOdds
3. Odds-API.io
4. Kambi public offering fallback
5. OddsPapi / existing bounded fallbacks
6. Underdog/Sleeper lines for modelling where appropriate

BALLDONTLIE player-prop betting endpoints are disabled by default because access can
be plan-gated. BALLDONTLIE can still be used for supported stats/results.

No synthetic sportsbook price is created. Alternate ladder rungs are accepted only
when an observed source returned that line and price.

## Settlement

`prop_hunter_settler.py` writes `prop_hunter_results`. `prophunter_results.py` then
merges those results into `picks_history.json` and edits the original Telegram
message when its message id was stored. Settlement uses exact game ids when
available, otherwise a narrow date-safe match; ambiguous games stay pending.

## Learning and maintenance

Settled picks feed source/market performance, source trust, the model registry,
coverage watchdog and market discovery. Retraining is guarded by minimum sample
requirements and runs outside normal card generation.

The GitHub watcher only inspects repository metadata. It never clones or executes
new third-party repositories automatically.

## Dependencies

Normal production uses `requirements.txt`. Results use `requirements_results.txt`.
Browser scraping is not installed or launched by normal workflows.

For an intentional manual browser-fallback session use:

```bash
pip install -r requirements_browser.txt
playwright install chromium
```

`requirements_browser.txt` adds Playwright and cloudscraper on top of the production
requirements. Browser fallbacks do not bypass logins, CAPTCHAs or geo restrictions.

## Secrets

Required for the bot infrastructure:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `SUPABASE_URL`
- `SUPABASE_KEY`

At least one keyed sportsbook source is strongly recommended:

- `ODDS_API_KEY`
- `SPORTSGAMEODDS_KEY` or `SPORTSGAMEODDS_API_KEY`
- `ODDSAPI_IO_KEY`
- `ODDSPAPI_KEY` or `ODDSPAPI`

Kambi is a keyless best-effort fallback and can vary by brand/region, so it should
not be the only production price source.

## Repository layout

`CURRENT_MANIFEST.txt` is the authoritative list of current production, persisted
state and manual support files. Persisted files such as `picks_history.json`,
`odds_cache.json`, model/state JSON files and `ml_model.pkl` must not be deleted
simply because they are not imported as Python modules.

Legacy duplicate loaders, normalizers, scanners and old orchestrators were removed
from `main` after dependency/workflow review. They remain recoverable from Git
history if an old migration or comparison is ever needed.
