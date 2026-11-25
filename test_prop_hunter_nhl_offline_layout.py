import xml.etree.ElementTree as ET
import pytest
from prop_hunter_nhl_offline_layout import KINDS, render, previews

@pytest.mark.parametrize("kind", KINDS)
def test_layout(kind):
    rows=[dict(player="QA & <test>",market="Testmarkt",match="A / B") for _ in range(1 if kind=="single" else 6)]
    svg=render(kind,rows,price="3.40")
    root=ET.fromstring(svg)
    assert root.attrib["width"]=="900"
    assert root.attrib["height"]=="1350"
    assert "PROP HUNTER" in svg and "@prophunter" in svg
    assert "OFFLINE QA" in svg
    assert ("BERECHNET 3.40" in svg)==(kind in ("kombi","cross","lottery"))

def test_preview_files(tmp_path):
    previews(tmp_path)
    assert sorted(p.stem for p in tmp_path.glob("*.svg"))==sorted(KINDS)

def test_invalid_family_and_rows():
    with pytest.raises(ValueError): render("NBA",[])
    with pytest.raises(ValueError): render("cross",[])
    with pytest.raises(ValueError): render("single",[{},{}])


def test_transparent_png_slots_and_formula_label():
    from io import BytesIO
    from PIL import Image, ImageDraw
    def asset(transparent):
        img=Image.new("RGBA",(100,100),(0,0,0,0) if transparent else (0,0,0,255))
        ImageDraw.Draw(img).rectangle((25,25,75,75),fill=(255,0,0,255))
        out=BytesIO()
        img.save(out,format="PNG")
        return out.getvalue()
    raw=asset(True)
    svg=render("single",[{"match":"QA A / QA B","market":"Test"}],assets={"player":raw,"home":raw,"away":raw})
    root=ET.fromstring(svg)
    assert len(root.findall("{http://www.w3.org/2000/svg}image"))==3
    assert "FOTO-SLOT" not in svg
    with pytest.raises(ValueError):
        render("single",[{}],assets={"player":asset(False)})
    with pytest.raises(ValueError):
        render("single",[{}],assets={"player":b"invalid"})
    assert "KEINE BUCHMACHERQUOTE" in render("cross",[{},{}],price="3.40")


@pytest.mark.parametrize("kind", ("builder","kombi","cross","lottery"))
@pytest.mark.parametrize("count", (7,10,12))
def test_long_ticket_extends_clean_canvas_and_keeps_every_leg(kind,count):
    rows=[dict(player=f"QA PLAYER {i}",market="TESTMARKT",match="QA MATCH") for i in range(count)]
    root=ET.fromstring(render(kind,rows,price="3.40"))
    ns="{http://www.w3.org/2000/svg}"
    height=1350+(count-6)*100
    assert int(root.get("height"))==height
    texts={e.text:float(e.get("y")) for e in root.findall(ns+"text") if e.text}
    assert all(f"QA PLAYER {i}" in texts for i in range(count))
    assert texts["QA PLAYER "+str(count-1)] < texts["QUOTE / MODELL"]
    assert texts["AUSWERTUNG: OFFEN"] < height
    with pytest.raises(ValueError):
        render(kind,rows+[{}]*(13-count))
