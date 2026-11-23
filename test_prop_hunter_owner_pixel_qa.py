"""Offline pixel tampering regression using only the user's owner source artwork.

No Telegram, bookmaker or Supabase credentials are used.
"""
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace as N

from PIL import Image, ImageChops, ImageDraw

from prop_hunter_owner_pixel_qa import APPROVED, CLEANED, owner_family, owner_pixel_provenance

families = {
    "single": N(type="single"),
    "ladder": N(type="ladder"),
    "builder": N(type="betbuilder",features={}),
    "lottery": N(type="lottery"),
}
for family, pick in families.items():
    with Image.open(APPROVED / (family + ".png")) as original, \
         Image.open(CLEANED / (family + ".png")) as working:
        master = original.convert("RGB")
        clean = working.convert("RGB")
        up_to_date = ImageChops.difference(master,clean).getbbox() is None
        ready = master.resize(
            (1080,round(1080*master.height/master.width)),Image.Resampling.LANCZOS
        )
        output = BytesIO()
        ready.save(output,"PNG")
        valid, reason=owner_pixel_provenance(pick,output.getvalue())
        assert valid is up_to_date,(family,valid,reason)
        if not up_to_date:
            assert reason == "approved_master_not_current_clean_plate", reason
        # Top logo/crown altered -> reject, even when the rest of image is valid.
        painted=ready.copy()
        d=ImageDraw.Draw(painted)
        d.rectangle((455,20,510,52),fill=(255,0,0))
        bad=BytesIO()
        painted.save(bad,"PNG")
        assert not owner_pixel_provenance(pick,bad.getvalue())[0], family
        # A false NBA badge at top-left must be rejected as firmly as
        # a forged PROP HUNTER header. Do not accept a pasted-on logo.
        badge_forgery=ready.copy()
        ImageDraw.Draw(badge_forgery).rectangle(
            (64,40,124,89),fill=(255,0,0))
        impostor=BytesIO()
        badge_forgery.save(impostor,"PNG")
        assert owner_pixel_provenance(pick,impostor.getvalue()) == (
            False,"owner_masthead_pixel_overlap"),family
        assert owner_family(pick)==family
        print("OWNER_ORIGINAL_PIXEL_QA",family,"approved_current="+str(up_to_date))
# A six-prop one-player Ladder expands only empty stadium rows. Its crown
# must remain byte-exact when rendered at the correctly extended height.
# Compare the EXACT same geometry as the overlay-free producer; no tolerance,
# no "ignore top pixels" waiver, and no old screenshot underpaint.
with Image.open(APPROVED / "ladder.png") as clean_ladder:
    raw = clean_ladder.convert("RGB")
    assert raw.size == (691,865)
    tall = Image.new("RGB",(691,985),(3,15,29))
    tall.paste(raw.crop((0,0,691,730)),(0,0))
    tall.paste(raw.crop((0,515,691,635)),(0,730))
    tall.paste(raw.crop((0,730,691,865)),(0,850))
    stretched = tall.resize((1080,round(1080*985/691)),Image.Resampling.LANCZOS)
    same_player = N(type="betbuilder",features={"same_player_multistat":True})
    buffer = BytesIO()
    stretched.save(buffer,"PNG")
    assert owner_pixel_provenance(same_player,buffer.getvalue()) == (
        True,"source_original_pixels_verified")
    corrupted = stretched.copy()
    ImageDraw.Draw(corrupted).rectangle((455,20,510,52),fill=(255,0,0))
    manipulated = BytesIO()
    corrupted.save(manipulated,"PNG")
    assert owner_pixel_provenance(same_player,manipulated.getvalue()) == (
        False,"owner_masthead_pixel_overlap")
    wrong_height = stretched.crop((0,0,1080,stretched.height-20))
    bad_height = BytesIO()
    wrong_height.save(bad_height,"PNG")
    assert owner_pixel_provenance(same_player,bad_height.getvalue())[0] is False
    print("OWNER_SIX_LEG_CROWN_EXACT_MATCH_AND_FORGERY_REJECTED")

assert owner_family(N(type="unknown")) is None
assert owner_family(N(type="betbuilder",features={"combo_scope":"cross_game"}))=="lottery"
assert owner_family(N(type="betbuilder",features={"same_player_multistat":True}))=="ladder"
assert not owner_pixel_provenance(N(type="unknown"),b"not an image")[0]
print("OWNER IMMUTABLE PIXEL / STALE ASSET / FORGED DESIGN QA PASSED")
