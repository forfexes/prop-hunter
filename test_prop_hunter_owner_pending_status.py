"""Offline original-card QA: pending is WHITE, unframed and on owner line.

Do not add a fake gold/black status box over the approved source artwork.
"""
from pathlib import Path
import ast
import prop_hunter_owner_clean_single as single
import prop_hunter_owner_clean_ladder as ladder
import prop_hunter_owner_clean_builder as builder
import prop_hunter_owner_clean_lottery as lottery

for module in (single,ladder,builder,lottery):
    src=Path(module.__file__).read_text(encoding="utf-8")
    ast.parse(src)
    assert "owner_settlement_state(" in src, module.__name__
    assert "Image.alpha_composite(im, ribbon)" not in src, module.__name__
    # The common rendering helper supplies the OFFEN default. Individual
    # family renderers no longer have to hardcode it a second time.
    assert module.WHITE==(250,251,253), module.__name__
print("OWNER_SINGLE_LADDER_BUILDER_LOTTERY_PENDING_WHITE_UNFRAMED_PASS")

from prop_hunter_owner_clean_single import owner_settlement_state
for value,expected in [
    ("OFFEN", "white"), ("pending", "white"), ("WON", "green"),
    ("VERLOREN", "red"), ("lost", "red"),
    ("2 gewonnen · 1 verloren", "red"),
    ("2 gewonnen · 0 verloren", "green"),
    ("1 gewonnen · 1 offen", "white"),
    ("2 gewonnen · 0 verloren · 1 offen", "white"),
    ("0 gewonnen · 0 verloren", "white"),
    ("PUSH", "white"), ("VOID", "white"),
    ("unbekannt", "white"),
]:
    label,ink=owner_settlement_state(value,green="green",red="red",white="white")
    assert ink==expected,(value,label,ink,expected)
assert owner_settlement_state("WON",green="green",red="red",white="white")[0]=="GEWONNEN"
assert owner_settlement_state("LOST",green="green",red="red",white="white")[0]=="VERLOREN"
assert owner_settlement_state(None,green="green",red="red",white="white")==("OFFEN","white")
print("OWNER_SETTLEMENT_MIXED_RESULT_COLOR_PASS")
