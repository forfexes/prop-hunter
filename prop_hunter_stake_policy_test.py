"""No Telegram, network or database: fractional Ladder units always match ticket."""
from types import SimpleNamespace as P
from prop_hunter_stake_policy import apply_flat_ticket_stake as flat

for n in (2, 3, 4, 5, 6):
    ticket = P(type="ladder",stake=.1,market="points",picks=[
        P(market=f"over {i}",odds=1.8+i*.1,stake=.05) for i in range(n)
    ])
    assert flat(ticket,1.0) is ticket
    assert ticket.stake == 1.0
    assert round(sum(leg.stake for leg in ticket.picks),2) == 1.0
    assert all(0 < leg.stake <= 1.0 for leg in ticket.picks)
    assert max(leg.stake for leg in ticket.picks)-min(
        leg.stake for leg in ticket.picks) <= 0.01000001
    print("ONE_UNIT_LADDER",n,[leg.stake for leg in ticket.picks])

for kind in ("single","betbuilder","combo","kombi2"):
    p=P(type=kind,stake=.2,market="points",picks=None)
    flat(p,1.0)
    assert p.stake == 1.0,kind
for kind in ("big","lottery"):
    p=P(type=kind,stake=1.0,market="lottery",picks=None)
    flat(p,1.0)
    assert p.stake == 1.0,kind
    # A lower Lottery stake is permitted only by explicit opt-in, never as
    # the production default or an unnoticed ledger/image discrepancy.
    flat(p,1.0,lottery_amount=.1)
    assert p.stake == 0.1,kind
for wrong in (0, -1, float("nan"), "bad", 6):
    try:flat(P(type="single",market="points",stake=.2),wrong)
    except ValueError:pass
    else:raise AssertionError("Invalid stake accepted: "+str(wrong))
try:flat(P(type="ladder",stake=1.0,market="points",picks=[]),1.0)
except ValueError:pass
else:raise AssertionError("Missing ladder legs accepted")
print("PROP_HUNTER_ALL_TICKETS_ONE_UNIT_LEDGER_TEST_PASS")
