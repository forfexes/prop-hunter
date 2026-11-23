"""Prevent fake same-game NBA Builder cards.

A Builder with athletes from multiple games MUST NEVER display one arbitrary
team pair. Cross-game parlays belong on the owner's Lottery artwork, with
each independently verified game/tipoff (and a real combined bookmaker quote).
This module has no network, Telegram or database side effects.
"""
from __future__ import annotations

from datetime import datetime
import re
import unicodedata
from zoneinfo import ZoneInfo


class WrongBuilderFixture(ValueError):
    pass


def _get(value, key, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def _team(value):
    raw = unicodedata.normalize("NFKD", str(value or "").casefold())
    no_marks = "".join(c for c in raw if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", no_marks))


def _teams_from_game(raw):
    value = re.split(r"\s+[·|]\s+", str(raw or "").strip(), maxsplit=1)[0]
    matches = re.fullmatch(r"(.+?)\s+(?:vs\.?|@)\s+(.+)", value, re.I)
    if not matches:
        raise WrongBuilderFixture("Verified individual Builder fixture missing")
    side_a, side_b = _team(matches.group(1)), _team(matches.group(2))
    if not side_a or not side_b or side_a == side_b:
        raise WrongBuilderFixture("Ambiguous NBA Builder opponents")
    return frozenset((side_a, side_b))


def assert_same_game_owner_builder(details, teams, values):
    """Validate displayed home/away clubs and EACH verified leg's event time.

    A parent pick may not attest to its children's game identity. The original
    owner Builder is only appropriate when every leg actually shares this one
    match; other tickets must use the separately designed Lottery.
    """
    if not isinstance(details, (list, tuple)) or len(details) < 2:
        raise WrongBuilderFixture("Builder needs independently verified fixtures for every leg")
    if not isinstance(teams, (list, tuple)) or len(teams) != 2:
        raise WrongBuilderFixture("Builder needs exactly two authenticated opponent names")
    pair = frozenset(_team(t[0]) for t in teams if isinstance(t, (list, tuple)) and t)
    if len(pair) != 2:
        raise WrongBuilderFixture("Builder header contains ambiguous teams")
    try:
        displayed = datetime.strptime(
            str(values["date"]) + " " + str(values["time"]), "%d.%m.%Y %H:%M")
    except (TypeError, ValueError, KeyError) as err:
        raise WrongBuilderFixture("Verified displayed Builder tipoff missing") from err
    ids = set()
    for pos, detail in enumerate(details, 1):
        game = _get(detail, "game") or _get(detail, "matchup")
        if _teams_from_game(game) != pair:
            raise WrongBuilderFixture(f"Builder leg {pos} belongs to a different game")
        instant = _get(detail, "commence_time")
        try:
            start = datetime.fromisoformat(str(instant or "").replace("Z", "+00:00"))
            if start.tzinfo is None or start.utcoffset() is None:
                raise ValueError("Timezone absent")
            local_start = start.astimezone(ZoneInfo("Europe/Zurich")).replace(
                second=0, microsecond=0, tzinfo=None)
        except (ValueError, TypeError, OverflowError) as err:
            raise WrongBuilderFixture(f"Builder leg {pos} has no independently verified tipoff") from err
        if local_start != displayed:
            raise WrongBuilderFixture(f"Builder leg {pos} has a conflicting tipoff")
        identity = _get(detail, "fixture_id") or _get(detail, "event_id")
        if identity is not None:
            ids.add(str(identity).strip())
    if len(ids) > 1:
        raise WrongBuilderFixture("Builder legs claim different event IDs")
    return True
