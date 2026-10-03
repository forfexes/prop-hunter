#!/usr/bin/env python3
from prop_hunter_backfill_swiss_nl import (
    _display_name,_minutes,_skater_rows,_goalie_rows,schedule_game_ids,
    GAME_META,KEEP
)

assert 30<=KEEP<=40
assert _display_name("Geering Patrick")=="Patrick Geering"
assert _display_name("von Rohr Manuel")=="Manuel von Rohr"
assert _minutes("13:50")>13.8

class _FakeResponse:
    def __init__(self,text,status=200,ctype="text/csv"):
        self.content=text.encode("utf-8")
        self.text=text
        self.status_code=status
        self.headers={"content-type":ctype}
    def raise_for_status(self):
        return None

class _FakeSession:
    def get(self,url,params=None,headers=None,timeout=None):
        season=str((params or {}).get("season") or "")
        if season=="2027":
            return _FakeResponse(
                "Tag;Datum;Zeit;Home;Away;Resultat;Drittel;OT/SO;Status;Versch.;Stadion;Zus.;TV/Online;Id;Liga;Region;Phase\n"
                "Di;29.09.2026;19:45;ZSC Lions;EHC Biel-Bienne;4:2;;;Ende;False;;;;20271105000049;NL;CH;Regular Season\n"
                "Sa;31.10.2099;19:45;A;B;;;;Wie geplant;False;;;;20991105000001;NL;CH;Regular Season\n"
            )
        return _FakeResponse(
            "Tag;Datum;Zeit;Home;Away;Resultat;Drittel;OT/SO;Status;Versch.;Stadion;Zus.;TV/Online;Id;Liga;Region;Phase\n"
            "Sa;28.03.2026;20:00;SC Bern;EV Zug;3:1;;;Ende;False;;;;20261105000310;NL;CH;Playoffs\n"
            "Fr;08.08.2025;18:00;Test;Test;1:0;;;Ende;False;;;;20266105000001;NL;CH;---\n"
        )

ids=schedule_game_ids(_FakeSession())
assert "20271105000049" in ids and "20261105000310" in ids, ids
assert "20991105000001" not in ids and "20266105000001" not in ids, ids
assert GAME_META["20271105000049"]["home"]=="ZSC Lions"

sk=[{"No":"4","Spieler":"Geering Patrick","Pos":"Verteidiger","G":"1","A":"2","PTS":"3","PIM Total":"0","+/-":"2","SOG":"4","SHM Total":"1","SHP Total":"0","BkS":"2","FOW Total":"0","FOL Total":"0","FO%":"0.00","TOI Total":"13:50","TOI PP":"00:10","TOI PK":"01:18"}]
r=_skater_rows(sk,"20271105000049","2026-09-29","gamePlayerStatsHome")[0]
assert r["player_name"]=="Patrick Geering" and r["goals"]==1 and r["assists_hockey"]==2
assert r["shots_on_goal"]==4 and r["blocked_shots"]==2
assert r["team"]=="ZSC Lions" and r["opponent"]=="EHC Biel-Bienne"

g=[{"No":"30","Spieler":"Hrubec Simon","GA":"3","SVS":"25","SA":"28","SVS%":"89.29","MIP":"60:00","GAA":"3","PIM":"0"}]
gr=_goalie_rows(g,"20271105000049","2026-09-29","gameGoalieStatsHome")[0]
assert gr["player_name"]=="Simon Hrubec" and gr["goalie_saves"]==25 and gr["minutes"]==60
assert gr["team"]=="ZSC Lions"
print("SWISS NL BACKFILL TEST PASSED")
