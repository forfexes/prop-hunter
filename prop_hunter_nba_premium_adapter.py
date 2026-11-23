#!/usr/bin/env python3
"""Bridge verified NBA picks into the user's 52 premium SVG masters.

No invented stats, timestamps, images, or combined prices. A rejected render
returns control to the caller; this module never sends Telegram messages.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
import os
import re
import sys
import math
import unicodedata
from PIL import Image

MASTER_DIR = Path(__file__).resolve().parent / "card_templates" / "nba_premium_v2"


class PremiumDataMissing(ValueError):
    """Pick lacks the real assets or provenance required by the master."""


def _get(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

def _verified_player_key(value):
    """Normalise accents and punctuation, not identities; no fuzzy matching."""
    value = unicodedata.normalize("NFKD", str(value or "").casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", value))




def _photo(img, slot):
    if img is None:
        raise PremiumDataMissing(f"Missing authentic {slot}")
    if not isinstance(img, Image.Image):
        raise PremiumDataMissing(f"Unexpected {slot} type")
    out = img.convert("RGBA")
    if slot == "player_photo" or slot.endswith("_photo"):
        alpha = out.getchannel("A")
        # A single artificially translucent pixel is not a genuine cutout.
        # Require a visible transparent border (>= 2% fully transparent area)
        # before composing a player over the owner's original stadium.
        clear_pixels = sum(alpha.histogram()[:32])
        if clear_pixels < max(1, int(out.width * out.height * .02)):
            raise PremiumDataMissing(f"{slot} must have a real transparent cutout border")
    buf = BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _tipoff(pick):
    feats = _get(pick, "features") or {}
    if not isinstance(feats, dict):
        feats = {}
    raw = _get(pick, "commence_time") or feats.get("commence_time") or feats.get("start_time_utc")
    if not raw:
        raise PremiumDataMissing("Verified game tipoff missing")
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise PremiumDataMissing("Invalid game tipoff") from exc
    if dt.tzinfo is None:
        raise PremiumDataMissing("Timezone missing from tipoff")
    dt = dt.astimezone(ZoneInfo("Europe/Zurich"))
    return dt.strftime("%d.%m.%Y"), dt.strftime("%H:%M")


def _price(value):
    try:
        n = float(str(value).replace("@", "").strip())
    except (TypeError, ValueError):
        raise PremiumDataMissing("Verified bookmaker price missing")
    if not math.isfinite(n) or not 1.0 < n < 100000:
        raise PremiumDataMissing("Invalid bookmaker price")
    return f"@{n:.2f}"


def _form(form):
    values = {}
    for key in ("l5", "l10", "l15"):
        match = re.search(r"\b" + key + r"\s+(\d+)/(\d+)\b", str(form or ""), re.I)
        if match:
            hits, total = int(match[1]), int(match[2])
            if 0 <= hits <= total and 0 < total <= int(key[1:]):
                values[key] = f"{hits}/{total}"
    return values


def _template(pick, rows):
    typ = str(_get(pick, "type") or "").lower()
    feats = _get(pick, "features") or {}
    feats = feats if isinstance(feats, dict) else {}
    n = len(rows)
    if typ == "longshot":
        if n != 1:
            raise PremiumDataMissing("Longshot requires exactly one verified selection")
        # Longshot is a single-leg payout variant, not a bypass of approved
        # markets or observed direction/threshold integrity checks.
        _template({"type": "single", "market": _get(pick, "market"),
                   "direction": _get(pick, "direction"),
                   "point": _get(pick, "point")}, rows)
        return "longshot"
    if typ == "single" and n == 1:
        # Real source picks often store the numeric line and direction as
        # part of market, e.g. "Rebounds Over 3.5", "Assists Under 4.5".
        # These still have their own approved REBOUNDS / ASSISTS master.
        # Strip ONLY the independently verified trailing line, not unknown
        # market terms; never silently substitute a generic card family.
        market = re.sub(r"\s+", " ", re.sub(r"[_-]+", " ",
                      str(_get(pick, "market") or "").lower())).strip()
        observed = re.fullmatch(
            r"(.+?)\s+(over|under)\s+([-+]?\d+(?:[.,]\d+)?)", market)
        if observed:
            direction = str(_get(pick, "direction") or "").strip().lower()
            if direction and direction != observed.group(2):
                raise PremiumDataMissing("Conflicting observed NBA pick direction")
            point = _get(pick, "point")
            if point is not None:
                try:
                    observed_point = float(observed.group(3).replace(",", "."))
                    stored_point = float(point)
                except (TypeError, ValueError) as exc:
                    raise PremiumDataMissing("Invalid observed NBA threshold") from exc
                if abs(stored_point - observed_point) > 0.000001:
                    raise PremiumDataMissing("Conflicting observed NBA pick threshold")
            market = observed.group(1)
        market = re.sub(r"^player\s+", "", market)
        market = re.sub(r"\s+alternate$", "", market)
        aliases = {
            "3pt":"threes", "3pm":"threes", "3pt made":"threes",
            "three pointers":"threes", "three pointers made":"threes",
            "pts":"points", "reb":"rebounds", "ast":"assists",
            "points rebounds assists":"pra", "p r a":"pra",
            "points rebounds":"points_rebounds", "points assists":"points_assists",
            "rebounds assists":"rebounds_assists",
            "double double":"double_double", "triple double":"triple_double",
            "first basket":"first_basket", "team total":"team_total",
            "match total":"match_total", "moneyline":"moneyline",
            "spread":"spread", "turnovers":"turnovers",
        }
        market = aliases.get(market, market.replace(" ", "_"))
        from json import loads
        manifest = loads((MASTER_DIR / "manifest.json").read_text())
        key = "single_" + market
        if key not in manifest["templates"]:
            # Never silently render an unknown market on a generic card.
            # Every production selection needs its explicit approved master.
            raise PremiumDataMissing("No approved NBA master for market: " + market[:55])
        return key
    if n < 2 or n > 12:
        raise PremiumDataMissing("Only 2–12 legs are supported")
    # 7+ is supported for Builder only through 7, and for multi-game
    # Combo/Lottery through 12. Ladder/same-player remain separately approved.
    if n > 6 and typ in ("ladder",):
        raise PremiumDataMissing("Ladder currently supports 2–6 original rungs")
    if typ == "ladder":
        return f"ladder_{n}"
    if typ in ("lottery", "big", "super"):
        return f"lottery_{n}"
    if typ in ("kombi2", "kombi3", "combo"):
        return f"combo_{n}"
    if typ == "betbuilder":
        if feats.get("combo_scope") == "cross_game":
            return f"cross_game_{n}"
        if feats.get("same_player_multistat") is True:
            if n > 6:
                raise PremiumDataMissing("Same-player master only supports 2–6 rungs")
            return f"same_player_{n}"
        if n > 7:
            raise PremiumDataMissing("Same-game Builder master only supports 2–7 legs")
        return f"builder_{n}"
    raise PremiumDataMissing(f"Unsupported NBA pick type: {typ}")



def _family_from_key(key):
    """Keep multiword single-market keys in the owner's Single family.

    E.g. single_points_rebounds and single_double_double must not become
    invented single_points or single_double layouts.
    """
    if key == "longshot":
        return "longshot"
    if key.startswith("single_"):
        return "single"
    for name in ("cross_game", "same_player", "lottery", "ladder",
                 "combo", "builder"):
        if re.fullmatch(re.escape(name) + r"_\d+", key):
            return name
    raise PremiumDataMissing("Unsupported NBA premium card master: " + key)


def render_nba_pick(pick, rows, teams):
    """Return a 1080×1440 PNG for a fully verified NBA pick, otherwise fail closed."""
    from importlib import import_module
    if str(MASTER_DIR) not in sys.path:
        sys.path.insert(0, str(MASTER_DIR))
    renderer = import_module("render_cards")
    feats = _get(pick, "features") or {}
    feats = feats if isinstance(feats, dict) else {}
    # Upstream legs may be dictionaries or typed model objects; preserve
    # observed bookmaker and fixture provenance for both representations.
    details = list(_get(pick, "leg_details") or [])
    books = {str(_get(leg, "bookmaker") or "").strip() for leg in details}
    bookmaker = feats.get("bookmaker") or _get(pick, "bookmaker")
    if not str(bookmaker or "").strip() and len(books)==1 and next(iter(books)):
        bookmaker=next(iter(books))
    if not str(bookmaker or "").strip():
        raise PremiumDataMissing("No observed individual-leg bookmaker provenance")
    key = _template(pick, rows)
    family = _family_from_key(key)
    multi_game = family in ("lottery", "combo", "cross_game")
    values = {
        "odds_verified": True,
        "settlement": str(_get(pick, "settlement_summary") or "OFFEN"),
    }
    if not multi_game:
        if len(teams) != 2 or not all(name and logo is not None for name, logo in teams):
            raise PremiumDataMissing("Verified home/away team logos missing")
        date, time = _tipoff(pick)
        values.update({"home_name": str(teams[0][0]), "away_name": str(teams[1][0]),
                       "date": date, "time": time, "venue": str(feats.get("venue") or "")})
    stake = _get(pick, "stake")
    if stake is not None:
        try:
            stake_value = float(stake)
        except (TypeError, ValueError, OverflowError):
            raise PremiumDataMissing("Invalid stake") from None
        if not math.isfinite(stake_value) or stake_value <= 0:
            raise PremiumDataMissing("Invalid stake")
        values["stake"] = f"{stake_value:g}u"
    images = {} if multi_game else {
        "home_logo": _photo(teams[0][1], "home_logo"),
        "away_logo": _photo(teams[1][1], "away_logo"),
    }
    typ = str(_get(pick, "type") or "").lower()
    if typ in ("single", "longshot", "ladder") or family == "same_player":
        names = {str(row.get("name") or "").strip().casefold() for row in rows}
        if len(names) != 1 or not next(iter(names)):
            raise PremiumDataMissing("Ladder/same-player must contain exactly one athlete")
        values["player_name"] = str(rows[0]["name"])
        images["player_photo"] = _photo(rows[0].get("photo"), "player_photo")
    if typ in ("single", "longshot"):
        # No unrelated athlete may be drawn over this pick's observed odds.
        identity = _get(pick, "player")
        if identity and _verified_player_key(identity) != _verified_player_key(rows[0].get("name")):
            raise PremiumDataMissing("NBA single displayed athlete differs from ticket")
        values["market"] = str(rows[0].get("label") or "")
        values["odds"] = _price(_get(pick, "odds"))
        values.update(_form(rows[0].get("form")))
        model = rows[0].get("model") or {}
        for source, target, suffix in (("prob", "prob", "%"), ("edge", "edge", "%"), ("confidence", "conf", "")):
            val = str(model.get(source) or "").strip()
            if val:
                values[target] = val if val.endswith(suffix) else val + suffix
    else:
        details = list(_get(pick, "leg_details") or [])
        if len(details) != len(rows):
            raise PremiumDataMissing("Exact leg provenance required")
        for i, (row, detail) in enumerate(zip(rows, details), 1):
            # A stale photo/row from another ticket must never be paired with
            # this leg's bookmaker price.  Do not accept approximate matches:
            # players with the same surname can be distinct athletes.
            declared_name = _get(detail, "player") or _get(detail, "player_name")
            if not _verified_player_key(declared_name) and (typ == "ladder" or family == "same_player"):
                # One-athlete ladder legs may omit redundant player names,
                # but the parent ticket must independently identify him.
                declared_name = _get(pick, "player") or _get(pick, "player_name")
            actual_name = row.get("name")
            if not _verified_player_key(declared_name):
                # A leg's model row cannot attest its own bookmaker selection.
                # In particular a missing identity must not be completed by
                # the unrelated player photo on an approved owner artwork.
                raise PremiumDataMissing(f"NBA leg {i} has no verified bookmaker player identity")
            if (not _verified_player_key(actual_name)
                    or _verified_player_key(declared_name) != _verified_player_key(actual_name)):
                raise PremiumDataMissing(f"NBA leg {i} player identity mismatches bookmaker selection")
            # A NBA-branded premium card must NEVER contain a WNBA, college,
            # EuroLeague or other sport's individual leg, even if the parent
            # pick was accidentally labelled NBA by an upstream source.
            leg_sport = str(_get(detail, "sport") or "").lower().replace("_", " ").strip()
            if leg_sport and not re.search(r"\bnba\b", leg_sport):
                raise PremiumDataMissing(f"Leg {i} is not NBA")
            values[f"leg_{i}_name"] = str(row.get("name") or "")
            values[f"leg_{i}_market"] = str(row.get("label") or "")
            for form_key, form_value in _form(row.get("form")).items():
                # Per-athlete L5/L10/L15 are observed windows only; do not
                # invent data or copy another builder leg's statistics.
                values[f"leg_{i}_{form_key}"] = form_value
            values[f"leg_{i}_line"] = str(row.get("label") or "")
            values[f"leg_{i}_odds"] = _price(_get(detail, "odds"))
            if multi_game:
                # Every leg must carry its own verified game and local tipoff.
                # A single generic VS would be false for a cross-game parlay.
                game = str(_get(detail, "game") or _get(detail, "matchup") or "").strip()
                # In a lottery/cross-game ticket, a generic parent game does NOT
                # establish which fixture each individual leg belongs to.
                if not game or not re.search(r"\s+(?:vs\.?|@)\s+", game, re.I):
                    raise PremiumDataMissing(f"Leg {i} has no verified matchup")
                # A parent's NBA label does not establish every cross-game leg's
                # league. Never quietly relabel WNBA/college/unknown legs as NBA.
                sport = str(_get(detail, "sport") or "").lower().replace("_", " ").strip()
                if not sport or not re.search(r"\bnba\b", sport):
                    raise PremiumDataMissing(f"Leg {i} has no verified NBA league")
                # Cross-game legs must carry their own event timestamp; a parent
                # timestamp cannot safely represent multiple different games.
                kickoff = _get(detail, "commence_time")
                if not kickoff:
                    raise PremiumDataMissing(f"Leg {i} tipoff missing")
                date, local_time = _tipoff({"commence_time": kickoff})
                values[f"leg_{i}_game"] = f"{game} · {date} {local_time}"
            if family in ("builder", "cross_game", "lottery"):
                images[f"leg_{i}_photo"] = _photo(row.get("photo"), f"leg_{i}_photo")
        if typ == "ladder":
            # A ladder contains several DIFFERENT thresholds. Never present
            # the first rung's form as if it described every rung.
            # leg_i_l5/l10/l15 are already supplied independently above.
            pass
        else:
            from prop_hunter_combo_prices import confirmed_ticket
            verified_combo = confirmed_ticket(pick)
            if os.getenv("PH_NBA_OWNER_ORIGINALS", "0").strip() == "1" and not verified_combo:
                # Production and settlement must obey the SAME genuine-price
                # rule. Never repaint an existing real owner card with a
                # calculated accumulator when its bookmaker ticket is absent.
                raise PremiumDataMissing("Original NBA multi-leg requires observed bookmaker combined ticket")
            # Calculated totals are retained strictly for isolated, non-owner
            # SVG analysis/QA; they can never reach Telegram owner cards.
            values["combo_quote_verified"] = verified_combo
            values["combo_quote_calculated"] = not verified_combo
            if verified_combo:
                values["total_odds"] = _price(_get(pick, "odds"))
            else:
                from prop_hunter_combo_prices import calculated_combo_odds
                calculated = calculated_combo_odds(pick)
                if calculated is None:
                    raise PremiumDataMissing("Authentic leg prices needed for calculated quote")
                # Keep the value numeric for SVG's strict arithmetic check;
                # the original total-quote label becomes BERECHNETE QUOTE.
                values["total_odds"] = f"@{calculated:.2f}"
    if os.getenv("PH_NBA_OWNER_ORIGINALS", "0").strip() == "1" and family in (
        "single", "ladder", "builder", "lottery", "combo", "cross_game",
        "same_player", "longshot"):
        # Cross-game/Combo use the owner's Lottery artwork via owner_bridge.
        # Never silently substitute NBA SVG masters when owner mode is active.
        # No silent fallback: if a true owner-original asset is absent or its
        # verified data cannot fit, refuse the image instead of publishing a
        # similar-looking generated SVG poster.
        from prop_hunter_nba_owner_bridge import render_owner
        return render_owner(pick, key, rows, teams, values,
                            list(_get(pick, "leg_details") or []))
    return renderer.render_png(key, values, images, strict=True)
