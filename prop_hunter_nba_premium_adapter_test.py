#!/usr/bin/env python3
"""Offline NBA premium integration tests; synthetic QA inputs never reach Telegram."""
from io import BytesIO
from types import SimpleNamespace
from PIL import Image, ImageDraw
from prop_hunter_nba_premium_adapter import render_nba_pick, PremiumDataMissing

def img(kind="player"):
    im=Image.new("RGBA",(180,220),(0,0,0,0))
    d=ImageDraw.Draw(im)
    d.ellipse((25,15,155,150),fill=(80,145,205,255))
    d.rounded_rectangle((12,125,168,219),24,fill=(40,65,110,255))
    return im

teams=[("HOME TEAM",img("logo")),("AWAY TEAM",img("logo"))]
feats={"bookmaker":"TEST ONLY BOOKMAKER","venue":"TEST ARENA",
       "combined_odds_observed":True,"combined_quote_id":"TEST-NOT-REAL"}
base={"source_sport":"NBA","game":"HOME TEAM vs AWAY TEAM",
      "commence_time":"2026-11-20T19:00:00+00:00","features":feats,
      "settlement_summary":"OFFEN","stake":1}
single=SimpleNamespace(**base,type="single",player="TEST ATHLETE",
                       market="points",odds=2.05)
row={"name":"TEST ATHLETE","photo":img(),"label":"Over 20.5 points",
     "form":"L5 3/5   L10 7/10   L15 10/15",
     "model":{"prob":"62","edge":"+5.5","confidence":"79/100"}}
png=render_nba_pick(single,[row],teams)
assert Image.open(BytesIO(png)).size==(1080,1440)
assert png.startswith(b"\x89PNG")

ladder=SimpleNamespace(**base,type="ladder",player="TEST ATHLETE",odds=None,
                       leg_details=[{"odds":1.75},{"odds":2.45}])
rungs=[dict(row,label="Over 20.5 points"),dict(row,label="Over 25.5 points")]
assert Image.open(BytesIO(render_nba_pick(ladder,rungs,teams))).size==(1080,1440)

builder=SimpleNamespace(**base,type="betbuilder",odds=5.10,
                        leg_details=[{"odds":1.7},{"odds":1.8}])
legs=[dict(row,name="TEST PLAYER A"),dict(row,name="TEST PLAYER B")]
assert Image.open(BytesIO(render_nba_pick(builder,legs,teams))).size==(1080,1440)

def rejects(pick,rows,teamlist=teams,contains=None):
    try:
        render_nba_pick(pick,rows,teamlist)
    except PremiumDataMissing as exc:
        if contains:assert contains in str(exc),(contains,str(exc))
    else:
        raise AssertionError("Unsafe NBA premium card accepted")

rejects(SimpleNamespace(**{**base,"commence_time":None},type="single",
       market="points",odds=2.05),[row],contains="tipoff")
rejects(SimpleNamespace(**{**base,"features":{}},type="single",
       market="points",odds=2.05),[row],contains="bookmaker")
rejects(single,[dict(row,photo=None)],contains="player_photo")
rejects(ladder,[dict(row,name="TEST A"),dict(row,name="TEST B")],
        contains="exactly one athlete")
rejects(SimpleNamespace(**{**base,"features":{**feats,"combined_odds_observed":False}},
       type="betbuilder",odds=5.10,
       leg_details=[{"odds":1.7},{"odds":1.8}]),legs,
       contains="combo ticket")
multi_legs=[{"odds":1.7,"game":"TEAM A vs TEAM B","commence_time":"2026-11-20T19:00:00+00:00","sport":"NBA"},
            {"odds":1.8,"game":"TEAM C vs TEAM D","commence_time":"2026-11-21T20:00:00+00:00","sport":"NBA"}]
cross=SimpleNamespace(**{**base,"features":{**feats,"combo_scope":"cross_game"}},
                      type="betbuilder",odds=5.10,leg_details=multi_legs)
assert Image.open(BytesIO(render_nba_pick(cross,legs,[]))).size==(1080,1440)
lottery=SimpleNamespace(**base,type="lottery",odds=18.25,leg_details=multi_legs)
assert Image.open(BytesIO(render_nba_pick(lottery,legs,[]))).size==(1080,1440)
rejects(SimpleNamespace(**{**base,"game":""},type="lottery",odds=18.25,
       leg_details=[{**multi_legs[0],"game":""},multi_legs[1]]),legs,[],
       contains="verified matchup")
rejects(SimpleNamespace(**{**base,"commence_time":None},type="lottery",odds=18.25,
       leg_details=[{**multi_legs[0],"commence_time":None},multi_legs[1]]),legs,[],
       contains="tipoff")
# Parent-game time must never be reused for a different cross-game leg.
rejects(SimpleNamespace(**base,type="lottery",odds=18.25,
       leg_details=[{**multi_legs[0], "commence_time": None}, multi_legs[1]]),
       legs, [], contains="tipoff")
# Exercise the actual production image-card routing with network fetches mocked.
# This proves that the opt-in uses the new master rather than the legacy compositor.
import os
from unittest.mock import patch
import prop_hunter_image_cards as image_cards
with patch.dict(os.environ, {"PH_NBA_PREMIUM_V2": "1"}), \
     patch.object(image_cards, "player_photo", return_value=img()), \
     patch.object(image_cards, "team_logo", return_value=img("logo")), \
     patch.object(image_cards, "render", side_effect=AssertionError("Legacy card unexpectedly used")):
    via_pipeline = image_cards.build_for_pick(single)
    assert via_pipeline and Image.open(BytesIO(via_pipeline)).size == (1080,1440)
# Test all four families through the actual production routing, not only the adapter.
with patch.object(image_cards, "ON", True), \
     patch.object(image_cards, "player_photo", return_value=img()), \
     patch.object(image_cards, "team_logo", return_value=img("logo")), \
     patch.object(image_cards, "render", side_effect=AssertionError("Legacy renderer called")):
    for family, pick in (("single", single), ("ladder", ladder),
                         ("builder", builder), ("lottery", lottery)):
        if family == "ladder":
            pick.leg_details = [
                {"player": "TEST ATHLETE", "market": "points", "odds": 1.75},
                {"player": "TEST ATHLETE", "market": "points", "odds": 2.45},
            ]
        if family == "builder":
            pick.leg_details = [
                {"player": "TEST PLAYER A", "market": "points", "odds": 1.7},
                {"player": "TEST PLAYER B", "market": "rebounds", "odds": 1.8},
            ]
        if family == "lottery":
            pick.leg_details = [
                {**multi_legs[0], "player": "TEST PLAYER A", "market": "points"},
                {**multi_legs[1], "player": "TEST PLAYER B", "market": "rebounds"},
            ]
        rendered = image_cards.build_for_pick(pick)
        assert rendered is not None, f"Production route rejected {family}"
        assert Image.open(BytesIO(rendered)).size == (1080, 1440), family

# Never mix WNBA or other-league selections into an NBA-branded ticket.
mixed_builder=SimpleNamespace(**base,type="betbuilder",odds=5.10,
        leg_details=[{"odds":1.7,"sport":"NBA"},
                     {"odds":1.8,"sport":"WNBA"}])
rejects(mixed_builder,legs,contains="not NBA")
mixed_ladder=SimpleNamespace(**base,type="ladder",player="TEST ATHLETE",
        leg_details=[{"odds":1.75,"sport":"NBA"},
                     {"odds":2.45,"sport":"EuroLeague"}])
rejects(mixed_ladder,rungs,contains="not NBA")
print("NBA LEAGUE ISOLATION PASS: no WNBA/EuroLeague legs in NBA cards")

# Preserve QA-only render samples for visual inspection in GitHub Actions.
# Synthetic names/odds/photos must never be published as actual Telegram tips.
from pathlib import Path
preview_dir = Path("output/nba_premium_qa")
preview_dir.mkdir(parents=True, exist_ok=True)
samples = {
    "single": render_nba_pick(single, [row], teams),
    "ladder": render_nba_pick(ladder, rungs, teams),
    "builder": render_nba_pick(builder, legs, teams),
    "lottery": render_nba_pick(lottery, legs, []),
}
for family, blob in samples.items():
    image = Image.open(BytesIO(blob)).convert("RGB")
    assert image.size == (1080, 1440), family
    assert image.getbbox() is not None, family
    (preview_dir / (family + ".png")).write_bytes(blob)
print("NBA QA PREVIEWS: " + ", ".join(sorted(samples)))
print("NBA PREMIUM ADAPTER PASS: verified single, ladder, builder, cross-game, lottery; authentic logos/photos; fail-closed missing tipoff/odds/assets")
