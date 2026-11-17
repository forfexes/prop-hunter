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
