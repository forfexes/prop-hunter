"""Regression: Sunday Telegram cards from Saturday's NBA slate must be repaired."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from prophunter_results import _recent_owner_visual_window

now = datetime(2026, 11, 22, 4, 23, tzinfo=timezone.utc)
swiss_today = now.astimezone(ZoneInfo("Europe/Zurich")).date().isoformat()
assert swiss_today == "2026-11-22"

def card(hours):
    return {"created_at": (now - timedelta(hours=hours)).isoformat()}

# Last night's 02:10 Telegram ladder can represent November 21 NBA fixture.
assert _recent_owner_visual_window(card(3), "2026-11-21", now_utc=now)
assert _recent_owner_visual_window(card(16), "2026-11-21", now_utc=now)
assert _recent_owner_visual_window(card(35.9), "2026-11-20", now_utc=now)
assert _recent_owner_visual_window(card(0), "2026-11-22", now_utc=now)
assert not _recent_owner_visual_window(card(36.1), "2026-11-22", now_utc=now)
assert not _recent_owner_visual_window(card(-.1), "2026-11-22", now_utc=now)
assert not _recent_owner_visual_window(
    {"created_at": "2026-11-22T01:00:00"}, "2026-11-22", now_utc=now
)
assert not _recent_owner_visual_window(
    {"created_at": "injected or invalid"}, "2026-11-22", now_utc=now
)
assert _recent_owner_visual_window({}, "2026-11-22", now_utc=now)
assert not _recent_owner_visual_window({}, "2026-11-21", now_utc=now)
print("TELEGRAM_POSTED_TODAY_VS_NBA_PREVIOUS_SLATE_DATE_QA_PASSED")
