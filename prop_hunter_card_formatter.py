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
    ("acca_safe", "🧩 SAFE ACCA:"),
    ("acca_value", "🧩 VALUE ACCA:"),
    ("acca_aggressive", "🔥 AGGRESSIVE ACCA:"),
    ("acca_lottery", "💣 LOTTERY ACCA:"),
    ("generic", "🎯 BET BUILDER:"),
)

TELEGRAM_SAFE_LIMIT = 3950


def _builder_signature(p: Any):
    legs=[str(x or "").strip().lower() for x in (getattr(p,"legs",None) or []) if str(x or "").strip()]
    if legs:return tuple(sorted(legs))
    return (
        str(getattr(p,"market","") or "").strip().lower(),
        _fmt_odds(getattr(p,"odds",None)),
        str(getattr(p,"player","") or "").strip().lower(),
    )


def _dedupe_builders(builders: Iterable[Any]):
    out=[];seen=set()
    for p in builders or []:
        sig=_builder_signature(p)
        if sig in seen:continue
        seen.add(sig);out.append(p)
    return out


def _builder_sort_key(p: Any):
    order={"safe":8,"value":7,"acca_safe":6,"acca_value":5,"aggressive":4,"acca_aggressive":3,"longshot":2,"acca_lottery":1,"generic":0}
    try:edge=float(getattr(p,"edge_pct",0) or 0)
    except Exception:edge=0.0
    try:prob=float(getattr(p,"probability",0) or 0)
    except Exception:prob=0.0
    return (order.get(_profile(p),0),edge,prob)


def _fmt_odds(v):
    try:return f"{float(v):.2f}"
    except Exception:return str(v or "?")


def _fmt_stake(v):
    try:
        x=float(v);return f"{x:.2f}".rstrip("0").rstrip(".")
    except Exception:return str(v or "0")


def _profile(p: Any) -> str:
    feats=getattr(p,"features",{}) or {};value=str(feats.get("builder_profile") or "").lower()
    if feats.get("combo_scope")=="cross_game":
        return f"acca_{value}" if value in {"safe","value","aggressive","lottery"} else "generic"
    if value in {"safe","value","aggressive","longshot"}:return value
    cat=str(getattr(p,"category","") or "").lower()
    if cat.startswith("acca_"):
        suffix=cat.split("acca_",1)[1]
        if suffix in {"safe","value","aggressive","lottery"}:return f"acca_{suffix}"
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
            if feats.get("combo_scope")=="cross_game":out.append("  🌐 Cross-Game · gleiche Sportsbook-Quelle")
            if feats.get("acca_odds_estimated_from_legs"):out.append("  ⚠️ ACCA-Quote aus Einzelquoten — finale Book-Quote bestätigen")
            elif feats.get("builder_odds_estimated_from_legs"):out.append("  ⚠️ SGP-Kombiquote aus Leg-Quoten — finale Book-Quote bestätigen")
        out.append("")
    return "\n".join(out).rstrip()


def install(base_build_post):
    def wrapped(picks):
        text=base_build_post(picks);builders=_dedupe_builders([p for p in (picks or []) if getattr(p,"type",None)=="betbuilder"])
        if not builders or "🎯 BET BUILDER:" not in text:return text
        start=text.find("🎯 BET BUILDER:")
        if start<0:return text
        tail=text[start:];markers=("\n🔥 2-LEG KOMBIS:","\n🔥 3-LEG TRIPLES:","\n💣 LOTTERY BIGS:","\n📊 Mehr Value Picks")
        ends=[tail.find(m) for m in markers if tail.find(m)>=0];end=start+(min(ends) if ends else len(tail))
        prefix=text[:start].rstrip();suffix=text[end:].lstrip("\n")

        def compose(items, omitted=0, compact_prefix=False):
            pre=prefix
            if compact_prefix:
                pre="\n".join(line for line in pre.splitlines() if not line.lstrip().startswith("💡 "))
            block=_builder_block(items)
            note=f"\n\nℹ️ {omitted} weitere verifizierte Builder im History-Log" if omitted else ""
            return pre+"\n"+block+note+"\n\n"+suffix

        result=compose(builders)
        if len(result)<=TELEGRAM_SAFE_LIMIT:return result

        ranked=sorted(builders,key=_builder_sort_key,reverse=True)
        selected=[]
        for p in ranked:
            candidate=compose(selected+[p],len(ranked)-len(selected)-1,True)
            if len(candidate)<=TELEGRAM_SAFE_LIMIT:selected.append(p)
        result=compose(selected,len(ranked)-len(selected),True)
        if len(result)<=TELEGRAM_SAFE_LIMIT:return result

        # Last-resort safety: old LOTTERY BIGS duplicate information already represented
        # by structured longshot/ACCA profiles. Remove that legacy section before clipping.
        if "\n💣 LOTTERY BIGS:" in result:
            a=result.find("\n💣 LOTTERY BIGS:")
            b=result.find("\n📊 Mehr Value Picks",a)
            if b>a:result=result[:a]+result[b:]
        if len(result)>TELEGRAM_SAFE_LIMIT:
            footer="\n\n📊 Mehr Value Picks · Keine negative Edge · Lines Pflicht 🎯\n@prophunter"
            room=max(200,TELEGRAM_SAFE_LIMIT-len(footer)-2)
            result=result[:room].rsplit("\n",1)[0]+"\n… Karte gekürzt"+footer
        return result
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
                    feats=dict(getattr(pick,"features",{}) or {});row["features"]=feats;row["edge_pct"]=getattr(pick,"edge_pct",None);row["ev"]=getattr(pick,"ev",None);row["game"]=getattr(pick,"game",None);row["analysis"]=getattr(pick,"analysis",None);row["bookmaker"]=feats.get("bookmaker");row["source"]=feats.get("source");row["builder_profile"]=feats.get("builder_profile");row["builder_odds_estimated_from_legs"]=bool(feats.get("builder_odds_estimated_from_legs"));row["acca_odds_estimated_from_legs"]=bool(feats.get("acca_odds_estimated_from_legs"));row["combo_scope"]=feats.get("combo_scope");row["same_player_multistat"]=bool(feats.get("same_player_multistat"))
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
            if telegram_message_id and telegram_text and combos and entry.get("cards"):
                card=next((c for c in reversed(entry.get("cards") or []) if str(c.get("message_id"))==str(telegram_message_id)),None)
                if card:
                    visible=[];seen_sig=set()
                    for row in target:
                        legs=[str(x or "").strip() for x in (row.get("legs") or []) if str(x or "").strip()]
                        sig=tuple(sorted(x.lower() for x in legs)) if legs else (str(row.get("market") or "").lower(),)
                        if sig in seen_sig:continue
                        is_visible=(all(leg in telegram_text for leg in legs) if legs else str(row.get("market") or "") in telegram_text)
                        if is_visible and row.get("combo_id"):
                            seen_sig.add(sig);visible.append(row["combo_id"])
                    card["combo_ids"]=visible
                    card["text"]=telegram_text
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
