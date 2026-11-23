"""Offline build of the owner-supplied NBA Single WITHOUT a baked ghost athlete.

This is an actual versioned blank master, not runtime masking of a published
screenshot. Keep every original team, price, quote, masthead and result slot.
The old silhouette-only polygon restoration caused a person-shaped dark hole:
use a continuous, softly blended DARK ARENA field instead.
"""
from pathlib import Path
import hashlib
import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE / "single_blank_20261122.png"
SOURCE = HERE / "single_blank_floating_20261123.png"
TARGET = HERE / "single_blank_no_silhouette_20261123.png"
SOURCE_SHA256 = "499ed837eb187b672c9a7781553eb9889c9fe37bb501aef3df61da1010019692"
EXPECTED_PIXEL_SHA256 = "f625b53b43ccfc3ddee80a568397d278724118624539417dab753ecfe516cd09"
REGION = (0, 51, 160, 327)
IMMUTABLE = ((139,143,512,235),(144,223,512,264),(103,263,512,318),
             (0,319,512,512),(37,0,56,73))


def _stadium_reconstruction(image):
    """Build a continuous uninhabited arena across the entire left photo area.

    The old mask followed the OLD person's hair and shoulders, leaving a
    clearly player-shaped dark negative silhouette after removal. The new
    alpha field is independent of that former person's shape.
    """
    original = np.asarray(image.convert("RGB")).astype(np.float32)
    ys, xs = np.mgrid[:512, :512].astype(np.float32)
    stops = np.array([50,53,65,90,140,167,200,255,290,317,325,340,512])
    left = np.zeros_like(stops)
    right = np.array([140,152,165,168,168,160,152,143,125,100,60,0,0])
    low = np.interp(ys[:,0], stops, left)
    high = np.interp(ys[:,0], stops, right)
    mask = np.zeros((512,512), np.float32)
    for y in range(512):
        if high[y] <= low[y]:
            continue
        # The broad mask follows the ARENA panel, never the old athlete.
        mask[y] = np.clip((high[y]-xs[y])/14, 0, 1)
    mask *= np.clip((ys-49)/11, 0, 1)*np.clip((332-ys)/24, 0, 1)
    mask[0:73, 37:56] = 0
    for x0,y0,x1,y1 in IMMUTABLE:
        mask[y0:y1,x0:x1] = 0

    progress = np.clip((ys-70)/240, 0, 1)
    background = np.zeros((512,512,3), np.float32)
    for channel,(start,stop) in enumerate(((4,7),(12,24),(28,48))):
        background[:,:,channel] = start+(stop-start)*progress
    # Original owner stadium navy/blue palette, without a gold human halo.
    reflection = np.exp(-((xs+23)/77)**2-((ys-150)/106)**2)
    background += reflection[:,:,None]*np.array([6,15,31])[None,None,:]
    texture = np.sin(ys*0.26+xs*.17)*.6+np.sin(xs*.11-ys*.36)*.5
    background[:,:,2] += texture

    alpha = cv2.GaussianBlur(mask, (0,0), 1.4)
    alpha[:51,:] = 0
    alpha[:,160:] = 0
    for x0,y0,x1,y1 in IMMUTABLE:
        alpha[y0:y1,x0:x1] = 0
    return Image.fromarray(
        np.clip(original*(1-alpha[:,:,None])+background*alpha[:,:,None],
                0,255).astype("uint8"))


def make_master(source=SOURCE, target=TARGET):
    if hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Owner NBA Single immutable original modified")
    with Image.open(source) as photo:
        before = photo.convert("RGB")
    if before.size != (512,512):
        raise ValueError("Owner original geometry changed")
    result = _stadium_reconstruction(before)
    original = np.asarray(before)
    finished = np.asarray(result)
    changed = np.any(original!=finished, axis=2)
    if not changed.any():
        raise ValueError("Baked portrait was not removed")
    x0,y0,x1,y1 = REGION
    permitted = np.zeros((512,512),np.uint8)
    permitted[y0:y1,x0:x1] = 1
    for a,b,c,d in IMMUTABLE:
        permitted[b:d,a:c] = 0
    if np.any(changed & (permitted==0)):
        raise ValueError("Original typography, header or odds changed")
    def count_halo(rgb):
        p = np.asarray(rgb)[65:162,22:135]
        return int(np.count_nonzero(
            (p[:,:,0]>130)&(p[:,:,1]>75)&(p[:,:,0]>1.3*p[:,:,2])))
    old,new=count_halo(before),count_halo(result)
    if old<400 or new>old//12:
        raise ValueError(f"Second gold silhouette remains: {old}->{new}")
    sha=hashlib.sha256(result.tobytes()).hexdigest()
    if sha!=EXPECTED_PIXEL_SHA256:
        raise ValueError("Owner master pixel audit does not match approved QA")
    target=Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    result.save(target,"PNG",optimize=True)
    return {"old_gold_pixels":old, "new_gold_pixels":new,
            "source_art_outside_player_unchanged":True,"pixel_sha256":sha}


if __name__=="__main__":
    print(make_master())
