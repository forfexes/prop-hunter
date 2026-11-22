"""Original PROP HUNTER per-rung Telegram settlement visual QA.

A settled Ladder retains each rung's independently verified win/loss/actual
reading inside the ORIGINAL image, rather than only displaying a headline.
Synthetic input only; never contacts Telegram or bookmakers.
"""
from io import BytesIO
from types import SimpleNamespace as Pick
from unittest.mock import patch

from PIL import Image, ImageDraw

import prop_hunter_nba_owner_bridge as bridge
import prop_hunter_owner_clean_ladder as ladder
from prop_hunter_telegram_safe_zone import split_owner_margin

portrait = Image.new("RGBA", (180, 220), (0, 0, 0, 0))
ImageDraw.Draw(portrait).ellipse((12, 12, 165, 208), fill=(70, 130, 205, 255))
club_logo = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
ImageDraw.Draw(club_logo).ellipse((6, 6, 74, 74), fill=(255, 205, 45, 255))

teams = [
    ("Boston Celtics", club_logo),
    ("Sacramento Kings", club_logo),
]
rows = [
    {"name": "SAME VERIFIED ATHLETE", "photo": portrait,
     "label": "Blocks Under 2.5", "form": "L5 4/5 L10 7/10 L15 13/15",
     "result": "GEWONNEN", "model": {}},
    {"name": "SAME VERIFIED ATHLETE", "photo": portrait,
     "label": "Blocks Under 1.5", "form": "L15 11/15",
     "result": "VERLOREN", "model": {}},
    {"name": "SAME VERIFIED ATHLETE", "photo": portrait,
     "label": "Blocks Under 0.5", "form": "L15 10/15",
     "result": "Ist: 1 · VERLOREN", "model": {}},
]
pick = Pick(
    type="ladder", source_sport="NBA", sport="NBA", stake=1.0,
    odds=1.8, features={"bookmaker": "QA ONLY"}, leg_details=[
        {"sport": "NBA", "odds": 1.80},
        {"sport": "NBA", "odds": 2.10},
        {"sport": "NBA", "odds": 3.10},
    ],
)
values = {
    "date": "22.11.2026", "time": "04:00", "stake": "1u",
    "leg_1_odds": "@1.80", "leg_2_odds": "@2.10",
    "leg_3_odds": "@3.10", "settlement": "VERLOREN",
}

seen = []
real_text = ladder._text


def capture_text(draw, xy, caption, *args, **kwargs):
    seen.append(str(caption))
    return real_text(draw, xy, caption, *args, **kwargs)


with patch.dict("os.environ", {"PH_NBA_OWNER_ORIGINALS": "1"}), \
     patch.object(ladder, "_text", side_effect=capture_text):
    rendered = bridge.render_owner(pick, "ladder_3", rows, teams, values, pick.leg_details)
# Archive this real compositor output for visual review, never Telegram.
from pathlib import Path
preview_dir=Path("output/nba_owner_qa")
preview_dir.mkdir(parents=True,exist_ok=True)
preview_dir.joinpath("ladder_settlement_status_owner.png").write_bytes(rendered)
with Image.open(BytesIO(rendered)) as photo:
    assert photo.width == 1080 and photo.height > 1300
    body, blank = split_owner_margin(photo, (round(1080 * 865 / 691),))
    assert blank and body.height == round(1080 * 865 / 691)

for state in ("GEWONNEN", "VERLOREN", "Ist: 1 · VERLOREN"):
    assert state in seen, (state, seen)
assert "L5 4/5 · L10 7/10 · L15 13/15" in seen
assert sum(x == "SAME VERIFIED ATHLETE" for x in seen) >= 2

# Missing evidence stays blank: never guess the result from its odds or form.
rows_unknown = [{**r, "result": ""} for r in rows]
seen.clear()
with patch.dict("os.environ", {"PH_NBA_OWNER_ORIGINALS": "1"}), \
     patch.object(ladder, "_text", side_effect=capture_text):
    bridge.render_owner(pick, "ladder_3", rows_unknown, teams, values, pick.leg_details)
assert "GEWONNEN" not in seen and "VERLOREN" in seen  # Only ticket status
assert "Ist: 1 · VERLOREN" not in seen
print("OWNER_NBA_LADDER_PER_RUNG_SETTLEMENT_IN_ORIGINAL_IMAGE_PASS")
