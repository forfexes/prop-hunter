#!/usr/bin/env python3
"""Read-only inventory of saved PROP HUNTER Telegram photo cards.

Used before any historical repaint. This script does not post to Telegram,
write history, invent player info, or overwrite existing settlements.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path
from prop_hunter_original_compositor import _family
from prophunter_results import _card_pick, _card_visual_text

VERSION = 11
HISTORY = Path("picks_history.json")

def inspect(history):
    allcards = Counter()
    by_day = defaultdict(Counter)
    by_family = defaultdict(Counter)
    by_version = Counter()
    eligible_by_day = defaultdict(Counter)
    reasons = Counter()
    older_eligible = Counter()
    for entry in history:
        day = str(entry.get("date") or "")[:10]
        picks = entry.get("picks") or []
        combos = entry.get("kombis") or []
        for card in entry.get("cards") or []:
            allcards["total"] += 1
            version = int(card.get("card_design_version") or 0)
            by_version[str(version)] += 1
            media = str(card.get("media_type") or "text")
            image_pick = card.get("image_pick")
            linked = _card_pick(card, picks, combos)
            visual = image_pick or linked
            kind = str((visual or {}).get("type") or card.get("card_kind") or "unknown").lower()
            try:
                family = _family(kind)
            except (ValueError, TypeError):
                family = "unknown"
            by_family[family]["all"] += 1
            by_day[day]["all"] += 1
            if media != "photo":
                reasons["not_photo"] += 1
                by_family[family]["not_photo"] += 1
                continue
            allcards["photos"] += 1
            by_day[day]["photos"] += 1
            by_family[family]["photos"] += 1
            if version >= VERSION:
                reasons["already_v11"] += 1
                by_family[family]["already_v11"] += 1
                continue
            if card.get("tg_gone") or not card.get("message_id"):
                reasons["gone_or_id_missing"] += 1
                by_family[family]["gone_or_id_missing"] += 1
                continue
            if not visual:
                reasons["missing_visual"] += 1
                by_family[family]["missing_visual"] += 1
                continue
            # This is the same evidence guard used by the real Telegram
            # photo migration. It may return None for invalidated tickets.
            try:
                safe_caption = _card_visual_text(card, picks, combos)
            except Exception:
                safe_caption = None
            if not safe_caption:
                reasons["no_safe_original_text"] += 1
                by_family[family]["no_safe_original_text"] += 1
                continue
            allcards["eligible_before_date_limit"] += 1
            by_day[day]["eligible"] += 1
            by_family[family]["eligible"] += 1
            eligible_by_day[day][family] += 1
            if day < "2026-11-12":
                older_eligible[family] += 1
    report = {
        "audit_version": 1,
        "minimum_card_design_version": VERSION,
        "overall": dict(allcards),
        "reasons": dict(reasons),
        "by_version": dict(sorted(by_version.items(), key=lambda x: int(x[0]))),
        "by_family": {k: dict(v) for k, v in sorted(by_family.items())},
        "by_day": {k: dict(v) for k, v in sorted(by_day.items(), reverse=True)},
        "eligible_by_day_family": {k:dict(v) for k,v in sorted(eligible_by_day.items(), reverse=True)},
        "eligible_before_2026_11_12": dict(older_eligible),
    }
    return report

if __name__ == "__main__":
    if not HISTORY.exists():
        raise SystemExit("Cannot audit: history file missing")
    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    if not isinstance(history, list):
        raise SystemExit("Invalid history; refusing report")
    report = inspect(history)
    dest = Path("diagnostics/prop_hunter_card_inventory.json")
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CARD_INVENTORY " + json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)
