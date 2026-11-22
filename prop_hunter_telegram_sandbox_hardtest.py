"""Offline Telegram chat-preview HARDTEST for EVERY generated owner card.

This is a visual *simulation* of Telegram's compressed chat thumbnail with
bottom-right 'edited / time' overlay; it does not claim to reproduce Telegram's
Android renderer pixel-for-pixel and never uses any network/API/credentials.

The exact production owner PNGs are generated first by the existing bridge QA.
Every resulting original-card variant must preserve an empty bottom metadata
strip, readable full artwork, and positive approval provenance. Synthetic
QA picks remain off Telegram. Unapproved non-NBA sport images MUST stay blocked.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from prop_hunter_telegram_safe_zone import margin_height, split_owner_margin

ROOT=Path("output/nba_owner_qa")
DEST=Path("output/telegram_sandbox")
DEST.mkdir(parents=True,exist_ok=True)
if not ROOT.is_dir():
    raise SystemExit("FAIL: owner render QA did not create any PNG")

required={
    "single","ladder","builder","lottery",
    "same_player_owner_ladder","same_player_owner_ladder6",
    "ladder_2_name_fixed","ladder_3_name_fixed","ladder_4_name_fixed",
    "ladder_5_name_fixed","ladder_6_name_fixed",
    "combo_owner_lottery","cross_game_owner_lottery",
    "longshot_owner_single",
    "single_double_double_owner","single_points_rebounds_owner",
    "ladder_settlement_status_owner",
    "builder_settlement_status_owner","lottery_settlement_status_owner",
}
found={p.stem for p in ROOT.glob("*.png")}
missing=sorted(required-found)
if missing:
    raise SystemExit("FAIL missing owner family or variant PNGs: "+", ".join(missing))

fontpath="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
try:
    font=ImageFont.truetype(fontpath,11)
    title_font=ImageFont.truetype(fontpath,13)
except OSError:
    font=ImageFont.load_default()
    title_font=font

report={}
for file in sorted(ROOT.glob("*.png")):
    with Image.open(file) as incoming:
        original=incoming.convert("RGB")
    if original.width != 1080:
        raise AssertionError(f"{file.name}: not full 1080px owner source")
    # Find the original height from the new 7.5% / min-112px metadata area.
    # Max displayed gutter is intentionally small, but large enough for
    # Telegram's real 'bearbeitet' label in a 354px thumbnail.
    candidates=[
        h for h in range(max(400, original.height-300), original.height-95)
        if h+margin_height(h)==original.height
    ]
    valid=[]
    for h in candidates:
        try:
            body, has_strip=split_owner_margin(original,(h,))
            if has_strip:
                valid.append(h)
        except ValueError:
            pass
    if len(valid)!=1:
        raise AssertionError(
            f"{file.name}: Telegram safe strip missing, forged or ambiguous: {valid}"
        )
    body_h=valid[0]
    assert original.height-body_h <= max(160, round(body_h*.09)), (
        file.name, "excessive black strip under original owner card")
    frame_w=390
    margin=18
    photo_w=frame_w-2*margin
    scale=photo_w/original.width
    photo_h=round(original.height*scale)
    scaled_body=round(body_h*scale)
    # Simulate Android chat view: dark background, image, real chat metadata
    # overlay. Exact dimensions/colors vary by Telegram platform and device.
    canvas=Image.new("RGB",(frame_w,photo_h+135),(20,28,43))
    draw=ImageDraw.Draw(canvas)
    draw.rounded_rectangle((0,0,frame_w,68),radius=0,fill=(30,43,64))
    draw.text((18,24),"PROP HUNTER  ·  OFFLINE QA",font=title_font,fill=(244,248,253))
    photo=original.resize((photo_w,photo_h),Image.Resampling.LANCZOS)
    x,y=margin,80
    canvas.paste(photo,(x,y))
    draw=ImageDraw.Draw(canvas)
    # "bearbeitet" and local clock are drawn in the bottom metadata gutter.
    overlay_y=y+photo_h-24
    assert overlay_y >= y+scaled_body+8,(
        file.name,"Telegram metadata overlaps original owner artwork"
    )
    box=(x+photo_w-127,overlay_y-1,x+photo_w-7,overlay_y+17)
    draw.rounded_rectangle(box,radius=6,fill=(15,22,38))
    draw.text((box[0]+5,overlay_y+3),"bearbeitet 23:01",font=font,fill=(247,249,254))
    draw.text((18,y+photo_h+15),"SANDBOX · NICHT AN TELEGRAM GESENDET",
              font=font,fill=(210,208,153))
    name="telegram_chat_"+file.stem+".png"
    canvas.save(DEST/name,optimize=True)
    report[file.stem]={
        "status":"PASS",
        "source_png":str(file),
        "chat_preview":str(DEST/name),
        "full_width":original.width,
        "body_height":body_h,
        "reserved_metadata_pixels":original.height-body_h,
        "telegram_overlay_overlaps_original":False,
        "bookmaker_source":"TEST DATA ONLY",
    }

# Preserve the user's actual design review, independent of the green
# transport/geometry test. This must not be silently treated as owner signoff.
# In particular the dark rectangular VS source is baked into the supplied
# clean plate, and a successful PNG render does not resolve that objection.
known_visual_blockers={
    "single":[
        "VS_BLACK_PANEL_SOURCE_ART_STILL_VISUALLY_UNAPPROVED",
        "OFFEN_SETTLEMENT_INTEGRATION_REQUIRES_FINAL_VISUAL_ACCEPTANCE",
    ],
    "ladder":[
        "VS_BLACK_PANEL_SOURCE_ART_STILL_VISUALLY_UNAPPROVED",
    ],
}
for family,issues in known_visual_blockers.items():
    if family in report:
        report[family]["owner_visual_signoff"]="PENDING"
        report[family]["unresolved_design_issues"]=issues
        report[family]["production_visual_acceptance_claim"]=False
# Create a contact sheet from the EXACT mock Telegram screenshots so people
# can review all 19+ variants without opening one artifact at a time.
screens=sorted(DEST.glob("telegram_chat_*.png"))
tile_w,tile_h=215,520
columns=5
rows=(len(screens)+columns-1)//columns
sheet=Image.new("RGB",(tile_w*columns,tile_h*rows),(21,28,42))
annotation=ImageDraw.Draw(sheet)
for i,png in enumerate(screens):
    with Image.open(png) as original_preview:
        tile=original_preview.convert("RGB")
        tile.thumbnail((tile_w-12,tile_h-32),Image.Resampling.LANCZOS)
    px=(i%columns)*tile_w+6
    py=(i//columns)*tile_h+25
    sheet.paste(tile,(px,py))
    annotation.text((px,py-20),png.stem.replace("telegram_chat_","")[:28],
                    font=font,fill=(248,250,255))
sheet.save(DEST/"contact_sheet.png",optimize=True)
print("TELEGRAM_SCREENSHOT_CONTACT_SHEET",len(screens),"cards; original VS acceptance pending")

# Unapproved sports are not quietly treated as eligible just because a
# technical SVG fallback exists. This is release readiness, not a test failure.
for sport in ("NFL","NHL","MLB","WNBA","EUROLEAGUE"):
    report["unapproved_"+sport]={
        "status":"BLOCKED_NO_OWNER_ART",
        "telegram_post_allowed":False,
    }
(DEST/"manifest.json").write_text(
    json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"
)
assert len([v for v in report.values() if v["status"]=="PASS"])>=len(required)
assert report["single"]["owner_visual_signoff"]=="PENDING"
assert not report["single"]["production_visual_acceptance_claim"]
print("OWNER_DESIGN_REVIEW_PENDING_SINGLE_VS_AND_SETTLEMENT_NOT_FALSELY_APPROVED")
print("TELEGRAM_OFFLINE_CHAT_HARDTEST_PASS",len(required),
      "owner variants; no Telegram token, no SMS, no API")
print("UNAPPROVED_SPORTS_BLOCKED",5)
