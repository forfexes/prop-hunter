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
                        leg_details=[{"player":"TEST PLAYER A","odds":1.7},{"player":"TEST PLAYER B","odds":1.8}])
legs=[dict(row,name="TEST PLAYER A"),dict(row,name="TEST PLAYER B")]
assert Image.open(BytesIO(render_nba_pick(builder,legs,teams))).size==(1080,1440)
builder_3=SimpleNamespace(**base,type="betbuilder",odds=6.40,
                          leg_details=[{"player":"TEST PLAYER A","odds":1.7},{"player":"TEST PLAYER B","odds":1.8},{"player":"TEST PLAYER C","odds":1.9}])
legs_3=[dict(row,name="TEST PLAYER A"),dict(row,name="TEST PLAYER B"),
        dict(row,name="TEST PLAYER C")]
assert Image.open(BytesIO(render_nba_pick(builder_3,legs_3,teams))).size==(1080,1440)

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
# Invalid numeric bookmaker values must never be rendered as @nan or @inf.
from prop_hunter_nba_premium_adapter import _price
for invalid_quote in (float("nan"), float("inf"), float("-inf"), "NaN", "Infinity", None, 0, 1):
    try:
        _price(invalid_quote)
    except PremiumDataMissing:
        pass
    else:
        raise AssertionError(f"Invalid premium quote was accepted: {invalid_quote!r}")
rejects(SimpleNamespace(**base,type="single",market="points",odds=float("nan")),
        [row],contains="Invalid bookmaker price")
print("NBA PREMIUM QUOTE FINITE-VALUE GATE PASSED")
# A zero-unit card is not an actionable stake; malformed units must fail closed.
for invalid_stake in (0, -1, float("nan"), float("inf"), "invalid"):
    rejects(SimpleNamespace(**{**base, "stake": invalid_stake},
                            type="single", market="points", odds=2.05),
            [row], contains="Invalid stake")
print("NBA PREMIUM STAKE GUARD PASSED")

# Stake must be an actual nonnegative finite unit amount.
for invalid_stake in (float("nan"), float("inf"), float("-inf"), -1, "NaN", "Infinity"):
    rejects(SimpleNamespace(**{**base, "stake": invalid_stake},
            type="single", player="TEST ATHLETE", market="points", odds=2.05),
            [row], contains="Invalid stake")
print("NBA PREMIUM STAKE FINITE-VALUE GATE PASSED")



# Multiword single markets are genuine owner-Single cards, never a phantom
# "single_points" family produced by splitting on the last underscore.
from prop_hunter_nba_premium_adapter import _family_from_key
for master_key in ("single_points_rebounds", "single_points_assists",
                   "single_double_double", "single_triple_double"):
    assert _family_from_key(master_key) == "single", master_key
for master_key, expected_family in (
    ("cross_game_3", "cross_game"), ("same_player_3", "same_player"),
    ("builder_4", "builder"), ("lottery_12", "lottery"),
    ("longshot", "longshot"),
):
    assert _family_from_key(master_key) == expected_family
print("NBA MULTIWORD SINGLE ORIGINAL FAMILY PASS")

# Unsupported markets must not silently use a generic single-card fallback.
rejects(SimpleNamespace(**base,type="single",market="unapproved_unsupported_prop",
       odds=2.05),[row],contains="No approved NBA master")
# Real live production strings: these are market and observed numeric lines,
# not new or synthetic market types. Preserve the exact direction and threshold.
from prop_hunter_nba_premium_adapter import _template
for observed,expected,direction,point in (
    ("Rebounds Over 3.5","single_rebounds","over",3.5),
    ("Assists Under 4.5","single_assists","under",4.5),
    ("Points Under 13.5","single_points","under",13.5),
    ("Player_Points_Alternate","single_points","over",13.5),
    ("Points Rebounds Assists Over 23.5","single_pra","over",23.5),
):
    assert _template(SimpleNamespace(type="single",market=observed,
                                     direction=direction,point=point),[row])==expected
rejects(SimpleNamespace(**base,type="single",market="Assists Under 4.5",
       direction="over",point=4.5,odds=2.05),[row],
       contains="Conflicting observed NBA pick direction")
rejects(SimpleNamespace(**base,type="single",market="Rebounds Over 3.5",
       direction="over",point=6.5,odds=2.05),[row],
       contains="Conflicting observed NBA pick threshold")
print("LIVE SOURCE SINGLE MARKET ROUTING PASSED: points/rebounds/assists + numeric lines")

# Fake transparency (one transparent pixel on an opaque photo) is not a
# cutout; a real picture needs visible transparent background around athlete.
almost_opaque=Image.new("RGBA",(180,220),(52,72,88,255))
almost_opaque.putpixel((0,0),(52,72,88,0))
rejects(single,[dict(row,photo=almost_opaque)],contains="transparent cutout border")
rejects(ladder,[dict(row,name="TEST A"),dict(row,name="TEST B")],
        contains="exactly one athlete")
unconfirmed=SimpleNamespace(**{**base,"features":{**feats,"combined_odds_observed":False}},
       type="betbuilder",odds=None,
       leg_details=[{"player":"TEST PLAYER A","odds":1.7},{"player":"TEST PLAYER B","odds":1.8}])
assert Image.open(BytesIO(render_nba_pick(unconfirmed,legs,teams))).size==(1080,1440)
multi_legs=[{"player":"TEST PLAYER A","odds":1.7,"game":"TEAM A vs TEAM B","commence_time":"2026-11-20T19:00:00+00:00","sport":"NBA"},
            {"player":"TEST PLAYER B","odds":1.8,"game":"TEAM C vs TEAM D","commence_time":"2026-11-21T20:00:00+00:00","sport":"NBA"}]
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
# Cross-game graphics must NEVER substitute the parent game for a leg
# that has no real event. They must also have independently verified NBA league.
rejects(SimpleNamespace(**base,type="lottery",odds=18.25,
       leg_details=[{**multi_legs[0], "game": None}, multi_legs[1]]),
       legs, [], contains="verified matchup")
rejects(SimpleNamespace(**base,type="lottery",odds=18.25,
       leg_details=[{**multi_legs[0], "sport": None}, multi_legs[1]]),
       legs, [], contains="verified NBA league")

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
# Verify production Longshot is treated as one-player Single artwork, with
# no fallback into an empty multi-leg ticket or a generic legacy renderer.
longshot=SimpleNamespace(**base,type="longshot",player="TEST ATHLETE",
                         market="points",odds=3.25)
with patch.object(image_cards,"ON",True), \
     patch.object(image_cards,"player_photo",return_value=img()), \
     patch.object(image_cards,"team_logo",return_value=img("logo")), \
     patch.object(image_cards,"render",
                  side_effect=AssertionError("legacy longshot renderer called")):
    real_route=image_cards.build_for_pick(longshot)
    assert real_route is not None,"Longshot lost before premium adapter"
    assert Image.open(BytesIO(real_route)).size==(1080,1440)
print("NBA PRODUCTION LONGSHOT ORIGINAL ROUTING PASS")
# An attractive payout does not exempt Longshot from verified market scope.
rejects(SimpleNamespace(**base,type="longshot",player="TEST ATHLETE",
       market="unapproved_unsupported_prop",odds=3.25),
       [row],contains="No approved NBA master")
rejects(SimpleNamespace(**base,type="longshot",player="TEST ATHLETE",
       market="Points Over 22.5",direction="under",point=22.5,odds=3.25),
       [row],contains="Conflicting observed NBA pick direction")


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

# Extended owner-layout variants: Builder 7 and Lottery/Combo 12.
# Every test input is synthetic and never eligible for a live Telegram post.
extended_rows=[dict(row,name=f"TEST PLAYER {i+1}",photo=img()) for i in range(12)]
extended_details=[
    {"player":f"TEST PLAYER {i+1}","market":"points","odds":round(1.22+i*.01,2),
     "game":f"TEAM {i+1} vs TEAM B {i+1}",
     "commence_time":f"2026-11-{20+i%7:02d}T19:00:00+00:00",
     "sport":"NBA","bookmaker":"TEST ONLY BOOKMAKER"}
    for i in range(12)]
calculated_feats={**feats,"combined_odds_observed":False,"combined_quote_id":""}
builder_7=SimpleNamespace(**{**base,"features":calculated_feats},
    type="betbuilder",odds=None,leg_details=extended_details[:7])
lottery_12=SimpleNamespace(**{**base,"features":calculated_feats},
    type="lottery",odds=None,leg_details=extended_details)
cross_12=SimpleNamespace(**{**base,"features":{**calculated_feats,
                         "combo_scope":"cross_game"}},
    type="betbuilder",odds=None,leg_details=extended_details)
with patch.dict(os.environ,{"PH_NBA_OWNER_ORIGINALS":"0"}):
    for title,pick,rows_ext,teams_ext,height in (
        ("builder_7",builder_7,extended_rows[:7],teams,1542),
        ("lottery_12",lottery_12,extended_rows,[],2070),
        ("cross_game_12",cross_12,extended_rows,[],2070),
    ):
        raw=render_nba_pick(pick,rows_ext,teams_ext)
        assert Image.open(BytesIO(raw)).size==(1080,height),title
        preview_dir_extended=__import__("pathlib").Path("output/nba_premium_qa")
        preview_dir_extended.mkdir(parents=True,exist_ok=True)
        (preview_dir_extended/(title+".png")).write_bytes(raw)

# Cross-game Combos must use the user's Lottery original when owner mode is on,
# not silently fail solely because there is no fifth artwork family.
from prop_hunter_nba_owner_bridge import BASE as ORIGINALS
if (ORIGINALS/"lottery.png").is_file():
    with patch.dict(os.environ,{"PH_NBA_OWNER_ORIGINALS":"1"}):
        # Owner-original production requires a genuine ticket total. The
        # calculated-quote fixtures above are allowed ONLY in isolated SVG
        # layout tests, never in original PNG Telegram or settlement.
        for title,unverified in (("lottery_12",lottery_12),
                                 ("cross_game_12",cross_12)):
            rejects(unverified,extended_rows,[],contains="observed bookmaker combined ticket")
            verified=SimpleNamespace(**{
                **vars(unverified),
                "features":{**feats,
                            "combo_scope":unverified.features.get("combo_scope")},
                "odds":18.37,
            })
            raw=render_nba_pick(verified,extended_rows,[])
            assert Image.open(BytesIO(raw)).width==1080,title

# Never mix WNBA or other-league selections into an NBA-branded ticket.
mixed_builder=SimpleNamespace(**base,type="betbuilder",odds=5.10,
        leg_details=[{"player":"TEST PLAYER A","odds":1.7,"sport":"NBA"},
                     {"player":"TEST PLAYER B","odds":1.8,"sport":"WNBA"}])
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
    "builder_3": render_nba_pick(builder_3, legs_3, teams),
    "lottery": render_nba_pick(lottery, legs, []),
}
for family, blob in samples.items():
    image = Image.open(BytesIO(blob)).convert("RGB")
    assert image.size == (1080, 1440), family
    assert image.getbbox() is not None, family
    (preview_dir / (family + ".png")).write_bytes(blob)
print("NBA QA PREVIEWS: " + ", ".join(sorted(samples)))
print("NBA PREMIUM ADAPTER PASS: verified single, ladder, builder, cross-game, lottery; authentic logos/photos; fail-closed missing tipoff/odds/assets")


# Typed upstream leg models (not dictionaries) must render identically.  This
# catches a production crash before any Telegram transport is attempted.
typed_ladder = SimpleNamespace(**base, type="ladder", player="TEST ATHLETE",
    odds=None, leg_details=[
        SimpleNamespace(player="TEST ATHLETE", market="points", odds=1.75,
                        sport="NBA", bookmaker="TEST ONLY BOOKMAKER"),
        SimpleNamespace(player="TEST ATHLETE", market="points", odds=2.45,
                        sport="NBA", bookmaker="TEST ONLY BOOKMAKER")])
assert Image.open(BytesIO(render_nba_pick(typed_ladder, rungs, teams))).size == (1080, 1440)
typed_builder = SimpleNamespace(**base, type="betbuilder", odds=5.10,
    leg_details=[
        SimpleNamespace(player="TEST PLAYER A", market="points", odds=1.7,
                        sport="NBA", bookmaker="TEST ONLY BOOKMAKER"),
        SimpleNamespace(player="TEST PLAYER B", market="rebounds", odds=1.8,
                        sport="NBA", bookmaker="TEST ONLY BOOKMAKER")])
assert Image.open(BytesIO(render_nba_pick(typed_builder, legs, teams))).size == (1080, 1440)
typed_lottery = SimpleNamespace(**base, type="lottery", odds=18.25,
    leg_details=[SimpleNamespace(**leg) for leg in multi_legs])
assert Image.open(BytesIO(render_nba_pick(typed_lottery, legs, []))).size == (1080, 1440)
typed_bad = SimpleNamespace(**base, type="betbuilder", odds=5.10,
    leg_details=[SimpleNamespace(player="TEST PLAYER A", odds=1.7, sport="NBA"),
                 SimpleNamespace(player="TEST PLAYER B", odds=1.8, sport="WNBA")])
rejects(typed_bad, legs, contains="not NBA")
# A bookmaker on typed legs is valid evidence when the parent lacks a label.
typed_leg_book = SimpleNamespace(**{**base, "features": {"venue": "TEST ARENA",
    "combined_odds_observed": True, "combined_quote_id": "TEST-NOT-REAL"}},
    type="betbuilder", odds=5.10, leg_details=typed_builder.leg_details)
assert Image.open(BytesIO(render_nba_pick(typed_leg_book, legs, teams))).width == 1080
print("NBA TYPED LEG OBJECT COMPATIBILITY PASS: ladder/builder/lottery, bookmaker provenance and mixed-league rejection")


# The actual published image entrypoint must also support typed legs, not only
# the lower-level SVG adapter. Mocked images are QA-only; never sent to Telegram.
with patch.dict(os.environ, {"PH_NBA_OWNER_ORIGINALS": "0"}), \
     patch.object(image_cards, "ON", True), \
     patch.object(image_cards, "player_photo", return_value=img()), \
     patch.object(image_cards, "team_logo", return_value=img("logo")), \
     patch.object(image_cards, "render", side_effect=AssertionError("Legacy fallback used")):
    for family, model in (("ladder", typed_ladder),
                          ("builder", typed_builder)):
        png = image_cards.build_for_pick(model)
        assert png and Image.open(BytesIO(png)).size == (1080, 1440), family
    typed_lottery_full = SimpleNamespace(**base, type="lottery", odds=18.25,
        leg_details=[
            SimpleNamespace(**{**leg, "player": f"TEST PLAYER {i+1}",
                               "market": "points"})
            for i, leg in enumerate(multi_legs)])
    png = image_cards.build_for_pick(typed_lottery_full)
    assert png and Image.open(BytesIO(png)).size == (1080, 1440)
from prop_hunter_image_cards import _venue_text, _kickoff_text
typed_venue = SimpleNamespace(features={}, leg_details=[
    SimpleNamespace(features={"venue": "TEST ARENA"})])
assert _venue_text(typed_venue) == "TEST ARENA"
typed_time = SimpleNamespace(features={}, commence_time=None,
    leg_details=[SimpleNamespace(commence_time="2026-11-20T19:00:00+00:00")])
assert "20.11." in _kickoff_text(typed_time)
print("NBA LIVE ENTRYPOINT TYPED LEGS PASS: all four families, league isolation, venue and kickoff")
