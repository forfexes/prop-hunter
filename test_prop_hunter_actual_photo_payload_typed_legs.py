"""Hermetic production send-entry regression for Pydantic/namespace leg models.

Extract ONLY the photo payload function from the large autonomous module.
No collectors, ESPN, Telegram, GitHub token or Supabase are called.
"""
import ast
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch

source = ast.parse(Path("prophunter_core_1391.py").read_text(encoding="utf-8"))
fn = next(n for n in source.body if isinstance(n, ast.FunctionDef)
          and n.name == "_payload_card_image")
code = compile(ast.Module(body=[fn], type_ignores=[]),
               "prophunter_core_1391.py", "exec")
errors = []
namespace = {"os": os, "log": N(error=lambda *args: errors.append(args))}
exec(code, namespace)
render = namespace["_payload_card_image"]

fake = types.ModuleType("prop_hunter_image_cards")
fake.ON = True
fake.league_of = lambda hint: ("basketball", "nba") if str(hint).upper() == "NBA" else None
fake.snapshot = lambda pick: {"type": pick.type, "sport": "NBA",
                              "leg_details": [{"sport": "NBA"}]}
built = []
fake.build_for_pick = lambda pick: built.append(pick) or b"QA_PNG"

for detail in (N(sport="NBA", odds=1.75), {"sport": "NBA", "odds": 1.75}):
    pick = N(type="ladder", source_sport=None, sport=None,
             leg_details=[detail, detail])
    payload = {"kind": "ladder", "combo_indices": [0]}
    with patch.dict(sys.modules, {"prop_hunter_image_cards": fake}), \
         patch.dict(os.environ, {"PH_NBA_OWNER_ORIGINALS": "1"}):
        result = render(payload, [pick])
    assert result == b"QA_PNG", (detail, errors)
    assert payload["premium_required"] is True, payload
    assert payload["media_type"] == "photo", payload
    assert isinstance(payload["image_pick"], dict)
    assert built[-1] is pick
assert not errors, errors
print("ACTUAL_TELEGRAM_TYPED_LADDER_LEGS_PHOTO_PASS")

# A renderer error must fail closed with a useful diagnostic, never fallback
# silently to a generic Telegram message or invent a photo.
fake.build_for_pick = lambda pick: (_ for _ in ()).throw(ValueError("QA error"))
payload = {"kind": "ladder", "combo_indices": [0]}
with patch.dict(sys.modules, {"prop_hunter_image_cards": fake}), \
     patch.dict(os.environ, {"PH_NBA_OWNER_ORIGINALS": "1"}):
    assert render(payload, [pick]) is None
assert payload.get("media_type") != "photo"
assert any("ValueError" in str(item) for item in errors), errors
print("ACTUAL_TELEGRAM_PHOTO_ERROR_FAILS_CLOSED_WITH_DIAGNOSTIC")

# Mark a message as safe for IN-PHOTO settlement only after the actual owner
# pixel verifier accepts the rendered image. The marker is saved alongside
# that message's original image_pick snapshot; old screenshots have none.
fake.build_for_pick = lambda pick: b"PIXEL_QA_ONLY"
pixel = types.ModuleType("prop_hunter_owner_pixel_qa")
pixel.owner_pixel_provenance = lambda pick, data: (
    (True, "source_original_pixels_verified")
    if data == b"PIXEL_QA_ONLY" else (False, "invalid_source")
)
payload = {"kind": "ladder", "combo_indices": [0]}
with patch.dict(sys.modules, {
         "prop_hunter_image_cards": fake,
         "prop_hunter_owner_pixel_qa": pixel}), \
     patch.dict(os.environ, {
         "PH_NBA_OWNER_ORIGINALS": "1",
         "PH_BLOCK_OVERPAINTED_MASTERS": "1",
         "PH_ALLOW_VERIFIED_LAYERED_OWNER": "1",
         "PH_OWNER_PIXEL_QA": "1"}):
    assert render(payload, [pick]) == b"PIXEL_QA_ONLY"
assert payload["image_pick"]["_owner_layered_original_v1"] is True
assert payload["media_type"] == "photo"

# A beautiful but unapproved image is NEVER tagged or sent.
pixel.owner_pixel_provenance = lambda pick, data: (
    False, "owner_masthead_pixel_overlap")
payload = {"kind": "ladder", "combo_indices": [0]}
with patch.dict(sys.modules, {
         "prop_hunter_image_cards": fake,
         "prop_hunter_owner_pixel_qa": pixel}), \
     patch.dict(os.environ, {
         "PH_NBA_OWNER_ORIGINALS": "1",
         "PH_BLOCK_OVERPAINTED_MASTERS": "1",
         "PH_ALLOW_VERIFIED_LAYERED_OWNER": "1",
         "PH_OWNER_PIXEL_QA": "1"}):
    assert render(payload, [pick]) is None
assert "_owner_layered_original_v1" not in payload["image_pick"]
assert payload.get("media_type") != "photo"
print("IN_PHOTO_SETTLEMENT_MARKER_REQUIRES_REAL_PIXEL_QA_PASS")
