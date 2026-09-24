#!/usr/bin/env python3
"""PROP HUNTER V13.9.2 hardened compatibility entrypoint.

This thin entrypoint loads the verified V13.9.1 core into this module namespace and
applies the V13.9.2 safety/source/settlement changes.  Keeping the core separate
lets GitHub reuse the already committed verified blob while preserving one public
``prophunter`` module for imports and Actions.
"""
from pathlib import Path as _PatchPath

_core_path = _PatchPath(__file__).with_name("prophunter_core_1391.py")
_core_source = _core_path.read_text(encoding="utf-8")
# Load the verified core without executing its CLI tail; keep this module's real
# __name__ so Pydantic resolves postponed annotations against the correct module.
_core_source = _core_source.rsplit('if __name__=="__main__":', 1)[0]
exec(compile(_core_source, str(_core_path), "exec"), globals(), globals())

# ---------------------------------------------------------------------------
# V13.9.2 HARDENED SOURCES + SETTLEMENT
# ---------------------------------------------------------------------------
PH_RUNTIME_VERSION = "13.9.2-HARDENED-SOURCES-SETTLEMENT"
BDL_PROPS_ENABLED = str(os.getenv("PH_BDL_PROPS_ENABLED", "0")).lower() in {"1", "true", "yes", "on"}
SPORTSGAMEODDS_KEY = (
    os.environ.get("SPORTSGAMEODDS_KEY", "")
    or os.environ.get("SPORTSGAMEODDS_API_KEY", "")
    or os.environ.get("SPORTS_GAME_ODDS_KEY", "")
).strip()

# The Odds API player props remain eventwise at /events/{eid}/odds.


class HistoricalPick(BaseModel):
    date: str
    player: str
    team: str
    market: str
    sport: str
    odds: float
    stake: float
    direction: Optional[str] = None
    probability: Optional[float] = None
    dedup_key: str
    point: Optional[float] = None
    line: Optional[float] = None
    game: Optional[str] = None
    game_id: Optional[str] = None
    event_id: Optional[str] = None
    commence_time: Optional[str] = None
    bookmaker: Optional[str] = None
    source: Optional[str] = None
    raw: dict = Field(default_factory=dict)
    result: Optional[str] = "pending"
    profit: Optional[float] = None
    closing_odds: Optional[float] = None
    clv_pct: Optional[float] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def fetch_snapshot_props(sport_filter=None) -> list:
    """Read recent sportsbook snapshots from Supabase.

    Only rows with an actually observed decimal price are converted into sportsbook
    Props. Pick'em/fantasy rows without a standalone price stay in the database for
    analysis but are never disguised as @1.85 bets.
    """
    c = _sb_read()
    if c is None:
        return []
    out = []
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=18)).isoformat()
        res = c.table("prop_hunter_prop_snapshots").select(
            "sport,league,source_event_id,player_name,market,market_key,direction,line,odds_decimal,commence_time,created_at,home_team,away_team,bookmaker,source"
        ).gte("created_at", cutoff).limit(5000).execute()
        snapshot_rows = list(res.data or [])
        try:
            from prop_hunter_market_intelligence import movement_index, market_key as _mi_key, consensus_count
            _movement = movement_index(snapshot_rows)
        except Exception as exc:
            log.warning("line movement unavailable: %s", exc)
            _movement = {}
            _mi_key = lambda row: ()
            consensus_count = lambda row, rows: 0
        emoji_map = {"NBA":"🏀","WNBA":"🏀","MLB":"⚾","NFL":"🏈","NHL":"🏒","NCAAB":"🏀","NCAAF":"🏈"}
        SEASON_MARKERS = ("season", "futures", "to win", "mvp", "champion", "award",
                          "regular season", "playoff", "total wins", "make the",
                          "division", "conference", "over/under wins")
        now_month = datetime.now(timezone.utc).month
        active_sports = {"MLB", "WNBA", "NCAAF"}
        if now_month >= 9 or now_month <= 2:
            active_sports |= {"NFL", "NBA", "NHL", "NCAAB"}
        if 4 <= now_month <= 6:
            active_sports |= {"NBA", "NHL"}

        for r in snapshot_rows:
            odds = r.get("odds_decimal")
            line = r.get("line")
            player = r.get("player_name")
            market = r.get("market")
            sport = (r.get("sport") or r.get("league") or "").upper()
            if not (player and market and line is not None):
                continue
            if sport_filter and sport_filter.lower() not in sport.lower():
                continue
            if any(m in market.lower() for m in SEASON_MARKERS):
                continue
            if sport and sport not in active_sports:
                continue
            try:
                if float(line) > 100 and sport not in ("MLB", "NFL"):
                    continue
                odds_val = float(odds)
            except Exception:
                continue
            if not (1.01 < odds_val < 50):
                continue
            book = str(r.get("bookmaker") or r.get("source") or "").strip().lower()
            if not book:
                continue
            observed_direction = str(r.get("direction") or "").lower().strip()
            if observed_direction not in {"over", "under"}:
                observed_direction = "under" if "under" in market.lower() else "over"
            try:
                ct = None
                if r.get("commence_time"):
                    try:
                        ct = datetime.fromisoformat(str(r.get("commence_time")).replace("Z", "+00:00"))
                    except Exception:
                        ct = None
                out.append(Prop(
                    player=player,
                    market=market,
                    odds=odds_val,
                    point=float(line),
                    sport=sport,
                    emoji=emoji_map.get(sport, "🎯"),
                    game=f"{r.get('away_team','')} @ {r.get('home_team','')}",
                    home=r.get("home_team") or None,
                    away=r.get("away_team") or None,
                    commence_time=ct,
                    direction=observed_direction,
                    enrichment=f"src:{book}",
                    features={
                        "odds_observed": True,
                        "price_type": "bookmaker",
                        "bookmaker": book,
                        "source": r.get("source") or book,
                        "source_event_id": r.get("source_event_id"),
                        "commence_time": r.get("commence_time"),
                        "home_team": r.get("home_team"),
                        "away_team": r.get("away_team"),
                        "consensus_sources": consensus_count(r, snapshot_rows),
                        **(_movement.get(_mi_key(r), {}) or {}),
                    },
                ))
            except Exception:
                continue
        if out:
            log.info("Snapshot sportsbook props (Supabase): %d", len(out))
    except Exception as e:
        log.warning("snapshot props: %s", e)
    return out


_fetch_bdl_props_1391 = fetch_bdl_props
def fetch_bdl_props(sport="nba"):
    if not BDL_KEY or not BDL_PROPS_ENABLED:
        return {}
    return _fetch_bdl_props_1391(sport)


def extract_props_from_data(data,mkey,label,min_pt,min_odds,sport,emoji,home,away,ct_iso):
    """Normalize The Odds API rows while preserving a real, placeable book price."""
    agg={}
    for bm in data.get("bookmakers",[]):
        bk=str(bm.get("key","") or "").lower()
        for mkt in bm.get("markets",[]):
            if mkt.get("key")!=mkey:
                continue
            for o in mkt.get("outcomes",[]):
                desc=o.get("description","") or ""
                nf=o.get("name","") or ""
                pt=o.get("point")
                price=o.get("price",0)
                if nf in {"Over","Under","Yes","No",""}:
                    pl,ot=desc,nf
                else:
                    pl,ot=nf,desc
                if not pl or pl in {"Over","Under","Yes","No",""}:
                    continue
                if min_pt and pt is not None and pt<min_pt:
                    continue
                try:
                    price=float(price)
                except Exception:
                    continue
                if price<=1:
                    continue
                k=f"{pl}|{pt if pt is not None else ''}"
                rec=agg.setdefault(k,{"player":pl,"point":pt,"prices":[],"po":None,"pu":None})
                if bk==SHARP_BOOK:
                    if ot in ("Over","Yes"):
                        rec["po"]=price
                    elif ot in ("Under","No"):
                        rec["pu"]=price
                if ot in ("Over","Yes") or ot=="":
                    rec["prices"].append((price,bk))
    out=[]
    ct=None
    if ct_iso:
        try:
            ct=datetime.fromisoformat(ct_iso.replace("Z","+00:00"))
        except Exception:
            pass
    for rec in agg.values():
        prices=[x for x in rec["prices"] if x[0]>1 and x[1]]
        if not prices:
            continue
        best_price,best_book=max(prices,key=lambda x:x[0])
        if best_price<min_odds:
            continue
        fair=no_vig(rec["po"],rec["pu"]) if rec["po"] and rec["pu"] else None
        feats={
            "odds_observed":True,
            "price_type":"bookmaker",
            "bookmaker":best_book,
            "source":"the_odds_api",
            "source_event_id": str(data.get("id") or data.get("event_id") or ""),
            "commence_time": ct_iso or "",
            "home_team": home,
            "away_team": away,
        }
        if fair is not None:
            feats["fair_prob"]=fair
        out.append(Prop(
            player=rec["player"],market=label,odds=round(best_price,2),point=rec["point"],
            sport=sport,emoji=emoji,game=f"{away} @ {home}",home=home,away=away,
            commence_time=ct,pinnacle_odds=rec["po"],pinnacle_opp_odds=rec["pu"],features=feats
        ))
    return out


def sb_insert(row):
    sb=_get_sb()
    if not sb:
        return
    safe = {k:v for k,v in row.items() if k not in ("closing_odds","clv_pct","features")}
    for _ in range(8):
        try:
            sb.table("prop_picks").insert(safe).execute()
            return
        except Exception as e:
            msg = str(e)
            low = msg.lower()
            if "duplicate key" in low or "23505" in low or "already exists" in low:
                return
            m = re.search(r"Could not find the '([^']+)' column", msg)
            if m and m.group(1) in safe:
                missing = m.group(1)
                log.warning("prop_picks schema missing %s; retry without it", missing)
                safe = {k:v for k,v in safe.items() if k != missing}
                continue
            log.warning("sb insert: %s", e)
            return


def persist(picks, telegram_message_id=None, telegram_text=None):
    today=datetime.now(timezone.utc).strftime("%Y-%m-%d")
    h=load_history()
    entry=next((e for e in h if e.get("date")==today),None)
    if entry is None:
        entry={"date":today,"picks":[],"kombis":[]}
        h.append(entry)
    singles=[p for p in picks if p.type=="single"]
    combos=[p for p in picks if p.type in ("kombi2","kombi3","big","super","lottery","betbuilder","ladder")]
    sport_map={"⚾":"MLB","🏀":"NBA/WNBA","🏈":"NFL"}
    def _clean_sport(p):
        s = (getattr(p, "source_sport", "") or getattr(p, "sport", "") or "").upper()
        if s in ("MLB","NBA","WNBA","NFL","NHL","NCAAB","NCAAF"):
            return s
        return sport_map.get(p.emoji or "", "?")
    for p in singles:
        dk=dedup_key(p.player or "",p.market or "",getattr(p,"point",None),p.direction)
        real_sport=_clean_sport(p)
        _point=getattr(p,"point",None)
        _features=getattr(p,"features",{}) or {}
        _event_id=str(getattr(p,"event_id",None) or _features.get("source_event_id") or _features.get("event_id") or "") or None
        _commence=getattr(p,"commence_time",None) or _features.get("commence_time")
        if isinstance(_commence, datetime):
            _commence=_commence.isoformat()
        hp=HistoricalPick(
            date=today,player=p.player or "",team=p.team or "",market=p.market or "",sport=real_sport,
            odds=p.odds,stake=p.stake,direction=p.direction,probability=p.probability,dedup_key=dk,
            point=_point,line=_point,game=getattr(p,"game",None),game_id=_event_id,event_id=_event_id,
            commence_time=str(_commence) if _commence else None,
            bookmaker=_features.get("bookmaker"),source=_features.get("source"),
            raw={"game":getattr(p,"game",None),"commence_time":str(_commence) if _commence else None,
                 "source_event_id":_event_id,"bookmaker":_features.get("bookmaker"),"source":_features.get("source")}
        )
        entry["picks"].append(hp.model_dump())
        sb_insert({**hp.model_dump(),"league":real_sport,"features":_features})
    for p in combos:
        combo = {
            "type":p.type,"category":getattr(p,"category",None),"player":p.player or "",
            "market":p.market or "","sport":_clean_sport(p),"legs":p.legs or [],
            "leg_details":getattr(p,"leg_details",[]) or [],"odds":p.odds,"stake":p.stake,
            "probability":p.probability,"result":"pending","created_at":datetime.now(timezone.utc).isoformat()
        }
        if p.type == "ladder":
            combo["ladder_legs"]=[x.model_dump() for x in (p.picks or [])]
            combo["direction"]=p.direction or "over"
            combo["point"]=getattr(p,"point",None)
        entry["kombis"].append(combo)
    if telegram_message_id:
        cards = entry.setdefault("cards", [])
        pick_keys = [
            dedup_key(p.player or "", p.market or "", getattr(p, "point", None), p.direction)
            for p in singles
        ]
        combo_ids = []
        for idx, combo in enumerate(entry.get("kombis", [])[-len(combos):] if combos else []):
            cid = combo.get("combo_id")
            if not cid:
                raw = json.dumps({
                    "type": combo.get("type"), "legs": combo.get("legs"),
                    "leg_details": combo.get("leg_details"), "odds": combo.get("odds"),
                    "stake": combo.get("stake"), "created_at": combo.get("created_at"),
                }, sort_keys=True, default=str)
                cid = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
                combo["combo_id"] = cid
            combo_ids.append(cid)
        cards.append({
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message_id": int(telegram_message_id),
            "chat_id": str(TG_CHAT),
            "text": telegram_text or "",
            "pick_keys": pick_keys,
            "combo_ids": combo_ids,
        })
    save_history(h)
    log.info("persisted %d singles + %d combos",len(singles),len(combos))


def _observed_rows_to_props(rows: list, source_name: str, sport_key: str) -> list:
    """Convert normalized observed sportsbook rows into Prop objects."""
    out=[]
    emoji=SPORTS.get(sport_key, SPORTS["baseball_mlb"]).emoji
    for raw in rows or []:
        try:
            dec=float(raw.get("decimal_odds") or raw.get("odds_decimal") or 0)
            if dec <= 1:
                continue
            player=str(raw.get("player_name") or "").strip()
            market=str(raw.get("market") or raw.get("market_key") or "").strip()
            line=raw.get("line")
            if not player or not market or line is None:
                continue
            sport_label=str(raw.get("sport") or raw.get("league") or "").upper()
            if not sport_label:
                sport_label={
                    "baseball_mlb":"MLB","basketball_nba":"NBA","basketball_wnba":"WNBA",
                    "americanfootball_nfl":"NFL","icehockey_nhl":"NHL",
                    "basketball_ncaab":"NCAAB","americanfootball_ncaaf":"NCAAF",
                }.get(sport_key, "?")
            commence = None
            if raw.get("commence_time"):
                try:
                    commence = datetime.fromisoformat(str(raw.get("commence_time")).replace("Z", "+00:00"))
                except Exception:
                    commence = None
            out.append(Prop(
                player=player,
                market=market,
                odds=round(dec,2),
                point=line,
                sport=sport_label,
                game=f"{raw.get('away_team','')} @ {raw.get('home_team','')}",
                direction=str(raw.get("direction") or "over").lower(),
                commence_time=commence,
                features={
                    "odds_observed": True,
                    "price_type": "sportsbook_observed",
                    "source": source_name,
                    "bookmaker": raw.get("bookmaker"),
                    "source_event_id": raw.get("source_event_id") or raw.get("event_id"),
                    "commence_time": raw.get("commence_time"),
                    "home_team": raw.get("home_team"),
                    "away_team": raw.get("away_team"),
                },
                emoji=emoji,
            ))
        except Exception:
            continue
    return out


_fetch_bdl_live_props_1391 = fetch_bdl_live_props
def fetch_bdl_live_props(sport_key):
    if not BALLDONTLIE_KEY or not BDL_PROPS_ENABLED:
        return []
    return _fetch_bdl_live_props_1391(sport_key)


_build_jk_extras_1391 = build_jk_extras
def build_jk_extras(picks):
    """Keep legacy extras but never synthesize ladder rungs from a single price."""
    return [x for x in (_build_jk_extras_1391(picks) or []) if getattr(x, "type", "") != "ladder"]


if __name__ == "__main__":
    main()
