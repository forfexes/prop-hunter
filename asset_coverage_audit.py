#!/usr/bin/env python3
"""Read-only complete roster inventory + bounded, real-source image checks.

Never modifies picks, Supabase, Telegram, card templates or repository assets.
No secrets or complete private rosters are written to output.
"""
from __future__ import annotations
import argparse
import collections
from datetime import datetime, timezone
import io
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "NETRATTLER-PropHunter-Asset-QA/1.0", "Accept": "application/json"})
OUT = Path("diagnostics/asset_coverage_audit.json")
PAGE = 1000

def norm(value):
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return re.sub(r"[^a-z0-9]+", "", "".join(c for c in text if not unicodedata.combining(c)))

def endpoint(url, key, table, columns):
    if not url or not key:
        raise RuntimeError("Supabase configuration absent: " + table)
    base = url.rstrip("/") + "/rest/v1/" + table
    auth = {"apikey": key, "Authorization": "Bearer " + key}
    start = 0
    # Large secondary snapshots have a unique indexed text PK; OFFSET gets
    # progressively slower and eventually times out. Use stable keyset paging.
    keyset = table == "prop_hunter_prop_snapshots"
    last_snapshot_id = None
    while True:
        response = None
        for retry in range(3):
            try:
                params = {"select": columns}
                headers = dict(auth)
                if keyset:
                    params.update({"select": columns + ",snapshot_id",
                                   "order": "snapshot_id.asc", "limit": str(PAGE)})
                    if last_snapshot_id:
                        params["snapshot_id"] = "gt." + last_snapshot_id
                else:
                    headers["Range"] = f"{start}-{start+PAGE-1}"
                response = SESSION.get(base, headers=headers, params=params, timeout=45)
                if response.status_code in (429, 500, 502, 503, 504):
                    time.sleep(2 * (retry + 1))
                    continue
                response.raise_for_status()
                break
            except requests.RequestException:
                if retry == 2:
                    raise
                time.sleep(2 * (retry + 1))
        if response is None or not response.ok:
            raise RuntimeError(f"{table} returned HTTP {getattr(response, 'status_code', 'none')}")
        rows = response.json()
        if not isinstance(rows, list):
            raise RuntimeError(f"{table}: unexpected response type")
        for row in rows:
            yield row
        if not rows or len(rows) < PAGE:
            break
        if keyset:
            next_id = rows[-1]["snapshot_id"]
            if next_id == last_snapshot_id:
                raise RuntimeError("Snapshot cursor did not advance")
            last_snapshot_id = next_id
        else:
            start += len(rows)

def image_ok(url, transparent=False):
    """Actually download and decode bounded image bytes; reject HTML and tiny placeholders."""
    if not isinstance(url, str) or not url.startswith("https://"):
        return False
    if urlparse(url).hostname not in {
        "a.espncdn.com", "resources.premierleague.com", "www.thesportsdb.com",
        "www.fotmob.com", "images.fotmob.com", "upload.wikimedia.org",
        "assets.football-logos.cc", "raw.githubusercontent.com",
        "media.api-sports.io", "img.mlbstatic.com", "assets.nhle.com",
        "cdn.nhle.com", "media.gettyimages.com", "static.www.nfl.com",
        "content.sportslogos.net"
    }:
        return False
    try:
        with SESSION.get(url, timeout=16, stream=True, headers={"Accept": "image/*"}) as r:
            if r.status_code != 200:
                return False
            blob = bytearray()
            for chunk in r.iter_content(65536):
                blob.extend(chunk)
                if len(blob) > 3_000_000:
                    return False
        im = Image.open(io.BytesIO(blob))
        im.load()
        if im.width < 48 or im.height < 48:
            return False
        if transparent:
            if "A" not in im.convert("RGBA").getbands():
                return False
            if im.convert("RGBA").getchannel("A").getextrema()[0] == 255:
                return False
        return True
    except (requests.RequestException, OSError, ValueError):
        return False

def select_batch(items, cap, *, rotate=False, anchor=20, ordinal=None):
    """Bounded coverage: priority identities every run, then a new daily roster slice.

    This is deterministic for a given day and sorted roster. No API calls/writes.
    """
    cap = max(1, min(int(cap), 500))
    if not rotate or len(items) <= cap:
        return items[:cap], {"mode": "priority", "slice": 0, "slices": 1}
    anchors = items[:min(anchor, cap)]
    rest = items[len(anchors):]
    width = max(1, cap - len(anchors))
    slices = (len(rest) + width - 1) // width
    day = int(ordinal if ordinal is not None else datetime.now(timezone.utc).date().toordinal())
    index = day % slices
    batch = anchors + rest[index*width:(index+1)*width]
    return batch, {"mode": "daily_rotation", "slice": index+1, "slices": slices,
                   "priority_count": len(anchors), "rotation_capacity": width}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", choices=("netrattler", "prop"), required=True)
    ap.add_argument("--max-photos", type=int, default=int(os.getenv("ASSET_MAX_PHOTOS", "80")))
    ap.add_argument("--max-teams", type=int, default=int(os.getenv("ASSET_MAX_TEAMS", "100")))
    ap.add_argument("--rotate", action="store_true",
                    help="Keep high-priority identities and cover a new historical roster slice each UTC day")
    args = ap.parse_args()
    root = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    secondary = os.getenv("SUPABASE_SECONDARY_URL", "").rstrip("/")
    secondary_key = os.getenv("SUPABASE_SECONDARY_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SECONDARY_KEY") or ""
    people, teams = {}, {}
    counts, blank = collections.Counter(), collections.Counter()
    priority = collections.Counter()
    existing_crests = {}
    from prop_hunter_asset_identity import resolve_provider, normalized_team

    def person(name, team="", sport="", boost=0, competition=""):
        n = norm(name)
        if n in {"alternatetotal", "alternatespread", "alternateline",
                 "teamtotal", "gametotal", "matchtotal", "overtotal",
                 "undertotal", "playerprops", "playerprop", "handicap",
                 "game", "totalgoals", "totalgoalsbycoloradoavalanche",
                 "gamespread", "totalpoints", "altspread",
                 "alternategametotal"} or re.search(r"(?i)\bstandings$", str(name or "")) or str(name or "").lower().startswith("total goals by "):
            blank["market_label_not_player"] += 1
            return
        if not n or len(n) < 4:
            blank["invalid_player"] += 1
            return
        league_key = str(competition or "").strip().upper()
        k = (str(sport or "").upper(), league_key, n)
        if k not in people:
            people[k] = {"name": str(name).strip(), "sport": str(sport or "").upper(),
                         "teams": set(), "leagues": set(), "count": 0}
        p = people[k]
        p["count"] += 1
        if team and norm(team):
            p["teams"].add(str(team).strip())
        if competition:
            p["leagues"].add(str(competition).strip().upper())
        if boost:
            priority[k] += boost

    def club(name, sport="", boost=0, competition=""):
        n = norm(name)
        # These are competition labels, not clubs; treating them as missing
        # logos creates misleading deficits in the image coverage report.
        if str(name or "").strip().upper() in {
            "NBA", "WNBA", "NHL", "NFL", "MLB", "NCAAF", "NCAAB",
            "EUROLEAGUE", "SWISS_NL", "SHL", "AHL",
            "ICE_HOCKEY", "BASKETBALL", "FOOTBALL",
        }:
            blank["league_label_not_team"] += 1
            return
        if not n or n in {"unknown", "none", "na", "home", "away"}:
            blank["invalid_team"] += 1
            return
        league_key = str(competition or "").strip().upper()
        k = (str(sport or "").upper(), league_key, n)
        if k not in teams:
            teams[k] = {"name": str(name).strip(), "sport": str(sport or "").upper(), "leagues": set(), "count": 0}
        teams[k]["count"] += 1
        if competition:
            teams[k]["leagues"].add(str(competition).strip().upper())
        if boost:
            priority[("team",) + k] += boost

    def load(table, cols, handler, u=root, secret=key):
        for row in endpoint(u, secret, table, cols):
            counts[table] += 1
            handler(row)

    if args.bot == "netrattler":
        load("netrattler_crest_cache", "team,url", lambda r: existing_crests.update(
            {norm(r.get("team")): r.get("url")} if norm(r.get("team")) else {}))
        for table in ("player_game_log", "fplci_player_match", "apif_player_match"):
            def add(r):
                name, team = r.get("player_name"), r.get("team")
                person(name, team, "SOCCER")
                club(team, "SOCCER")
            load(table, "player_name,team", add)
        def tip(r):
            person(r.get("player_name"), r.get("player_team"), "SOCCER", 15)
            club(r.get("player_team"), "SOCCER", 15)
        load("tips", "player_name,player_team", tip)
        def builder(r):
            for leg in r.get("legs") or []:
                if not isinstance(leg, dict):
                    continue
                person(leg.get("player"), leg.get("team"), "SOCCER", 60)
                club(leg.get("team"), "SOCCER", 60)
                match = str(leg.get("match") or "")
                sides = re.split(r"\s+(?:vs\.?|v\.?|@)\s+", match, maxsplit=1, flags=re.I)
                if len(sides) == 2:
                    for side in sides:
                        club(side, "SOCCER", 30)
        load("netrattler_builder_picks", "legs", builder)
    else:
        def add(r, boost):
            league = str(r.get("league") or "").upper()
            sport = league if league in {"NBA","WNBA","NHL","NFL","MLB","NCAAF","NCAAB","EUROLEAGUE"} else str(r.get("sport") or "").upper()
            p = r.get("player_name") or r.get("player")
            team = r.get("team") or ""
            competition = str(r.get("league") or "").upper()
            person(p, team, sport, boost, competition=competition)
            club(team, sport, boost, competition=competition)
            club(r.get("opponent"), sport, boost, competition=competition)
        load("prop_hunter_player_gamelogs", "sport,league,player_name,team,opponent", lambda r: add(r, 0))
        load("prop_hunter_player_features", "sport,league,player_name", lambda r: add(r, 0))
        load("prop_hunter_picks", "sport,league,player_name,player,team,opponent", lambda r: add(r, 80))
        load("prop_picks", "sport,league,player_name,player,team", lambda r: add(r, 40))
        if secondary and secondary_key:
            def snap(r):
                add(r, 1)
                sport = str(r.get("sport") or "").upper()
                competition = str(r.get("league") or "").upper()
                club(r.get("home_team"), sport, 1, competition=competition)
                club(r.get("away_team"), sport, 1, competition=competition)
            load("prop_hunter_prop_snapshots",
                "sport,league,player_name,team,opponent,home_team,away_team", snap,
                secondary, secondary_key)
        else:
            blank["secondary_not_configured"] += 1

    report = {"bot": args.bot, "data_counts": dict(counts), "unique_players": len(people),
              "unique_team_variants": len(teams), "quality_flags": dict(blank),
              "verified_photos": 0, "missing_or_unverified_photos": 0,
              "verified_crests": 0, "missing_or_unverified_crests": 0,
              "photo_checked": 0, "crest_checked": 0, "not_probed_photo": 0,
              "not_probed_crest": 0, "missing_photo_samples": [],
              "missing_crest_samples": [], "telegram": "DISABLED", "writes": "NONE"}
    if args.bot == "netrattler":
        # These are stored references only. HTTP and alpha check performed below.
        report["cached_crest_urls"] = len(existing_crests)
        report["teams_without_exact_cached_url"] = sum(
            1 for (_, name) in teams if name not in existing_crests)
        import netrattler_stats_match_cards as card
        import netrattler_player_photos as portraits
    else:
        import prop_hunter_image_cards as card

    def photo_test(p):
        if args.bot == "netrattler":
            # Source search is a candidate only, never imply surname-only identity is verified.
            try:
                url = portraits.photo_url(p["name"])
                return bool(url and image_ok(url)), ("name_only_unverified" if url else "not_found")
            except Exception:
                return False, "provider_error"
        league, league_reason, competition = resolve_provider(p["sport"], p.get("leagues") or ())
        # Swiss National League, Swedish SHL and American AHL are not NHL.
        # A missing licensed/identity-verified local provider is a source gap,
        # not a reason to fetch some other league's player photo.
        try:
            if not league:
                return False, league_reason
            img = card.player_photo(p["name"], league)
            if img is None:
                return False, "not_found"
            # Real premium layouts require genuinely transparent portraits.
            a = img.convert("RGBA").getchannel("A")
            return a.getextrema()[0] < 255 and min(img.size) >= 48, "provider_match"
        except Exception:
            return False, "provider_error"

    def crest_test(t):
        if args.bot == "netrattler":
            url = existing_crests.get(norm(t["name"]))
            if url and image_ok(url, transparent=True):
                return True, "verified_cached_url"
            try:
                payload = card._badge_bytes(t["name"])
                if not payload:
                    return False, "not_found"
                im = Image.open(io.BytesIO(payload)).convert("RGBA")
                im.load()
                return min(im.size) >= 48 and im.getchannel("A").getextrema()[0] < 255, "provider_fallback"
            except Exception:
                return False, "provider_error"
        league, league_reason, competition = resolve_provider(t["sport"], t.get("leagues") or ())
        try:
            if not league:
                return False, league_reason
            name, alias_reason = normalized_team(t["name"], competition)
            if name is None:
                return False, alias_reason
            img = card.team_logo(name, league)
            if img is None:
                return False, "not_found"
            return min(img.size) >= 48 and img.convert("RGBA").getchannel("A").getextrema()[0] < 255, "provider_match"
        except Exception:
            return False, "provider_error"

    plist = sorted(people.items(), key=lambda kv: (-priority[kv[0]], -kv[1]["count"], kv[0]))
    tlist = sorted(teams.items(), key=lambda kv: (-priority[("team",) + kv[0]], -kv[1]["count"], kv[0]))
    photo_batch, photo_plan = select_batch(plist, args.max_photos, rotate=args.rotate)
    team_batch, team_plan = select_batch(tlist, args.max_teams, rotate=args.rotate)
    report["coverage_plan"] = {"photos": photo_plan, "crests": team_plan}
    report["not_probed_photo"] = max(0, len(plist)-len(photo_batch))
    report["not_probed_crest"] = max(0, len(tlist)-len(team_batch))
    # Breakdown prevents a missing league data adapter from being presented
    # as a permanently missing player picture.
    report["photo_failures_by_reason"] = {}
    report["crest_failures_by_reason"] = {}
    for _, p in photo_batch:
        ok, evidence = photo_test(p)
        if not ok:
            report["photo_failures_by_reason"][evidence] = (
                report["photo_failures_by_reason"].get(evidence, 0) + 1)
        report["photo_checked"] += 1
        report["verified_photos" if ok else "missing_or_unverified_photos"] += 1
        if not ok and len(report["missing_photo_samples"]) < 50:
            report["missing_photo_samples"].append({"name": p["name"], "sport": p["sport"],
                                                        "league": sorted(p.get("leagues") or []),
                                                        "status": evidence})
    for _, t in team_batch:
        ok, evidence = crest_test(t)
        if not ok:
            report["crest_failures_by_reason"][evidence] = (
                report["crest_failures_by_reason"].get(evidence, 0) + 1)
        report["crest_checked"] += 1
        report["verified_crests" if ok else "missing_or_unverified_crests"] += 1
        if not ok and len(report["missing_crest_samples"]) < 50:
            report["missing_crest_samples"].append({"team": t["name"], "sport": t["sport"],
                                                        "league": sorted(t.get("leagues") or []),
                                                        "status": evidence})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Report only counts to log; report artifact contains limited sample names, never credentials.
    print("ASSET_AUDIT", json.dumps({k:v for k,v in report.items() if not k.endswith("_samples")}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
