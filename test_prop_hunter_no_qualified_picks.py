#!/usr/bin/env python3
"""Run the actual selection functions with offline stubs; never send Telegram."""
import ast
import logging
import os
from pathlib import Path
from types import SimpleNamespace

path = Path(__file__).with_name("prophunter_core_1391.py")
tree = ast.parse(path.read_text(encoding="utf-8"))
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"run", "analyse"}]
assert len(nodes) == 2

def forbidden(*args, **kwargs):
    raise AssertionError("No card rendering, send, or persistence allowed")

def execute(props, model_candidates, rescue_candidates=()):
    log = logging.getLogger("no-qualified-picks-regression")
    calls = []
    def rescue(*args, **kwargs):
        calls.append("rescue")
        return list(rescue_candidates)
    ns = dict(os=os, log=log, PH_RUNTIME_VERSION="offline",
              RESCUE_MAX_PICKS=4, RESCUE_FILL_TARGET=4,
              gather=lambda _: props,
              build_prompt=lambda _: "",
              call_with_retry=lambda *_: [SimpleNamespace(type="builder")] * model_candidates,
              quality_filter_picks=lambda _: [],
              rescue_picks_from_props=rescue,
              filter_picks=lambda _: [],
              build_post=forbidden, send_telegram=forbidden, persist=forbidden)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), ns)
    ns["run"]()
    return calls

os.environ["PH_FAIL_ON_EMPTY_CARD"] = "1"
assert len(execute([object()], 7)) == 2
assert len(execute([object()], 7, [object()])) == 2
for props, model, expected in [([], 0, "no observed props"), ([object()], 0, "zero qualified")]:
    try:
        execute(props, model)
    except RuntimeError as exc:
        assert expected in str(exc), str(exc)
    else:
        raise AssertionError("Technical failure must remain visible")
print("NO_QUALIFIED_PICKS regression passed: valid abstention, dedup, empty data, missing model")
