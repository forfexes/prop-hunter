"""Hermetic proof that missing NBA photos never block valid neighbouring picks."""
from types import SimpleNamespace as N
from prop_hunter_image_publication_gate import filter_verified_nba_images

PNG=bytes((137,80,78,71,13,10,26,10))+b"QA"

class Cards:
    def __init__(self):self.calls=[]
    def league_of(self,sport):
        return ("basketball","nba") if str(sport or "").lower() in (
            "nba","basketball_nba") else None
    def build_for_pick(self,pick):
        self.calls.append(pick.player)
        return {"good":PNG,"missing":None,"fake":b"not a png",
                "details_ok":PNG}.get(pick.player)

def p(player,sport=None,details=None):
    return N(type="single",player=player,sport=sport,source_sport=None,
             leg_details=details or [])

picks=[p("good","NBA"),p("missing","basketball_nba"),
       p("wnba","WNBA"),p("nhl","NHL"),p("fake","NBA"),
       p("details_ok",None,[{"sport":"NBA"}])]
cards=Cards()
published,rejected=filter_verified_nba_images(picks,cards)
assert rejected==2, rejected
assert [p.player for p in published]==["good","wnba","nhl","details_ok"]
assert cards.calls==["good","missing","fake","details_ok"]
assert len(picks)==6
print("NBA OWNER IMAGE PUBLICATION GATE PASSED: individual skips, no false histories, no text fallback")
