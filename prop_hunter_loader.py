#!/usr/bin/env python3
"""
PROP HUNTER - prop_hunter_loader.py (mit EV-Filter)
Lädt Props in Supabase + berechnet echten Expected Value.
"""

import argparse, json, os
from typing import Any, Dict, List
from collections import defaultdict
import requests
from supabase import create_client, Client

TABLE_NAME = "american_player_props"

def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Fehlt: SUPABASE_URL oder SUPABASE_KEY")
    return create_client(url, key)

def load_rows(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def clean_row(r: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {"source","sport","event_id","commence_time","home_team","away_team",
               "bookmaker","bookmaker_title","market_key","market_last_update",
               "player_name","selection","line","american_odds","decimal_odds",
               "implied_probability","raw","created_at_utc"}
    return {k: v for k, v in r.items() if k in allowed}

def upsert_rows(rows: List[Dict[str, Any]], batch_size: int = 500) -> int:
    if not rows: return 0
    supabase = get_supabase()
    cleaned = [clean_row(r) for r in rows]
    total = 0
    for i in range(0, len(cleaned), batch_size):
        batch = cleaned[i:i+batch_size]
        supabase.table(TABLE_NAME).upsert(
            batch,
            on_conflict="source,sport,event_id,bookmaker,market_key,player_name,selection,line",
        ).execute()
        total += len(batch)
        print(f"[OK] Upsert Batch: {len(batch)}")
    return total

def calculate_ev_candidates(rows: List[Dict[str, Any]], min_ev: float = 0.02, limit: int = 10) -> List[Dict[str, Any]]:
    """No-Vig EV: vergleicht jeden Bookie gegen Markt-Durchschnitt."""
    market_groups = defaultdict(list)
    for r in rows:
        if not r.get("decimal_odds") or not r.get("implied_probability"):
            continue
        key = (r["event_id"], r.get("player_name",""), r["market_key"], r.get("line"), r.get("selection",""))
        market_groups[key].append(r)

    candidates = []
    for key, group in market_groups.items():
        if len(group) < 2: continue
        # No-Vig: Durchschnitt der implizierten Wahrscheinlichkeiten
        avg_implied = sum(item["implied_probability"] for item in group) / len(group)
        for r in group:
            ev = (avg_implied * r["decimal_odds"]) - 1
            if ev >= min_ev:
                c = dict(r)
                c["calculated_ev"] = round(ev * 100, 2)
                c["num_bookmakers"] = len(group)
                candidates.append(c)

    candidates.sort(key=lambda x: x["calculated_ev"], reverse=True)
    return candidates[:limit]

def telegram_send(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id: return
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True},
        timeout=20)
    print(f"[TELEGRAM] {r.status_code}")

def build_report(rows: List[Dict[str, Any]], inserted: int) -> str:
    sports = sorted(set(r.get("sport","?") for r in rows))
    events = set(r.get("event_id","?") for r in rows)
    players = set(r.get("player_name","?") for r in rows if r.get("player_name"))
    candidates = calculate_ev_candidates(rows, min_ev=0.02, limit=5)

    SPORT_EMOJI = {"baseball_mlb":"⚾","basketball_nba":"🏀",
                   "americanfootball_nfl":"🏈","icehockey_nhl":"🏒",
                   "basketball_wnba":"🏀"}
    sport_str = " ".join(SPORT_EMOJI.get(s,s) for s in sports)

    text = (f"🎯 <b>PROP HUNTER Tracker</b>\n\n"
            f"Sport: <b>{sport_str}</b>\n"
            f"Events: <b>{len(events)}</b> | Spieler: <b>{len(players)}</b>\n"
            f"Props gespeichert: <b>{inserted}</b>\n\n"
            "🔥 <b>Top +EV Value Bets</b>\n")

    if not candidates:
        text += "Keine Ausreißer vom Marktschnitt gefunden."
        return text

    for c in candidates:
        market = c.get("market_key","").replace("player_","").replace("batter_","").replace("pitcher_","")
        text += (
            f"• <b>{c.get('player_name')}</b>\n"
            f"  {c.get('away_team')} @ {c.get('home_team')}\n"
            f"  {market} | {c.get('selection')} {c.get('line')}\n"
            f"  Quote: <b>{c.get('decimal_odds')}</b> @ {c.get('bookmaker_title')}\n"
            f"  🔥 EV: <b>+{c.get('calculated_ev')}%</b> ({c.get('num_bookmakers')} Bookies)\n\n"
        )
    return text

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="american_props_output.json")
    parser.add_argument("--print-sql", action="store_true")
    parser.add_argument("--telegram", action="store_true")
    args = parser.parse_args()

    if args.print_sql:
        print("""
create table if not exists american_player_props (
  id bigserial primary key,
  source text not null, sport text not null,
  event_id text not null, commence_time timestamptz,
  home_team text, away_team text,
  bookmaker text, bookmaker_title text,
  market_key text not null, market_last_update timestamptz,
  player_name text not null, selection text,
  line numeric, american_odds numeric,
  decimal_odds numeric, implied_probability numeric,
  raw jsonb, created_at_utc timestamptz,
  inserted_at timestamptz default now(),
  unique(source,sport,event_id,bookmaker,market_key,player_name,selection,line)
);
alter table american_player_props disable row level security;
""")
        return

    rows = load_rows(args.input)
    inserted = upsert_rows(rows)
    report = build_report(rows, inserted)
    print(report)
    if args.telegram:
        telegram_send(report)

if __name__ == "__main__":
    main()
