#!/usr/bin/env python3
"""Small parser extensions for direct keyless sportsbook feeds.

Keeps the upstream keyless adapter compact while teaching it additional prop
families observed in real sportsbook cards. No login/browser behavior is added.
"""
from __future__ import annotations
import re

EXTRA_SUFFIXES = (
    "triple double", "double double",
    "points rebounds assists", "points rebounds", "points assists", "rebounds assists",
    "rushing attempts", "rush attempts", "carries",
    "passing completions", "pass completions", "completions",
    "passing attempts", "pass attempts",
    "receiving targets", "targets",
    "passing touchdowns", "rushing touchdowns", "receiving touchdowns",
    "touchdowns", "touchdown",
    "tackles assists", "tackles + assists", "tackles", "sacks", "interceptions",
)


def _norm(v):
    return re.sub(r"[^a-z0-9]+", " ", str(v or "").lower()).strip()


def install(kb):
    if getattr(kb, "_ph_keyless_extensions_installed", False):return kb
    old_mk=kb._mk;old_player_market=kb._player_market

    def market_key(value):
        s=_norm(value)
        direct=(
            (("triple double",),"triple_double"),(("double double",),"double_double"),
            (("points rebounds assists","points rebounds and assists","pra"),"pra"),
            (("points rebounds","points and rebounds"),"pr"),(("points assists","points and assists"),"pa"),
            (("rebounds assists","rebounds and assists"),"ra"),
            (("rushing attempts","rush attempts","carries"),"rushing_attempts"),
            (("passing completions","pass completions","completions"),"passing_completions"),
            (("passing attempts","pass attempts"),"passing_attempts"),(("receiving targets","targets"),"receiving_targets"),
            (("rushing touchdowns","rush touchdowns","rush tds"),"rushing_touchdowns"),
            (("receiving touchdowns","receiving tds"),"receiving_touchdowns"),
            (("tackles assists","tackles and assists"),"tackles_assists"),(("tackles",),"tackles"),(("sacks",),"sacks"),(("interceptions",),"interceptions"),
        )
        for needles,key in direct:
            if any(n in s for n in needles):return key
        return old_mk(value)

    def player_market(text):
        found=old_player_market(text)
        if found:return found
        raw=re.sub(r"\s+O/U\s*$","",str(text or ""),flags=re.I).strip();low=_norm(raw)
        for suffix in sorted(EXTRA_SUFFIXES,key=len,reverse=True):
            ns=_norm(suffix)
            if low.endswith(" "+ns):
                raw_words=raw.split();suffix_words=suffix.replace("+"," ").split();cut=len(suffix_words)
                if cut<len(raw_words):return " ".join(raw_words[:-cut]).strip(" -–—:")
        return ""

    kb._mk=market_key;kb._player_market=player_market
    kb.SUFFIXES=tuple(dict.fromkeys(tuple(getattr(kb,"SUFFIXES",()))+EXTRA_SUFFIXES))
    kb.DK_HINTS=tuple(dict.fromkeys(tuple(getattr(kb,"DK_HINTS",()))+("double double","triple double","attempts","completions","carries","targets","tackles","sacks","interceptions")))
    if hasattr(kb,"BOV_PATH"):kb.BOV_PATH.setdefault("EUROLEAGUE","basketball/euroleague")
    if hasattr(kb,"BR_PATH"):kb.BR_PATH.setdefault("EUROLEAGUE","basketball/euroleague")
    kb._ph_keyless_extensions_installed=True
    return kb
