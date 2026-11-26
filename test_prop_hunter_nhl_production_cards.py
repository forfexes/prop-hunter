"""Production image routes with deterministic official-source fixtures and no sends."""
import ast
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image, ImageDraw

import prop_hunter_image_cards as cards
import prop_hunter_nhl_cards as nhl
from prop_hunter_image_publication_gate import filter_verified_nba_images


def test_nhl_and_nfl_strict_production_preflight(monkeypatch):
    when = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0).isoformat()
    match = "Seattle Kraken @ Edmonton Oilers"
    teams = {"SEA": "Seattle Kraken", "EDM": "Edmonton Oilers",
             "TOR": "Toronto Maple Leafs", "BOS": "Boston Bruins"}
    names = {"EDM": ("Connor", "McDavid"), "BOS": ("David", "Pastrnak")}
    games = [{"awayTeam": {"abbrev": a}, "homeTeam": {"abbrev": h},
              "startTimeUTC": when, "venue": {"default": "QA Arena"}}
             for a, h in (("SEA", "EDM"), ("TOR", "BOS"))]

    def get_json(url):
        if "/football/nfl/" in url:
            code = url.split("/")[-2]
            row = {"id": 3918298, "fullName": "Josh Allen"} if code == "buf" else {"id": 1, "fullName": "Other QB"}
            return {"team": {"name": "Bills" if code == "buf" else "Jets"},
                    "athletes": [{"items": [row]}]}
        if url.endswith("/standings/now"):
            return {"standings": [{"teamAbbrev": {"default": code}, "teamName": {"default": name}}
                                  for code, name in teams.items()]}
        if "/schedule/" in url:
            return {"gameWeek": [{"games": games}]}
        code = url.split("/")[-2]
        first, last = names.get(code, ("Other", "Athlete"))
        return {"forwards": [{"id": 123, "firstName": {"default": first},
                              "lastName": {"default": last},
                              "headshot": f"https://assets.nhle.com/mugs/nhl/20262027/{code}/123.png"}]}

    art = Image.new("RGBA", (128, 128))
    ImageDraw.Draw(art).rectangle((16, 16, 112, 112), fill=(159, 58, 49, 255))
    monkeypatch.setattr(cards, "_get_json", get_json)
    monkeypatch.setattr(cards, "_get_image", lambda _: art)
    monkeypatch.setattr(nhl, "_official_crest", lambda *_: art)
    monkeypatch.setattr(cards, "ON", True)
    monkeypatch.setenv("PH_OWNER_APPROVED_ALL_SPORTS", "1")
    monkeypatch.setenv("PH_OWNER_PIXEL_QA", "1")
    monkeypatch.setenv("PH_ALLOW_VERIFIED_LAYERED_OWNER", "1")
    monkeypatch.setenv("PH_BLOCK_OVERPAINTED_MASTERS", "1")
    monkeypatch.setenv("PH_NHL_PREMIUM_CARDS", "1")
    monkeypatch.setenv("PH_NFL_PREMIUM_CARDS", "1")

    source = ast.parse(Path("prophunter_core_1391.py").read_text())
    methods = [node for node in source.body if isinstance(node, ast.FunctionDef)
               and node.name == "_payload_card_image"]
    import os
    ns = {"os": os, "log": Mock()}
    exec(compile(ast.Module(body=methods, type_ignores=[]), "<card-payload>", "exec"), ns)

    first = dict(player="Connor McDavid", sport="NHL", game=match, commence_time=when,
                 market="Torschüsse", point=2.5, direction="over", odds=1.85, odds_observed=True)
    second = dict(first, player="David Pastrnak", game="Toronto Maple Leafs @ Boston Bruins")
    for kind in ("single", "ladder", "betbuilder", "kombi2", "cross", "lottery"):
        features = {"odds_observed": True, "bookmaker": "QA BOOK"}
        rows = [first, dict(first, point=3.5)]
        if kind == "single":
            rows = []
        if kind == "betbuilder":
            features.update(combined_odds_observed=True, combined_quote_id="QA TICKET")
        if kind in ("kombi2", "cross", "lottery"):
            rows = [first, second]
            if kind == "cross":
                features["combo_scope"] = "cross_game"
        pick = SimpleNamespace(**first, type="kombi2" if kind == "cross" else kind, source_sport="NHL",
                               features=features, leg_details=rows)
        if kind != "single":
            del pick.commence_time
        assert filter_verified_nba_images([pick], cards) == ([pick], 0)
        payload = {"kind": "single" if kind == "single" else "combo",
                   "single_indices": [0], "combo_indices": [0]}
        png = ns["_payload_card_image"](payload, [pick])
        assert png == pick._verified_owner_png
        assert payload["media_type"] == "photo"
        with Image.open(BytesIO(png)) as image:
            assert image.size == (900, 1350)
            image.verify()

    pick.leg_details = [first, dict(second, commence_time="2099-01-01T00:00:00Z")]
    assert filter_verified_nba_images([pick], cards) == ([], 1)
    pick.leg_details = [first, dict(second, player="Wrong Player")]
    assert filter_verified_nba_images([pick], cards) == ([], 1)
    nfl = SimpleNamespace(**dict(first, player="Josh Allen", sport="NFL", game="Bills @ Jets"),
                          source_sport="NFL", type="single", leg_details=[],
                          features={"odds_observed": True, "bookmaker": "QA BOOK"})
    monkeypatch.setattr(cards, "_get_image", lambda _: None)
    assert filter_verified_nba_images([nfl], cards) == ([], 1)
    monkeypatch.setattr(cards, "_get_image", lambda _: art)
    assert filter_verified_nba_images([nfl], cards) == ([nfl], 0)
    assert ns["_payload_card_image"]({"kind": "single", "single_indices": [0]}, [nfl]) == nfl._verified_owner_png
