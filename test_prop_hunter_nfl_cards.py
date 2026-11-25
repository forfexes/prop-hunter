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
from prop_hunter_combo_prices import calculated_combo_quote, publishable_extra


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
                 "odds": 1.85, "odds_observed": True}
                for i in range(n)
            ]
            pick = Pick(
                type={"builder": "betbuilder", "cross": "kombi2"}.get(kind, kind),
                source_sport="NFL", game=fixtures[0], player="QA Player",
                features={"combo_scope": "cross_game"} if kind == "cross" else {},
                market="receiving_yards", direction="over", point=50.5, odds=1.85,
                leg_details=details,
            )
            if kind == "builder":
                assert cards.build_for_pick(pick) is None  # no bookmaker receipt
                pick.features.update(combined_odds_observed=True, combined_quote_id=f"qa-{kind}-{n}")
            if kind in ("cross", "lottery"):
                assert not publishable_extra(pick)
                assert calculated_combo_quote(pick) == round(1.85 ** n, 4)
                with patch.dict(details[-1], {"odds": None}):
                    assert cards.build_for_pick(pick) is None
            img = cards.build_for_pick(pick)
            with Image.open(BytesIO(img)) as rendered:
                assert rendered.format == "PNG"
                assert rendered.size == (900, 1125)
                rendered.verify()
            review_dir = os.getenv("PH_NFL_OFFLINE_REVIEW")
            if review_dir:
                from PIL import ImageDraw, ImageFont
                out = Path(review_dir)
                out.mkdir(parents=True, exist_ok=True)
                with Image.open(BytesIO(img)) as source:
                    # Add a separate QA footer BELOW the exact transmitted
                    # card, never alter its actual pixels or production art.
                    preview = Image.new("RGB", (source.width, source.height+48), "#041021")
                    preview.paste(source.convert("RGB"), (0,0))
                    draw = ImageDraw.Draw(preview)
                    draw.text((source.width//2,source.height+24),
                              "SANDBOX · SYNTHETISCHE DATEN · KEIN TIPP",
                              font=ImageFont.truetype("DejaVuSans-Bold.ttf",20),
                              fill="white",anchor="mm")
                    preview.save(out/f"{kind}_{n}_SANDBOX.png")
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


def test_formula_publication_across_sports():
    from datetime import datetime, timezone
    from prop_hunter_combo_prices import publishable_tip
    from prop_hunter_image_publication_gate import filter_verified_nba_images

    source = ast.parse(Path("prophunter_core_1391.py").read_text())
    names = {"_combo_pro_title", "_render_combo_pro_tip", "_telegram_payloads", "_payload_card_image"}
    functions = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {"datetime": datetime, "timezone": timezone, "os": os, "log": Mock(),
                 "_fmt_leg": lambda leg, _: leg}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "<telegram>", "exec"), namespace)
    with patch.dict(os.environ, {"PH_NBA_OWNER_ORIGINALS": "1", "PH_OWNER_APPROVED_ALL_SPORTS": "1"}):
        for sport in ("NBA", "WNBA", "NHL", "MLB", "NFL"):
            for kind in ("kombi2", "lottery", "betbuilder"):
                pick = Pick(type=kind, source_sport=sport, odds=99, edge_pct=12,
                            features={"combo_scope": "cross_game"} if kind == "betbuilder" else {},
                            leg_details=[{"sport": sport, "game": "A vs B", "odds": 1.5, "odds_observed": True},
                                         {"sport": sport, "game": "C vs D", "odds": 2.0, "odds_observed": True}])
                assert publishable_tip(pick)
                assert not publishable_extra(pick)
                assert filter_verified_nba_images([pick], cards) == ([], 1)
                payload, = namespace["_telegram_payloads"]("", [pick])
                assert "Berechnete Gesamtquote @3.00" in payload["text"]
                assert "keine bestätigte Buchmacherquote" in payload["text"]
                assert "@99" not in payload["text"] and "EV 12" not in payload["text"]
                if sport != "NFL":
                    assert namespace["_payload_card_image"](payload, [pick]) is None
                    assert payload.get("premium_required")
                pick.leg_details[0]["odds_observed"] = False
                assert not publishable_tip(pick)
                pick.leg_details[0]["odds_observed"] = True
                pick.leg_details[0]["odds"] = None
                assert not publishable_tip(pick)
