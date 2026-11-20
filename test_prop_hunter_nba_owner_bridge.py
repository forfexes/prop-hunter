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
for family in ("single","ladder","builder"):
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
    ("ladder",N(**common,type="ladder",odds=2.4,leg_details=[
         {"odds":1.8,"sport":"NBA"},{"odds":2.4,"sport":"NBA"}]),
     [row,dict(row,label="Over 25.5 points")],[]),
    ("builder",N(**common,type="betbuilder",odds=3.45,leg_details=[
         {"odds":1.75,"sport":"NBA"},{"odds":1.9,"sport":"NBA"},
         {"odds":2.0,"sport":"NBA"}]),
     [row,dict(row,name="TEST PLAYER TWO"),dict(row,name="TEST PLAYER THREE")],[]),
]

old_master=originals.APPROVED_MASTER
old_base=bridge.BASE
try:
    originals.APPROVED_MASTER=CLEAN
    bridge.BASE=CLEAN
    originals._source.cache_clear()
    with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}):
        for family,pick,rows,_ in examples:
            raw=adapter.render_nba_pick(pick,rows,teams)
            with Image.open(BytesIO(raw)) as image:
                assert image.width==1080 and image.height>=1100,(family,image.size)
                image.verify()
            outdir=Path("output/nba_owner_qa")
            outdir.mkdir(parents=True,exist_ok=True)
            (outdir/(family+".png")).write_bytes(raw)
            print("OWNER_NBA_PREVIEW_OK",family,len(raw))
finally:
    originals.APPROVED_MASTER=old_master
    bridge.BASE=old_base
    originals._source.cache_clear()

# Approval-gate: exercise the actual checked-in approved production files,
# not only a monkeypatched working directory.
APPROVED=Path(__file__).resolve().parent/"card_templates"/"approved"
if all((APPROVED/(family+".png")).is_file() for family in ("single","ladder","builder")):
    with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}):
        for family,pick,rows,_ in examples:
            raw=adapter.render_nba_pick(pick,rows,teams)
            with Image.open(BytesIO(raw)) as image:
                assert image.width==1080 and image.height>=1100
                image.verify()
            print("PRODUCTION_APPROVED_ORIGINAL_OK",family)
else:
    print("OWNER_PRODUCTION_APPROVED_FILES_NOT_YET_PRESENT")

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
