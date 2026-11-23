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
    # The original circles have no usable background outside their neon
    # rims. Neither rectangle inpainting (bright triangles) nor stretching
    # the old *circle interior* (blue disks) is a clean floating-logo plate.
    # Reconstruct the dark arena behind each ring from genuine neighbouring
    # dark stadium pixels. Every horizontal line smoothly interpolates the
    # left and right undisturbed source bands; no disk, polygon, sticker,
    # invented team artwork or dynamic screenshot overpaint is introduced.
    cleaned=original.copy()
    allowed=np.zeros((512,512),dtype=np.uint8)
    safe=original[70:99,244:272].reshape(-1,3).astype(np.float32)
    safe=safe[np.max(safe,axis=1)<105]
    if not len(safe):
        raise AssertionError("Owner source lacks a dark unchanged stadium donor")
    dark_stadium=np.median(safe,axis=0)
    for x0,y0,x1,y1 in RINGS:
        for y in range(y0,y1):
            left=original[y,max(0,x0-19):x0-4].astype(np.float32)
            right=original[y,x1+4:min(512,x1+19)].astype(np.float32)
            # Reject gold outlines/text, only use natural dark stadium.
            left=left[np.max(left,axis=1)<105]
            right=right[np.max(right,axis=1)<105]
            # Fixture labels/VS sometimes occupy a whole border row.
            # In that case borrow the genuinely dark upper-center ARENA
            # pixels from the same uploaded original, never the bright rim.
            a=np.median(left,axis=0) if len(left) else dark_stadium
            b=np.median(right,axis=0) if len(right) else dark_stadium
            blend=np.linspace(0,1,x1-x0,dtype=np.float32)[:,None]
            cleaned[y,x0:x1]=np.clip(a[None,:]*(1-blend)+b[None,:]*blend,
                                     0,255).astype(np.uint8)
        # Smooth within the original source slots, never in the surrounding
        # crown, VS label, name rails or NBA shield.
        restored=cleaned[y0:y1,x0:x1].copy()
        cleaned[y0:y1,x0:x1]=cv2.GaussianBlur(restored,(0,0),1.6)
        allowed[y0:y1,x0:x1]=255
    changed=np.any(cleaned!=original,axis=2)
    if np.any(changed & (allowed==0)):
        raise AssertionError("Original artwork changed outside the two crest slots")
    if not np.any(changed):
        raise AssertionError("Original static circles were not removed")
    Image.fromarray(cleaned).save(target,"PNG",optimize=True)
    return {"removed_circle_pixels": int(changed.sum()),
            "brand_and_stadium_outside_circles_unchanged": True}


if __name__ == "__main__":
    print(make_master())
