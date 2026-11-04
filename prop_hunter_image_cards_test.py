from types import SimpleNamespace as N
import prop_hunter_image_cards as cards


def _det(name, market, point, odds):
    return {"player": name, "sport": "basketball_nba", "market": market, "direction": "over", "point": point, "odds": odds,
            "features": {"recent_form": {"l5": {"hits": 4, "n": 5}, "l10": {"hits": 8, "n": 10}, "l15": {"hits": 11, "n": 15}}}}


def _no_net(monkeypatch):
    monkeypatch.setattr(cards, "player_photo", lambda *a, **k: None)
    monkeypatch.setattr(cards, "team_logo", lambda *a, **k: None)


def test_builder_card_is_png(monkeypatch):
    _no_net(monkeypatch)
    pick = N(type="betbuilder", features={}, game="Lakers vs Celtics", source_sport="basketball_nba", odds=3.4,
             leg_details=[_det("Luka Doncic", "Points", 25.5, 1.8), _det("Jayson Tatum", "Rebounds", 6.5, 1.9)])
    png = cards.build_for_pick(pick)
    assert png and png[:8] == b"\x89PNG\r\n\x1a\n"


def test_cross_game_has_no_team_header(monkeypatch):
    _no_net(monkeypatch)
    pick = N(type="betbuilder", features={"combo_scope": "cross_game", "builder_odds_estimated_from_legs": True}, game="Cross", source_sport="nhl",
             leg_details=[_det("A B", "Shots", 3.5, 1.9), _det("C D", "Points", 1.5, 2.1)], odds=4.0)
    assert cards.build_for_pick(pick)


def test_ladder_card(monkeypatch):
    _no_net(monkeypatch)
    legs = [N(market="Over 15.5 Points", odds=1.7), N(market="Over 20.5 Points", odds=2.4), N(market="Over 25.5 Points", odds=4.1)]
    pick = N(type="ladder", features={}, player="Luka Doncic", game="Lakers vs Celtics", source_sport="basketball_nba", picks=legs,
             leg_details=[{"gamelog_l15_hits": 13, "gamelog_l15_n": 15}] * 3)
    assert cards.build_for_pick(pick)


def test_missing_data_returns_none(monkeypatch):
    _no_net(monkeypatch)
    assert cards.build_for_pick(N(type="betbuilder", features={}, leg_details=[])) is None


def test_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(cards, "ON", False)
    assert cards.build_for_pick(N(type="betbuilder", features={}, leg_details=[_det("A B", "Points", 10.5, 1.8)])) is None
