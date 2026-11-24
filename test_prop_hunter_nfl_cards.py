"""NFL render and existing Telegram transport with a fake HTTP endpoint."""
import ast
import os
import time
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace as Pick
from unittest.mock import Mock, patch

from PIL import Image

import prop_hunter_image_cards as cards


def test_nfl_cards_offline():
    tree = ast.parse(Path("prophunter_core_1391.py").read_text())
    names = {"_payload_card_image", "send_telegram"}
    methods = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    call = Mock(return_value=Pick(
        status_code=200, text="", content=b"{}",
        json=lambda: {"ok": True, "result": {"message_id": 47}},
    ))
    payload = {"text": "NFL sandbox", "kind": "single", "single_indices": [0]}
    namespace = {
        "os": os, "time": time, "log": Mock(), "requests": Pick(post=call),
        "TG_TOKEN": "OFFLINE", "TG_CHAT": "OFFLINE", "TIMEOUT": 5,
        "_LAST_TELEGRAM_CARDS": [], "_telegram_payloads": lambda *_: [payload],
    }
    exec(compile(ast.Module(body=methods, type_ignores=[]), "<telegram>", "exec"), namespace)
    fixtures = ["Vikings vs Bears", "Bills vs Jets", "Bengals vs Ravens"]
    examples = [("single", 0), ("ladder", 3)]
    examples += [(kind, n) for kind in ("builder", "cross", "lottery") for n in range(2, 7)]
    with patch.object(cards, "ON", True), patch.object(cards, "player_photo", return_value=None), \
         patch.dict(os.environ, {"PH_NFL_PREMIUM_CARDS": "1", "PH_TELEGRAM_SEND_DELAY": "0"}):
        for kind, n in examples:
            details = [
                {"sport": "NFL", "player": "QA Player" if kind == "ladder" else f"QA Player {i}",
                 "game": fixtures[0 if kind in ("builder", "ladder") else i % 3],
                 "market": "receiving_yards", "direction": "over", "point": 50.5+i,
                 "odds": 1.85}
                for i in range(n)
            ]
            pick = Pick(
                type={"builder": "betbuilder", "cross": "kombi2"}.get(kind, kind),
                source_sport="NFL", game=fixtures[0], player="QA Player",
                features={"combo_scope": "cross_game"} if kind == "cross" else {},
                market="receiving_yards", direction="over", point=50.5, odds=1.85,
                leg_details=details,
            )
            if kind not in ("single", "ladder"):
                assert cards.build_for_pick(pick) is None  # no bookmaker receipt
                pick.features.update(combined_odds_observed=True, combined_quote_id=f"qa-{kind}-{n}")
            img = cards.build_for_pick(pick)
            with Image.open(BytesIO(img)) as rendered:
                assert rendered.format == "PNG"
                assert rendered.size == (900, 1125)
                rendered.verify()
            payload.clear()
            payload.update(text="NFL sandbox", kind="single" if kind == "single" else "combo",
                           single_indices=[0], combo_indices=[0])
            assert namespace["send_telegram"]("NFL sandbox", picks=[pick]) == 47
            args, kwargs = call.call_args
            assert args[0].endswith("/sendPhoto")
            assert kwargs["files"]["photo"][1] == img
        assert call.call_count == 17
        with patch.dict(os.environ, {"PH_NFL_PREMIUM_CARDS": "0"}):
            assert cards.build_for_pick(pick) is None
        pick.leg_details[0]["sport"] = "NBA"
        assert cards.build_for_pick(pick) is None


if __name__ == "__main__":
    test_nfl_cards_offline()
    print("NFL sandbox: 17 PNG variants and 17 simulated Telegram photo deliveries")
