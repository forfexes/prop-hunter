"""Hermetic proof that missing NBA photos never block valid neighbouring picks."""
from types import SimpleNamespace as N
from io import BytesIO
from PIL import Image
from prop_hunter_image_publication_gate import filter_verified_nba_images

_out=BytesIO()
Image.new("RGBA",(1080,1402),(12,35,54,255)).save(_out,"PNG")
PNG=_out.getvalue()

class Cards:
    def __init__(self):self.calls=[]
    def league_of(self,sport):
        return ("basketball","nba") if str(sport or "").lower() in (
            "nba","basketball_nba") else None
    def build_for_pick(self,pick):
        self.calls.append(pick.player)
        return {"good":PNG,"missing":None,"fake":b"not a png",
                "corrupt":PNG[:55],"details_ok":PNG,
                "verified_combo":PNG}.get(pick.player)

def p(player,sport=None,details=None):
    return N(type="single",player=player,sport=sport,source_sport=None,
             leg_details=details or [])

picks=[p("good","NBA"),p("missing","basketball_nba"),
       p("wnba","WNBA"),p("nhl","NHL"),p("fake","NBA"),
       p("corrupt","NBA"),p("details_ok",None,[{"sport":"NBA"}]),
       N(type="betbuilder",player="calculated_combo",sport="NBA",
         leg_details=[{"sport":"NBA"},{"sport":"NBA"}],
         features={"combined_odds_observed":False,
                   "calculated_combined_odds":3.30}),
       N(type="lottery",player="verified_combo",sport="NBA",
         leg_details=[{"sport":"NBA"},{"sport":"NBA"}],
         features={"combined_odds_observed":True,
                   "combined_quote_id":"QA_BOOK_TICKET"})]
cards=Cards()
published,rejected=filter_verified_nba_images(picks,cards)
assert rejected==4, rejected
assert [p.player for p in published]==[
    "good","wnba","nhl","details_ok","verified_combo"]
assert cards.calls==[
    "good","missing","fake","corrupt","details_ok","verified_combo"]
assert len(picks)==9
assert picks[0]._verified_owner_png == PNG
assert picks[6]._verified_owner_png == PNG
assert not hasattr(picks[1],"_verified_owner_png")
assert not hasattr(picks[4],"_verified_owner_png")
assert not hasattr(picks[5],"_verified_owner_png")
print("NBA OWNER IMAGE PUBLICATION GATE PASSED: individual skips, no false histories, no text fallback")

# Never upload a calculated/parlay-derived total, even when a renderer
# could draw a visually convincing authentic PNG.
assert not hasattr(picks[7], "_verified_owner_png")
assert picks[8]._verified_owner_png == PNG
print("NBA UNOBSERVED COMBO TOTAL REJECTED BEFORE IMAGE CREATION")
