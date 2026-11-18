"""Offline PNG regression for all four premium poster families."""
from io import BytesIO
from PIL import Image
from prop_hunter_image_cards import render

def test_family(kind, count):
    rows = [{"name": "Test Player " + str(i), "label": "Over 20.5 Points",
             "photo": None, "form": "L10 8/10   L15 12/15", "odds": "@1.90"}
            for i in range(count)]
    data = render(kind, kind.upper(), "Verified sample only", "basketball",
                  [("Home", None), ("Away", None)], rows, "Quote @1.90", "")
    assert data[:8] == bytes([137,80,78,71,13,10,26,10])
    image = Image.open(BytesIO(data))
    assert image.width == 1080 and image.height >= 800
    image.verify()

for family, count in [("single",1),("ladder",3),("builder",3),("lottery",3)]:
    test_family(family,count)
print("FOUR POSTER FAMILIES PNG RENDER PASS")
