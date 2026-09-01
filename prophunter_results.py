#!/usr/bin/env python3
"""PROP HUNTER — Results Evaluator v2 Style"""
import json, os, requests, time, re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ZURICH = ZoneInfo("Europe/Zurich")

def _target_date(offset_days: int = -1) -> str:
    return (datetime.now(ZURICH) + timedelta(days=offset_days)).strftime("%Y-%m-%d")


# ─── Day-level cache (1 API call covers all picks of that day) ───
_NBA_DAY_CACHE = {}
_MLB_DAY_CACHE = {}
_ESPN_NBA_DAY_CACHE = {}
_ESPN_MLB_DAY_CACHE = {}

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN","")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID","")
BDL_KEY  = os.environ.get("BALLDONTLIE_API_KEY","")
SUPABASE_URL = os.environ.get("SUPABASE_URL","")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY","")
HISTORY  = "picks_history.json"
TIMEOUT  = 30

def _supabase_rest_headers(extra=None):
    """Build REST headers compatible with legacy JWT keys and new sb_* API keys.

    New Supabase secret/publishable keys are opaque API keys, not JWTs, so they
    must not be forced into an Authorization: Bearer header. Legacy anon/service_role
    JWT keys keep the Bearer header for backwards compatibility.
    """
    headers = {"apikey": SUPABASE_KEY}
    if SUPABASE_KEY and not SUPABASE_KEY.startswith(("sb_secret_", "sb_publishable_")):
        headers["Authorization"] = f"Bearer {SUPABASE_KEY}"
    if extra:
        headers.update(extra)
    return headers

def update_supabase_result(pick, result, profit):
    """Update both supported Supabase pick schemas.

    The project historically wrote ``prop_picks`` while newer tools read
    ``prop_hunter_picks``.  Settlement now mirrors the result to both tables so
    learning and reporting cannot silently diverge.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    dedup_key = pick.get("dedup_key")
    pick_date = pick.get("sent_date") or pick.get("date")
    if not dedup_key or not pick_date:
        return False

    headers = _supabase_rest_headers({
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    })

    updates=(
        (
            "prop_picks",
            {"dedup_key": f"eq.{dedup_key}", "date": f"eq.{str(pick_date)[:10]}"},
            {"result": result, "profit": profit},
        ),
        (
            "prop_hunter_picks",
            {"dedup_key": f"eq.{dedup_key}", "sent_date": f"eq.{str(pick_date)[:10]}"},
            {"status": result, "profit_units": profit},
        ),
    )
    success=False
    errors=[]
    for table, params, payload in updates:
        try:
            response=requests.patch(
                f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}",
                headers=headers,
                params=params,
                json=payload,
                timeout=TIMEOUT,
            )
            if response.status_code in (200,204):
                success=True
            elif response.status_code not in (404,400):
                errors.append(f"{table} HTTP {response.status_code}: {response.text[:160]}")
        except Exception as exc:
            errors.append(f"{table}: {exc}")
    if errors:
        print("Supabase result update warning: " + " | ".join(errors))
    return success


def send(text):
    if not TG_TOKEN or not TG_CHAT: print(text); return
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id":TG_CHAT,"text":text,"disable_web_page_preview":True},timeout=TIMEOUT)
        print(f"Telegram: {r.status_code}")
    except Exception as e: print(f"Telegram: {e}")


def edit_telegram_message(message_id, text, chat_id=None):
    """Edit an existing PROP HUNTER card instead of posting a second result message."""
    if not TG_TOKEN or not message_id:
        return False
    target_chat = str(chat_id or TG_CHAT or "").strip()
    if not target_chat:
        return False
    if len(text) > 4096:
        print(f"Telegram edit skipped: message too long ({len(text)})")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/editMessageText",
            json={
                "chat_id": target_chat,
                "message_id": int(message_id),
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            print(f"Telegram edit OK message_id={message_id}")
            return True
        # Telegram returns 400 if content is already identical; treat that as success.
        if r.status_code == 400 and "message is not modified" in r.text.lower():
            return True
        print(f"Telegram edit {r.status_code}: {r.text[:200]}")
    except Exception as exc:
        print(f"Telegram edit: {exc}")
    return False

def load():
    if not os.path.exists(HISTORY): return []
    try: return json.load(open(HISTORY))
    except: return []

def save(h):
    try: json.dump(h, open(HISTORY,"w"), indent=2, default=str)
    except Exception as e: print(f"save: {e}")


def _result_key(p):
    """Dedupe-Key für Settlement. Verhindert doppelte Max-Muncy/Ozzie-Zählungen."""
    if p.get("dedup_key"):
        return str(p.get("dedup_key"))
    market = re.sub(r"\s+", " ", str(p.get("market","")).strip().lower())
    player = re.sub(r"\s+", " ", str(p.get("player","")).strip().lower())
    sport = str(p.get("sport","")).strip().upper()
    direction = str(p.get("direction","over")).strip().lower()
    return f"{sport}|{player}|{market}|{direction}"

def _team_player_line(p):
    emoji = p.get("emoji") or "🎯"
    team = str(p.get("team") or "").strip()
    player = str(p.get("player") or "").strip()
    if team.lower() in ("none", "null", "-", "@"):
        team = ""
    return f"{emoji} {team} — {player}" if team else f"{emoji} {player}"

def _is_duplicate_result(p):
    return str(p.get("result","")).lower() == "duplicate"


def _status_icon(status):
    return {"win":"✅", "won":"✅", "loss":"❌", "lost":"❌", "push":"↔️"}.get(str(status or "").lower())

def _norm_text(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

def _decorate_single(lines, pick, used):
    icon = _status_icon(pick.get("result"))
    if not icon:
        return False
    player = _norm_text(pick.get("player") or pick.get("player_name"))
    market = _norm_text(pick.get("market"))
    if not player:
        return False
    market_words = [w for w in market.split() if w not in {"over","under"}][:3]
    for i, line in enumerate(lines):
        if i in used or player not in _norm_text(line):
            continue
        for j in range(i + 1, min(i + 4, len(lines))):
            block = _norm_text(lines[j])
            if market_words and not all(w in block for w in market_words[:2]):
                continue
            # Replace the tree marker, so the evaluation is literally inside the original tip.
            if "└" in lines[j]:
                lines[j] = lines[j].replace("└", icon, 1)
            elif not lines[j].lstrip().startswith(("✅","❌","↔️")):
                prefix = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
                lines[j] = prefix + icon + " " + lines[j].lstrip()

            # Actual stat + unit result stay inside the original tip message.
            extras = []
            actual = pick.get("actual_value")
            if actual is not None:
                try:
                    extras.append(f"Ist {float(actual):g}")
                except Exception:
                    extras.append(f"Ist {actual}")
            try:
                profit = float(pick.get("profit") or 0)
                if str(pick.get("result") or "").lower() in ("win","won","loss","lost","push"):
                    extras.append(f"{profit:+.2f}u")
            except Exception:
                pass
            if extras and " · Ist " not in lines[j]:
                lines[j] += " · " + " · ".join(extras)
            used.add(i); used.add(j)
            return True
    return False

def _decorate_combo(lines, combo, used):
    icon = _status_icon(combo.get("result"))
    if not icon:
        return False
    odds = combo.get("odds")
    stake = combo.get("stake")
    odds_tokens = []
    try:
        odds_tokens.extend([f"@{float(odds):.2f}", f"@{float(odds):.1f}"])
    except Exception:
        pass
    for i, line in enumerate(lines):
        if i in used:
            continue
        stripped = line.lstrip()
        if not stripped.startswith(("•","🚀")):
            continue
        if odds_tokens and not any(tok in line for tok in odds_tokens):
            continue
        prefix = line[:len(line)-len(stripped)]
        rest = stripped[1:].lstrip() if stripped else stripped
        lines[i] = prefix + icon + " " + rest
        used.add(i)
        return True
    return False

def decorate_original_card(card, picks, combos):
    """Return the original card with ✅/❌/↔️ markers placed on each settled tip."""
    base = str(card.get("text") or "")
    if not base:
        return None
    lines = base.splitlines()
    used = set()
    pick_map = {str(p.get("dedup_key")): p for p in picks if p.get("dedup_key")}
    combo_map = {str(c.get("combo_id")): c for c in combos if c.get("combo_id")}
    card_picks = [pick_map[k] for k in map(str, card.get("pick_keys") or []) if k in pick_map]
    card_combos = [combo_map[k] for k in map(str, card.get("combo_ids") or []) if k in combo_map]

    closed = 0; wins = 0; losses = 0; pushes = 0; profit = 0.0
    for pick in card_picks:
        if _decorate_single(lines, pick, used):
            st = str(pick.get("result") or "").lower()
            closed += 1
            wins += int(st in ("win","won")); losses += int(st in ("loss","lost")); pushes += int(st == "push")
            profit += float(pick.get("profit") or 0)
    for combo in card_combos:
        if _decorate_combo(lines, combo, used):
            st = str(combo.get("result") or "").lower()
            closed += 1
            wins += int(st in ("win","won")); losses += int(st in ("loss","lost")); pushes += int(st == "push")
            profit += float(combo.get("profit") or 0)

    if not closed:
        return None
    summary = f"🏁 Auswertung: {wins}✅ {losses}❌" + (f" {pushes}↔️" if pushes else "") + f" · {profit:+.2f}u"
    # Put the compact evaluation inside the same card, immediately before the channel tag.
    insert_at = next((i for i, line in enumerate(lines) if line.strip() == "@prophunter"), len(lines))
    candidate = lines[:insert_at] + [summary] + lines[insert_at:]
    text = "\n".join(candidate)
    if len(text) <= 4096:
        return text
    # Original cards can be close to Telegram's limit. The inline symbols are the priority.
    text = "\n".join(lines)
    return text if len(text) <= 4096 else None

def edit_original_cards(entry):
    cards = entry.get("cards") or []
    if not cards:
        return 0
    picks = entry.get("picks") or []
    combos = entry.get("kombis") or []
    edited = 0
    for card in cards:
        text = decorate_original_card(card, picks, combos)
        if not text:
            continue
        if edit_telegram_message(card.get("message_id"), text, card.get("chat_id")):
            edited += 1
            card["settlement_text"] = text
            card["settlement_updated_at"] = datetime.now(timezone.utc).isoformat()
    return edited

# ─── NBA via balldontlie ───
def nba_stats_yesterday(player):
    yesterday = _target_date(-1)
    h = {"Accept":"application/json"}
    if BDL_KEY: h["Authorization"] = BDL_KEY
    try:
        r = requests.get("https://api.balldontlie.io/v1/players",
            params={"search":player,"per_page":5},headers=h,timeout=TIMEOUT)
        if r.status_code != 200: return None
        players = r.json().get("data",[])
        if not players: return None
        nl = player.lower()
        p = next((x for x in players if f"{x.get('first_name','')} {x.get('last_name','')}".lower().strip()==nl),players[0])
        pid = p.get("id")
        r2 = requests.get("https://api.balldontlie.io/v1/stats",
            params={"player_ids[]":pid,"dates[]":yesterday,"per_page":1},headers=h,timeout=TIMEOUT)
        if r2.status_code != 200: return None
        rows = r2.json().get("data",[])
        if not rows: return None
        s = rows[0]
        return {"pts":float(s.get("pts") or 0),"reb":float(s.get("reb") or 0),
                "ast":float(s.get("ast") or 0),"blk":float(s.get("blk") or 0),
                "stl":float(s.get("stl") or 0),"fg3m":float(s.get("fg3m") or 0),
                "tov":float(s.get("turnover") or s.get("turnovers") or 0),
                "ftm":float(s.get("ftm") or 0)}
    except: return None

# ─── MLB via statsapi ───
def mlb_stats_yesterday(player):
    try:
        import statsapi
        yesterday = _target_date(-1)
        for game in statsapi.schedule(date=yesterday):
            try:
                box = statsapi.boxscore_data(game.get("game_id"))
                for side in ("home","away"):
                    for bid in box.get(side,{}).get("batters",[])+box.get(side,{}).get("pitchers",[]):
                        info = box.get(side,{}).get("players",{}).get(f"ID{bid}",{})
                        name = info.get("person",{}).get("fullName","")
                        if player.lower() not in name.lower(): continue
                        b = info.get("stats",{}).get("batting",{})
                        p = info.get("stats",{}).get("pitching",{})
                        return {"hits":int(b.get("hits",0)),"runs":int(b.get("runs",0)),"hr":int(b.get("homeRuns",0)),
                                "tb":int(b.get("totalBases",0)),"rbi":int(b.get("rbi",0)),
                                "sb":int(b.get("stolenBases",0)),"k":int(p.get("strikeOuts",0)),
                                "outs":int(p.get("outs",0)),"er":int(p.get("earnedRuns",0))}
            except: continue
    except: pass
    return None

# ─── ESPN Fallback ───
def espn_nba_scoreboard(date_str):
    """ESPN NBA scoreboard for a given date (YYYYMMDD), cached per day."""
    if date_str in _ESPN_NBA_DAY_CACHE:
        return _ESPN_NBA_DAY_CACHE[date_str]
    games = []
    try:
        d = date_str.replace("-", "")
        r = requests.get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
            params={"dates": d}, timeout=TIMEOUT)
        if r.status_code == 200:
            games = r.json().get("events", [])
    except Exception:
        pass
    _ESPN_NBA_DAY_CACHE[date_str] = games
    return games

def espn_mlb_scoreboard(date_str):
    """ESPN MLB scoreboard for a given date (YYYYMMDD), cached per day."""
    if date_str in _ESPN_MLB_DAY_CACHE:
        return _ESPN_MLB_DAY_CACHE[date_str]
    games = []
    try:
        d = date_str.replace("-", "")
        r = requests.get("https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
            params={"dates": d}, timeout=TIMEOUT)
        if r.status_code == 200:
            games = r.json().get("events", [])
    except Exception:
        pass
    _ESPN_MLB_DAY_CACHE[date_str] = games
    return games

def espn_nba_player_stats(player_name, date_str):
    """Fallback: find NBA player boxscore stats via ESPN scoreboard summary."""
    games = espn_nba_scoreboard(date_str)
    pl = player_name.lower()
    for ev in games:
        try:
            comp = ev.get("competitions", [{}])[0]
            event_id = ev.get("id")
            if not event_id:
                continue
            r = requests.get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary",
                params={"event": event_id}, timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            box = r.json().get("boxscore", {})
            for team in box.get("players", []):
                for stat_group in team.get("statistics", []):
                    labels = stat_group.get("labels", [])
                    for athlete in stat_group.get("athletes", []):
                        name = (athlete.get("athlete", {}) or {}).get("displayName", "")
                        if pl not in name.lower():
                            continue
                        vals = athlete.get("stats", [])
                        stat_map = dict(zip(labels, vals))
                        def gi(k):
                            try: return float(stat_map.get(k, 0) or 0)
                            except: return 0.0
                        return {
                            "pts": gi("PTS"), "reb": gi("REB"), "ast": gi("AST"),
                            "blk": gi("BLK"), "stl": gi("STL"),
                            "fg3m": gi("3PM") or gi("3PT"),
                            "tov": gi("TO") or gi("TOV"),
                            "ftm": gi("FTM"),
                        }
        except Exception:
            continue
    return None

def espn_mlb_player_stats(player_name, date_str):
    """Fallback: find MLB player boxscore stats via ESPN scoreboard summary."""
    games = espn_mlb_scoreboard(date_str)
    pl = player_name.lower()
    for ev in games:
        try:
            event_id = ev.get("id")
            if not event_id:
                continue
            r = requests.get("https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/summary",
                params={"event": event_id}, timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            box = r.json().get("boxscore", {})
            for team in box.get("players", []):
                for stat_group in team.get("statistics", []):
                    labels = stat_group.get("labels", [])
                    for athlete in stat_group.get("athletes", []):
                        name = (athlete.get("athlete", {}) or {}).get("displayName", "")
                        if pl not in name.lower():
                            continue
                        vals = athlete.get("stats", [])
                        stat_map = dict(zip(labels, vals))
                        def gi(k):
                            try: return int(float(stat_map.get(k, 0) or 0))
                            except: return 0
                        return {
                            "hits": gi("H"), "runs": gi("R"), "hr": gi("HR"), "tb": gi("TB"),
                            "rbi": gi("RBI"), "sb": gi("SB"),
                            "k": gi("K"), "outs": gi("IP") * 3 if "IP" in stat_map else 0,
                            "er": gi("ER"),
                        }
        except Exception:
            continue
    return None



def espn_basket_player_stats(player_name, date_str, league="wnba"):
    """ESPN Boxscore Stats für NBA/WNBA (Free, kein Key)."""
    try:
        r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/scoreboard",
            params={"dates": date_str}, timeout=TIMEOUT)
        if r.status_code != 200: return None
        pl = player_name.lower()
        for ev in r.json().get("events", []):
            eid = ev.get("id")
            if not eid: continue
            r2 = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/summary",
                params={"event": eid}, timeout=TIMEOUT)
            if r2.status_code != 200: continue
            for team in (r2.json().get("boxscore", {}) or {}).get("players", []):
                for grp in team.get("statistics", []):
                    labels = grp.get("labels", [])
                    for ath in grp.get("athletes", []):
                        name = (ath.get("athlete", {}) or {}).get("displayName", "")
                        if pl not in name.lower(): continue
                        sm = dict(zip(labels, ath.get("stats", [])))
                        def gi(k):
                            try: return float(sm.get(k, 0) or 0)
                            except: return 0.0
                        return {"pts": gi("PTS"), "reb": gi("REB"), "ast": gi("AST"),
                                "blk": gi("BLK"), "stl": gi("STL"),
                                "fg3m": gi("3PM") or gi("3PT"),
                                "tov": gi("TO") or gi("TOV"),
                                "ftm": gi("FTM")}
    except Exception:
        pass
    return None

def espn_nfl_player_stats(player_name, date_str):
    """Aggregate public ESPN NFL boxscore groups for one player."""
    try:
        r = requests.get(
            "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
            params={"dates": date_str},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return None
        target = re.sub(r"\s+", " ", player_name.lower()).strip()
        aggregate = {
            "pass_yds": 0.0, "pass_cmp": 0.0, "pass_att": 0.0,
            "pass_td": 0.0, "pass_int": 0.0,
            "rush_yds": 0.0, "rush_att": 0.0, "rush_td": 0.0,
            "rec_yds": 0.0, "receptions": 0.0, "rec_td": 0.0,
            "long_rec": 0.0, "sacks": 0.0, "tackles": 0.0,
            "tackle_assists": 0.0, "kicking_points": 0.0,
            "fg_made": 0.0, "long_fg": 0.0, "long_punt": 0.0,
        }
        found = False

        for event in r.json().get("events", []):
            event_id = event.get("id")
            if not event_id:
                continue
            summary = requests.get(
                "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary",
                params={"event": event_id},
                timeout=TIMEOUT,
            )
            if summary.status_code != 200:
                continue
            boxscore = (summary.json().get("boxscore") or {})
            for team in boxscore.get("players", []) or []:
                for group in team.get("statistics", []) or []:
                    group_name = str(group.get("name") or group.get("displayName") or "").lower()
                    labels = [str(x).upper() for x in group.get("labels", [])]
                    for athlete in group.get("athletes", []) or []:
                        name = ((athlete.get("athlete") or {}).get("displayName") or "").lower()
                        if target not in name and name not in target:
                            continue
                        found = True
                        stat_map = dict(zip(labels, athlete.get("stats", []) or []))

                        def number(*keys):
                            for key in keys:
                                raw = stat_map.get(key.upper())
                                if raw not in (None, ""):
                                    try:
                                        return float(str(raw).split("/")[0])
                                    except Exception:
                                        continue
                            return 0.0

                        if "passing" in group_name:
                            comp_att = stat_map.get("C/ATT") or stat_map.get("CMP/ATT")
                            if comp_att and "/" in str(comp_att):
                                try:
                                    cmp_v, att_v = str(comp_att).split("/", 1)
                                    aggregate["pass_cmp"] += float(cmp_v)
                                    aggregate["pass_att"] += float(att_v)
                                except Exception:
                                    pass
                            else:
                                aggregate["pass_cmp"] += number("CMP", "C")
                                aggregate["pass_att"] += number("ATT")
                            aggregate["pass_yds"] += number("YDS")
                            aggregate["pass_td"] += number("TD")
                            aggregate["pass_int"] += number("INT")
                        elif "rushing" in group_name:
                            aggregate["rush_att"] += number("CAR", "ATT")
                            aggregate["rush_yds"] += number("YDS")
                            aggregate["rush_td"] += number("TD")
                        elif "receiving" in group_name:
                            aggregate["receptions"] += number("REC")
                            aggregate["rec_yds"] += number("YDS")
                            aggregate["rec_td"] += number("TD")
                            aggregate["long_rec"] = max(aggregate["long_rec"], number("LONG", "LNG"))
                        elif "defensive" in group_name:
                            aggregate["sacks"] += number("SACKS", "SACK")
                            aggregate["tackles"] += number("TOT", "TOTAL", "TACKLES")
                            aggregate["tackle_assists"] += number("AST", "ASSISTS")
                        elif "kicking" in group_name:
                            fgm_fga = stat_map.get("FG") or stat_map.get("FGM/FGA")
                            if fgm_fga and "/" in str(fgm_fga):
                                try:
                                    aggregate["fg_made"] += float(str(fgm_fga).split("/", 1)[0])
                                except Exception:
                                    pass
                            else:
                                aggregate["fg_made"] += number("FGM")
                            aggregate["kicking_points"] += number("PTS")
                            aggregate["long_fg"] = max(aggregate["long_fg"], number("LONG", "LNG"))
                        elif "punting" in group_name:
                            aggregate["long_punt"] = max(aggregate["long_punt"], number("LONG", "LNG"))
        return aggregate if found else None
    except Exception:
        return None


# ─── Grade single pick ───
def grade(pick):
    market = (pick.get("market") or "").lower()
    direction = (pick.get("direction") or "over").lower()
    sport = (pick.get("sport") or "").upper()
    player = pick.get("player","")

    # Extract line
    line = pick.get("point")
    if line is None:
        nums = re.findall(r"(?<![a-z])(\d+(?:\.\d+)?)", market)
        if nums:
            line = float(nums[-1])

    stats = None
    if sport in ("NBA","WNBA"):
        stats = nba_stats_yesterday(player) if sport == "NBA" else None
        if not stats:
            yesterday = _target_date(-1).replace("-", "")
            stats = espn_basket_player_stats(player, yesterday, "wnba" if sport=="WNBA" else "nba")
        if not stats: return None
        if "rebounds+assists" in market or re.search(r'\bra\b', market):
            val = stats["reb"] + stats["ast"]
        elif "pra" in market or ("points" in market and "rebounds" in market and "assists" in market):
            val = stats["pts"] + stats["reb"] + stats["ast"]
        elif "points+rebounds" in market or re.search(r'\bpr\b', market):
            val = stats["pts"] + stats["reb"]
        elif "points+assists" in market or re.search(r'\bpa\b', market):
            val = stats["pts"] + stats["ast"]
        elif "steals+blocks" in market or ("steals" in market and "blocks" in market):
            val = stats["stl"] + stats["blk"]
        elif "triple double" in market:
            val = 1 if sum(x >= 10 for x in (stats["pts"], stats["reb"], stats["ast"], stats["stl"], stats["blk"])) >= 3 else 0
            line = line or 0.5
        elif "double double" in market:
            val = 1 if sum(x >= 10 for x in (stats["pts"], stats["reb"], stats["ast"], stats["stl"], stats["blk"])) >= 2 else 0
            line = line or 0.5
        elif "3pm" in market or "three" in market or "3-pointer" in market:
            val = stats["fg3m"]
        elif "turnover" in market:
            val = stats.get("tov", 0)
        elif "free throw" in market:
            val = stats.get("ftm", 0)
        elif "points" in market:
            val = stats["pts"]
        elif "rebounds" in market:
            val = stats["reb"]
        elif "assists" in market:
            val = stats["ast"]
        elif "blocks" in market:
            val = stats["blk"]
        elif "steals" in market:
            val = stats["stl"]
        else:
            return None
    elif sport == "MLB":
        stats = mlb_stats_yesterday(player)
        if not stats:
            yesterday = _target_date(-1).replace("-", "")
            stats = espn_mlb_player_stats(player, yesterday)
        if not stats: return None
        if "hits+runs+rbis" in market or "hits+runs+rbi" in market or "hits runs rbis" in market or "hits runs rbi" in market:
            val = stats.get("hits",0) + stats.get("runs",0) + stats.get("rbi",0)
        elif "home run" in market or "hr" in market:
            val = stats["hr"]; line = line or 0.5
        elif "total bases" in market:
            val = stats["tb"]
        elif "stolen base" in market:
            val = stats["sb"]; line = line or 0.5
        elif "rbi" in market:
            val = stats["rbi"]
        elif re.search(r"\bruns?\b", market) and "earned" not in market:
            val = stats.get("runs", 0)
        elif "hits" in market:
            val = stats["hits"]
        elif "pitcher k" in market or "strikeout" in market: val = stats["k"]
        elif "outs recorded" in market: val = stats["outs"]
        elif "earned runs" in market: val = stats["er"]
        else: return None
    elif sport == "NFL":
        yesterday = _target_date(-1).replace("-", "")
        stats = espn_nfl_player_stats(player, yesterday)
        if not stats:
            return None
        if "passing yards" in market:
            val = stats["pass_yds"]
        elif "passing completions" in market or "pass completions" in market:
            val = stats["pass_cmp"]
        elif "passing attempts" in market or "pass attempts" in market:
            val = stats["pass_att"]
        elif "passing touchdown" in market or "pass tds" in market:
            val = stats["pass_td"]
        elif "interceptions thrown" in market or "passing interceptions" in market:
            val = stats["pass_int"]
        elif "rushing+receiving" in market or "rush+receiving" in market:
            val = stats["rush_yds"] + stats["rec_yds"]
        elif "rushing yards" in market or "rush yards" in market:
            val = stats["rush_yds"]
        elif "rushing attempts" in market or "carries" in market:
            val = stats["rush_att"]
        elif "receiving yards" in market:
            val = stats["rec_yds"]
        elif "receptions" in market:
            val = stats["receptions"]
        elif "longest reception" in market:
            val = stats["long_rec"]
        elif "2+ touchdown" in market or "2 or more touchdown" in market:
            val = stats["rush_td"] + stats["rec_td"]
            line = line or 1.5
        elif "anytime touchdown" in market:
            val = stats["rush_td"] + stats["rec_td"]
            line = line or 0.5
        elif "tackles+assists" in market or ("tackles" in market and "assists" in market):
            val = stats["tackles"] + stats["tackle_assists"]
        elif "tackle assists" in market:
            val = stats["tackle_assists"]
        elif "tackles" in market:
            val = stats["tackles"]
        elif "defensive sacks" in market or re.search(r"\bsacks?\b", market):
            val = stats["sacks"]
        elif "kicking points" in market:
            val = stats["kicking_points"]
        elif "field goals made" in market:
            val = stats["fg_made"]
        elif "longest field goal" in market:
            val = stats["long_fg"]
        elif "longest punt" in market:
            val = stats["long_punt"]
        else:
            return None
    else:
        return None

    if line is None: return None
    # Persist realised stat on the pick so the ORIGINAL Telegram tip can show it.
    pick["actual_value"] = val
    pick["settled_line"] = line
    try:
        if float(val) == float(line): return "push"
    except Exception:
        pass
    if direction == "under": return "win" if val < line else "loss"
    return "win" if val > line else "loss"

def _match_old_leg(leg_text, singles):
    low = str(leg_text or "").lower()
    matches = []
    for p in singles:
        name = str(p.get("player") or "").strip().lower()
        if name and (name in low or name.split()[-1] in low):
            matches.append(p)
    return matches[0].copy() if len(matches) == 1 else None


def _combo_leg_rows(combo, singles):
    details = combo.get("leg_details") or []
    if details:
        return [dict(x) for x in details if isinstance(x, dict)]
    if combo.get("type") == "ladder" and combo.get("ladder_legs"):
        rows = []
        for leg in combo.get("ladder_legs") or []:
            row = {
                "player": combo.get("player"), "sport": combo.get("sport"),
                "market": leg.get("market"), "direction": combo.get("direction") or "over",
                "odds": leg.get("odds"), "stake": leg.get("stake"),
            }
            rows.append(row)
        return rows
    rows = []
    for text in combo.get("legs") or []:
        matched = _match_old_leg(text, singles)
        if matched:
            rows.append(matched)
    return rows


def grade_combo(combo, singles):
    """Return (result, profit, leg_results). Never guesses an unresolved leg."""
    legs = _combo_leg_rows(combo, singles)
    expected = len(combo.get("leg_details") or combo.get("ladder_legs") or combo.get("legs") or [])
    if not legs or (expected and len(legs) != expected):
        return None, 0.0, []
    graded = []
    for leg in legs:
        res = grade(leg)
        graded.append((leg, res))
        if res is None:
            return None, 0.0, graded
    if combo.get("type") == "ladder":
        profit = 0.0
        for leg, res in graded:
            stake = float(leg.get("stake") or 0)
            odds = float(leg.get("odds") or 0)
            if res == "win": profit += (odds - 1.0) * stake
            elif res == "loss": profit -= stake
        status = "win" if profit > 0 else "loss" if profit < 0 else "push"
        return status, round(profit, 2), graded
    states = [res for _, res in graded]
    if "loss" in states:
        return "loss", -float(combo.get("stake") or 0), graded
    if "push" in states:
        # Exact reduced parlay payout needs per-leg settlement rules; don't invent it.
        return "push", 0.0, graded
    stake = float(combo.get("stake") or 0)
    odds = float(combo.get("odds") or 0)
    return "win", round((odds - 1.0) * stake, 2), graded


# ─── Main ───
def fetch_clv_for_date(date_str):
    """Holt CLV-Werte (Closing Line Value) aus prop_hunter_clv für einen Tag.
    Positiver clv_odds_pct = unser gesendeter Preis war besser als der Closing-Preis."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/prop_hunter_clv",
            headers=_supabase_rest_headers(),
            params={"select": "pick_id,clv_odds_pct,clv_line_diff,raw",
                    "computed_at": f"gte.{date_str}T00:00:00", "limit": "500"},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"CLV fetch error: {e}")
    return []

def main():
    yesterday = _target_date(-1)
    today     = datetime.now(ZURICH).strftime("%Y-%m-%d")
    month     = today[:7]
    print(f"Grading: {yesterday}")

    history = load()
    entry = next((e for e in history if e.get("date")==yesterday), None)
    if not entry:
        print(f"No picks for {yesterday}")
        # Still post empty summary
        send(f"📊 PROP HUNTER — Auswertung {yesterday}\n\n❕ Keine Picks gestern\n\n@prophunter")
        return

    picks = entry.get("picks",[])
    raw_pending = [p for p in picks if p.get("result","pending")=="pending"]

    # Doppelte Picks aus alten Runs markieren, aber NICHT mehrfach zählen/posten.
    seen = set()
    pending = []
    dupes = 0
    for p in raw_pending:
        k = _result_key(p)
        if k in seen:
            p["result"] = "duplicate"
            p["profit"] = 0
            dupes += 1
            continue
        seen.add(k)
        pending.append(p)

    print(f"{len(pending)} pending picks ({dupes} duplicates skipped)")

    results = []
    for p in pending:
        result = grade(p)
        stake  = float(p.get("stake",1))
        odds   = float(p.get("odds",2))
        if result is None:
            results.append(("❓",p,0))
            continue
        profit = round((odds-1)*stake if result=="win" else -stake if result=="loss" else 0.0, 2)
        p["result"] = result
        p["profit"] = profit
        update_supabase_result(p, result, profit)
        results.append(("✅" if result=="win" else "❌" if result=="loss" else "↔️", p, profit))
        time.sleep(0.3)

    combo_results = []
    for combo in [c for c in entry.get("kombis", []) if c.get("result", "pending") == "pending"]:
        status, profit, legs = grade_combo(combo, picks)
        if status is None:
            combo_results.append(("❓", combo, 0.0, legs))
            continue
        combo["result"] = status
        combo["profit"] = profit
        combo["leg_results"] = [
            {"player": leg.get("player"), "market": leg.get("market"), "result": leg_status}
            for leg, leg_status in legs
        ]
        icon = "✅" if status == "win" else "❌" if status == "loss" else "↔️"
        combo_results.append((icon, combo, profit, legs))

    save(history)

    # ─── Build post (V2 style) ───
    wins   = sum(1 for ic,_,_ in results if ic=="✅")
    losses = sum(1 for ic,_,_ in results if ic=="❌")
    total  = wins+losses
    total_profit = sum(profit for _,_,profit in results if profit!=0) + sum(profit for _,_,profit,_ in combo_results if profit!=0)

    stakes_settled = sum(float(p.get("stake",1)) for _,p,_ in results if p.get("result") in ("win","loss"))
    stakes_settled += sum(float(c.get("stake",0)) for _,c,_,_ in combo_results if c.get("result") in ("win","loss"))
    roi = round(100*total_profit/stakes_settled,1) if stakes_settled>0 else 0

    lines = [f"📊 PROP HUNTER — Auswertung {yesterday}", ""]
    for icon,p,profit in results:
        odds = float(p.get("odds",0)); stake = float(p.get("stake",0))
        ps = f"+{profit:.2f}u" if profit>0 else f"{profit:.2f}u" if profit!=0 else ""
        lines.append(f"{icon} {_team_player_line(p)}")
        lines.append(f"   └ {p.get('market','')} @{odds:.2f} → {stake}u  {ps}")

    if combo_results:
        lines += ["", "🧩 BUILDER / LADDERS:"]
        for icon, combo, profit, leg_rows in combo_results:
            ps = f"+{profit:.2f}u" if profit > 0 else f"{profit:.2f}u" if profit < 0 else ""
            lines.append(f"{icon} {str(combo.get('type') or 'combo').upper()} @{float(combo.get('odds') or 0):.2f} → {float(combo.get('stake') or 0):.2f}u {ps}")
            for leg, status in leg_rows:
                leg_icon = "✅" if status == "win" else "❌" if status == "loss" else "↔️" if status == "push" else "❓"
                lines.append(f"   {leg_icon} {leg.get('player','')} · {leg.get('market','')}")

    # Monthly stats
    m_wins=m_total=0; m_profit=0.0
    for e in history:
        if not e.get("date","").startswith(month): continue
        for p in e.get("picks",[]):
            if p.get("result") in ("win","loss") and not _is_duplicate_result(p):
                m_total+=1
                if p["result"]=="win": m_wins+=1
                m_profit+=float(p.get("profit",0))
    m_roi = round(100*m_profit/m_total,1) if m_total else 0

    # ─── CLV Auswertung (Timing-Qualität) ───
    clv_rows = fetch_clv_for_date(yesterday)
    clv_line = ""
    if clv_rows:
        odds_clvs = [float(r["clv_odds_pct"]) / 100.0 for r in clv_rows if r.get("clv_odds_pct") is not None]
        if odds_clvs:
            avg_clv = sum(odds_clvs) / len(odds_clvs)
            positive = sum(1 for v in odds_clvs if v > 0)
            clv_pct = round(100 * positive / len(odds_clvs))
            clv_emoji = "🟢" if avg_clv > 0 else "🔴"
            clv_line = f"\n{clv_emoji} CLV: {avg_clv*100:+.1f}% Ø · {clv_pct}% besser als Closing Line ({len(odds_clvs)} Picks)"

    lines += [
        "",
        "━━━━━━━━━━",
        f"{'🟢' if total_profit>=0 else '🔴'} {'Gewinn' if total_profit>=0 else 'Verlust'}: {total_profit:+.2f}u",
        f"📊 Heute: {wins}/{total} ({round(100*wins/total) if total else 0}%)",
    ]
    if clv_line:
        lines.append(clv_line.strip())
    if m_total:
        lines.append(f"📅 {month}: {m_wins}/{m_total} ({round(100*m_wins/m_total)}%) · ROI {m_roi}%")
    lines.append("@prophunter")

    msg = "\n".join(lines)
    print("\n"+msg+"\n")

    # V13.3: edit the original Telegram tip/card in place.
    # Old cards from before V13.3 have no message_id metadata and therefore fall back
    # to the separate evaluation post for backwards compatibility.
    edited_cards = edit_original_cards(entry)
    if edited_cards:
        save(history)
        print(f"Original Telegram cards edited: {edited_cards}")
    else:
        send(msg)

if __name__=="__main__":
    main()
