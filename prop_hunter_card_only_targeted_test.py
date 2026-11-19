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

# Confirmed Telegram no-op must count as identical, not a new photo edit.
unchanged_history=[{"date":today,"picks":[],"kombis":[],
                    "cards":[card(7100,9)]}]
def unchanged_edit(message_id,text,chat_id=None,image_pick=None):
    migrate._EDIT_STATE["unchanged"]=True
    return True
with patch.object(migrate,"TARGET_DATE",today), \
     patch.object(migrate,"VERSION",10), \
     patch.object(migrate,"MAX_UPDATES",100), \
     patch.object(migrate,"_load_history",return_value=unchanged_history), \
     patch.object(migrate,"_save_history"), \
     patch.object(migrate,"_card_visual_text",return_value="Pending"), \
     patch.object(migrate,"_card_pick",side_effect=lambda c,p,co:c["image_pick"]), \
     patch.object(migrate,"_edit_message",side_effect=unchanged_edit):
    report=migrate.migrate()
assert report["photo_updated"]==0, report
assert report["photo_unchanged"]==1, report
assert report["updated_message_ids"]==[], report
assert unchanged_history[0]["cards"][0]["card_design_version"]==10
migrate._EDIT_STATE["unchanged"]=False
print("MIGRATION ACK-NOOP IS RECORDED AS ALREADY-IDENTICAL, NOT AS EDITED")

# New visual repair targets SINGLE + LADDER only, never repaints unrelated
# builder/lottery originals or manufactures missing model statistics.
cases=[card(8011,10),card(8012,10),card(8013,10)]
cases[1]["image_pick"]["type"]="builder"
cases[2]["image_pick"]["type"]="ladder"
focused=[{"date":today,"picks":[],"kombis":[],"cards":cases}]
calls=[]
def edited(mid,text,chat_id=None,image_pick=None):
    calls.append((mid,dict(image_pick or {})))
    migrate._EDIT_STATE["unchanged"]=False
    return True
def recover(card,picks,combos):
    return {"type":card["image_pick"]["type"],"probability":.65,
            "edge_pct":26.1,"game_date":"2026-11-19"}
with patch.object(migrate,"TARGET_DATE",today), \
     patch.object(migrate,"FAMILY_FILTER",{"single","ladder"}), \
     patch.object(migrate,"VERSION",11), \
     patch.object(migrate,"MAX_UPDATES",100), \
     patch.object(migrate,"_load_history",return_value=focused), \
     patch.object(migrate,"_save_history"), \
     patch.object(migrate,"_card_visual_text",return_value="Pending"), \
     patch.object(migrate,"_card_pick",side_effect=recover), \
     patch.object(migrate,"_edit_message",side_effect=edited):
    result=migrate.migrate()
assert {mid for mid,_ in calls}=={8011,8013},calls
assert result["photo_updated"]==2 and result["failed"]==0,result
assert cases[1]["card_design_version"]==10
assert all(visual["probability"]==.65 and visual["edge_pct"]==26.1 for mid,visual in calls)
print("TARGETED V11 PHOTO REPAINT: SINGLE+LADDER ONLY / LINKED MODEL FIELDS PASS")
