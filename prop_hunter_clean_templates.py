#!/usr/bin/env python3
"""Create CLEAN source plates, once, from the owner's four ORIGINAL JPGs.

The originals are NEVER overwritten.  This script removes baked-in sample
athletes, team crests, names, odds, figures and dates using a clean arena-photo donor and feathered masks BEFORE any new pick is rendered.  Runtime mask boxes cannot
replace source cleanup.  All masks are source-coordinate masks (691-px crop).
"""
from __future__ import annotations
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from prop_hunter_original_compositor import CROP, FAMILIES

ROOT = Path(__file__).resolve().parent / "card_templates"
ORIG = ROOT / "originals"
DEST = ROOT / "cleaned"
DIAG = Path(__file__).resolve().parent / "diagnostics"

# Rectangles are pixel masks for example content in each 691px-wide crop.
# Masks remove the sample entirely; the saved clean plate does not contain
# an opaque dark patch drawn on top of somebody else's name or photograph.
# Permanent PROP-HUNTER logos, league badge, decorative card frame and
# gold/purple format header are OUTSIDE masks.
RECTS = {
 "single": [
    (4,139,237,458), (56,69,206,140),    # Curry cut-out incl. hair
    (239,141,352,273),(397,141,520,273),# team crests and labels
    (519,138,688,277),                    # example event info
    (240,278,559,374),                    # sample player name / market
    (158,380,620,446),                    # sample prop and price
    (519,278,689,456),                    # Warriors bridge watermark
    (90,465,245,500),(31,505,247,602),  # form example values
    (269,500,511,601), (529,518,670,600), # model / stake numbers
    (348,663,473,704),                    # example open settlement
 ],
 "ladder": [
    (15,151,252,279),(325,151,482,279), # teams
    (492,149,688,285),                    # event info
    (2,272,246,617), (52,272,171,340),  # three example athletes
    (166,284,679,356),                    # sample 3-leg heading
    (198,352,688,620),                    # example rungs
    (30,621,317,744),(316,615,672,746), # model/legs summary
    (365,766,497,820),                    # settlement number
 ],
 "builder": [
    (4,139,690,409),                      # three sample athletes/text
    (65,99,165,140),(279,108,412,142),(527,97,628,141), # hair
    (109,411,316,480),(379,411,612,481), # teams
    (161,482,544,516),                    # date/time
    (69,518,665,586),                     # 3-leg & odds heading
    (28,588,663,716),                     # old legs + logos
    (39,733,674,782),                     # model/settlement numbers
 ],
 "lottery": [
    (4,65,200,331), (63,43,200,70),      # sample Brunson portrait
    (201,149,320,275),(386,148,494,274),# example teams
    (509,110,691,262),                    # event info
    (88,279,685,339),                     # 3-leg headline / price
    (39,333,654,533),                     # three sample athlete rows
    (36,534,379,643),(392,535,661,645), # details and stake
    (340,651,512,704),                    # settled text
 ],
}

def build(family: str):
    path=ORIG/(family+".jpg")
    image=Image.open(path).convert("RGB")
    if image.size!=(691,1536):
        raise ValueError(f"Unexpected owner JPG dimensions {family}: {image.size}")
    source=np.asarray(image.crop(CROP[family])).copy()
    mask=np.zeros(source.shape[:2],np.uint8)
    for x0,y0,x1,y1 in RECTS[family]:
        x0=max(0,x0); y0=max(0,y0)
        x1=min(source.shape[1],x1); y1=min(source.shape[0],y1)
        if x1>x0 and y1>y0:
            cv2.rectangle(mask,(x0,y0),(x1,y1),255,-1)
    # 2px safety expansion catches anti-aliased glyph fringes.
    mask=cv2.dilate(mask,np.ones((5,5),np.uint8),iterations=1)
    if family == "single":
        # The owner's original vertical NBA badge overlaps the Curry hair
        # cleanup at the left margin. Preserve the COMPLETE authentic badge,
        # including the small white NBA lettering, without redrawing a logo.
        mask[14:126,36:79]=0
    # Large erased player regions must NEVER be filled by OpenCV Telea:
    # on a nearly empty interior it produces giant polygonal color smears.
    # Use the separate player-free, verified basketball arena artwork as a
    # clean photographic donor. Preserve ALL outside-mask original pixels,
    # feathering inwards from the cut edge to avoid a rectangular seam.
    arena_path=ROOT/"nba_premium_v2"/"assets"/"arena.jpg"
    if not arena_path.is_file():
        raise FileNotFoundError("Clean NBA arena donor missing")
    with Image.open(arena_path) as arena:
        donor=np.asarray(arena.convert("RGB").resize(
            (source.shape[1],source.shape[0]),Image.Resampling.LANCZOS))
    depth=cv2.distanceTransform(mask,cv2.DIST_L2,5)
    alpha=np.clip(depth/11.0,0.0,1.0)[...,None]
    clean=np.clip(source.astype("float32")*(1-alpha)+
                  donor.astype("float32")*alpha,0,255).astype("uint8")
    clean[mask==0]=source[mask==0]
    if clean.shape!=source.shape: raise AssertionError("Image shape mismatch")
    if not np.array_equal(clean[mask==0],source[mask==0]):
        raise AssertionError("The permanent source artwork was modified")
    return Image.fromarray(clean,"RGB"), Image.fromarray(mask,"L")

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    DIAG.mkdir(parents=True,exist_ok=True)
    report={}
    for family in FAMILIES:
        im,mask=build(family)
        out=DEST/(family+".png")
        im.save(out,optimize=True)
        mask.save(DIAG/("template_cleanup_mask_"+family+".png"))
        report[family]={"size":list(im.size),"file":str(out),
                        "mask_fraction":round(np.asarray(mask).mean()/255,4)}
    (DIAG/"template_cleanup_report.json").write_text(
        json.dumps(report,indent=2)+"\n",encoding="utf8")
    print("ORIGINAL_TEMPLATE_CLEANUP "+json.dumps(report),flush=True)

if __name__=="__main__":
    main()
