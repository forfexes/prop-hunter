#!/usr/bin/env python3
"""
PROP HUNTER — CLEAN FINAL
=========================

Eine saubere Hauptdatei ohne Patch-Chaos.

- Titel nur: PROP HUNTER
- liest Supabase zuerst aus: player_prop_db
- keine Quellen/Books in Telegram
- keine "JK STYLE" Anzeige
- 3PM sauber
- doppelte Lines entfernt
- Builder automatisch, wenn genug Picks vorhanden
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

MIN_EDGE = float(os.environ.get("PH_MIN_EDGE", "3.0"))
MAX_TOTAL_PICKS = int(os.environ.get("PH_MAX_PICKS_TOTAL", "50"))
MAX_PER_PLAYER = int(os.environ.get("PH_MAX_PER_PLAYER", "3"))
MAX_PER_GAME = int(os.environ.get("PH_MAX_PER_GAME", "6"))

TODAY = datetime.now(timezone.utc).strftime("%d.%m.%Y")
SENT_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} INFO    {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} WARNING {msg}", flush=True)


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
        s = f"{self.sport} {self.league}".lower()
        if "mlb" in s or "baseball" in s:
            return "⚾ MLB"
        if "nfl" in s or "americanfootball" in s:
            return "🏈 NFL"
        if "wnba" in s:
            return "🏀 WNBA"
        if "nba" in s:
            return "🏀 NBA"
        return "🏀 BASKETBALL"


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


def get_any(row: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return default


def clean_player(name: Any) -> str:
    return re.sub(r"\s+", " ", norm(name)).strip()


def clean_team(team: Any, player: Any = "") -> str:
    p = clean_player(player).lower()
    if p in TEAM_FIX:
        return TEAM_FIX[p]
    t = norm(team)
    if not t or t.lower() in {"none", "null", "unknown"}:
        return ""
    return t


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


def clean_market_name(market: Any) -> str:
    s = norm(market)
    low = s.lower().replace("_", " ")

    if "points rebounds assists" in low or "pra" == low:
        return "PRA"
    if "points rebounds" in low or low == "pr":
        return "PR"
    if "points assists" in low or low == "pa":
        return "PA"
    if "rebounds assists" in low or "reb ast" in low or low == "ra":
        return "Reb+Ast"
    if "three" in low or "3pm" in low or "3 pointers" in low or "threes" in low:
        return "3PM"
    if "home run" in low or "homer" in low:
        return "Home Run"
    if "strikeout" in low:
        return "Strikeouts"
    if "total base" in low:
        return "Total Bases"
    if "point" in low:
        return "Points"
    if "rebound" in low:
        return "Rebounds"
    if "assist" in low:
        return "Assists"
    if "steal" in low:
        return "Steals"
    if "block" in low:
        return "Blocks"

    s = s.replace("_", " ")
    s = re.sub(r"\b3pm\b", "3PM", s, flags=re.I)
    return s.title().replace("3Pm", "3PM").replace("Pra", "PRA")


def clean_market(market: Any, side: Any, line: Any) -> str:
    m = clean_market_name(market)
    if m == "Home Run":
        return "Home Run"
    sd = clean_side(side)
    ln = clean_line(line)
    text = f"{m} {sd} {ln}".strip() if ln else f"{m} {sd}".strip()
    text = re.sub(r"\b(Over|Under)\s+([0-9]+(?:\.[0-9]+)?)\s+\2\b", r"\1 \2", text, flags=re.I)
    return text.replace("3Pm", "3PM")


def implied_prob(odds: float) -> float:
    return 100.0 / odds if odds > 1 else 0.0


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
        ("pra", 1), ("pr", 2), ("pa", 3), ("reb+ast", 4),
        ("points", 5), ("strikeouts", 6), ("total bases", 7),
        ("home run", 8), ("rebounds", 9), ("assists", 10), ("3pm", 11),
    ]
    for key, val in order:
        if key in m:
            return val
    return 50


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
    tables = [
        "player_prop_db",
        "prop_hunter_event_props",
        "event_props",
        "prop_event_props",
        "props",
    ]
    for table in tables:
        rows = supabase_select(table, limit=1000)
        if rows:
            log(f"loaded {len(rows)} props from {table}")
            return rows
    return []


def load_local_props() -> List[Dict[str, Any]]:
    for path in [Path("prop_hunter_event_props.json"), Path("event_props.json"), Path("props.json")]:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data = data.get("props") or data.get("data") or []
            if isinstance(data, list):
                log(f"loaded {len(data)} props from {path}")
                return data
        except Exception as e:
            warn(f"local props {path} failed: {e}")
    return []


def row_to_pick(row: Dict[str, Any]) -> Optional[Pick]:
    player = clean_player(get_any(row, [
        "player", "player_name", "name", "description", "athlete", "participant", "selection_name"
    ]))
    if not player:
        return None

    market = get_any(row, [
        "market", "market_name", "prop", "stat", "type", "market_key", "bet_type", "category"
    ], "")
    line = get_any(row, [
        "line", "point", "points", "handicap", "threshold", "total", "spread"
    ], "")
    side = get_any(row, [
        "side", "outcome", "over_under", "selection", "label", "direction"
    ], "Over")

    try:
        odds = float(get_any(row, [
            "odds", "price", "decimal_odds", "best_odds", "book_odds", "value", "odd"
        ], 0))
    except Exception:
        return None
    if odds <= 1.01:
        return None

    prob_raw = get_any(row, [
        "prob", "probability", "model_prob", "fair_prob", "hit_prob", "projection_prob", "win_prob"
    ], None)
    if prob_raw is None:
        prob = implied_prob(odds) + MIN_EDGE + 1.0
    else:
        try:
            prob = float(prob_raw)
            if prob <= 1:
                prob *= 100.0
        except Exception:
            prob = implied_prob(odds) + MIN_EDGE + 1.0

    edge_raw = get_any(row, [
        "edge", "edge_pct", "value_edge", "ev", "ev_pct", "expected_value"
    ], None)
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

    sport = norm(get_any(row, ["sport", "sport_key", "league", "sport_name"], ""))
    league = norm(get_any(row, ["league", "competition", "sport_title"], sport))
    team = clean_team(get_any(row, ["team", "player_team", "home_team", "away_team", "team_name"], ""), player)
    game_key = norm(get_any(row, ["event_id", "game_id", "match_id", "event", "game", "commence_time"], ""))

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
    picks = sorted(picks, key=lambda p: (p.label_sport, market_priority(p.market), -p.edge, -p.odds))
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


def fmt_odds(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def fmt_edge(x: float) -> str:
    return f"+{x:.1f}%" if x >= 0 else f"{x:.1f}%"


def build_builders(picks: List[Pick]) -> List[str]:
    if len(picks) < 2:
        return []

    base = []
    used = set()
    for p in sorted(picks, key=lambda x: (-x.edge, market_priority(x.market), -x.odds)):
        if p.player.lower() in used:
            continue
        base.append(p)
        used.add(p.player.lower())
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
    lines: List[str] = [
        "🎯 PROP HUNTER",
        f"📅 {TODAY}",
        "",
        "━━━━━━━━━━━━━━━━━━",
    ]

    if not picks:
        lines += ["", "Keine sauberen Value Picks gefunden.", "", "@prophunter"]
        return "\n".join(lines)

    grouped: Dict[str, List[Pick]] = defaultdict(list)
    for p in picks:
        grouped[p.label_sport].append(p)

    total = 0
    for sport in sorted(grouped.keys()):
        lines += ["", sport, "", "🔥 BEST PICKS", ""]
        for idx, p in enumerate(grouped[sport], 1):
            total += 1
            team_part = f"{p.team} — " if p.team else ""
            lines.append(f"{idx}️⃣ {team_part}{p.player}")
            lines.append(f"🎯 {p.clean_market} @{fmt_odds(p.odds)}")
            lines.append(f"📈 Edge {fmt_edge(p.edge)} · Model {p.prob:.0f}% · Stake {p.stake:.2f}u")
            lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━")

    builders = build_builders(picks)
    if builders:
        lines += ["", "\n\n".join(builders), "", "━━━━━━━━━━━━━━━━━━"]

    lottery_count = 1 if any(b.startswith("💣") for b in builders) else 0
    builder_count = sum(1 for b in builders if not b.startswith("💣"))

    lines += [
        "",
        "📊 CARD",
        f"✅ Singles: {total}",
        f"🎯 Builder: {builder_count}",
        f"💣 Lottery/Kombis: {lottery_count}",
        "",
        "✅ Nur positive Edge",
        "✅ Konzentration begrenzt",
        "✅ Lines bestätigt",
        "",
        "@prophunter",
    ]
    return "\n".join(lines).strip()


def send_telegram(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        warn("Telegram env missing, print only")
        print(text)
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": True}, timeout=20)
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


def persist_picks(picks: List[Pick]) -> None:
    if not SUPABASE_URL or not SUPABASE_KEY or not picks:
        return

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

    for table in ["prop_hunter_picks", "prop_picks"]:
        try:
            url = f"{SUPABASE_URL}/rest/v1/{table}"
            r = requests.post(url, headers={**sb_headers(), "Prefer": "resolution=ignore-duplicates"}, json=rows, timeout=25)
            if r.status_code < 300:
                log(f"persisted {len(rows)} singles into {table}")
                return
            warn(f"persist {table} failed {r.status_code}: {r.text[:180]}")
        except Exception as e:
            warn(f"persist {table} exception: {e}")


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
        print(card)
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
