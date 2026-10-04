#!/usr/bin/env python3
"""PROP HUNTER — in-place Telegram settlement reporter.

Source of truth: ``prop_hunter_results`` produced by ``prop_hunter_settler.py``.
The reporter does NOT re-grade games on its own.  It merges settled rows back into
``picks_history.json`` and edits the original Telegram card so ✅/❌/↔️ and the
realised stat/profit appear directly inside the original tip.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

HISTORY = Path("picks_history.json")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
TIMEOUT = int(os.getenv("PH_RESULTS_HTTP_TIMEOUT", "8"))
LOOKBACK_DAYS = max(1, int(os.getenv("PH_RESULTS_LOOKBACK_DAYS", "4")))
FALLBACK_SUMMARY = os.getenv("PH_RESULTS_FALLBACK_SUMMARY", "0").strip() == "1"

CLOSED = {"win", "won", "loss", "lost", "push"}


def _headers(extra: Optional[dict] = None) -> dict:
    h = {"apikey": SUPABASE_KEY}
    if SUPABASE_KEY and not SUPABASE_KEY.startswith(("sb_secret_", "sb_publishable_")):
        h["Authorization"] = f"Bearer {SUPABASE_KEY}"
    if extra:
        h.update(extra)
    return h


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _load_history() -> list:
    if not HISTORY.exists():
        return []
    try:
        data = json.loads(HISTORY.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as exc:
        print(f"history load failed: {exc}")
        return []


def _save_history(history: list) -> None:
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _fetch_results() -> list:
    """Fetch recent settled rows, newest first, without scanning old history forever."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Supabase missing; cannot publish settlement")
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS + 2)).isoformat()
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/prop_hunter_results",
            headers=_headers(),
            params={
                "select": "*",
                "settled_at": f"gte.{since}",
                "order": "settled_at.desc",
                "limit": "2500",
            },
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            print(f"results fetch HTTP {r.status_code}: {r.text[:250]}")
            return []
        rows = r.json()
        return rows if isinstance(rows, list) else []
    except Exception as exc:
        print(f"results fetch failed: {exc}")
        return []


def _result_status(row: dict) -> str:
    return str(row.get("result") or row.get("status") or "").lower().strip()


def _result_pick(row: dict) -> dict:
    raw = row.get("pick_raw")
    return raw if isinstance(raw, dict) else {}


def _commence_dt(p: dict):
    raw = p.get("raw") if isinstance(p.get("raw"), dict) else {}
    value = p.get("commence_time") or raw.get("commence_time")
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _settlement_ready_time(p: dict) -> bool:
    start = _commence_dt(p)
    if start is None:
        return True
    sport = str(p.get("sport") or p.get("league") or "").upper()
    hours = {
        "MLB": 4.0, "BASEBALL": 4.0, "NFL": 5.0, "NCAAF": 5.0,
        "NBA": 3.5, "WNBA": 3.5, "NCAAB": 3.5, "EUROLEAGUE": 3.5,
        "NHL": 4.0,
    }.get(sport, 4.0)
    return datetime.now(timezone.utc) >= start + timedelta(hours=hours)


def _reset_premature_result(p: dict) -> bool:
    if str(p.get("result") or p.get("status") or "").lower() not in CLOSED:
        return False
    if _settlement_ready_time(p):
        return False
    p["result"] = "pending"
    p["status"] = "pending"
    for key in ("profit", "profit_units", "actual_value", "settled_at", "settlement_note"):
        if key in p:
            p[key] = None
    return True


def _date_of_pick(p: dict) -> str:
    raw = p.get("sent_date") or p.get("date") or p.get("created_at") or ""
    return str(raw)[:10]


def _line_of_pick(p: dict) -> Optional[float]:
    for key in ("line", "point", "prop_line", "threshold"):
        val = _to_float(p.get(key))
        if val is not None:
            return val
    # Last-resort: line embedded in market text.
    nums = re.findall(r"(?<![a-z])(\d+(?:\.\d+)?)", str(p.get("market") or p.get("selection") or "").lower())
    return float(nums[-1]) if nums else None


def _side_of_pick(p: dict) -> str:
    raw = str(p.get("side") or p.get("direction") or p.get("over_under") or "").lower()
    if "under" in raw:
        return "under"
    return "over"


def _signature(p: dict) -> Tuple[str, str, Optional[float], str]:
    return (
        _norm(p.get("player") or p.get("player_name") or p.get("selection")),
        _norm(p.get("market") or p.get("prop_type") or p.get("selection")),
        _line_of_pick(p),
        _side_of_pick(p),
    )


def _index_results(rows: Iterable[dict]):
    by_dedup: Dict[str, dict] = {}
    by_signature: Dict[Tuple[str, str, Optional[float], str], dict] = {}
    for row in rows:
        if _result_status(row) not in CLOSED:
            continue
        raw = _result_pick(row)
        dedup = str(raw.get("dedup_key") or "").strip()
        if dedup and dedup not in by_dedup:
            by_dedup[dedup] = row
        sig = _signature(raw or row)
        if sig[0] and sig[1] and sig not in by_signature:
            by_signature[sig] = row
    return by_dedup, by_signature


def _match_result(pick: dict, by_dedup: dict, by_signature: dict) -> Optional[dict]:
    dedup = str(pick.get("dedup_key") or "").strip()
    if dedup and dedup in by_dedup:
        return by_dedup[dedup]
    sig = _signature(pick)
    exact = by_signature.get(sig)
    if exact:
        return exact
    # Safe fallback: same player + normalized market + side; accept one unique line-near candidate.
    candidates = []
    for rsig, row in by_signature.items():
        if sig[0] and rsig[0] == sig[0] and rsig[1] == sig[1] and rsig[3] == sig[3]:
            if sig[2] is None or rsig[2] is None or abs(float(sig[2]) - float(rsig[2])) < 1e-9:
                candidates.append(row)
    return candidates[0] if len(candidates) == 1 else None


def _profit_for(pick: dict, status: str) -> float:
    stake = _to_float(pick.get("stake"), 1.0) or 0.0
    odds = _to_float(pick.get("odds"), 0.0) or 0.0
    if status in {"win", "won"}:
        return round(max(0.0, odds - 1.0) * stake, 2)
    if status in {"loss", "lost"}:
        return round(-stake, 2)
    return 0.0


def _merge_single(pick: dict, result_row: dict) -> bool:
    status = _result_status(result_row)
    if status not in CLOSED:
        return False
    actual = result_row.get("actual_value")
    profit = _profit_for(pick, status)
    changed = (
        str(pick.get("result") or "pending").lower() != status
        or pick.get("actual_value") != actual
        or _to_float(pick.get("profit"), 0.0) != profit
    )
    pick["result"] = "win" if status == "won" else "loss" if status == "lost" else status
    pick["actual_value"] = actual
    pick["profit"] = profit
    pick["settled_at"] = result_row.get("settled_at")
    pick["settlement_source"] = "prop_hunter_results"
    return changed


def _leg_rows(combo: dict) -> list:
    rows = combo.get("leg_details") or combo.get("ladder_legs") or []
    return [dict(x) for x in rows if isinstance(x, dict)]


def _settle_combo(combo: dict, by_dedup: dict, by_signature: dict) -> bool:
    legs = _leg_rows(combo)
    if not legs:
        return False
    states = []
    profit = 0.0
    for leg in legs:
        row = _match_result(leg, by_dedup, by_signature)
        if not row:
            return False
        status = _result_status(row)
        if status not in CLOSED:
            return False
        leg["result"] = status
        leg["actual_value"] = row.get("actual_value")
        states.append(status)
        if combo.get("type") == "ladder":
            profit += _profit_for(leg, status)
    if combo.get("type") == "ladder":
        final = "win" if profit > 0 else "loss" if profit < 0 else "push"
    elif any(s in {"loss", "lost"} for s in states):
        final = "loss"
        profit = -(_to_float(combo.get("stake"), 0.0) or 0.0)
    elif all(s in {"win", "won"} for s in states):
        final = "win"
        stake = _to_float(combo.get("stake"), 0.0) or 0.0
        odds = _to_float(combo.get("odds"), 0.0) or 0.0
        profit = (odds - 1.0) * stake
    else:
        final = "push"
        profit = 0.0
    old = (combo.get("result"), _to_float(combo.get("profit"), 0.0))
    combo["result"] = final
    combo["profit"] = round(profit, 2)
    combo["leg_details"] = legs if combo.get("leg_details") else combo.get("leg_details", [])
    combo["settlement_legs"] = legs
    return old != (combo["result"], combo["profit"])


def _status_icon(status: Any) -> str:
    return {"win": "✅", "won": "✅", "loss": "❌", "lost": "❌", "push": "↔️"}.get(str(status or "").lower(), "")


def _fmt_actual(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Ja" if value else "Nein"
    try:
        f = float(value)
        return f"{f:g}"
    except Exception:
        return str(value)


def _decorate_single(lines: List[str], pick: dict, used: set) -> bool:
    icon = _status_icon(pick.get("result"))
    if not icon:
        return False
    player = _norm(pick.get("player") or pick.get("player_name"))
    if not player:
        return False
    market = _norm(pick.get("market"))
    words = [w for w in market.split() if w not in {"over", "under"}]
    for i, line in enumerate(lines):
        if i in used or player not in _norm(line):
            continue
        # In PROP HUNTER cards the market line immediately follows the player line.
        for j in range(i + 1, min(i + 4, len(lines))):
            nline = _norm(lines[j])
            if words and not all(w in nline for w in words[: min(2, len(words))]):
                continue
            base = lines[j]
            base = re.sub(r"^\s*[✅❌↔️]\s*", "   ", base)
            if "└" in base:
                base = base.replace("└", icon, 1)
            else:
                base = "   " + icon + " " + base.strip()
            # Idempotent: remove previous settlement suffix before writing the fresh one.
            base = re.sub(r"\s+·\s+Ergebnis\s+[^·]+(?:\s+·\s+[+-]?\d+(?:\.\d+)?u)?\s*$", "", base)
            suffix = []
            actual = _fmt_actual(pick.get("actual_value"))
            if actual:
                suffix.append(f"Ergebnis {actual}")
            profit = _to_float(pick.get("profit"), 0.0) or 0.0
            suffix.append(f"{profit:+.2f}u")
            lines[j] = base + " · " + " · ".join(suffix)
            used.update({i, j})
            return True
    return False


def _decorate_combo(lines: List[str], combo: dict, used: set) -> bool:
    icon = _status_icon(combo.get("result"))
    if not icon:
        return False
    odds = _to_float(combo.get("odds"))
    # Locate by odds first; combo text can contain several player names.
    tokens = []
    if odds is not None:
        tokens = [f"@{odds:.2f}", f"@{odds:.1f}"]
    for i, line in enumerate(lines):
        if i in used:
            continue
        stripped = line.lstrip()
        if not stripped.startswith(("•", "🚀", "✅", "❌", "↔️")):
            continue
        if tokens and not any(t in line for t in tokens):
            continue
        clean = re.sub(r"^[•🚀✅❌↔️]\s*", "", stripped)
        profit = _to_float(combo.get("profit"), 0.0) or 0.0
        prefix = line[: len(line) - len(stripped)]
        lines[i] = f"{prefix}{icon} {clean} · {profit:+.2f}u"
        used.add(i)
        return True
    return False


def _decorate_card(card: dict, picks: list, combos: list) -> Optional[str]:
    original = str(card.get("text") or "")
    if not original:
        return None
    lines = original.splitlines()
    used = set()
    pick_by_key = {str(p.get("dedup_key")): p for p in picks if p.get("dedup_key")}
    combo_by_id = {str(c.get("combo_id")): c for c in combos if c.get("combo_id")}
    selected_picks = [pick_by_key[k] for k in map(str, card.get("pick_keys") or []) if k in pick_by_key]
    selected_combos = [combo_by_id[k] for k in map(str, card.get("combo_ids") or []) if k in combo_by_id]

    edited = 0
    for p in selected_picks:
        edited += int(_decorate_single(lines, p, used))
    for c in selected_combos:
        edited += int(_decorate_combo(lines, c, used))
    if not edited:
        return None

    closed = [p for p in selected_picks if _status_icon(p.get("result"))]
    closed += [c for c in selected_combos if _status_icon(c.get("result"))]
    wins = sum(str(x.get("result")).lower() in {"win", "won"} for x in closed)
    losses = sum(str(x.get("result")).lower() in {"loss", "lost"} for x in closed)
    pushes = sum(str(x.get("result")).lower() == "push" for x in closed)
    total_expected = len(selected_picks) + len(selected_combos)
    pending = max(0, total_expected - len(closed))
    profit = sum(_to_float(x.get("profit"), 0.0) or 0.0 for x in closed)
    summary = f"🏁 Auswertung: {wins}✅ {losses}❌"
    if pushes:
        summary += f" {pushes}↔️"
    if pending:
        summary += f" {pending}⏳"
    summary += f" · {profit:+.2f}u"

    # Remove an older summary if the card is being updated a second time.
    lines = [ln for ln in lines if not ln.strip().startswith("🏁 Auswertung:")]
    insert_at = next((i for i, ln in enumerate(lines) if ln.strip() == "@prophunter"), len(lines))
    lines.insert(insert_at, summary)
    text = "\n".join(lines)
    return text if len(text) <= 4096 else None


def _edit_message(message_id: Any, text: str, chat_id: Any = None) -> bool:
    if not TG_TOKEN or not message_id:
        return False
    target = str(chat_id or TG_CHAT or "").strip()
    if not target:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/editMessageText",
            json={"chat_id": target, "message_id": int(message_id), "text": text, "disable_web_page_preview": True},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return True
        if r.status_code == 400 and "message is not modified" in r.text.lower():
            return True
        print(f"Telegram edit {r.status_code}: {r.text[:200]}")
    except Exception as exc:
        print(f"Telegram edit failed: {exc}")
    return False


def _send_summary(text: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        print(text)
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": text, "disable_web_page_preview": True},
            timeout=TIMEOUT,
        )
    except Exception as exc:
        print(f"Telegram send failed: {exc}")


def _sync_pick_table(pick: dict) -> None:
    """Best-effort mirror status/profit to both historical pick tables."""
    if not SUPABASE_URL or not SUPABASE_KEY or not pick.get("dedup_key"):
        return
    status = str(pick.get("result") or "pending")
    profit = _to_float(pick.get("profit"), 0.0) or 0.0
    d = _date_of_pick(pick)
    headers = _headers({"Content-Type": "application/json", "Prefer": "return=minimal"})
    targets = [
        ("prop_picks", {"dedup_key": f"eq.{pick['dedup_key']}"}, {"result": status, "profit": profit}),
        ("prop_hunter_picks", {"dedup_key": f"eq.{pick['dedup_key']}"}, {"status": status, "result": status, "profit_units": profit}),
    ]
    if d:
        targets[0][1]["date"] = f"eq.{d}"
        targets[1][1]["sent_date"] = f"eq.{d}"
    for table, params, payload in targets:
        try:
            requests.patch(
                f"{SUPABASE_URL}/rest/v1/{table}", headers=headers, params=params, json=payload, timeout=TIMEOUT
            )
        except Exception:
            pass


def main() -> int:
    history = _load_history()
    rows = _fetch_results()
    print(f"Settlement reporter: history_days={len(history)} results={len(rows)} lookback={LOOKBACK_DAYS}d")
    if not history or not rows:
        print("Nothing to publish")
        return 0

    by_dedup, by_signature = _index_results(rows)
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    merged = 0
    cards_edited = 0
    cards_ready = 0
    changed = False
    fallback_lines = []

    for entry in history:
        day = str(entry.get("date") or "")[:10]
        if day and day < cutoff:
            continue
        picks = entry.get("picks") or []
        combos = entry.get("kombis") or []
        for p in picks:
            if _reset_premature_result(p):
                changed = True
                _sync_pick_table(p)
            row = _match_result(p, by_dedup, by_signature)
            if not row:
                continue
            if _merge_single(p, row):
                changed = True
                merged += 1
                _sync_pick_table(p)
        for combo in combos:
            if _settle_combo(combo, by_dedup, by_signature):
                changed = True

        for card in entry.get("cards") or []:
            text = _decorate_card(card, picks, combos)
            if not text:
                continue
            cards_ready += 1
            # Skip network call when identical to the last successful in-place settlement.
            if text == card.get("settlement_text"):
                continue
            if _edit_message(card.get("message_id"), text, card.get("chat_id")):
                card["settlement_text"] = text
                card["settlement_updated_at"] = datetime.now(timezone.utc).isoformat()
                cards_edited += 1
                changed = True

        if FALLBACK_SUMMARY and not entry.get("cards"):
            closed = [p for p in picks if _status_icon(p.get("result"))]
            if closed:
                fallback_lines.append((day, closed))

    if changed:
        _save_history(history)

    if FALLBACK_SUMMARY:
        for day, closed in fallback_lines:
            wins = sum(str(p.get("result")).lower() in {"win", "won"} for p in closed)
            losses = sum(str(p.get("result")).lower() in {"loss", "lost"} for p in closed)
            profit = sum(_to_float(p.get("profit"), 0.0) or 0.0 for p in closed)
            _send_summary(f"📊 PROP HUNTER — Auswertung {day}\n\n{wins}✅ {losses}❌ · {profit:+.2f}u\n\n@prophunter")

    print(f"Settlement reporter done: merged={merged} cards_ready={cards_ready} cards_edited={cards_edited}")
    if cards_ready == 0:
        has_cards = any((entry.get("cards") or []) for entry in history if str(entry.get("date") or "")[:10] >= cutoff)
        if has_cards:
            print("No Telegram card has newly settled selections ready for an in-place edit.")
        else:
            print("No recent Telegram card metadata found; future tips need message_id metadata from current prophunter.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
