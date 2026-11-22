"""No new Telegram messages. Per-leg outcomes appear in the original
Builder/Lottery row-number slots without painting over user artwork.
"""
from io import BytesIO
from unittest.mock import patch
from PIL import Image, ImageDraw

from prop_hunter_owner_leg_status import leg_result_mark
import prop_hunter_owner_clean_builder as builder
import prop_hunter_owner_clean_lottery as lottery
import prop_hunter_original_compositor as compositor

assert leg_result_mark(1, "GEWONNEN") == ("1✓", "won")
assert leg_result_mark(2, "Ist: 14 · VERLOREN") == ("2✕", "lost")
assert leg_result_mark(3, "VOID") == ("3–", "void")
assert leg_result_mark(4, "PUSH") == ("4–", "void")
assert leg_result_mark(5, "") == ("5.", "open")
assert leg_result_mark(6, None) == ("6.", "open")
assert leg_result_mark(7, "OFFEN") == ("7.", "open")
assert leg_result_mark(8, "unknown") == ("8.", "open")
for impossible in (0, 13, None, "abc"):
    try:
        leg_result_mark(impossible, "GEWONNEN")
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid leg index accepted")

logo = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
ImageDraw.Draw(logo).ellipse((5, 5, 75, 75), fill=(20, 180, 220, 255))
photo = Image.new("RGBA", (120, 160), (0, 0, 0, 0))
ImageDraw.Draw(photo).ellipse((14, 10, 105, 150), fill=(80, 120, 200, 255))
clubs = [("HOME TEST", logo), ("AWAY TEST", logo)]
status_rows = ["GEWONNEN", "Ist: 14 · VERLOREN", ""]
rows = [
    {"name": "ATHLETE", "label": f"Points Under {i+1}.5",
     "odds": f"@{1.8+i*.2:.2f}", "result": state,
     "form": "L5 4/5 L10 8/10 L15 12/15", "photo": photo,
     "game": "HOME TEST vs AWAY TEST · 22.11.2026 04:00"}
    for i, state in enumerate(status_rows)
]

records = []
real_builder_text = builder._text
real_lottery_text = lottery._text

def builder_spy(draw, position, caption, *args, **kwargs):
    records.append(str(caption))
    return real_builder_text(draw, position, caption, *args, **kwargs)

with patch.object(compositor, "_background_portrait", return_value=True), \
     patch.object(builder, "_text", side_effect=builder_spy):
    result = builder.render(
        Image.new("RGB", (691, 867), (2, 18, 34)),
        subtitle="HOME TEST vs AWAY TEST · So 22.11. · 04:00",
        teams=clubs, rows=rows, footer="Quote @6.00 · Einsatz 1u",
        settlement="VERLOREN")
with Image.open(BytesIO(result)) as checked:
    assert checked.width == 1080
assert "1✓" in records, records
assert "2✕" in records, records
assert "3." in records, records
assert "3✓" not in records and "3✕" not in records

records.clear()
def lottery_spy(draw, position, caption, *args, **kwargs):
    records.append(str(caption))
    return real_lottery_text(draw, position, caption, *args, **kwargs)

with patch.object(compositor, "_background_portrait", return_value=True), \
     patch.object(lottery, "_text", side_effect=lottery_spy):
    result = lottery.render(
        Image.new("RGB", (691, 753), (2, 18, 34)),
        rows=rows, footer="Quote @6.00 · Einsatz 1u",
        settlement="VERLOREN")
with Image.open(BytesIO(result)) as checked:
    assert checked.width == 1080
assert "1✓ ATHLETE" in records, records
assert "2✕ ATHLETE" in records, records
assert "3. ATHLETE" in records, records
print("OWNER_LEG_RESULTS_VISIBLE_IN_BUILDER_LOTTERY_3_FAMILIES_NO_FAKE_WIN_PASS")
