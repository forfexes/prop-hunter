# PROP HUNTER

Current production runtime: **13.10.0-MULTISOURCE-CONSENSUS**.

PROP HUNTER collects observed player-prop prices, enriches them with sports data, creates +EV singles/ladders/builders, settles picks from official/result feeds and updates the original Telegram card in place. Browser work stays out of normal card runs.

## Production schedule
- Card: 16:30 UTC and 21:00 UTC, 8-minute timeout.
- Results: 10:15 UTC.
- Self-maintenance: Sunday 03:15 UTC.

## Live prop sources
The collector is coverage-aware. It can use The Odds API/in-engine event props plus SportsGameOdds, ParlayAPI, PropLine, Odds-API.io, OddsPapi, four Kambi brands and a bounded 1xBet-family LineFeed fallback. Underdog/Sleeper remain modelling/context sources where appropriate.

It does **not** create synthetic sportsbook prices. Observed alternate lines remain separate ladder rungs. Kambi brands are retained as separate books. 1xBet is best-effort public JSON only: no login, proxy, browser, CAPTCHA or geo bypass.

## No-vig consensus
13.10 pairs real Over/Under prices at the same player/market/line, calculates per-book no-vig probability and falls back to cross-book median implied probabilities when necessary. Only after consensus is calculated does the card layer collapse identical sides to the best observed bookmaker price. This gives the pick engine a real market-based `fair_prob` instead of treating every observed price as its own probability estimate.

## Optional free-key sources
- `SPORTSGAMEODDS_KEY` / `SPORTSGAMEODDS_API_KEY`
- `PARLAY_API_KEY`
- `PROPLINE_API_KEY`
- `ODDSAPI_IO_KEY`
- `ODDSPAPI_KEY` / `ODDSPAPI`
- `ODDS_API_KEY`

Required infrastructure secrets remain `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SUPABASE_URL`, and `SUPABASE_KEY`.

## Settlement / learning
`prop_hunter_settler.py` writes settled rows and `prophunter_results.py` edits the original Telegram card when its message id is stored. Settled picks feed source/market learning, model registry, CLV, coverage watchdog and retraining.

See `CURRENT_MANIFEST.txt` for the authoritative production file list. Persisted model/history/state files must not be deleted.
