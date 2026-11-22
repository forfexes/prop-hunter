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
    assert 'else RED if "verloren" in state.casefold() else WHITE)' in src, module.__name__
    assert "Image.alpha_composite(im, ribbon)" not in src, module.__name__
    assert "OFFEN" in src
    assert module.WHITE==(250,251,253), module.__name__
print("OWNER_SINGLE_LADDER_BUILDER_LOTTERY_PENDING_WHITE_UNFRAMED_PASS")
