"""Fail if original Single has transparent stickers or floating result text.

Uses two drastically different EMPTY approved-plate test backgrounds. If any
stadium/player pixels show through the actual market/odds area, the two final
rendered text regions differ and this offline hardtest fails. No network.
"""
from __future__ import annotations
import io
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageChops

import prop_hunter_owner_clean_single as single

BASE=Path(__file__).resolve().parent/"card_templates"/"approved"/"single.png"
logo=Image.new("RGBA",(80,80),(0,0,0,0))
ImageDraw.Draw(logo).ellipse((4,4,75,75),fill=(20,180,220,255))
hero=Image.new("RGBA",(160,200),(0,0,0,0))
ImageDraw.Draw(hero).ellipse((18,5,145,180),fill=(168,92,77,255))
teams=[("DETROIT PISTONS",logo),("ATLANTA HAWKS",logo)]
row={"name":"OFFLINE TEST PLAYER","photo":hero,"label":"Under 12.5 points",
     "odds":"@1.76","form":"L5 4/5 L10 9/10 L15 13/14",
     "model":{"prob":"71.2%","edge":"+14.3%","confidence":"—"}}
with Image.open(BASE) as src:
    original=src.convert("RGB")
changed=original.copy()
p=ImageDraw.Draw(changed)
p.rectangle((236,398,449,426),fill=(255,5,245))
p.rectangle((496,398,600,426),fill=(5,255,245))
seen=[]
realtext=single._text
def witness(draw,position,value,*args,**kwargs):
    seen.append((str(value),tuple(position),kwargs.get("max_width")))
    return realtext(draw,position,value,*args,**kwargs)

def build(plate):
    with patch("prop_hunter_original_compositor._background_portrait",return_value=True), \
         patch.object(single,"_text",side_effect=witness):
        return single.render(plate,title="SINGLE",
            subtitle="Detroit Pistons vs Atlanta Hawks · So 22.11. · 21:40",
            teams=teams,row=row,footer="Quote @1.76 · Einsatz 1u",
            settlement="OFFEN")
a,b=build(original),build(changed)
with Image.open(io.BytesIO(a)) as im:
    pristine=im.convert("RGB")
with Image.open(io.BytesIO(b)) as im:
    mutated=im.convert("RGB")
assert pristine.size==mutated.size
scale=pristine.width/original.width
def scaled_rect(r):
    return tuple(round(v*scale) for v in r)
# Source is already an EMPTY approved master. Its actual neon market
# rails must remain visible after dynamic text is drawn. If the renderer
# pastes old-style opaque rectangles, the two cards would look identical
# here even though the underlying source rails were deliberately changed.
for source_rect in ((239,401,446,423),(499,402,596,422)):
    rect=scaled_rect(source_rect)
    delta=ImageChops.difference(pristine.crop(rect),mutated.crop(rect))
    assert delta.getbbox() is not None,(
        "ORIGINAL_SINGLE_NEON_RAIL_WAS_COVERED",source_rect)
assert any(text=="Under 12.5 points" and xy==(340,410) and mx==236 for text,xy,mx in seen)
assert any(text=="@1.76" and xy==(547,410) and mx==125 for text,xy,mx in seen)
# No bulk tint/rectangle layer. The photographed background is untouched.
for x,y in ((235,390),(600,390),(225,434),(610,434)):
    sx,sy=round(x*scale),round(y*scale)
    source_scaled=original.resize(pristine.size,Image.Resampling.LANCZOS)
    assert pristine.getpixel((sx,sy))==source_scaled.getpixel((sx,sy)),(
        "SINGLE_MASKED_ORIGINAL_ARTWORK",(x,y))

# Pending is transparent (no added shape), the same white as the owner's
# AUSWERTUNG text, and on the SAME baseline.
assert any(text=="OFFEN" and xy==(405,669) and mx<=135 for text,xy,mx in seen)
assert single.WHITE == (250,251,253)
# In the region previously covered by the gigantic new status rectangle,
# untouched source-floor pixels must remain untouched except for glyphs.
source_scaled=original.resize(pristine.size,Image.Resampling.LANCZOS)
for point in ((342,659),(463,697),(480,662)):
    x,y=point
    sx,sy=round(x*scale),round(y*scale)
    assert pristine.getpixel((sx,sy))==source_scaled.getpixel((sx,sy)),(
        "FLOATING_BLACK_FOOTER_STATUS_STICKER",point
    )
assert "p.rounded_rectangle((211, 387, 470, 437)" not in __import__("inspect").getsource(single.render)
print("SINGLE_CLEAN_ORIGINAL_NEON_RAILS_AND_RESULT_IN_RIBBON_PASS")
