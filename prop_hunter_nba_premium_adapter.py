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
import re
import sys
from PIL import Image

MASTER_DIR = Path(__file__).resolve().parent / "card_templates" / "nba_premium_v2"


class PremiumDataMissing(ValueError):
    """Pick lacks the real assets or provenance required by the master."""


def _get(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


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
    if not 1.0 < n < 100000:
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
    if typ == "single" and n == 1:
        market = str(_get(pick, "market") or "").lower().replace("-", "_")
        aliases = {"3pt": "threes", "3pm": "threes", "three_pointers": "threes",
                   "pts": "points", "reb": "rebounds", "ast": "assists"}
        market = aliases.get(market, market)
        from json import loads
        manifest = loads((MASTER_DIR / "manifest.json").read_text())
        key = "single_" + market
        if key not in manifest["templates"]:
            # Never silently render an unknown market on a generic card.
            # Every production selection needs its explicit approved master.
            raise PremiumDataMissing("No approved NBA master for market: " + market[:55])
        return key
    if n < 2 or n > 6:
        raise PremiumDataMissing("Only 2–6 legs are supported")
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
            return f"same_player_{n}"
        return f"builder_{n}"
    raise PremiumDataMissing(f"Unsupported NBA pick type: {typ}")


def render_nba_pick(pick, rows, teams):
    """Return a 1080×1440 PNG for a fully verified NBA pick, otherwise fail closed."""
    from importlib import import_module
    if str(MASTER_DIR) not in sys.path:
        sys.path.insert(0, str(MASTER_DIR))
    renderer = import_module("render_cards")
    feats = _get(pick, "features") or {}
    feats = feats if isinstance(feats, dict) else {}
    bookmaker = feats.get("bookmaker") or _get(pick, "bookmaker")
    if not str(bookmaker or "").strip():
        raise PremiumDataMissing("No observed bookmaker provenance")
    key = _template(pick, rows)
    family = key.rsplit("_", 1)[0]
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
            values["stake"] = f"{float(stake):g}u"
        except (TypeError, ValueError):
            raise PremiumDataMissing("Invalid stake")
    images = {} if multi_game else {
        "home_logo": _photo(teams[0][1], "home_logo"),
        "away_logo": _photo(teams[1][1], "away_logo"),
    }
    typ = str(_get(pick, "type") or "").lower()
    if typ in ("single", "ladder") or family == "same_player":
        names = {str(row.get("name") or "").strip().casefold() for row in rows}
        if len(names) != 1 or not next(iter(names)):
            raise PremiumDataMissing("Ladder/same-player must contain exactly one athlete")
        values["player_name"] = str(rows[0]["name"])
        images["player_photo"] = _photo(rows[0].get("photo"), "player_photo")
    if typ == "single":
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
            # A NBA-branded premium card must NEVER contain a WNBA, college,
            # EuroLeague or other sport's individual leg, even if the parent
            # pick was accidentally labelled NBA by an upstream source.
            leg_sport = str(detail.get("sport") or "").lower().replace("_", " ").strip()
            if leg_sport and not re.search(r"\bnba\b", leg_sport):
                raise PremiumDataMissing(f"Leg {i} is not NBA")
            values[f"leg_{i}_name"] = str(row.get("name") or "")
            values[f"leg_{i}_market"] = str(row.get("label") or "")
            values[f"leg_{i}_line"] = str(row.get("label") or "")
            values[f"leg_{i}_odds"] = _price(detail.get("odds"))
            if multi_game:
                # Every leg must carry its own verified game and local tipoff.
                # A single generic VS would be false for a cross-game parlay.
                game = str(detail.get("game") or detail.get("matchup") or "").strip()
                # In a lottery/cross-game ticket, a generic parent game does NOT
                # establish which fixture each individual leg belongs to.
                if not game or not re.search(r"\s+(?:vs\.?|@)\s+", game, re.I):
                    raise PremiumDataMissing(f"Leg {i} has no verified matchup")
                # A parent's NBA label does not establish every cross-game leg's
                # league. Never quietly relabel WNBA/college/unknown legs as NBA.
                sport = str(detail.get("sport") or "").lower().replace("_", " ").strip()
                if not sport or not re.search(r"\bnba\b", sport):
                    raise PremiumDataMissing(f"Leg {i} has no verified NBA league")
                # Cross-game legs must carry their own event timestamp; a parent
                # timestamp cannot safely represent multiple different games.
                kickoff = detail.get("commence_time")
                if not kickoff:
                    raise PremiumDataMissing(f"Leg {i} tipoff missing")
                date, local_time = _tipoff({"commence_time": kickoff})
                values[f"leg_{i}_game"] = f"{game} · {date} {local_time}"
            if family in ("builder", "cross_game", "lottery"):
                images[f"leg_{i}_photo"] = _photo(row.get("photo"), f"leg_{i}_photo")
        if typ == "ladder":
            values.update(_form(rows[0].get("form")))
        else:
            if not (feats.get("combined_odds_observed") is True and feats.get("combined_quote_id")):
                raise PremiumDataMissing("No verified bookmaker combo ticket")
            values["total_odds"] = _price(_get(pick, "odds"))
    return renderer.render_png(key, values, images, strict=True)
