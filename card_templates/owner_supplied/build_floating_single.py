"""Build the NO-RINGS NBA Single plate once from the immutable owner art.

The two preprinted team circles belong to the static 2026-11-22 screenshot.
Remove them in a *new, derived* PNG, never on a live Telegram image.
The owner crown, league shield, VS and original stadium remain untouched.
"""
from __future__ import annotations

from pathlib import Path
import hashlib

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE / "single_blank_20261122.png"
BASE = HERE / "single_blank_editable_20261122.png"
TARGET = HERE / "single_blank_floating_20261123.png"
SOURCE_SHA256 = "499ed837eb187b672c9a7781553eb9889c9fe37bb501aef3df61da1010019692"
# Only the two actual gold circles, not the VS, title, dates or name plates.
RINGS = ((145, 64, 240, 145), (273, 64, 371, 145))


def make_master(source=BASE, target=TARGET):
    if hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Owner's unmodified reference failed integrity check")
    with Image.open(source) as image:
        if image.size != (512, 512):
            raise ValueError("Unexpected owner Single plate dimensions")
        original = np.array(image.convert("RGB"))
    # A rectangular OpenCV inpaint of both giant neon circles propagated
    # their gold edges INTO the middle, creating pale angular triangles.
    # Reuse only genuine DARK interior stadium pixels from each owner's
    # original circle; expand those pixels behind the original gold rim
    # with a soft oval seam. This is a ONE-TIME clean master operation.
    # Runtime ONLY alpha-composites genuine transparent team logos.
    result=Image.fromarray(original).convert("RGB")
    allowed=np.zeros((512,512),dtype=np.uint8)
    for x0,y0,x1,y1 in RINGS:
        w,h=x1-x0,y1-y0
        cx=(x0+x1)//2
        cy=(y0+y1)//2
        # The central interior has no preprinted rim, text or old crest.
        donor=Image.fromarray(original).crop(
            (cx-17,cy-17,cx+17,cy+17)).resize(
                (w,h),Image.Resampling.BICUBIC)
        donor=donor.filter(ImageFilter.GaussianBlur(1.2))
        feather=Image.new("L",(w,h),0)
        d=ImageDraw.Draw(feather)
        d.ellipse((1,0,w-2,h-1),fill=255)
        feather=feather.filter(ImageFilter.GaussianBlur(2.6))
        result.paste(donor,(x0,y0),feather)
        allowed[y0:y1,x0:x1]=255
    cleaned=np.array(result)
    changed=np.any(cleaned!=original,axis=2)
    if np.any(changed & (allowed==0)):
        raise AssertionError("Original artwork changed outside the two crest slots")
    if not np.any(changed):
        raise AssertionError("Original static circles were not removed")
    result.save(target,"PNG",optimize=True)
    return {"removed_circle_pixels": int(changed.sum()),
            "brand_and_stadium_outside_circles_unchanged": True}


if __name__ == "__main__":
    print(make_master())
