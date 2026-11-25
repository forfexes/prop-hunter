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
