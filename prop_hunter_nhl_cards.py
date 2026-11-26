"""Render approved NHL F cards using the exact fixture teams and official assets."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from functools import lru_cache
import math
import re

from prop_hunter_asset_identity import normalized_team
from prop_hunter_nhl_offline_assets import (
    GROUPS, localized, name_key, resolve_legs, resolve_single, team_code,
)
from prop_hunter_nhl_offline_layout import render

API = "https://api-web.nhle.com/v1"


@lru_cache(maxsize=32)
def _official_crest(code, league):
    import cairosvg
    import requests

    url = f"https://assets.nhle.com/logos/nhl/svg/{code}_light.svg"
    response = requests.get(url, timeout=8, allow_redirects=False)
    if response.status_code != 200 or len(response.content) > 256_000:
        raise ValueError("Official NHL crest unavailable")
    return cairosvg.svg2png(bytestring=response.content, output_width=192, output_height=192)


@lru_cache(maxsize=4)
def _teams(day, get_json):
    data = get_json(f"{API}/standings/now")
    if not data or not data.get("standings"):
        raise ValueError("Official NHL team list unavailable")
    return {team_code(localized(row["teamAbbrev"])): localized(row["teamName"])
            for row in data["standings"]}


@lru_cache(maxsize=96)
def _roster(code, day, get_json):
    data = get_json(f"{API}/roster/{code}/current")
    if not data or not any(data.get(group) for group in GROUPS):
        raise ValueError("Official NHL roster unavailable")
    return data


@lru_cache(maxsize=16)
def _schedule(day, get_json):
    data = get_json(f"{API}/schedule/{day}")
    if not data or not data.get("gameWeek"):
        raise ValueError("Official NHL schedule unavailable")
    return [game for item in data["gameWeek"] for game in item.get("games", [])]


def _official_game(away, home, value, get_json):
    when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if when.tzinfo is None:
        raise ValueError("NHL kickoff needs a timezone")
    # Games starting after midnight UTC are often on the preceding NHL slate.
    day = when.astimezone(timezone.utc).date() - timedelta(days=1)
    matching = [
        game for game in _schedule(day, get_json)
        if (game.get("awayTeam") or {}).get("abbrev") == away
        and (game.get("homeTeam") or {}).get("abbrev") == home
        and game.get("startTimeUTC")
        and datetime.fromisoformat(game["startTimeUTC"].replace("Z", "+00:00")) == when
    ]
    if len(matching) != 1:
        raise ValueError("NHL kickoff differs from the official schedule")
    return when, localized(matching[0].get("venue"))


def render_nhl_pick(pick, details, cards, *, formula_quote=None):
    import cairosvg

    features = pick.features or {}
    scope = getattr(pick, "combo_scope", None) or features.get("combo_scope")
    kind = str(pick.type).lower()
    if kind in {"single", "longshot"}:
        kind = "single"
    elif kind in {"big", "super", "lottery"}:
        kind = "lottery"
    elif kind == "cross" or scope == "cross_game":
        kind = "cross"
    elif kind in {"betbuilder", "builder"}:
        kind = "builder"
    elif kind in {"kombi2", "kombi3", "combo", "kombi"}:
        kind = "kombi"
    elif kind != "ladder":
        raise ValueError("Unsupported NHL card type")
    day = datetime.now(timezone.utc).date()
    teams = _teams(day, cards._get_json)
    aliases = {name_key(name): code for code, name in teams.items()}

    def code_for(name):
        canonical, _ = normalized_team(name, "nhl")
        key = str(canonical or "").upper()
        code = key if key in teams else aliases.get(name_key(canonical))
        if code is None:
            raise ValueError("Unknown NHL fixture team")
        return code

    if kind == "single":
        data = pick.model_dump() if callable(getattr(pick, "model_dump", None)) else vars(pick)
        details = [data]
    if not details:
        raise ValueError("Missing NHL card rows")
    if len(details) > (6 if kind == "ladder" else 12):
        raise ValueError("Unsupported NHL card row count")
    rosters, legs, rows = {}, [], []
    for detail in details:
        game = detail.get("game") or (pick.game if kind in {"single", "builder", "ladder"} else "")
        parts = re.split(r"\s+@\s+", str(game or "").strip(), maxsplit=1)
        if len(parts) != 2:
            raise ValueError("NHL fixture needs explicit away and home teams")
        away, home = map(code_for, parts)
        if away == home:
            raise ValueError("Duplicate NHL fixture team")
        same_fixture = kind in {"single", "ladder", "builder"}
        kickoff = detail.get("commence_time")
        if not kickoff and same_fixture:
            kickoff = getattr(pick, "commence_time", None) or features.get("commence_time")
        when, venue = _official_game(away, home, kickoff, cards._get_json)
        local = when.astimezone(ZoneInfo("Europe/Zurich"))
        event = " · ".join(filter(None, (local.strftime("%d.%m.%Y %H:%M CH"), venue)))
        player = detail.get("player") or (pick.player if kind == "ladder" else "")
        if not player:
            raise ValueError("Missing NHL athlete identity")
        for code in (away, home):
            if code not in rosters:
                rosters[code] = _roster(code, day, cards._get_json)
        matches = [
            code for code in (away, home)
            if any(name_key(f"{localized(row.get('firstName'))} {localized(row.get('lastName'))}") == name_key(player)
                   for group in GROUPS for row in rosters[code].get(group) or [])
        ]
        if len(matches) != 1:
            raise ValueError("Player is not unique across the two NHL rosters")
        detail_features = detail.get("features") or {}
        claim = detail.get("team") or detail_features.get("player_team")
        if not claim and kind == "ladder":
            claim = getattr(pick, "team", None)
        if claim and code_for(claim) != matches[0]:
            raise ValueError("Player team contradicts official NHL roster")
        legs.append(dict(player=player, home=home, away=away, player_team=matches[0]))
        result = cards._result_text(detail)
        form = " · ".join(filter(None, (cards._form_text(detail_features), result)))
        rows.append(dict(player=player, match=f"{teams[away]} @ {teams[home]}",
                         market=cards._label(detail), event=event, form=form, odds=detail.get("odds"),
                         odds_observed=(kind == "ladder" or detail.get("odds_observed") is True
                                        or detail_features.get("odds_observed") is True)))
    loaders = dict(rosters=rosters, load_photo=cards._get_image, load_logo=_official_crest)
    assets = resolve_single(**legs[0], **loaders) if kind == "single" else resolve_legs(kind, legs, **loaders)
    price = ""
    if kind != "ladder":
        quote = float(formula_quote if formula_quote is not None else pick.odds)
        if not math.isfinite(quote) or quote <= 1:
            raise ValueError("Invalid NHL quote")
        price = f"{quote:.2f}"
    result = getattr(pick, "settlement_summary", None) or cards._result_text(vars(pick)) or "OFFEN"
    form = features.get("recent_form") or {}
    def hits(window):
        row = form.get(window) or {}
        return f"{row['hits']}/{row['n']}" if row.get("n") and row.get("hits") is not None else ""
    return cairosvg.svg2png(bytestring=render(
        kind, rows, player=pick.player, price=price, assets=assets,
        l10=hits("l10"), l15=hits("l15"), result=result,
        production=True, calculated=formula_quote is not None,
    ).encode())
