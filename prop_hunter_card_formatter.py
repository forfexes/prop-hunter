#!/usr/bin/env python3
"""Telegram card formatter overlay for structured PROP HUNTER builders.

Also installs a small persistence overlay when imported from the live card
process.  This keeps builder profile/EV/audit metadata in picks_history.json so
settlement and later learning do not lose the context used to create the card.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Iterable

PROFILE_HEADINGS = (
    ("safe", "🛡️ SAFE SGP:"),
    ("value", "🎯 VALUE SGP:"),
    ("aggressive", "🔥 AGGRESSIVE SGP:"),
    ("longshot", "💣 LONGSHOT SGP:"),
    ("generic", "🎯 BET BUILDER:"),
)


def _fmt_odds(v):
    try: return f"{float(v):.2f}"
    except Exception: return str(v or "?")


def _fmt_stake(v):
    try:
        x=float(v)
        s=f"{x:.2f}".rstrip("0").rstrip(".")
        return s
    except Exception:return str(v or "0")


def _profile(p: Any) -> str:
    feats=getattr(p,"features",{}) or {}
    value=str(feats.get("builder_profile") or "").lower()
    if value in {"safe","value","aggressive","longshot"}: return value
    cat=str(getattr(p,"category","") or "").lower()
    for key in ("safe","value","aggressive","longshot"):
        if key in cat:return key
    return "generic"


def _builder_block(builders: Iterable[Any]) -> str:
    grouped={k:[] for k,_ in PROFILE_HEADINGS}
    for p in builders or []: grouped[_profile(p)].append(p)
    out=[]
    for key,heading in PROFILE_HEADINGS:
        items=grouped[key]
        if not items: continue
        out.append(heading)
        for p in items:
            feats=getattr(p,"features",{}) or {}
            legs=list(getattr(p,"legs",None) or [])
            label=getattr(p,"market",None) or f"{len(legs)}-Leg Builder"
            same=" · Same-Player" if feats.get("same_player_multistat") else ""
            out.append(f"• {label} @{_fmt_odds(getattr(p,'odds',None))} → {_fmt_stake(getattr(p,'stake',0))}u{same}")
            for i,leg in enumerate(legs):
                branch="└" if i==len(legs)-1 else "├"
                out.append(f"  {branch} {leg}")
            meta=[]
            prob=getattr(p,"probability",None); edge=getattr(p,"edge_pct",None)
            if prob is not None:
                try: meta.append(f"Prob {float(prob)*100:.1f}%")
                except Exception: pass
            if edge is not None:
                try: meta.append(f"Edge {float(edge):+.1f}%")
                except Exception: pass
            if meta: out.append("  📈 " + " · ".join(meta))
            if feats.get("builder_odds_estimated_from_legs"):
                out.append("  ⚠️ SGP-Kombiquote aus Leg-Quoten — finale Book-Quote bestätigen")
        out.append("")
    return "\n".join(out).rstrip()


def install(base_build_post):
    """Return build_post overlay that only replaces the generic builder section."""
    def wrapped(picks):
        text=base_build_post(picks)
        builders=[p for p in (picks or []) if getattr(p,"type",None)=="betbuilder"]
        if not builders or "🎯 BET BUILDER:" not in text:
            return text
        start=text.find("🎯 BET BUILDER:")
        if start<0:return text
        tail=text[start:]
        markers=("\n🔥 2-LEG KOMBIS:","\n🔥 3-LEG TRIPLES:","\n💣 LOTTERY BIGS:","\n📊 Mehr Value Picks")
        ends=[tail.find(m) for m in markers if tail.find(m)>=0]
        end_rel=min(ends) if ends else len(tail)
        end=start+end_rel
        replacement=_builder_block(builders)
        prefix=text[:start].rstrip()
        suffix=text[end:].lstrip("\n")
        return prefix+"\n"+replacement+"\n\n"+suffix
    return wrapped


_COMBO_TYPES={"kombi2","kombi3","big","super","lottery","betbuilder","ladder"}


def install_persistence(module: Any) -> bool:
    """Preserve builder/ladders metadata after the legacy persist() call.

    The legacy history format remains untouched; we only enrich the combo rows
    that were just appended.  This makes profile, EV, game, source and SGP quote
    provenance available to settlement/auditing/learning without a SQL change.
    """
    if module is None or getattr(module, "_ph_combo_metadata_persistence_installed", False):
        return False
    if not all(hasattr(module, name) for name in ("persist", "load_history", "save_history")):
        return False

    base_persist=module.persist

    def wrapped(picks, telegram_message_id=None, telegram_text=None):
        result=base_persist(picks, telegram_message_id, telegram_text)
        try:
            combos=[p for p in (picks or []) if getattr(p,"type",None) in _COMBO_TYPES]
            if not combos:
                return result
            history=module.load_history()
            today=datetime.now(timezone.utc).strftime("%Y-%m-%d")
            entry=next((e for e in reversed(history or []) if e.get("date")==today),None)
            if not entry:
                return result
            rows=list(entry.get("kombis") or [])
            if len(rows)<len(combos):
                return result
            target=rows[-len(combos):]
            for row,pick in zip(target,combos):
                feats=dict(getattr(pick,"features",{}) or {})
                row["features"]=feats
                row["edge_pct"]=getattr(pick,"edge_pct",None)
                row["ev"]=getattr(pick,"ev",None)
                row["game"]=getattr(pick,"game",None)
                row["analysis"]=getattr(pick,"analysis",None)
                row["bookmaker"]=feats.get("bookmaker")
                row["source"]=feats.get("source")
                row["builder_profile"]=feats.get("builder_profile")
                row["builder_odds_estimated_from_legs"]=bool(feats.get("builder_odds_estimated_from_legs"))
                row["same_player_multistat"]=bool(feats.get("same_player_multistat"))
            entry["kombis"]=rows
            module.save_history(history)
        except Exception as exc:
            try: module.log.warning("combo metadata persistence: %s",exc)
            except Exception: pass
        return result

    module.persist=wrapped
    module._ph_combo_metadata_persistence_installed=True
    return True


def _auto_install_persistence() -> None:
    try:
        import sys
        for name in ("prophunter","__main__"):
            install_persistence(sys.modules.get(name))
    except Exception:
        pass


_auto_install_persistence()
