# PROP HUNTER — NFL / NHL / MLB / WNBA premium card acceptance gates

Status: specification only; **not** approved artwork, not production enabled.
The existing NBA premium masters are not permitted as mislabeled substitutes.

## Required families
For each league: Single, Ladder, Builder, Lottery. 1080 × 1440 PNG.
Use the same premium hierarchy and four family structures as the approved
NBA reference, but league-specific colors, sport imagery and market labels.
No historical fallback graphics, no fake odds or statistics.

## Authentic logos (hard requirement)
- Show the **correct original league logo** (NFL, NHL, MLB, or WNBA) on every card.
- Show the **correct original team logos** for the verified fixture.
- Retrieve assets from an identified, reliable league/team source; validate
  league, team identity, file integrity and transparency before rendering.
- Keep league logos and team logos in distinct slots. Never substitute one for
  another, recolor a logo, use text/emoji as a logo, or borrow NBA branding.
- Missing, ambiguous, mismatched, or corrupt league/team logo => reject the
  image card (fail closed); never silently fall back to the old compositor.
- Respect logo usage rights and source terms. Source/rights verification is
  required before production distribution.

## Data and imagery
- Authentic player photo, with a clean transparent cutout where required.
- Correct league-specific market labels and real observed bookmaker odds.
- L5/L10/L15 only from actual player game logs; absent values stay absent.
- Ladder: one athlete, several thresholds; Builder/Lottery: each leg's actual
  athlete, game and odds; cross-game leg times verified independently.
- No sample data, fake logos, fake player portraits, or unverified event times
  in published Telegram tips.

## Release checklist
1. Commit actual editable source masters and required approved logo assets or
   verified runtime logo retrieval/validation code for all four leagues.
2. Generate isolated offline QA PNGs for all 16 league/family combinations.
3. Automated assertions: size, sport isolation, mandatory logos/photos,
   missing-logo rejection, no legacy renderer, authentic data provenance.
4. Visually inspect all previews for cropping, readability, logos and photos.
5. Test production route with mocked delivery; only after approval enable
   Telegram publishing. No synthetic QA card may be sent as a real tip.

## Current implementation boundary
As of the inspection on 2026-11-20, `prop_hunter_image_cards.py` is explicitly
NBA-premium-only. Its legacy image renderer is inert for production routing;
other leagues await their own approved premium masters. This specification
does not claim that those assets or tests already exist.
