"""Numerical guardrails for both sports bots' formula-only analyses."""
import math
import pytest
from premium_joint_formula import estimate_combo


def leg(game, odds, p=None, observed=True):
    return dict(game=game, odds=odds, model_probability=p,
                odds_observed=observed)


def test_independent_games_compound_probability_and_odds():
    rows=[leg("A vs B",1.90,0.60),leg("C vs D",1.80,0.50)]
    result=estimate_combo(rows)
    assert result["scope"]=="separate_games_independence_assumed"
    assert result["indicative_leg_product"]==3.42
    assert math.isclose(result["joint_probability"],0.30)
    assert math.isclose(result["fair_model_odds"],10/3)
    assert result["real_bookmaker_combined_odds"] is None
    assert result["ev_percent_using_real_ticket_only"] is None
    assert result["settle_as_bookmaker_ticket"] is False
    assert "KEINE BUCHMACHERQUOTE" in result["indicative_label"]


def test_actual_ticket_ev_different_from_leg_product():
    rows=[leg("A vs B",1.90,0.60),leg("C vs D",1.80,0.50)]
    answer=estimate_combo(rows,observed_ticket=dict(
        combined_odds_observed=True,combined_quote_id="book-quote",
        odds=3.60))
    assert math.isclose(answer["ev_percent_using_real_ticket_only"],8.0)
    assert answer["real_bookmaker_combined_odds"]==3.60
    assert answer["indicative_leg_product"]==3.42


def test_same_game_is_correlated_not_independent():
    rows=[leg("A vs B",1.9,0.60),leg("A vs B",2.2,0.65)]
    r=estimate_combo(rows)
    assert r["scope"]=="shared_game_correlated"
    assert r["joint_probability"] is None
    assert r["fair_model_odds"] is None
    assert r["ev_percent_using_real_ticket_only"] is None


def test_same_game_chain_rule():
    rows=[leg("A vs B",1.9,0.60),leg("A vs B",2.2,0.65)]
    r=estimate_combo(rows,conditional_probabilities=[0.70])
    assert r["joint_probability_method"]=="chain_rule_observed_conditionals"
    assert math.isclose(r["joint_probability"],0.42)
    assert math.isclose(r["fair_model_odds"],1/0.42)


def test_same_game_joint_sample_frequency():
    rows=[leg("A vs B",1.9,0.60),leg("A vs B",2.2,0.65)]
    r=estimate_combo(rows,joint_observations={"wins":18,"total":40})
    assert math.isclose(r["joint_probability"],0.45)
    assert r["joint_probability_method"]=="observed_joint_frequency"


def test_unknown_game_identity_must_not_assume_independence():
    rows=[dict(odds=1.8,model_probability=0.7),
          dict(odds=1.9,model_probability=0.6)]
    r=estimate_combo(rows)
    assert r["scope"]=="event_identity_unknown"
    assert r["fair_model_odds"] is None


def test_unverified_leg_odds_are_not_mislabeled_observed():
    r=estimate_combo([leg("A vs B",1.8,0.6,False),leg("C vs D",1.9,0.6)])
    assert r["individual_prices_observed"] is False
    assert r["indicative_leg_product"]==3.42


@pytest.mark.parametrize("bad", [None,1.0,0,-3,float("nan"),float("inf"),"not a price"])
def test_bad_individual_quote_rejected(bad):
    with pytest.raises(ValueError):
        estimate_combo([leg("A vs B",1.7,0.6),leg("C vs D",bad,0.7)])


@pytest.mark.parametrize("ticket", [
    {"combined_odds_observed":False,"combined_quote_id":"123","odds":4.0},
    {"combined_odds_observed":True,"combined_quote_id":" ","odds":4.0},
    {"combined_odds_observed":True,"combined_quote_id":"123","odds":float("inf")},
])
def test_no_real_ev_from_invalid_ticket(ticket):
    r=estimate_combo([leg("A vs B",1.7,0.6),leg("C vs D",1.8,0.7)],
                     observed_ticket=ticket)
    assert r["real_bookmaker_combined_odds"] is None
    assert r["ev_percent_using_real_ticket_only"] is None


def test_joint_sample_and_conditional_reject_bad_inputs():
    rows=[leg("A vs B",1.7,0.6),leg("A vs B",1.8,0.7)]
    with pytest.raises(ValueError):
        estimate_combo(rows,joint_observations={"wins":10,"total":20})
    with pytest.raises(ValueError):
        estimate_combo(rows,conditional_probabilities=[0.8,0.7])
    with pytest.raises(ValueError):
        estimate_combo(rows,conditional_probabilities=[float("nan")])
