#!/usr/bin/env python3
"""Regression tests for fail-closed probability and collector reporting gates."""
from pathlib import Path
from types import SimpleNamespace

import prop_hunter_builder_engine as engine


def prop(features, probability=None):
    return SimpleNamespace(
        odds=2.20,
        probability=probability,
        features={"odds_observed": True, "price_type": "bookmaker", **features},
        market="Points",
    )


# A bookmaker quote alone must never be turned into a model probability.
assert engine._candidate_probability(prop({"gamelog_n": 15})) is None
assert engine._candidate_probability(prop({"fair_prob": 0.72, "gamelog_n": 15})) is None

# Independent probability is passed through, not blended with implied odds.
p = engine._candidate_probability(prop({"model_prob": 0.63, "gamelog_n": 10}))
assert p == 0.63, p

# Small samples cannot produce builder EV.
assert engine._candidate_probability(prop({"model_prob": 0.80, "gamelog_n": 5})) is None
assert engine._candidate_probability(prop({"model_prob": 0.80, "gamelog_n": 0})) is None

core = Path("prophunter_core_1391.py").read_text(encoding="utf-8")
assert "max(0.12" not in core, "synthetic HR probability floor returned"
assert "hr_prob_unavailable" in core, "HR fail-closed rejection missing"

workflow = Path(".github/workflows/prophunter_results.yml").read_text(encoding="utf-8")
assert "python prop_hunter_results_mlb.py || true" not in workflow
assert '"$@" || rc=$?' in workflow
assert "PH_COLLECTOR_FAILURE=1" in workflow
assert "Fail visibly when any results collector failed" in workflow

print("Quality gates OK: HR probability, builder sample size, and collector failures")
