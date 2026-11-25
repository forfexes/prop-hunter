"""Offline NHL portrait layout prototype; deliberately not a production sender."""
from html import escape
from base64 import b64encode
from io import BytesIO
from PIL import Image, ImageFont
from pathlib import Path

KINDS = ("single", "ladder", "builder", "kombi", "cross", "lottery")
CREAM, WINE, INK = "#f0dfc4", "#641525", "#171411"

def render(kind, rows=(), player="", price="", l10="", l15="", model="", result="OFFEN", assets=None):
    if kind not in KINDS:
        raise ValueError("Unknown NHL card family")
    rows = list(rows)
    if kind == "single" and len(rows) != 1 or kind != "single" and not 2 <= len(rows) <= 6:
        raise ValueError("Unsupported row count")
    if kind in ("kombi","cross","lottery") and price:
        price = "BERECHNET " + str(price)
    assets = assets or {}
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="900" height="1350" viewBox="0 0 900 1350">']
    def rect(x,y,w,h,c):
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{c}"/>')
    def txt(x,y,s,size=30,c=INK,weight=700,limit=36):
        s=str(s or "")
        # Measure actual font width, not only character counts.
        max_width = min(900-x-28, limit*size*0.58)
        while size > 12:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", size)
            if font.getlength(s) <= max_width: break
            size -= 1
        parts.append(f'<text x="{x}" y="{y}" font-family="DejaVu Sans, sans-serif" font-weight="{weight}" font-size="{size}" fill="{c}">{escape(s)}</text>')
    def photo(slot,x,y,w,h):
        raw=assets.get(slot)
        if raw is None: return False
        try:
            with Image.open(BytesIO(raw)) as im:
                if im.format!="PNG" or min(im.size)<64 or max(im.size)>4096:
                    raise ValueError("Invalid image dimensions or format")
                rgba=im.convert("RGBA")
                lo,hi=rgba.getchannel("A").getextrema()
                if lo!=0 or hi==0: raise ValueError("Transparent authentic asset required")
                out=BytesIO()
                rgba.save(out,format="PNG")
        except (OSError,TypeError) as exc:
            raise ValueError("Invalid asset") from exc
        encoded=b64encode(out.getvalue()).decode("ascii")
        parts.append(f'<image x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid meet" xlink:href="data:image/png;base64,{encoded}"/>')
        return True
    rect(0,0,900,1350,CREAM)
    parts.append(f'<path d="M520 0H900V825H466Z" fill="{WINE}"/>')
    txt(36,72,"PROP HUNTER",48)
    txt(38,121,"NHL / "+kind.upper(),31,WINE)
    txt(38,164,"OFFLINE QA – KEIN WETTTIPP",20,WINE)
    if kind=="single":
        txt(38,310,player or "SPIELER",69,limit=13)
        if not photo("player",490,180,410,465):
            txt(540,390,"FOTO-SLOT",26,CREAM)
        photo("home",38,500,90,90)
        photo("away",166,500,90,90)
        txt(38,660,rows[0].get("match","SPIEL"),30,limit=25)
        txt(38,708,rows[0].get("market","MARKT"),32,WINE,limit=24)
    else:
        rect(0,200,900,625,CREAM)
        for i,row in enumerate(rows):
            y=240+i*94
            rect(36,y+55,828,1,WINE)
            txt(38,y+1,row.get("player","SPIELER"),26,limit=39)
            txt(38,y+36,row.get("market","MARKT"),23,WINE,limit=34)
            txt(540,y+36,row.get("match","SPIEL"),19,limit=24)
    rect(0,825,900,173,WINE)
    txt(38,872,"QUOTE / MODELL",24,CREAM)
    txt(38,952,price or "—",54,CREAM,limit=24)
    if kind in ("kombi","cross","lottery") and price:
        txt(540,982,"KEINE BUCHMACHERQUOTE",20,CREAM)
    txt(38,1055,"L10  "+str(l10 or "—"),29)
    txt(326,1055,"L15  "+str(l15 or "—"),29)
    txt(614,1055,"P  "+str(model or "—"),29)
    rect(0,1150,900,200,INK)
    txt(38,1211,"AUSWERTUNG: "+str(result),30,CREAM)
    txt(38,1293,"@prophunter",27,CREAM)
    txt(560,1293,"ENTWURF / OFFLINE",22,CREAM)
    parts.append("</svg>")
    return "".join(parts)

def previews(output):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    for kind in KINDS:
        rows=[dict(player="QA Spieler "+str(i+1),market="Testmarkt",match="QA A / QA B")
              for i in range(1 if kind=="single" else 3)]
        (output/(kind+".svg")).write_text(render(kind,rows,player="QA SPIELER"),encoding="utf-8")

if __name__=="__main__":
    previews("output/nhl_offline")
