"""Hermetic proof that missing NBA photos never block valid neighbouring picks."""
from types import SimpleNamespace as N
from io import BytesIO
from PIL import Image
from prop_hunter_image_publication_gate import filter_verified_nba_images,owner_image_signature

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
       N(type="lottery",player="verified_combo",sport="NBA",odds=3.40,
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
assert picks[8]._verified_owner_signature == owner_image_signature(picks[8])
# Even an updated, still-bookmaker-confirmed odd is a different ticket image.
_old_signature=picks[8]._verified_owner_signature
picks[8].odds=4.25
assert owner_image_signature(picks[8]) != _old_signature
picks[8].odds=3.40
assert owner_image_signature(picks[8]) == _old_signature
print("NBA UNOBSERVED COMBO TOTAL REJECTED BEFORE IMAGE CREATION")

# A previously successful photo MUST be invalidated when the ticket changes.
# Production reuses exactly the _verified_owner_png bytes; leaving old bytes
# after a failed recheck would silently publish obsolete selections.
again,failed=filter_verified_nba_images([picks[8]],cards)
assert failed==0 and again==[picks[8]]
assert picks[8]._verified_owner_png==PNG
picks[8].features["combined_odds_observed"]=False
again,failed=filter_verified_nba_images([picks[8]],cards)
assert again==[] and failed==1
assert not hasattr(picks[8],"_verified_owner_png")
picks[8].features["combined_odds_observed"]=True
picks[8].features["combined_quote_id"]="QA_BOOK_TICKET"
print("NBA STALE ORIGINAL PREVIEW REJECTED AFTER TICKET CHANGE")

# Global Premium-KI rule: no unapproved NFL/NHL/MLB/WNBA owner images may
# enter Telegram, even when legacy renderers could create a convincing card.
from unittest.mock import patch
with patch.dict("os.environ",{"PH_OWNER_APPROVED_ALL_SPORTS":"1"}):
    owner_only=[
        p("good","NBA"),
        p("wnba","WNBA"),
        p("nhl","NHL"),
        p("details_ok",None,[{"sport":"NBA"}]),
        N(type="lottery",player="verified_combo",sport="NBA",
          leg_details=[{"sport":"NBA"},{"sport":"NHL"}],
          features={"combined_odds_observed":True,
                    "combined_quote_id":"QA_VALID_COMBINED_BOOK_TICKET"}),
    ]
    screened,blocked_count=filter_verified_nba_images(owner_only,Cards())
    assert blocked_count==3,(blocked_count,[x.player for x in screened])
    assert [x.player for x in screened]==["good","details_ok"]
    assert all(not hasattr(x,"_verified_owner_png")
               for x in owner_only if x not in screened)
print("ALL-SPORT OWNER-APPROVAL BLOCK: no overpainted unapproved premium images")

# Historical records can contain model leg objects instead of dictionaries.
# One malformed or unsupported sport must not throw and block valid NBA cards.
with patch.dict("os.environ", {"PH_OWNER_APPROVED_ALL_SPORTS": "1"}):
    object_leg_good=p("good", None, [N(sport="NBA")])
    object_leg_nhl=p("nhl", None, [N(sport="NHL")])
    object_leg_unknown=p("fake", None, [N()])
    object_leg_nhl._verified_owner_png=PNG  # stale preview must be invalidated
    checked=Cards()
    accepted,blocked=filter_verified_nba_images(
        [object_leg_good,object_leg_nhl,object_leg_unknown], checked)
    assert accepted==[object_leg_good] and blocked==2
    assert checked.calls==["good"]
    assert object_leg_good._verified_owner_png==PNG
    assert not hasattr(object_leg_nhl, "_verified_owner_png")
    assert not hasattr(object_leg_unknown, "_verified_owner_png")
print("HISTORICAL OBJECT-LEG PREFLIGHT SAFE: one valid NBA card survives")

# A green image-PNG validation alone cannot approve the overpainted legacy
# compositor. Production must refuse it even when photos/odds are populated.
from prop_hunter_nba_owner_bridge import render_owner
with patch.dict("os.environ", {"PH_BLOCK_OVERPAINTED_MASTERS": "1"}):
    try:
        render_owner(None, "single_points", [], [], {}, [])
    except ValueError as exc:
        assert "overpainted" in str(exc), str(exc)
    else:
        raise AssertionError("Opaque-patch compositor leaked into production")
print("PRODUCTION NO-OVERPAINT RELEASE LOCK PASSED")


# Regression: a disguised Single or mixed-player Ladder must not reach
# Telegram even when an old preflight PNG and claimed quote ID both exist.
# Verify that stale bytes are erased BEFORE anything is published.
with patch.dict("os.environ", {"PH_OWNER_APPROVED_ALL_SPORTS":"1"}):
    forged=[
        N(type="single",player="good",sport="NBA",odds=3.19,
          leg_details=[{"sport":"NBA","player":"A","odds":1.79},
                       {"sport":"NBA","player":"B","odds":1.80}],
          features={"combined_odds_observed":True,"combined_quote_id":"other"}),
        N(type="ladder",player="good",sport="NBA",odds=3.19,
          leg_details=[{"sport":"NBA","player":"A","odds":1.79},
                       {"sport":"NBA","player":"B","odds":1.80}]),
    ]
    for item in forged:
        item._verified_owner_png=PNG
    untouched=Cards()
    sent,blocked=filter_verified_nba_images(forged,untouched)
    assert sent == [] and blocked == 2
    assert untouched.calls == []
    assert all(not hasattr(item, "_verified_owner_png") for item in forged)
print("FORGED SINGLE/LADDER STALE IMAGE FAIL-CLOSED PASSED")


# Owner pixel QA is REQUIRED for live production. A valid PNG header, correct
# dimensions and genuine-looking generic artwork are not visual approval.
with patch.dict("os.environ", {
    "PH_OWNER_APPROVED_ALL_SPORTS":"1",
    "PH_NBA_OWNER_ORIGINALS":"1",
    "PH_OWNER_PIXEL_QA":"1",
}):
    synthetic=p("good","NBA")
    good,blocked=filter_verified_nba_images([synthetic],Cards())
    assert good == [] and blocked == 1
    assert not hasattr(synthetic,"_verified_owner_png")
print("PIXEL QA REJECTS SYNTHETIC PNG BEFORE TELEGRAM")


# Fresh single odds must come from a named observed bookmaker, and pre-match
# tickets must have a future event timestamp. No live HTTP or Telegram.
from datetime import datetime,timezone,timedelta
from prop_hunter_image_publication_gate import pre_match_quote_provenance
future=(datetime.now(timezone.utc)+timedelta(days=3)).isoformat()
past=(datetime.now(timezone.utc)-timedelta(hours=3)).isoformat()
observed={"odds_observed":True,"bookmaker":"QA_OBSERVED_BOOK"}
valid=N(type="single",sport="NBA",odds=1.86,
        commence_time=future,features=dict(observed))
assert pre_match_quote_provenance(valid)[0]
assert not pre_match_quote_provenance(N(
    type="single",odds=1.86,commence_time=future,features={}))[0]
assert not pre_match_quote_provenance(N(
    type="single",odds=float("inf"),commence_time=future,
    features=dict(observed)))[0]
assert not pre_match_quote_provenance(N(
    type="single",odds=1.86,commence_time=past,features=dict(observed)))[0]
assert not pre_match_quote_provenance(N(
    type="single",odds=1.86,features=dict(observed)))[0]
assert not pre_match_quote_provenance(N(
    type="single",odds=1.86,commence_time=future,
    features={"odds_observed":True,"bookmaker":"model"}))[0]
cross=N(type="lottery",odds=3.55,
        features={"combined_odds_observed":True,"combined_quote_id":"QA",
                  "combo_scope":"cross_game"},
        leg_details=[{"commence_time":future},{"commence_time":past}])
assert not pre_match_quote_provenance(cross)[0]
cross.leg_details[1]["commence_time"]=future
assert pre_match_quote_provenance(cross)[0]
print("PREMATCH SOURCE / BOOKMAKER / STARTED-FIXTURE BLOCK PASSED")
