"""Offline regression: configured odds keys must reach the autonomous collector.

Extract only the pure top-level config assignments from the production source:
no external requests, no imports of the live engine, no Telegram or DB.
"""
from __future__ import annotations
import ast
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

CORE = Path(__file__).resolve().with_name("prophunter_core_1391.py")
NAMES = {"ODDSPAPI_KEY", "SPORTSGAMEODDS_KEY"}


def read_config_assignments():
    tree = ast.parse(CORE.read_text(encoding="utf-8"))
    matched = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in NAMES
            for target in node.targets
        ):
            matched.append(node)
    if len(matched) != 2:
        raise AssertionError("Production odds-source config contract changed")
    return compile(ast.fix_missing_locations(ast.Module(body=matched,type_ignores=[])),
                   str(CORE), "exec")


EXTRACT = read_config_assignments()


def source_keys(environment):
    scope = {"os":os,"re":re}
    with patch.dict(os.environ,environment,clear=True):
        exec(EXTRACT,scope)
    return scope["ODDSPAPI_KEY"],scope["SPORTSGAMEODDS_KEY"]


class OddsSourceEnvironment(unittest.TestCase):
    def test_only_modern_rotating_key_list(self):
        first, second=source_keys({"ODDSPAPI_KEYS":"Key_A,Key_B;Key_C\nKey_D"})
        self.assertEqual(first,"Key_A")
        self.assertEqual(second,"")

    def test_legacy_only_oddspapi_key_still_supported(self):
        for env in ("ODDSPAPI_KEY","ODDSPAPI","ODDSPAPI_API_KEY"):
            with self.subTest(env=env):
                first,_=source_keys({env:"LegacyKey"})
                self.assertEqual(first,"LegacyKey")

    def test_empty_or_whitespace_list_does_not_shadow_valid_single_key(self):
        first,_=source_keys({"ODDSPAPI_KEYS":" , ; \n ",
                             "ODDSPAPI_KEY":"LegacyFallback"})
        self.assertEqual(first,"LegacyFallback")

    def test_modern_rotating_key_precedes_single_key(self):
        first,_=source_keys({"ODDSPAPI_KEYS":"Modern1,Modern2",
                             "ODDSPAPI_KEY":"Legacy1"})
        self.assertEqual(first,"Modern1")

    def test_sportsgameodds_new_and_legacy_aliases(self):
        for env in ("SPORTSGAMEODDS_KEY","SPORTSGAMEODDS_API_KEY",
                    "SPORTS_GAME_ODDS_KEY"):
            with self.subTest(env=env):
                _,actual=source_keys({env:"RealPriceProviderKey"})
                self.assertEqual(actual,"RealPriceProviderKey")

    def test_sportsgameodds_empty_primary_does_not_shadow_alias(self):
        _,actual=source_keys({"SPORTSGAMEODDS_KEY":"  ",
                               "SPORTSGAMEODDS_API_KEY":"Fallback"})
        self.assertEqual(actual,"Fallback")

    def test_missing_source_keys_remain_disabled(self):
        self.assertEqual(source_keys({}),("",""))


if __name__=="__main__":
    unittest.main()
