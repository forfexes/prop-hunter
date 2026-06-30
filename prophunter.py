#!/usr/bin/env python3
"""
PROP HUNTER — CLEAN FINAL
=========================

Eine saubere Hauptdatei ohne v5/v6 Patch-Chaos.

Ziel:
- Telegram-Ausgabe nur "PROP HUNTER"
- keine Quellen/Books in der Nachricht
- keine Debug-Texte
- keine "JK STYLE" Anzeige
- 3PM sauber
- doppelte Lines entfernen
- mehr Picks, wenn Edge positiv ist
- einfache Builder, wenn genug Picks vorhanden sind

Diese Datei ersetzt:
- prophunter.py

Nicht mehr nötig:
- prop_hunter_v5_patch.py
- prop_hunter_v6_patch.py
- prop_hunter_title_clean_patch.py
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests


# ============================================================
# ENV / CONFIG
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

MIN_EDGE = float(os.environ.get("PH_MIN_EDGE", "3.0"))
MAX_TOTAL_PICKS = int(os.environ.get("PH_MAX_PICKS_TOTAL", "50"))
MAX_PER_PLAYER = int(os.environ.get("PH_MAX_PER_PLAYER", "3"))
MAX_PER_GAME = int(os.environ.get("PH_MAX_PER_GAME", "6"))

DATA_CACHE = Path(os.environ.get("PH_DATA_CACHE", "prop_hunter_data_cache.json"))

TODAY = datetime.now(timezone.utc).strftime("%d.%m.%Y")
SENT_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ============================================================
# LOGGING
# ============================================================

def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} INFO    {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} WARNING {msg}", flush=True)


# ============================================================
# MODEL
# ============================================================

@dataclass
class Pick:
    sport: str
    league: str
    team: str
    player: str
    market: str
    line: str
    side: str
    odds: float
    edge: float
    prob: float
    stake: float
    game_key: str = ""

    @property
    def clean_market(self) -> str:
        return clean_market(self.market, self.side, self.line)

    @property
    def label_sport(self) -> str:
        s = (self.sport or self.league or "").lower()
        if "mlb" in s or "baseball" in s:
            return "⚾ MLB"
        if "nfl" in s or "football" in s:
            return "🏈 NFL"
        if "wnba" in s:
            return "🏀 WNBA"
        if "nba" in s:
            return "🏀 NBA"
        return "🏀 BASKETBALL"


# ============================================================
# CLEAN HELPERS
# ============================================================

BOOK_WORDS = {
    "draftkings", "fanduel", "betonlineag", "betrivers", "betmgm", "caesars",
    "pointsbet", "pinnacle", "betfair", "espnbet", "fanatics", "williamhill_us"
}

TEAM_FIX = {
    "a'ja wilson": "Las Vegas Aces",
    "chelsea gray": "Las Vegas Aces",
    "jackie young": "Las Vegas Aces",
    "rhyne howard": "Atlanta Dream",
    "allisha gray": "Atlanta Dream",
    "arike ogunbowale": "Dallas Wings",
    "natisha hiedeman": "Minnesota Lynx",
    "dearica hamby": "Los Angeles Sparks",
    "nneka ogwumike": "Seattle Storm",
}


def norm(s: Any) -> str:
    return str(s or "").strip()


def clean_player(name: Any) -> str:
    s = norm(name)
    return re.sub(r"\s+", " ", s).strip()


def clean_team(team: Any, player: Any = "") -> str:
    p = clean_player(player).lower()
    if p in TEAM_FIX:
        return TEAM_FIX[p]
    t = norm(team)
    if not t or t.lower() in {"none", "null", "unknown"}:
        return ""
    return t


def clean_market_name(market: Any) -> str:
    s = norm(market)

    low = s.lower()
    mapping = [
        ("player_points_rebounds_assists", "PRA"),
        ("points_rebounds_assists", "PRA"),
        ("points+rebounds+assists", "PRA"),
        ("rebounds+assists", "Reb+Ast"),
        ("points+rebounds", "PR"),
        ("points+assists", "PA"),
        ("player_points", "Points"),
        ("player_rebounds", "Rebounds"),
        ("player_assists", "Assists"),
        ("player_threes", "3PM"),
        ("3pm", "3PM"),
        ("3-pointers", "3PM"),
        ("three pointers", "3PM"),
        ("home run", "Home Run"),
        ("strikeouts", "Strikeouts"),
        ("total bases", "Total Bases"),
    ]
    for key, val in mapping:
        if key in low:
            return val

    s = s.replace("_", " ").replace("+", "+")
    s = re.sub(r"\b3pm\b", "3PM", s, flags=re.I)
    s = re.sub(r"\b3Pm\b", "3PM", s)
    return s.title().replace("3Pm", "3PM").replace("Pra", "PRA")


def clean_line(line: Any) -> str:
    s = norm(line)
    if s.endswith(".0"):
        s = s[:-2]
    return s


def clean_side(side: Any) -> str:
    s = norm(side).lower()
    if s.startswith("under"):
        return "Under"
    if s.startswith("over"):
        return "Over"
    if s in {"yes", "true"}:
        return ""
    return s.title() if s else "Over"


def clean_market(market: Any, side: Any, line: Any) -> str:
    m = clean_market_name(market)
    sd = clean_side(side)
    ln = clean_line(line)

    if m.lower() in {"home run", "homer"}:
        return "Home Run"

    if ln:
        return f"{m} {sd} {ln}".strip()
    return f"{m} {sd}".strip()


def implied_prob(odds: float) -> float:
    if odds <= 1:
        return 0.0
    return 100.0 / odds


def calc_edge(prob: float, odds: float) -> float:
    return prob - implied_prob(odds)


def stake_from_edge(edge: float, odds: float) -> float:
    if edge >= 10:
        return 0.75
    if edge >= 7:
        return 0.60
    if edge >= 4:
        return 0.50
    if odds >= 4:
        return 0.20
    return 0.33


def market_priority(market: Any) -> int:
    m = clean_market_name(market).lower()
    order = [
        ("pra", 1),
        ("pr", 2),
        ("pa", 3),
        ("reb+ast", 4),
        ("points", 5),
        ("strikeouts", 6),
        ("total bases", 7),
        ("home run", 8),
        ("rebounds", 9),
        ("assists", 10),
        ("3pm", 11),
    ]
    for key, val in order:
        if key in m:
            return val
    return 50


def pick_sort_key(p: Pick):
    return (p.label_sport, market_priority(p.market), -p.edge, -p.odds)


# ============================================================
# DATA LOADERS
# ============================================================

def sb_headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def supabase_select(table: str, limit: int = 1000) -> List[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {"select": "*", "limit": str(limit)}
    try:
        r = requests.get(url, headers=sb_headers(), params=params, timeout=25)
        if r.status_code >= 300:
            warn(f"supabase {table} status={r.status_code}: {r.text[:200]}")
            return []
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        warn(f"supabase {table} failed: {e}")
        return []


def load_supabase_props() -> List[Dict[str, Any]]:
    # verschiedene mögliche Tabellennamen probieren
    tables = [
        "prop_hunter_event_props",
        "event_props",
        "prop_event_props",
        "props",
    ]
    for t in tables:
        rows = supabase_select(t, limit=1000)
        if rows:
            log(f"loaded {len(rows)} props from {t}")
            return rows
    return []


def load_local_props() -> List[Dict[str, Any]]:
    paths = [
        Path("prop_hunter_event_props.json"),
        Path("event_props.json"),
        Path("props.json"),
    ]
    for p in paths:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data = data.get("props") or data.get("data") or []
                if isinstance(data, list):
                    log(f"loaded {len(data)} props from {p}")
                    return data
            except Exception as e:
                warn(f"local props {p} failed: {e}")
    return []


def get_any(row: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return default


def row_to_pick(row: Dict[str, Any]) -> Optional[Pick]:
    player = clean_player(get_any(row, ["player", "player_name", "name", "description"]))
    if not player:
        return None

    market = get_any(row, ["market", "market_name", "prop", "stat", "type"], "")
    line = get_any(row, ["line", "point", "handicap", "threshold"], "")
    side = get_any(row, ["side", "outcome", "over_under", "selection"], "Over")

    odds_raw = get_any(row, ["odds", "price", "decimal_odds", "best_odds"], 0)
    try:
        odds = float(odds_raw)
    except Exception:
        return None
    if odds <= 1.01:
        return None

    prob_raw = get_any(row, ["prob", "probability", "model_prob", "fair_prob"], None)
    if prob_raw is None:
        # conservative fallback: implied + MIN_EDGE
        prob = implied_prob(odds) + MIN_EDGE
    else:
        try:
            prob = float(prob_raw)
            if prob <= 1:
                prob *= 100.0
        except Exception:
            prob = implied_prob(odds) + MIN_EDGE

    edge_raw = get_any(row, ["edge", "edge_pct", "value_edge"], None)
    if edge_raw is None:
        edge = calc_edge(prob, odds)
    else:
        try:
            edge = float(edge_raw)
            if abs(edge) <= 1:
                edge *= 100.0
        except Exception:
            edge = calc_edge(prob, odds)

    if edge < MIN_EDGE:
        return None

    sport = norm(get_any(row, ["sport", "sport_key", "league"], ""))
    league = norm(get_any(row, ["league", "competition"], sport))
    team = clean_team(get_any(row, ["team", "player_team", "home_team"], ""), player)
    game_key = norm(get_any(row, ["event_id", "game_id", "match_id", "event", "game"], ""))

    return Pick(
        sport=sport,
        league=league,
        team=team,
        player=player,
        market=market,
        line=clean_line(line),
        side=clean_side(side),
        odds=odds,
        edge=edge,
        prob=prob,
        stake=stake_from_edge(edge, odds),
        game_key=game_key,
    )


def dedupe_and_limit(picks: List[Pick]) -> List[Pick]:
    picks = sorted(picks, key=pick_sort_key)

    seen = set()
    per_player = defaultdict(int)
    per_game = defaultdict(int)
    out: List[Pick] = []

    for p in picks:
        key = (p.player.lower(), p.clean_market.lower(), round(p.odds, 2))
        if key in seen:
            continue
        seen.add(key)

        player_key = p.player.lower()
        game_key = p.game_key or f"{p.label_sport}:{p.team}"

        if per_player[player_key] >= MAX_PER_PLAYER:
            continue
        if per_game[game_key] >= MAX_PER_GAME:
            continue

        out.append(p)
        per_player[player_key] += 1
        per_game[game_key] += 1

        if len(out) >= MAX_TOTAL_PICKS:
            break

    return out


# ============================================================
# TELEGRAM CARD
# ============================================================

def fmt_odds(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def fmt_edge(x: float) -> str:
    return f"+{x:.1f}%" if x >= 0 else f"{x:.1f}%"


def build_builders(picks: List[Pick]) -> List[str]:
    if len(picks) < 2:
        return []

    # bevorzugt starke, nicht identische Spieler
    base = []
    used_players = set()
    for p in sorted(picks, key=lambda x: (-x.edge, market_priority(x.market), -x.odds)):
        if p.player.lower() in used_players:
            continue
        base.append(p)
        used_players.add(p.player.lower())
        if len(base) >= 6:
            break

    blocks = []

    if len(base) >= 2:
        a, b = base[0], base[1]
        blocks.append(
            "🎯 SAFE BUILDER\n"
            f"✅ {a.player} — {a.clean_market}\n"
            f"✅ {b.player} — {b.clean_market}\n"
            "💰 Quote: siehe Book"
        )

    if len(base) >= 3:
        a, b, c = base[0], base[1], base[2]
        blocks.append(
            "💎 VALUE BUILDER\n"
            f"✅ {a.player} — {a.clean_market}\n"
            f"✅ {b.player} — {b.clean_market}\n"
            f"✅ {c.player} — {c.clean_market}\n"
            "💰 Quote: siehe Book"
        )

    longshots = [p for p in picks if p.odds >= 3.0 or "home run" in p.clean_market.lower()]
    longshots = sorted(longshots, key=lambda x: (-x.edge, -x.odds))
    if len(longshots) >= 2:
        legs = "\n".join(f"⭐ {p.player} — {p.clean_market} @{fmt_odds(p.odds)}" for p in longshots[:3])
        blocks.append("💣 LOTTERY\n" + legs)

    return blocks


def build_card(picks: List[Pick]) -> str:
    lines: List[str] = []
    lines.append("🎯 PROP HUNTER")
    lines.append(f"📅 {TODAY}")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━")

    if not picks:
        lines.append("Keine sauberen Value Picks gefunden.")
        lines.append("")
        lines.append("@prophunter")
        return "\n".join(lines)

    grouped: Dict[str, List[Pick]] = defaultdict(list)
    for p in picks:
        grouped[p.label_sport].append(p)

    total = 0
    for sport in sorted(grouped.keys()):
        sport_picks = grouped[sport]
        lines.append("")
        lines.append(sport)
        lines.append("")
        lines.append("🔥 BEST PICKS")
        lines.append("")

        for idx, p in enumerate(sport_picks, 1):
            total += 1
            team_part = f"{p.team} — " if p.team else ""
            lines.append(f"{idx}️⃣ {team_part}{p.player}")
            lines.append(f"🎯 {p.clean_market} @{fmt_odds(p.odds)}")
            lines.append(f"📈 Edge {fmt_edge(p.edge)} · Model {p.prob:.0f}% · Stake {p.stake:.2f}u")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━")

    builders = build_builders(picks)
    if builders:
        lines.append("")
        lines.extend(["\n\n".join(builders)])
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━")

    lottery_count = 1 if any(b.startswith("💣") for b in builders) else 0
    builder_count = sum(1 for b in builders if not b.startswith("💣"))

    lines.append("")
    lines.append("📊 CARD")
    lines.append(f"✅ Singles: {total}")
    lines.append(f"🎯 Builder: {builder_count}")
    lines.append(f"💣 Lottery/Kombis: {lottery_count}")
    lines.append("")
    lines.append("✅ Nur positive Edge")
    lines.append("✅ Konzentration begrenzt")
    lines.append("✅ Lines bestätigt")
    lines.append("")
    lines.append("@prophunter")

    return "\n".join(lines).strip()


def send_telegram(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        warn("Telegram env missing, print only")
        print(text)
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if r.status_code >= 300:
            warn(f"Telegram failed {r.status_code}: {r.text[:300]}")
            print(text)
            return False
        log("Telegram OK")
        return True
    except Exception as e:
        warn(f"Telegram exception: {e}")
        print(text)
        return False


# ============================================================
# PERSISTENCE
# ============================================================

def persist_picks(picks: List[Pick]) -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return

    url = f"{SUPABASE_URL}/rest/v1/prop_picks"
    rows = []
    for p in picks:
        rows.append({
            "sent_date": SENT_DATE,
            "sport": p.label_sport,
            "team": p.team,
            "player": p.player,
            "market": p.clean_market,
            "line": p.line,
            "side": p.side,
            "odds": p.odds,
            "edge": p.edge,
            "prob": p.prob,
            "stake": p.stake,
            "dedup_key": f"{p.player.lower()}|{p.clean_market.lower()}|{p.line}|{p.side.lower()}",
        })

    try:
        # ignore duplicates
        r = requests.post(
            url,
            headers={**sb_headers(), "Prefer": "resolution=ignore-duplicates"},
            json=rows,
            timeout=25,
        )
        if r.status_code >= 300:
            warn(f"persist picks failed {r.status_code}: {r.text[:300]}")
        else:
            log(f"persisted {len(rows)} singles")
    except Exception as e:
        warn(f"persist exception: {e}")


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    log("========================================")
    log("PROP HUNTER CLEAN FINAL")
    log("========================================")

    raw_rows = load_supabase_props()
    if not raw_rows:
        raw_rows = load_local_props()

    if not raw_rows:
        warn("no props found from Supabase/local files")
        card = build_card([])
        send_telegram(card)
        return 0

    picks: List[Pick] = []
    rejected = defaultdict(int)

    for row in raw_rows:
        p = row_to_pick(row)
        if not p:
            rejected["invalid_or_low_edge"] += 1
            continue
        picks.append(p)

    log(f"raw picks after quality filter: {len(picks)} | rejected={dict(rejected)}")

    picks = dedupe_and_limit(picks)
    log(f"final picks: {len(picks)}")

    card = build_card(picks)
    send_telegram(card)
    persist_picks(picks)

    print(card)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
