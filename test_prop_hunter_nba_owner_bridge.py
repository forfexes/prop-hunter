import os as _os
_os.environ["PH_MASTER_CARDS"]="0"  # these checks cover the legacy compositor only
"""Hermetic original-owner NBA Single/Ladder/Builder render and odds guard QA."""
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch

from PIL import Image, ImageDraw

import prop_hunter_nba_premium_adapter as adapter
import prop_hunter_nba_owner_bridge as bridge
import prop_hunter_original_compositor as originals

CLEAN=Path(__file__).resolve().parent/"card_templates"/"cleaned"
for family in ("single","ladder","builder","lottery"):
    assert (CLEAN/(family+".png")).is_file(),family

hero=Image.new("RGBA",(160,200),(0,0,0,0))
d=ImageDraw.Draw(hero)
d.ellipse((35,9,126,105),fill=(216,160,125,255))
d.rounded_rectangle((9,101,151,196),18,fill=(38,125,213,255))
logo=Image.new("RGBA",(100,100),(0,0,0,0))
ImageDraw.Draw(logo).ellipse((6,6,94,94),fill=(45,194,245,255))
teams=[("HOME TEST",logo),("AWAY TEST",logo)]
features={"bookmaker":"TEST_BOOKMAKER_ONLY",
          "combined_odds_observed":True,"combined_quote_id":"QA_TICKET"}
common={"commence_time":"2026-11-20T19:00:00+00:00",
        "sport":"NBA","game":"HOME TEST @ AWAY TEST","stake":1.0,"features":features}

row={"name":"TEST PLAYER","label":"Over 20.5 points","photo":hero,
     "form":"L5 4/5 L10 7/10 L15 11/15",
     "model":{"prob":"64","edge":"+8","confidence":"78/100"}}
examples=[
    ("single",N(**common,type="single",market="points",odds=1.90),
     [row],[]),
    ("single_points_rebounds_owner",N(**common,type="single",
     market="points rebounds",odds=1.90),
     [dict(row,label="Points Rebounds Over 20.5")],[]),
    ("single_double_double_owner",N(**common,type="single",
     market="double double",odds=2.45),
     [dict(row,label="Double Double")],[]),
    ("ladder",N(**common,type="ladder",player="TEST PLAYER",odds=2.4,leg_details=[
         {"odds":1.8,"sport":"NBA"},{"odds":2.4,"sport":"NBA"}]),
     [row,dict(row,label="Over 25.5 points")],[]),
    ("builder",N(**common,type="betbuilder",odds=3.45,leg_details=[
         {"player":"TEST PLAYER","odds":1.75,"sport":"NBA","game":common["game"],
          "commence_time":common["commence_time"],"fixture_id":"OWNER-QA-123"},
         {"player":"TEST PLAYER TWO","odds":1.9,"sport":"NBA","game":common["game"],
          "commence_time":common["commence_time"],"fixture_id":"OWNER-QA-123"},
         {"player":"TEST PLAYER THREE","odds":2.0,"sport":"NBA","game":common["game"],
          "commence_time":common["commence_time"],"fixture_id":"OWNER-QA-123"}]),
     [row,dict(row,name="TEST PLAYER TWO"),dict(row,name="TEST PLAYER THREE")],[]),
    ("lottery",N(**common,type="lottery",odds=13.80,leg_details=[
         {"player":"TEST PLAYER","odds":1.75,"sport":"NBA","game":"HOME TEST vs AWAY TEST",
          "commence_time":"2026-11-20T19:00:00+00:00"},
         {"player":"TEST PLAYER TWO","odds":2.30,"sport":"NBA","game":"TEAM C vs TEAM D",
          "commence_time":"2026-11-21T19:00:00+00:00"},
         {"player":"TEST PLAYER THREE","odds":3.40,"sport":"NBA","game":"TEAM E vs TEAM F",
          "commence_time":"2026-11-22T19:00:00+00:00"}]),
     [row,dict(row,name="TEST PLAYER TWO"),dict(row,name="TEST PLAYER THREE")],[]),
]

# Combo and cross-game are data variants of the user's Lottery original.
# Confirm the production owner bridge is called, not the generated SVG route.
lottery_reference=next(example for example in examples if example[0]=="lottery")
lottery_rows=lottery_reference[2]
lottery_details=lottery_reference[1].leg_details
combo_original=N(**common,type="combo",odds=13.80,
                 leg_details=lottery_details)
cross_original=N(**{**common,"features":{**features,"combo_scope":"cross_game"}},
                 type="betbuilder",odds=13.80,leg_details=lottery_details)
examples.extend([
    ("combo_owner_lottery",combo_original,lottery_rows,[]),
    ("cross_game_owner_lottery",cross_original,lottery_rows,[]),
])

same_player_rows=[
    dict(row,label="Points Over 20.5"),
    dict(row,label="Assists Over 5.5"),
    dict(row,label="Rebounds Over 7.5"),
]
same_player_details=[
    {"player":"TEST PLAYER","sport":"NBA","market":"points","odds":1.75},
    {"player":"TEST PLAYER","sport":"NBA","market":"assists","odds":1.85},
    {"player":"TEST PLAYER","sport":"NBA","market":"rebounds","odds":1.90},
]
same_player_pick=N(**{**common,"features":{**features,"same_player_multistat":True}},
                   type="betbuilder",odds=6.15,leg_details=same_player_details)
examples.append(("same_player_owner_ladder",same_player_pick,same_player_rows,[]))

same_player_rows6 = [
    dict(row, label=f"Same-player verified QA market {i+1}")
    for i in range(6)
]
same_player_details6 = [
    {"player":"TEST PLAYER","sport":"NBA","market":f"qa_market_{i+1}",
     "odds":round(1.30+i*.1,2)}
    for i in range(6)
]
same_player_pick6 = N(
    **{**common,"features":{**features,"same_player_multistat":True}},
    type="betbuilder",odds=10.50,leg_details=same_player_details6)
examples.append(("same_player_owner_ladder6",same_player_pick6,same_player_rows6,[]))

longshot_original=N(**common,type="longshot",player="TEST PLAYER",
                    market="points",odds=3.25)
examples.append(("longshot_owner_single",longshot_original,[row],[]))

# Even a previously published historical card cannot be repainted with a
# multiplied estimate in owner-only Telegram settlement mode.
builder_fixture=next(item for item in examples if item[0]=="builder")
historical_without_ticket=N(**{
    **vars(builder_fixture[1]),
    "features":{"bookmaker":"TEST_BOOKMAKER_ONLY"},
})
with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}):
    try:
        adapter.render_nba_pick(historical_without_ticket,
                                builder_fixture[2],teams)
    except adapter.PremiumDataMissing as exc:
        assert "observed bookmaker combined ticket" in str(exc)
    else:
        raise AssertionError("Owner-image settlement displayed a calculated combined quote")
print("NBA HISTORIC UNVERIFIED PARLAY CANNOT REPAINT OWNER ORIGINAL")

old_master=originals.APPROVED_MASTER
old_base=bridge.BASE
try:
    originals.APPROVED_MASTER=CLEAN
    bridge.BASE=CLEAN
    originals._source.cache_clear()
    with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}):
        for family,pick,rows,_ in examples:
            if family in ("combo_owner_lottery","cross_game_owner_lottery",
                          "same_player_owner_ladder","longshot_owner_single"):
                with patch.object(bridge,"render_owner", wraps=bridge.render_owner) as check_owner:
                    raw=adapter.render_nba_pick(pick,rows,teams)
                    check_owner.assert_called_once()
                    expected=(("same_player_",) if family=="same_player_owner_ladder"
                              else ("longshot",) if family=="longshot_owner_single"
                              else ("combo_","cross_game_"))
                    assert check_owner.call_args.args[1].startswith(expected)
            else:
                raw=adapter.render_nba_pick(pick,rows,teams)
            with Image.open(BytesIO(raw)) as image:
                assert image.width==1080 and image.height>=1100,(family,image.size)
                image.verify()
            outdir=Path("output/nba_owner_qa")
            outdir.mkdir(parents=True,exist_ok=True)
            (outdir/(family+".png")).write_bytes(raw)
            print("OWNER_NBA_PREVIEW_OK",family,len(raw))
        six_rows=same_player_rows+[dict(row,label=f"Extra {i}") for i in range(3)]
        six_details=same_player_details+[
            {"player":"TEST PLAYER","sport":"NBA","market":"points","odds":1.91}
            for _ in range(3)]
        six=N(**{**common,"features":{**features,"same_player_multistat":True}},
              type="betbuilder",odds=21.5,leg_details=six_details)
        # The new user-source-derived clean plate extends the arena rather
        # than squeezing six same-player props onto the five-row screenshot.
        expanded = adapter.render_nba_pick(six,six_rows,teams)
        with Image.open(BytesIO(expanded)) as proof_six:
            assert proof_six.width == 1080 and proof_six.height > 1350
        outdir.joinpath("same_player_owner_ladder6.png").write_bytes(expanded)
        print("SAME_PLAYER_SIX_LAYERED_APPROVED_QA")
        # Visual regression: the owner's Ladder must display the real athlete
        # name, not only a portrait and anonymous numbered stages. Test every
        # owner-approved rung count without Telegram or external lookups.
        import prop_hunter_owner_clean_ladder as clean_ladder
        real_text=clean_ladder._text
        for n in (2,3,4,5,6):
            named=[]
            def capture_name(draw, xy, label, *args, **kwargs):
                if str(label).strip()=="TEST PLAYER":
                    named.append(tuple(xy))
                return real_text(draw, xy, label, *args, **kwargs)
            ladder=N(**common,type="ladder",player="TEST PLAYER",odds=None,
                     leg_details=[{"odds":round(1.30+i*.2,2),"sport":"NBA"}
                                  for i in range(n)])
            ladder_rows=[dict(row,label=f"Under {1.5+i} blocks")
                         for i in range(n)]
            with patch.object(clean_ladder,"_text",side_effect=capture_name):
                raw=adapter.render_nba_pick(ladder,ladder_rows,teams)
            # Athlete name appears once ABOVE the price ladder; the second
            # caption below the portrait was rejected by the owner.
            assert named == [(443,332)], (n,named)
            with Image.open(BytesIO(raw)) as proof:
                assert proof.width==1080 and proof.height>=1100
            outdir.joinpath(f"ladder_{n}_name_fixed.png").write_bytes(raw)
            print("OWNER_LADDER_NAME_VISIBLE_OK",n)
finally:
    originals.APPROVED_MASTER=old_master
    bridge.BASE=old_base
    originals._source.cache_clear()

# Clean approved owner originals MUST NOT be masked a second time.
# A synthetic preview is allowed in offline QA; never send it to Telegram.
# Guard the actual compositor against accidental reintroduction of the
# legacy screenshot cover-up functions after the clean plate is loaded.
def _legacy_coverup_forbidden(*_args, **_kwargs):
    raise AssertionError("Legacy screenshot overpainting on a clean owner master")
with patch.dict("os.environ", {"PH_NBA_OWNER_ORIGINALS":"1"}), \
     patch.object(originals, "_erase_template_head_remnants",
                  side_effect=_legacy_coverup_forbidden), \
     patch.object(originals, "_fade_baked_lottery_arm",
                  side_effect=_legacy_coverup_forbidden), \
     patch.object(originals, "_clean_hero",
                  side_effect=_legacy_coverup_forbidden):
    for family,pick,rows,_ in examples:
        data=adapter.render_nba_pick(pick,rows,teams)
        with Image.open(BytesIO(data)) as verification:
            assert verification.format=="PNG" and verification.width==1080
        print("CLEAN_PLATE_NO_LEGACY_MASK_QA",family)
print("CLEAN OWNER COMPOSITOR WITHOUT SAMPLE OVERPAINT PASSED")

# No opaque runtime screenshot coverups are permitted on the three newly
# layered owner families. Each input is synthetic and never sent to Telegram.
with patch.dict("os.environ", {"PH_NBA_OWNER_ORIGINALS": "1"}), \
     patch.object(originals, "APPROVED_MASTER", CLEAN), \
     patch.object(bridge, "BASE", CLEAN), \
     patch.object(originals, "_rect", side_effect=AssertionError("Opaque screenshot repaint detected")), \
     patch.object(originals, "_blend_fill", side_effect=AssertionError("Opaque source blending detected")):
    originals._source.cache_clear()
    for name, pick, rows, _ in examples:
        if name in ("single", "ladder", "builder", "lottery",
                    "same_player_owner_ladder6",
                    "combo_owner_lottery", "cross_game_owner_lottery"):
            raw = adapter.render_nba_pick(pick, rows, teams)
            with Image.open(BytesIO(raw)) as approved_layered:
                assert approved_layered.width == 1080, name
            print("OWNER_LAYERED_NO_OPAQUE_REPAINT_OK", name)
originals._source.cache_clear()

# Approval-gate: exercise the actual checked-in approved production files,
# not only a monkeypatched working directory.
APPROVED=Path(__file__).resolve().parent/"card_templates"/"approved"
if all((APPROVED/(family+".png")).is_file() for family in ("single","ladder","builder","lottery")):
    with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1",
                                 "PH_BLOCK_OVERPAINTED_MASTERS":"1",
                                 "PH_ALLOW_VERIFIED_LAYERED_OWNER":"1"}):
        for family,pick,rows,_ in examples:
            raw=adapter.render_nba_pick(pick,rows,teams)
            with Image.open(BytesIO(raw)) as image:
                assert image.width==1080 and image.height>=1100
                image.verify()
            # Compare the ACTUALLY rendered owner-card output, not a blank
            # master PNG, against the immutable masthead and current clean plate.
            from prop_hunter_owner_pixel_qa import owner_family,owner_pixel_provenance
            from PIL import ImageChops
            actual=owner_family(pick)
            with Image.open(APPROVED/(actual+".png")) as prod, \
                 Image.open(CLEAN/(actual+".png")) as clean:
                up_to_date=(ImageChops.difference(
                    prod.convert("RGB"),clean.convert("RGB")).getbbox() is None)
            pixel_ok,pixel_reason=owner_pixel_provenance(pick,raw)
            assert up_to_date and pixel_ok,(family,actual,pixel_reason)
            print("PRODUCTION_APPROVED_ORIGINAL_OK",family,
                  "pixel_gate=",pixel_reason)
else:
    print("OWNER_PRODUCTION_APPROVED_FILES_NOT_YET_PRESENT")

# Release is NOT a bypass of the universal legacy screenshot ban. Missing
# approved/cleaned source must reject a posted PNG before photo lookup.
with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1",
                              "PH_BLOCK_OVERPAINTED_MASTERS":"1",
                              "PH_ALLOW_VERIFIED_LAYERED_OWNER":"1"}), \
     patch.object(bridge,"BASE",CLEAN/"intentionally_missing_approved"):
    try:
        adapter.render_nba_pick(examples[0][1],examples[0][2],teams)
    except ValueError as err:
        assert "clean_plates_not_ready" in str(err),str(err)
    else:
        raise AssertionError("Release accepted missing or unclean owner source")

# If actual approved cleaned source is not present, NO generic SVG fallback.
with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
     patch.object(bridge, "BASE", CLEAN / "intentionally_missing_approved"):
    try:
        adapter.render_nba_pick(examples[0][1],examples[0][2],teams)
    except ValueError as err:
        assert "not approved" in str(err).lower()
    else:
        raise AssertionError("Owner-only mode accepted missing approved source")
print("NO OWNER ORIGINAL FALLBACK PASS")
# Never paint a premium pick on the raw user JPEG if the APPROVED plate
# is missing: this is how stale sample players/lines leak into Telegram.
with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
     patch.object(originals,"APPROVED_MASTER",CLEAN/"missing_production_plates"):
    originals._source.cache_clear()
    for family in ("single","ladder","builder","lottery"):
        try:
            originals._source(family)
        except ValueError as exc:
            assert "Approved owner-original master missing" in str(exc),str(exc)
        else:
            raise AssertionError("Premium "+family+" fell back to prefilled owner JPG")
originals._source.cache_clear()
print("NO SAMPLE-TEXT OVERPAINT FALLBACK PASS")

