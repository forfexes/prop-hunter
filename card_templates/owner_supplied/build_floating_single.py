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
from PIL import Image

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE / "single_blank_20261122.png"
BASE = HERE / "single_blank_editable_20261122.png"
TARGET = HERE / "single_blank_floating_20261123.png"
SOURCE_SHA256 = "499ed837eb187b672c9a7781553eb9889c9fe37bb501aef3df61da1010019692"
# Only the two actual gold circles, not the VS, title, dates or name plates.
RINGS = ((150, 64, 234, 145), (280, 64, 365, 145))


def make_master(source=BASE, target=TARGET):
    if hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Owner's unmodified reference failed integrity check")
    with Image.open(source) as image:
        if image.size != (512, 512):
            raise ValueError("Unexpected owner Single plate dimensions")
        original = np.array(image.convert("RGB"))
    mask = np.zeros((512, 512), dtype=np.uint8)
    for x0, y0, x1, y1 in RINGS:
        mask[y0:y1, x0:x1] = 255
    # Reconstruct stadium pixels instead of drawing opaque navy rectangles;
    # the genuine team emblems are inserted later with alpha only.
    cleaned = cv2.inpaint(original, mask, 5, cv2.INPAINT_TELEA)
    changed = np.any(cleaned != original, axis=2)
    if np.any(changed & (mask == 0)):
        raise AssertionError("Changing unrelated original artwork is forbidden")
    if not np.any(changed):
        raise AssertionError("Original static circles were not removed")
    Image.fromarray(cleaned).save(target, "PNG", optimize=True)
    return {"removed_circle_pixels": int(changed.sum()),
            "brand_and_stadium_outside_circles_unchanged": True}


if __name__ == "__main__":
    print(make_master())
