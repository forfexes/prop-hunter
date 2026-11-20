"""Offline deterministic proof: no invented NBA kickoff timestamps."""
from types import SimpleNamespace as N
from datetime import datetime,timezone
from prop_hunter_verified_tipoffs import enrich_verified_tipoffs

def prop(player="Exact Athlete",game="A @ B",sport="basketball_nba",
         start="2026-11-21T00:30:00Z"):
    return N(player=player,game=game,sport=sport,commence_time=start)

def ticket(kind="single",player="Exact Athlete",game="A @ B",
           sport="NBA",legs=None,commence_time=None):
    return N(type=kind,player=player,game=game,sport=sport,
             leg_details=legs or [],commence_time=commence_time)

p=ticket()
assert enrich_verified_tipoffs([p], [prop()])==1
assert p.commence_time=="2026-11-21T00:30:00+00:00"

p=ticket()
assert enrich_verified_tipoffs([p], [
    prop(start="2026-11-21T00:30:00Z"),
    prop(start="2026-11-21T01:30:00+01:00")])==1
assert p.commence_time=="2026-11-21T00:30:00+00:00"

p=ticket()
assert enrich_verified_tipoffs([p], [
    prop(start="2026-11-21T00:30:00Z"),
    prop(start="2026-11-21T02:30:00Z")])==0
assert p.commence_time is None

p=ticket()
assert enrich_verified_tipoffs([p], [
    prop(player="Other Athlete"),prop(game="B @ A"),
    prop(sport="basketball_wnba"),prop(start="2026-11-21T00:30:00")])==0
assert p.commence_time is None

p=ticket("ladder", legs=[
    {"player":"Exact Athlete","game":"A @ B","sport":"basketball_nba",
     "commence_time":"2026-11-21T00:30:00Z"},
    {"player":"Exact Athlete","game":"A @ B","sport":"NBA",
     "commence_time":"2026-11-21T01:30:00+01:00"},
])
assert enrich_verified_tipoffs([p],[])==1
assert p.commence_time=="2026-11-21T00:30:00+00:00"

p=ticket("ladder", legs=[
    {"player":"Exact Athlete","game":"A @ B","sport":"NBA",
     "commence_time":"2026-11-21T00:30:00Z"},
    {"player":"Exact Athlete","game":"WRONG @ CLUB","sport":"NBA",
     "commence_time":"2026-11-21T00:30:00Z"},
])
assert enrich_verified_tipoffs([p],[])==0

p=ticket()
assert enrich_verified_tipoffs([p], [prop(sport="wnba")])==0
assert p.commence_time is None

p=ticket(commence_time=datetime(2026,11,21,0,30,tzinfo=timezone.utc))
assert enrich_verified_tipoffs([p], [prop()])==0
assert isinstance(p.commence_time,datetime)

print("NBA VERIFIED TIPOFF ENRICHMENT PASS: unique exact player/event, cross-timezone UTC, ambiguity fails closed")
