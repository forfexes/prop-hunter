#!/usr/bin/env python3
"""
PROP HUNTER v5 RUNTIME PATCH
----------------------------
Legt v5-Verhalten über die bestehende prophunter.py:
- keine harte Gesamtlimitierung guter Singles
- negative Edge bleibt gesperrt
- JK-Style Telegram Card
- Sport-Gruppen: WNBA/NBA/MLB/NFL
- Builder-Klassen: Safe / Value / Lottery
- bessere Market-Namen: 3PM => 3er, PRA bleibt sichtbar

Wichtig: Diese Datei wird im GitHub Workflow vor `python prophunter.py` ausgeführt.
Sie ersetzt nur sichere Textstellen/Funktionen in prophunter.py und macht ein Backup.
"""
from __future__ import annotations

from pathlib import Path
import re

TARGET = Path("prophunter.py")
BACKUP = Path("prophunter.py.v4_backup")

NEW_BUILD_POST = r'''
def _ph_v5_float(x, default=0.0):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _ph_v5_stars(p):
    edge = _ph_v5_float(getattr(p, "edge_pct", None), 0.0)
    prob = getattr(p, "probability", None)
    odds = _ph_v5_float(getattr(p, "odds", None), 0.0)
    if edge >= 8.0 or (prob and prob >= 0.66 and odds >= 1.80):
        return "⭐⭐⭐⭐⭐", "ELITE"
    if edge >= 5.0:
        return "⭐⭐⭐⭐", "STRONG VALUE"
    if edge >= 3.0:
        return "⭐⭐⭐", "VALUE"
    return "⭐⭐", "LEAN"


def _ph_v5_sport_name(p):
    s = str(getattr(p, "sport", "") or "").upper()
    g = str(getattr(p, "game", "") or "").upper()
    e = str(getattr(p, "emoji", "") or "")
    raw = " ".join([s, g, e]).upper()
    if "MLB" in raw or "BASEBALL" in raw or e == "⚾":
        return "⚾ MLB"
    if "WNBA" in raw:
        return "🏀 WNBA"
    if "NBA" in raw:
        return "🏀 NBA"
    if "NFL" in raw or e == "🏈":
        return "🏈 NFL"
    if e == "🏀":
        return "🏀 BASKET"
    return "🎯 OTHER"


def _ph_v5_market_name(market, direction=None, point=None):
    m = str(market or "").strip()
    low = m.lower()
    names = {
        "player_points_rebounds_assists": "PRA",
        "points_rebounds_assists": "PRA",
        "player_points_rebounds": "Punkte+Rebounds",
        "player_points_assists": "Punkte+Assists",
        "player_rebounds_assists": "Rebounds+Assists",
        "player_threes_alternate": "3er",
        "player_3pm": "3er",
        "3pm": "3er",
        "player_points_alternate": "Punkte",
        "player_rebounds_alternate": "Rebounds",
        "player_assists_alternate": "Assists",
        "batter_home_runs": "Home Run",
        "batter_hits": "Hits",
        "batter_total_bases": "Total Bases",
        "pitcher_strikeouts": "Pitcher Strikeouts",
        "pitcher_outs": "Pitcher Outs",
    }
    label = names.get(low, m.replace("player_", "").replace("batter_", "").replace("pitcher_", "").replace("_", " ").title())
    d = (direction or "").lower()
    if d == "under" and "under" not in label.lower():
        label += " Under"
    elif d in ("over", "yes", "") and not any(x in label.lower() for x in ["over", "home run", "double double"]):
        label += " Over"
    if point is not None:
        try:
            label += f" {float(point):g}"
        except Exception:
            label += f" {point}"
    return label


def _ph_v5_clean_reason(txt):
    txt = str(txt or "").strip()
    if not txt:
        return "Line bestätigt · positive Edge · Modell über Markt"
    # Debug-Dopplungen raus
    parts = []
    for part in re.split(r"\s*\|\s*", txt):
        p = part.strip()
        pl = p.lower()
        if not p:
            continue
        if pl in ("event props", "data+: basket line vorhanden"):
            continue
        if pl.startswith("fair ") or pl.startswith("edge="):
            continue
        if p not in parts:
            parts.append(p)
    return " · ".join(parts[:3]) or "Line bestätigt · positive Edge · Modell über Markt"


def _ph_v5_pick_line(p, idx):
    stars, tier = _ph_v5_stars(p)
    player = str(getattr(p, "player", "") or "Unknown").strip()
    team = str(getattr(p, "team", "") or "").strip()
    odds = _ph_v5_float(getattr(p, "odds", None), 0.0)
    stake = _ph_v5_float(getattr(p, "stake", None), 0.25)
    edge = getattr(p, "edge_pct", None)
    prob = getattr(p, "probability", None)
    market = _ph_v5_market_name(getattr(p, "market", ""), getattr(p, "direction", None), getattr(p, "point", None))
    reason = _ph_v5_clean_reason(getattr(p, "analysis", ""))
    meta = []
    if edge is not None:
        meta.append(f"Edge {float(edge):+.1f}%")
    if prob is not None:
        meta.append(f"Model {float(prob)*100:.0f}%")
    meta.append(f"Stake {stake:g}u")
    head_team = f"{team} — " if team else ""
    return (
        f"{idx}️⃣ {stars} {tier}\n"
        f"{head_team}{player}\n"
        f"🎯 {market} @ {odds:.2f}\n"
        f"📈 {' · '.join(meta)}\n"
        f"💡 {reason}"
    )


def _ph_v5_leg_text(leg, singles):
    if isinstance(leg, str):
        key = leg
        for s in singles:
            try:
                if dedup_key(getattr(s, "player", None), getattr(s, "market", None), getattr(s, "point", None), getattr(s, "direction", None)) == key:
                    return f"{getattr(s,'player','')} {_ph_v5_market_name(getattr(s,'market',''), getattr(s,'direction',None), getattr(s,'point',None))}"
            except Exception:
                pass
        return key.split("|")[0].title() if "|" in key else key
    player = getattr(leg, "player", "") or ""
    market = _ph_v5_market_name(getattr(leg, "market", ""), getattr(leg, "direction", None), getattr(leg, "point", None))
    return f"{player} {market}".strip()


def build_post(picks):
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    singles = [p for p in picks if getattr(p, "type", None) == "single"]
    builders = [p for p in picks if getattr(p, "type", None) == "betbuilder"]
    kombis = [p for p in picks if getattr(p, "type", None) == "kombi2"]
    bigs = [p for p in picks if getattr(p, "type", None) in ("big", "super")]

    # Safety: negative Edge nie posten, aber KEIN hartes Gesamtlimit mehr.
    clean_singles = []
    seen = set()
    per_player = {}
    per_game = {}
    for p in sorted(singles, key=lambda x: (_ph_v5_float(getattr(x,"edge_pct",0)), _ph_v5_float(getattr(x,"odds",0))), reverse=True):
        edge = getattr(p, "edge_pct", None)
        if edge is not None and float(edge) < 0:
            continue
        player = str(getattr(p, "player", "") or "").lower().strip()
        game = str(getattr(p, "game", "") or getattr(p, "team", "") or "unknown").lower().strip()
        key = dedup_key(getattr(p,"player",None), getattr(p,"market",None), getattr(p,"point",None), getattr(p,"direction",None))
        if key in seen:
            continue
        # Konzentration begrenzen, nicht die Gesamtkarte.
        if per_player.get(player, 0) >= int(os.environ.get("PH_MAX_PER_PLAYER", "3")):
            continue
        if per_game.get(game, 0) >= int(os.environ.get("PH_MAX_PER_GAME", "6")):
            continue
        seen.add(key)
        per_player[player] = per_player.get(player, 0) + 1
        per_game[game] = per_game.get(game, 0) + 1
        clean_singles.append(p)

    grouped = {}
    for p in clean_singles:
        grouped.setdefault(_ph_v5_sport_name(p), []).append(p)

    order = ["🏀 WNBA", "🏀 NBA", "⚾ MLB", "🏈 NFL", "🏀 BASKET", "🎯 OTHER"]
    out = [f"🔥 PROP HUNTER v5 — JK STYLE", f"📅 {today}", "", "━━━━━━━━━━━━━━━━━━", ""]

    total_singles = 0
    for sport in order:
        arr = grouped.get(sport, [])
        if not arr:
            continue
        total_singles += len(arr)
        out += [sport, ""]
        elite = [p for p in arr if _ph_v5_float(getattr(p,"edge_pct",0)) >= 8]
        strong = [p for p in arr if 5 <= _ph_v5_float(getattr(p,"edge_pct",0)) < 8]
        value = [p for p in arr if _ph_v5_float(getattr(p,"edge_pct",0)) < 5]
        blocks = [("🔥 ELITE PICKS", elite), ("💎 STRONG VALUE", strong), ("🟡 VALUE PICKS", value)]
        idx = 1
        for title, items in blocks:
            if not items:
                continue
            out += [title, ""]
            for p in items:
                out += [_ph_v5_pick_line(p, idx), ""]
                idx += 1
        out += ["━━━━━━━━━━━━━━━━━━", ""]

    def add_combo_section(title, items, max_items=None):
        if not items:
            return
        out.extend([title, ""])
        selected = items[:max_items] if max_items else items
        for p in selected:
            legs = [_ph_v5_leg_text(x, clean_singles) for x in (getattr(p, "legs", None) or [])]
            odds = _ph_v5_float(getattr(p, "odds", None), 0.0)
            stake = _ph_v5_float(getattr(p, "stake", None), 0.25)
            if legs:
                out.append("✅ " + "\n+\n✅ ".join(legs))
                out.append(f"💰 Quote: {odds:.2f} · Einsatz {stake:g}u")
                out.append("")
        out.append("━━━━━━━━━━━━━━━━━━")
        out.append("")

    safe_builders = [b for b in builders if 1.7 <= _ph_v5_float(getattr(b,"odds",0)) <= 4.0]
    value_builders = [b for b in builders if 4.0 < _ph_v5_float(getattr(b,"odds",0)) <= 10.0]
    add_combo_section("🎯 SAFE BUILDER", safe_builders)
    add_combo_section("💎 VALUE BUILDER", value_builders)
    add_combo_section("🔥 2-LEG KOMBIS", kombis)
    add_combo_section("💣 LOTTERY BIGS", bigs)

    out += [
        "📊 CARD",
        f"✅ Singles: {total_singles}",
        f"🎯 Builder: {len(builders)}",
        f"💣 Lottery/Kombis: {len(kombis) + len(bigs)}",
        "",
        "✅ Nur positive Edge",
        "✅ Keine harte Pick-Begrenzung",
        "✅ Max Konzentration pro Spieler/Spiel",
        "✅ Lines Pflicht",
        "",
        "@prophunter",
    ]
    return "\n".join(out).strip()
'''


def replace_constant(text: str, name: str, value: str) -> str:
    return re.sub(rf"^{name}\s*=\s*[^\n]+", f"{name:<23}= {value}", text, flags=re.M)


def replace_build_post(text: str) -> str:
    m = re.search(r"\n# ─+\n# POST BUILDER\n# ─+\n", text)
    if not m:
        raise SystemExit("POST BUILDER section not found")
    start = m.end()
    next_m = re.search(r"\n# ─+\n# ", text[start:])
    if not next_m:
        raise SystemExit("End of POST BUILDER section not found")
    end = start + next_m.start()
    return text[:start] + NEW_BUILD_POST.strip() + "\n" + text[end:]


def patch_run_log(text: str) -> str:
    text = text.replace("PROP HUNTER v4 DATA+ TEAM-SAFE", "PROP HUNTER v5 JK STYLE")
    text = text.replace("PROP HUNTER v4", "PROP HUNTER v5")
    text = text.replace("PROP HUNTER v3", "PROP HUNTER v5")
    return text


def main() -> None:
    if not TARGET.exists():
        raise SystemExit("prophunter.py not found")
    original = TARGET.read_text(encoding="utf-8")
    if not BACKUP.exists():
        BACKUP.write_text(original, encoding="utf-8")

    text = original
    # Mehr Picks erlauben; Qualität bleibt über Edge/Line/Concentration gesichert.
    replacements = {
        "MAX_SINGLES_TOTAL": "999",
        "MAX_HR_SINGLES": "20",
        "MAX_COMBOS_TOTAL": "20",
        "MAX_LOTTERY_TOTAL": "10",
        "MAX_LOTTERY_LEGS": "4",
        "MAX_EVENTS": "30",
        "LOOKAHEAD_H": "36",
        "MAX_PROPS_AI": "160",
    }
    for k, v in replacements.items():
        text = replace_constant(text, k, v)

    # Optional niedrigere Basket-Min-Odds, damit 1.70-2.50 und PRA/PR/PA nicht wegfallen.
    text = text.replace('Market("player_points_rebounds_assists","PRA",20,1.8)', 'Market("player_points_rebounds_assists","PRA",20,1.65)')
    text = text.replace('Market("player_rebounds_assists","Rebounds+Assists",8,1.8)', 'Market("player_rebounds_assists","Rebounds+Assists",8,1.65)')

    text = replace_build_post(text)
    text = patch_run_log(text)

    TARGET.write_text(text, encoding="utf-8")
    print("✅ PROP HUNTER v5 patch applied: JK style, more picks, builder classes, evening-ready")


if __name__ == "__main__":
    main()
