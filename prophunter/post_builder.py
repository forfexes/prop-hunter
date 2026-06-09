"""Build the Telegram message body from validated picks."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from .models import Pick


def build_post(picks: List[Pick]) -> str:
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    singles  = [p for p in picks if p.type == "single"]
    ladders  = [p for p in picks if p.type == "ladder"]
    builders = [p for p in picks if p.type == "betbuilder"]
    kombis   = [p for p in picks if p.type == "kombi2"]
    bigs     = [p for p in picks if p.type in ("big", "super")]

    tier2 = [p for p in singles if (p.tier or 1) == 2]
    tier1 = [p for p in singles if (p.tier or 1) != 2]

    out = [f"🎯 PROP HUNTER — {today}", ""]

    def fmt_single(p: Pick, header_emoji: str) -> str:
        m = p.market or ""
        if p.direction == "under" and "under" not in m.lower():
            m = f"UNDER {m}"
        line = f"{header_emoji} {p.team or ''} — {p.player}\n"
        line += f"   └ {m} @{p.odds:.2f} → {p.stake}u"
        if p.edge_pct is not None:
            line += f"  (edge {p.edge_pct:+.1f}%)"
        if p.analysis:
            line += f"\n   💡 {p.analysis}"
        return line

    if tier2:
        out.append("🔵 STABILE PICKS (High Confidence):")
        out.append("")
        for p in tier2:
            out.append(fmt_single(p, p.emoji or "🏀"))
            out.append("")

    if tier1:
        out.append("🟡 VALUE PICKS:")
        out.append("")
        for p in tier1:
            out.append(fmt_single(p, p.emoji or "⚾"))
            out.append("")

    if not singles and (ladders or builders or kombis or bigs):
        out.append("📋 SPECIAL PICKS:")
        out.append("")

    if ladders:
        out.append("🪜 LADDERS:")
        for p in ladders:
            for leg in (p.picks or []):
                out.append(f"• {p.player} {leg.market} @{leg.odds:.2f} → {leg.stake}u")
        out.append("")

    if builders:
        out.append("🎯 BET BUILDER:")
        for p in builders:
            out.append(f"• {' + '.join(p.legs or [])} @{p.odds:.2f} → {p.stake}u")
        out.append("")

    if kombis:
        out.append("🔥 2-LEG KOMBIS:")
        for p in kombis:
            out.append(f"• {' + '.join(p.legs or [])} @{p.odds:.2f} → {p.stake}u")
        out.append("")

    if bigs:
        out.append("💣 LOTTERY BIGS:")
        for p in bigs:
            prefix = "🚀" if p.type == "super" else "•"
            out.append(f"{prefix} {' + '.join(p.legs or [])} @{p.odds:.1f} → {p.stake}u")
        out.append("")

    out.append("📊 ANALYSIERT · GEZIELT · GEWONNEN 🎯")
    out.append("@prophunter")
    return "\n".join(out)
