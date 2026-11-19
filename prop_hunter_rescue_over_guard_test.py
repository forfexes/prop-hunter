"""Regression for direct-source side recognition in rescue Over odds cap."""
import ast
import re
from pathlib import Path
from types import SimpleNamespace

tree=ast.parse(Path("prophunter_core_1391.py").read_text(encoding="utf8"))
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="rescue_picks_from_props")
assigns={}
for node in ast.walk(fn):
    if isinstance(node,ast.Assign):
        for target in node.targets:
            if isinstance(target,ast.Name) and target.id in ("_source_direction","_is_over"):
                assigns[target.id]=node
assert set(assigns)=={"_source_direction","_is_over"}, "Rescue source-side guard missing"
guard=compile(ast.fix_missing_locations(ast.Module(
    body=[assigns["_source_direction"],assigns["_is_over"]],type_ignores=[])),
    "rescue-over-direction","exec")
def check(direction,market,expected):
    ns={"sp":SimpleNamespace(direction=direction),"feats":{},
        "_mkt_low":market.lower(),"re":re}
    exec(guard,ns)
    assert ns["_is_over"] is expected,(direction,market,ns["_is_over"])
check("over","Points",True)
check("under","Points",False)
check("","Points Over 5.5",True)
check("","Points Under 5.5",False)
print("RESCUE DIRECT BOOKMAKER OVER-DIRECTION GUARD PASSED")

# When qualified NFL/NHL picks exist, the global NBA edge ranking may NOT
# crowd every other sport out of the bounded 20-pick rescue.
from collections import defaultdict
select_fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_rescue_select_diverse")
select_ns={"defaultdict":defaultdict}
exec(compile(ast.fix_missing_locations(ast.Module(body=[select_fn],type_ignores=[])),
             "rescue-diversity-offline","exec"),select_ns)
choose=select_ns["_rescue_select_diverse"]
def p(name,sport,game):
    return SimpleNamespace(player=name,sport=sport,game=game,team=None)
ranked=[p("NBA 1","NBA","NBA A"),p("NBA 2","NBA","NBA A"),
        p("NBA 3","NBA","NBA A"),p("NBA 4","NBA","NBA A"),
        p("NFL 1","NFL","NFL A"),p("NHL 1","NHL","NHL A")]
result=choose(ranked,4)
assert len(result)==4, result
assert {p.sport for p in result}=={"NBA","NFL","NHL"}, result
assert result[0].player=="NBA 1", result
assert len({p.player for p in result})==len(result)
assert len([p for p in result if p.game=="NBA A"])<=3
# Never fabricate or force NHL when no NHL prop survived all upstream gates.
assert {p.sport for p in choose(ranked[:4],4)}=={"NBA"}
# Sport priority can be disabled without changing legacy global-edge semantics.
legacy=choose(ranked,3,min_per_sport=0)
assert [p.player for p in legacy]==["NBA 1","NBA 2","NBA 3"]
# Small windows and duplicate athletes still preserve capacity and IDs.
assert len(choose(ranked,2))==2
assert len(choose([p("Same","NBA","G1"),p("Same","NFL","G2")],2))==1
print("SPORT DIVERSITY ONLY AFTER QUALITY / NO FORCED PICKS PASSED")
