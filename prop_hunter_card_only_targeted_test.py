"""Offline fixture for targeted repaint of the ORIGINAL Telegram message IDs."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import prop_hunter_card_only_migrate as migrate

today = datetime.now(timezone.utc).date().isoformat()
yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

def card(mid, version=6):
    return {"message_id": mid, "media_type": "photo",
            "card_design_version": version, "chat_id": "test-chat",
            "image_pick": {"type": "single", "player": f"Player {mid}",
                           "market": "points", "game": "Away @ Home"}}

history = [
    {"date": today, "picks": [], "kombis": [], "cards": [
        card(7001, 6), card(7002, 7), card(7003, 4),
    ]},
    {"date": yesterday, "picks": [], "kombis": [], "cards": [card(7004, 4)]},
]
edits = []
def edit(message_id, text, chat_id=None, image_pick=None):
    edits.append(message_id)
    return True

with patch.object(migrate, "TARGET_DATE", today), \
     patch.object(migrate, "VERSION", 7), \
     patch.object(migrate, "MAX_UPDATES", 100), \
     patch.object(migrate, "_load_history", return_value=history), \
     patch.object(migrate, "_save_history"), \
     patch.object(migrate, "_card_visual_text", return_value="Original pending tip"), \
     patch.object(migrate, "_card_pick", side_effect=lambda c, p, co: c["image_pick"]), \
     patch.object(migrate, "_edit_message", side_effect=edit):
    stats = migrate.migrate()

assert set(edits) == {7001, 7003}, edits
assert stats["photo_updated"] == 2, stats
assert stats["skipped_current_version"] == 1, stats
assert stats["target_date"] == today, stats
assert set(stats["updated_message_ids"]) == {7001, 7003}, stats
assert history[0]["cards"][0]["card_design_version"] == 7
assert history[0]["cards"][2]["card_design_version"] == 7
assert history[1]["cards"][0]["card_design_version"] == 4
print("TELEGRAM TARGET-DATE REPAINT / ORIGINAL MESSAGE ID TEST PASSED")
