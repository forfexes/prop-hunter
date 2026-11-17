"""Offline regression for public-position table parsing and evidence-only NBA joins."""
import json
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from prop_hunter_nba_dvp_scraper import parse_page, TEAM_CODES, collect
from prop_hunter_nba_live_context import attach_verified_nba_context

def make_html(season="2026-2027", duplicate=False):
    rows=[]
    for team in sorted(TEAM_CODES):
        rows.append(f"<tr><td>{team} Example</td><td>15</td><td>24.5</td><td>8.2</td><td>5.4</td><td>2.5</td></tr>")
    if duplicate: rows.append(rows[0])
    return (f"<html><h1>FanDuel NBA Defense Vs. Position | {season}</h1>"
            "<table><thead><tr><th>Team</th><th>GP</th><th>PTS</th>"
            "<th>REB</th><th>AST</th><th>3PM</th></tr></thead><tbody>"
            +"".join(rows)+"</tbody></table></html>")

today=date(2026,11,18)
for position in ("PG","SG","SF","PF","C"):
    assert len(parse_page(make_html(),position=position,day=today))==120
for bad in (make_html("2025-2026"),make_html(duplicate=True),"<html>access denied</html>"):
    try: parse_page(bad,position="PG",day=today)
    except ValueError: pass
    else: raise AssertionError("Invalid stale/ambiguous page accepted")
class Response:
    text=make_html()
    def raise_for_status(self):return None
class Session:
    def get(self,url,params,headers,timeout):
        assert params["position"] in ("PG","SG","SF","PF","C")
        return Response()
data=collect(day=today,session=Session(),delay_seconds=0)
assert len(data["rows"])==600 and not data["model_ready"]
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/"observed.json"
    path.write_text(json.dumps(data),encoding="utf8")
    p=SimpleNamespace(sport="NBA",home="Boston Celtics",away="Atlanta Hawks",
       market="Assists Over 5.5",probability=0.6,odds=1.85,
       features={"player_team":"Boston Celtics","verified_position":"PG","fair_prob":0.62})
    other=SimpleNamespace(sport="NBA",home="Boston Celtics",away="Atlanta Hawks",
       market="Assists Over 5.5",probability=0.6,odds=1.85,
       features={"verified_position":"PG","fair_prob":0.62})
    attach_verified_nba_context([p,other],cache_path=str(path),now=today)
    got=p.features["nba_dvp_position_evidence"]
    assert got["opponent_team"]=="ATL" and got["stat"]=="assists" and got["allowed_per_game"]==5.4
    assert not got["model_ready"]
    assert "nba_dvp_position_evidence" not in other.features
    assert p.probability==0.6 and p.odds==1.85 and p.features["fair_prob"]==0.62
print("NBA PUBLIC DVP PARSER + SAFE PRODUCTION ENRICHMENT PASSED")
