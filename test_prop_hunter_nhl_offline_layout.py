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
