"""Same-message v7 owner Ladder settlement refresh excludes old examples.

All checks use offline synthetic timestamps.  No Telegram edit is performed.
"""
from datetime import datetime, timedelta, timezone

from prophunter_results import _verified_owner_rung_refresh_due

now=datetime(2026,11,22,5,0,tzinfo=timezone.utc)
stamp=(now-timedelta(hours=3)).isoformat()
card={
    "media_type":"photo",
    "created_at":stamp,
    "image_pick":{"_owner_layered_original_v1":True},
    "ladder_rung_version":2,
}
graded={
    "type":"ladder",
    "result":"loss",
    "leg_details":[{"market":"blocks","result":"win","actual_value":1},
                   {"market":"blocks","result":"loss","actual_value":1}],
}
assert _verified_owner_rung_refresh_due(card,graded,"2026-11-21",3,now_utc=now)
# A 21 Nov NBA slate can have a 22 Nov Telegram photo.
for changes in [
    {"media_type":"text"},
    {"image_pick":{"_owner_layered_original_v1":False}},
    {"image_pick":{}},
    {"ladder_rung_version":3},
    {"created_at":(now-timedelta(hours=37)).isoformat()},
    {"created_at":"bad"},
]:
    altered={**card,**changes}
    assert not _verified_owner_rung_refresh_due(
        altered,graded,"2026-11-21",3,now_utc=now
    ),changes
for source in [
    {**graded,"result":"pending"},
    {**graded,"type":"betbuilder"},
    {**graded,"leg_details":[]},
    {**graded,"leg_details":[{"result":None}]},
]:
    assert not _verified_owner_rung_refresh_due(card,source,"2026-11-21",3,now_utc=now),source
assert not _verified_owner_rung_refresh_due(
    {},graded,"2026-11-21",3,now_utc=now
)
print("OWNER_RUNG_V3_VERIFIED_RECENT_PHOTO_ONLY_NONDESTRUCTIVE_QA_PASS")
