#!/usr/bin/env python3
"""Telegram card formatter overlay for structured PROP HUNTER builders.

Also installs a persistence overlay so builder context and EuroLeague sport
identity survive the legacy history/database persistence path.
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
    try:return f"{float(v):.2f}"
    except Exception:return str(v or "?")


def _fmt_stake(v):
    try:
        x=float(v);return f"{x:.2f}".rstrip("0").rstrip(".")
    except Exception:return str(v or "0")


def _profile(p: Any) -> str:
    feats=getattr(p,"features",{}) or {};value=str(feats.get("builder_profile") or "").lower()
    if value in {"safe","value","aggressive","longshot"}:return value
    cat=str(getattr(p,"category","") or "").lower()
    for key in ("safe","value","aggressive","longshot"):
        if key in cat:return key
    return "generic"


def _builder_block(builders: Iterable[Any]) -> str:
    grouped={k:[] for k,_ in PROFILE_HEADINGS}
    for p in builders or []:grouped[_profile(p)].append(p)
    out=[]
    for key,heading in PROFILE_HEADINGS:
        items=grouped[key]
        if not items:continue
        out.append(heading)
        for p in items:
            feats=getattr(p,"features",{}) or {};legs=list(getattr(p,"legs",None) or [])
            label=getattr(p,"market",None) or f"{len(legs)}-Leg Builder";same=" · Same-Player" if feats.get("same_player_multistat") else ""
            out.append(f"• {label} @{_fmt_odds(getattr(p,'odds',None))} → {_fmt_stake(getattr(p,'stake',0))}u{same}")
            for i,leg in enumerate(legs):out.append(f"  {'└' if i==len(legs)-1 else '├'} {leg}")
            meta=[];prob=getattr(p,"probability",None);edge=getattr(p,"edge_pct",None)
            if prob is not None:
                try:meta.append(f"Prob {float(prob)*100:.1f}%")
                except Exception:pass
            if edge is not None:
                try:meta.append(f"Edge {float(edge):+.1f}%")
                except Exception:pass
            if meta:out.append("  📈 "+" · ".join(meta))
            if feats.get("builder_odds_estimated_from_legs"):out.append("  ⚠️ SGP-Kombiquote aus Leg-Quoten — finale Book-Quote bestätigen")
        out.append("")
    return "\n".join(out).rstrip()


def install(base_build_post):
    def wrapped(picks):
        text=base_build_post(picks);builders=[p for p in (picks or []) if getattr(p,"type",None)=="betbuilder"]
        if not builders or "🎯 BET BUILDER:" not in text:return text
        start=text.find("🎯 BET BUILDER:")
        if start<0:return text
        tail=text[start:];markers=("\n🔥 2-LEG KOMBIS:","\n🔥 3-LEG TRIPLES:","\n💣 LOTTERY BIGS:","\n📊 Mehr Value Picks")
        ends=[tail.find(m) for m in markers if tail.find(m)>=0];end=start+(min(ends) if ends else len(tail))
        return text[:start].rstrip()+"\n"+_builder_block(builders)+"\n\n"+text[end:].lstrip("\n")
    return wrapped


_COMBO_TYPES={"kombi2","kombi3","big","super","lottery","betbuilder","ladder"}

def _is_euroleague_pick(pick: Any) -> bool:
    feats=getattr(pick,"features",{}) or {}
    values=(getattr(pick,"source_sport",None),getattr(pick,"sport",None),feats.get("sport"),feats.get("league"),feats.get("source_sport"))
    return any("EUROLEAGUE" in str(v or "").upper().replace("_","").replace("-","") for v in values)


def _fix_euroleague_db(module: Any, dedup_keys) -> None:
    if not dedup_keys or not hasattr(module,"_get_sb"):return
    try:sb=module._get_sb()
    except Exception:return
    if not sb:return
    for dk in dedup_keys:
        try:
            sb.table("prop_picks").update({"sport":"EUROLEAGUE","league":"EUROLEAGUE"}).eq("dedup_key",dk).execute()
        except Exception:
            try:sb.table("prop_picks").update({"sport":"EUROLEAGUE"}).eq("dedup_key",dk).execute()
            except Exception:pass


def install_persistence(module: Any) -> bool:
    """Preserve builder metadata and repair EuroLeague identity after legacy persist."""
    if module is None or getattr(module,"_ph_combo_metadata_persistence_installed",False):return False
    if not all(hasattr(module,name) for name in ("persist","load_history","save_history")):return False
    base_persist=module.persist

    def wrapped(picks,telegram_message_id=None,telegram_text=None):
        result=base_persist(picks,telegram_message_id,telegram_text)
        try:
            all_picks=list(picks or []);combos=[p for p in all_picks if getattr(p,"type",None) in _COMBO_TYPES]
            euro=[p for p in all_picks if _is_euroleague_pick(p)]
            if not combos and not euro:return result
            history=module.load_history();today=datetime.now(timezone.utc).strftime("%Y-%m-%d");entry=next((e for e in reversed(history or []) if e.get("date")==today),None)
            if not entry:return result
            rows=list(entry.get("kombis") or [])
            if combos and len(rows)>=len(combos):
                target=rows[-len(combos):]
                for row,pick in zip(target,combos):
                    feats=dict(getattr(pick,"features",{}) or {});row["features"]=feats;row["edge_pct"]=getattr(pick,"edge_pct",None);row["ev"]=getattr(pick,"ev",None);row["game"]=getattr(pick,"game",None);row["analysis"]=getattr(pick,"analysis",None);row["bookmaker"]=feats.get("bookmaker");row["source"]=feats.get("source");row["builder_profile"]=feats.get("builder_profile");row["builder_odds_estimated_from_legs"]=bool(feats.get("builder_odds_estimated_from_legs"));row["same_player_multistat"]=bool(feats.get("same_player_multistat"))
                    if _is_euroleague_pick(pick):row["sport"]="EUROLEAGUE"
                entry["kombis"]=rows
            euro_keys=[]
            if euro and hasattr(module,"dedup_key"):
                for pick in euro:
                    if getattr(pick,"type",None)!="single":continue
                    dk=module.dedup_key(getattr(pick,"player","") or "",getattr(pick,"market","") or "",getattr(pick,"point",None),getattr(pick,"direction",None));euro_keys.append(dk)
                    for hist_row in reversed(entry.get("picks") or []):
                        if hist_row.get("dedup_key")==dk:
                            hist_row["sport"]="EUROLEAGUE";raw=hist_row.get("raw") if isinstance(hist_row.get("raw"),dict) else {};raw["league"]="EUROLEAGUE";hist_row["raw"]=raw;break
            module.save_history(history);_fix_euroleague_db(module,euro_keys)
        except Exception as exc:
            try:module.log.warning("combo/euroleague metadata persistence: %s",exc)
            except Exception:pass
        return result

    module.persist=wrapped;module._ph_combo_metadata_persistence_installed=True;return True


def _auto_install_persistence() -> None:
    try:
        import sys
        for name in ("prophunter","__main__"):install_persistence(sys.modules.get(name))
    except Exception:pass

_auto_install_persistence()
