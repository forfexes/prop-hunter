"""Never attach an unrelated ESPN athlete photo when identities are ambiguous."""
from unittest.mock import patch
import prop_hunter_image_cards as cards


def _item(pid, name="Alex Smith", league="nba"):
    return {"id": str(pid), "displayName": name, "league": league}


def test_unique_exact_player_id_is_accepted():
    cards._CACHE.clear()
    marker = object()
    with patch.object(cards, "_get_json", return_value={"items":[_item(123), _item(123), _item(99, "Other Player")]}), \
         patch.object(cards, "_get_image", return_value=marker) as load:
        assert cards.player_photo("Alex Smith", cards.LEAGUES["nba"]) is marker
        assert load.call_count == 1
        assert "/123.png" in load.call_args.args[0]
    cards._CACHE.clear()


def test_same_name_two_ids_is_rejected_without_image_fetch():
    cards._CACHE.clear()
    with patch.object(cards, "_get_json", return_value={"items":[_item(123), _item(456)]}), \
         patch.object(cards, "_get_image", side_effect=AssertionError("Wrong image fetch")):
        assert cards.player_photo("Alex Smith", cards.LEAGUES["nba"]) is None
    cards._CACHE.clear()


def test_other_league_cannot_supply_same_name_face():
    cards._CACHE.clear()
    with patch.object(cards, "_get_json", return_value={"items":[_item(123, league="wnba")]}), \
         patch.object(cards, "_get_image", side_effect=AssertionError("Wrong league image")):
        assert cards.player_photo("Alex Smith", cards.LEAGUES["nba"]) is None
    cards._CACHE.clear()


def test_no_name_or_league_rejected_before_search():
    with patch.object(cards, "_get_json", side_effect=AssertionError("Unexpected search")):
        assert cards.player_photo("", cards.LEAGUES["nba"]) is None
        assert cards.player_photo("Alex Smith", None) is None


def test_accented_player_name_uses_ascii_query_but_exact_identity():
    cards._CACHE.clear()
    marker = object()
    with patch.object(cards, "_get_json", side_effect=[
        {"items": []},
        {"items": [_item(123, "Julio Rodriguez", "mlb")]}
    ]) as search, patch.object(cards, "_get_image", return_value=marker) as load:
        assert cards.player_photo("Julio Rodríguez", cards.LEAGUES["mlb"]) is marker
        assert search.call_count == 2
        assert search.call_args_list[0].args[1]["query"] == "Julio Rodríguez"
        assert search.call_args_list[1].args[1]["query"] == "Julio Rodriguez"
        assert "/123.png" in load.call_args.args[0]
    cards._CACHE.clear()
