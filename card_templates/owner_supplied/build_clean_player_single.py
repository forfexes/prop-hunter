"""Create a blank NBA Single master: NO baked player, gold silhouette, or fake outline.

The untouched owner source and floating-team master stay immutable. This
offline build removes ONLY the obsolete player silhouette in one bounded area.
No betting, image APIs, Telegram or network access.
"""
from pathlib import Path
import hashlib
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE / "single_blank_20261122.png"
SOURCE = HERE / "single_blank_floating_20261123.png"
TARGET = HERE / "single_blank_no_silhouette_20261123.png"
SOURCE_SHA256 = "499ed837eb187b672c9a7781553eb9889c9fe37bb501aef3df61da1010019692"
EXPECTED_PIXEL_SHA256 = "da3d86b160113cdc3cc593202ff3c570f763d52fb5372389781ac62c1b73b50c"
REGION = (0, 51, 160, 327)


def mask_for_player():
    m = Image.new("L", (512, 512), 0)
    d = ImageDraw.Draw(m)
    d.polygon([(38, 53), (120, 53), (151, 78), (158, 129),
               (158, 163), (140, 174), (122, 196), (130, 222),
               (134, 242), (118, 264), (105, 265), (104, 306),
               (85, 326), (-1, 326), (-1, 221), (7, 195),
               (19, 146), (20, 110)], fill=255)
    # Do not erase the true source's name / market / quote rails.
    d.rectangle((132, 183, 511, 233), fill=0)
    d.rectangle((146, 229, 511, 270), fill=0)
    d.rectangle((102, 269, 511, 312), fill=0)
    # Never touch the NBA shield, PROP HUNTER title or stadium masthead.
    d.rectangle((0, 0, 511, 52), fill=0)
    return m


def make_master(source=SOURCE, target=TARGET):
    if hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Owner NBA Single source modified")
    with Image.open(source) as raw:
        original = raw.convert("RGB")
    if original.size != (512, 512):
        raise ValueError("Unexpected original master dimensions")
    permitted = mask_for_player()
    allowed = np.asarray(permitted, dtype=np.uint8)
    ys, xs = np.mgrid[0:512, 0:512].astype(np.float32)
    progress = np.clip((ys-65)/260, 0, 1)
    stadium = np.empty((512, 512, 3), dtype=np.float32)
    stadium[:, :, 0] = 5 + 5*progress
    stadium[:, :, 1] = 16 + 12*progress
    stadium[:, :, 2] = 29 + 18*progress
    glow = 11*np.exp(-((xs-4-.35*(ys-130))/58)**2)*np.exp(-((ys-205)/130)**2)
    stadium[:, :, 0] += glow*.28
    stadium[:, :, 1] += glow*.67
    stadium[:, :, 2] += glow
    grain=(np.sin(xs*.63+ys*.31)+np.sin(xs*.22-ys*.54))*.8
    stadium[:, :, 2] += np.clip(grain, 0, 3)
    background = Image.fromarray(np.uint8(np.clip(stadium, 0, 255)))
    alpha = ImageChops.multiply(
        permitted.filter(ImageFilter.GaussianBlur(3.5)), permitted)
    result = Image.composite(background, original, alpha)
    delta = np.any(np.asarray(original) != np.asarray(result), axis=2)
    if not np.any(delta) or np.any(delta & (allowed==0)):
        raise ValueError("Original artwork was altered outside old player")
    def gold_pixels(img):
        rgb=np.asarray(img)[65:162,22:135]
        return int(np.count_nonzero((rgb[:,:,0]>130) &
                   (rgb[:,:,1]>75) & (rgb[:,:,0]>1.3*rgb[:,:,2])))
    old,new=gold_pixels(original),gold_pixels(result)
    if old<400 or new>old//12:
        raise ValueError("Baked gold player silhouette was not removed")
    pixel_sha=hashlib.sha256(result.tobytes()).hexdigest()
    if pixel_sha != EXPECTED_PIXEL_SHA256:
        raise ValueError("Derived owner pixels differ from tested empty master")
    target=Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    result.save(target,"PNG",optimize=True)
    return {"removed_gold_pixels":old-new,
            "original_outside_portrait_unchanged":True,
            "pixel_sha256":pixel_sha}


if __name__=="__main__":
    print(make_master())
