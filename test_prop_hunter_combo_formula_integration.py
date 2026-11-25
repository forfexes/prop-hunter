"""Integration: real ticket prices and separately labelled mathematical formulas."""
from types import SimpleNamespace
import math
from prop_hunter_combo_prices import prepare_calculated_combo, publishable_extra

def _pick(features, games=("A vs B","C vs D"),odds=3.6):
    return SimpleNamespace(
        type="lottery", odds=odds, features=dict(features),
        leg_details=[
            dict(game=games[0],odds=1.90,probability=0.60,odds_observed=True),
            dict(game=games[1],odds=1.80,probability=0.50,odds_observed=True),
        ])

def test_real_ticket_has_separate_model_fair_odds_and_ev():
    p=_pick(dict(combined_odds_observed=True,combined_quote_id="BOOK-REAL-EXAMPLE"))
    result=prepare_calculated_combo(p)
    assert result.odds==3.6
    f=result.features
    assert f["formula_indicative_leg_product"]==3.42
    assert math.isclose(f["formula_joint_probability"],0.3)
    assert math.isclose(f["formula_fair_odds"],1/0.3)
    assert math.isclose(f["formula_ev_real_ticket_only"],8.0)
    assert f["formula_method"]=="independence_assumption"
    assert publishable_extra(result)

def test_unbookable_combo_still_calculated_but_cannot_publish_as_real_quote():
    p=_pick(dict(),odds=None)
    result=prepare_calculated_combo(p)
    assert result.odds==3.42
    assert result.features["calculated_combined_odds"]==3.42
    assert result.features["formula_joint_probability"]==0.3
    assert result.features["formula_ev_real_ticket_only"] is None
    assert not publishable_extra(result)

def test_correlated_builder_never_assumes_independence():
    p=_pick(dict(combined_odds_observed=True,combined_quote_id="BOOK-TICKET"),
            games=("A vs B","A vs B"))
    prepare_calculated_combo(p)
    assert p.features["formula_scope"]=="shared_game_correlated"
    assert p.features["formula_joint_probability"] is None
    assert p.features["formula_fair_odds"] is None
    assert p.features["formula_ev_real_ticket_only"] is None

def test_correlated_builder_with_true_conditionals():
    p=_pick(dict(combined_odds_observed=True,combined_quote_id="BOOK-TICKET",
                 conditional_probabilities=[0.7]),games=("A vs B","A vs B"))
    prepare_calculated_combo(p)
    assert p.features["formula_method"]=="chain_rule_observed_conditionals"
    assert math.isclose(p.features["formula_joint_probability"],0.42)
    assert math.isclose(p.features["formula_ev_real_ticket_only"],51.2)

def test_conflicting_formula_markers_never_produce_bookmaker_ev():
    p=_pick(dict(combined_odds_observed=True,combined_quote_id="STALE",
                 combined_quote_calculated=True),odds=5)
    prepare_calculated_combo(p)
    assert p.features["formula_ev_real_ticket_only"] is None
    assert not publishable_extra(p)


def test_formula_runs_before_price_rejection_and_preserves_live_separation():
    from prop_hunter_combo_prices import analyse_formula_candidates
    missing=_pick({},odds=None)
    actual=_pick({"combined_odds_observed":True,"combined_quote_id":"BOOK-ID"})
    accepted,deferred,summary=analyse_formula_candidates([missing,actual])
    assert accepted==[actual] and deferred==[missing]
    assert missing.features["calculated_combined_odds"]==3.42
    assert missing.features["formula_ev_real_ticket_only"] is None
    assert summary["verified_leg_formulas"]==2
    assert summary["offline_unbookable"]==1
    assert not publishable_extra(missing)

def test_core_does_not_drop_extras_before_formula():
    from pathlib import Path
    source=Path("prophunter_core_1391.py").read_text()
    stage=source[source.index("extras = build_autonomous_extras(picks, props, Pick, LadderLeg)"):]
    stage=stage[:stage.index("from prop_hunter_form_quality import filter_tickets")]
    assert "picks = picks + extras" in stage
    assert "analyse_formula_candidates(picks)" in stage
    assert "extras = [p for p in extras if publishable_extra(p)]" not in stage
