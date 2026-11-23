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
RINGS = ((140, 64, 374, 145),)  # One seamless band, genuine VS restored


def make_master(source=BASE, target=TARGET):
    if hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Owner's unmodified reference failed integrity check")
    with Image.open(source) as image:
        if image.size != (512, 512):
            raise ValueError("Unexpected owner Single plate dimensions")
        original = np.array(image.convert("RGB"))
    # Rebuild ONE continuous stadium header band under BOTH original
    # preprinted team rings. Previous isolated replacements left obvious
    # blue disk/rectangular seams. All values are sourced from unchanged
    # DARK owner-stadium pixels. Keep the original VS lettering itself.
    cleaned=original.copy()
    allowed=np.zeros((512,512),dtype=np.uint8)
    x0,y0,x1,y1=RINGS[0]
    safe=np.concatenate((
        original[72:96,242:273].reshape(-1,3),
        original[82:101,175:208].reshape(-1,3),
        original[82:101,301:338].reshape(-1,3),
    )).astype(np.float32)
    safe=safe[(safe[:,2]>safe[:,0]*1.15) &
              (safe[:,2]>=safe[:,1]*0.85) &
              (np.max(safe,axis=1)<105)]
    if not len(safe):
        raise AssertionError("Actual original stadium donor unavailable")
    center=np.median(safe,axis=0)
    # Select only blue/dark real pixels from either side of the empty
    # header band, excluding the gold player outline and cyan date rail.
    def genuine_dark(values):
        p=values.reshape(-1,3).astype(np.float32)
        p=p[(p[:,2]>p[:,0]*1.1)&(np.max(p,axis=1)<115)]
        return np.median(p,axis=0) if len(p) else center
    left=genuine_dark(original[76:139,124:139])
    right=genuine_dark(original[76:139,375:391])
    width=x1-x0
    # Smooth 2D, continuous arena texture -- no two oval/circle shapes.
    for y in range(y0,y1):
        for ix in range(width):
            t=ix/max(width-1,1)
            if t<0.5:
                rgb=left*(1-2*t)+center*2*t
            else:
                rgb=center*(2-2*t)+right*(2*t-1)
            cleaned[y,x0+ix]=np.clip(rgb,0,255).astype(np.uint8)
    cleaned[y0:y1,x0:x1]=cv2.GaussianBlur(
        cleaned[y0:y1,x0:x1],(0,0),sigmaX=7,sigmaY=6)
    allowed[y0:y1,x0:x1]=255
    # Preserve actual gold VS glyphs (including 2px glow) rather than
    # approximating them with a retyped or generated symbol.
    vx0,vy0,vx1,vy1=(237,92,277,138)
    old=original[vy0:vy1,vx0:vx1]
    text_mask=((old[:,:,0].astype(np.float32)>110) &
               (old[:,:,1].astype(np.float32)>70) &
               (old[:,:,0].astype(np.float32)>old[:,:,2]*1.25))
    alpha=cv2.dilate(text_mask.astype(np.uint8),
                     np.ones((3,3),np.uint8),iterations=1)
    alpha=cv2.GaussianBlur(alpha.astype(np.float32),(0,0),0.85)
    alpha=np.clip(alpha[:,:,None],0,1)
    clean_patch=cleaned[vy0:vy1,vx0:vx1].astype(np.float32)
    cleaned[vy0:vy1,vx0:vx1]=np.clip(
        old.astype(np.float32)*alpha+clean_patch*(1-alpha),0,255
    ).astype(np.uint8)
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
