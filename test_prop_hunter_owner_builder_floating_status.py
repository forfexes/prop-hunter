"""Owner Builder final-result banner must float in one line, no sticker.

Offline synthetic-only check. Actual template files are never modified.
"""
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw

import prop_hunter_owner_clean_builder as builder

ROOT=Path(__file__).resolve().parent
PLATE=ROOT/"card_templates"/"cleaned"/"builder.png"
assert PLATE.exists()
plate=Image.open(PLATE).convert("RGBA")
portrait=Image.new("RGBA",(150,210),(0,0,0,0))
ImageDraw.Draw(portrait).ellipse((15,10,120,195),fill=(65,130,205,255))
badge=Image.new("RGBA",(70,70),(0,0,0,0))
ImageDraw.Draw(badge).ellipse((4,4,65,65),fill=(235,189,39,255))
teams=[("Home Team",badge),("Away Team",badge)]
rows=[{
    "name":f"TEST ATHLETE {i}",
    "label":"Over 20.5 points",
    "odds":"@1.75",
    "photo":portrait,
    "form":"L5 4/5 L10 8/10 L15 12/15",
    "result":"",
} for i in (1,2,3)]

for state, tone in (("OFFEN",builder.WHITE),
                    ("GEWONNEN",builder.GREEN),
                    ("VERLOREN",builder.RED),
                    ("2 gewonnen · 1 verloren",builder.RED),
                    ("2 gewonnen · 0 verloren",builder.GREEN),
                    ("1 gewonnen · 1 offen",builder.WHITE)):
    texts=[]
    real=builder._text
    def track(draw,xy,value,*args,**kwargs):
        texts.append((str(value),xy,kwargs))
        return real(draw,xy,value,*args,**kwargs)
    with patch.object(builder,"_text",side_effect=track):
        result=builder.render(
            plate,subtitle="Home Team vs Away Team · So 22.11.2026 · 20:00",
            teams=teams,rows=rows,footer="Quote @3.45 · Einsatz 1u",
            settlement=state,
        )
    states=[(txt,xy,kwargs) for txt,xy,kwargs in texts
            if txt.startswith("AUSWERTUNG: ")]
    assert len(states)==1,(state,states)
    txt,xy,options=states[0]
    assert txt=="AUSWERTUNG: "+state
    assert xy==(350,786)
    assert options["color"]==tone
    # The status is not rendered as a second box over the gold bet ticket.
    assert all(t!="OFFEN" for t,_,_ in texts)
    with Image.open(BytesIO(result)) as image:
        assert image.format=="PNG" and image.size==(1080,round(1080*867/691))
        image.verify()
print("NBA_OWNER_BUILDER_FLOATING_ONE_LINE_SETTLEMENT_QA_PASSED")
