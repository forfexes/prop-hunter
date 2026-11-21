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
        assert owner_family(pick)==family
        print("OWNER_ORIGINAL_PIXEL_QA",family,"approved_current="+str(up_to_date))
assert owner_family(N(type="unknown")) is None
assert owner_family(N(type="betbuilder",features={"combo_scope":"cross_game"}))=="lottery"
assert owner_family(N(type="betbuilder",features={"same_player_multistat":True}))=="ladder"
assert not owner_pixel_provenance(N(type="unknown"),b"not an image")[0]
print("OWNER IMMUTABLE PIXEL / STALE ASSET / FORGED DESIGN QA PASSED")
