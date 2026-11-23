"""Offline parity for NBA premium single CONF with the existing text model."""
import unittest
from types import SimpleNamespace

from prop_hunter_confidence_display import normal_pick_confidence
from prop_hunter_image_cards import _display_model_evidence


class ConfidenceDisplayQA(unittest.TestCase):
    def pick(self, **changes):
        fields=dict(type="single",sport="NBA",odds=1.85,
                    probability=0.72,edge_pct=11.0)
        fields.update(changes)
        return SimpleNamespace(**fields)

    def test_same_scoring_formula_as_normal_core_text(self):
        # Existing core: 35 + probability*50 + min(edge,20)
        #                - max(odds-2,0)*3 (bounded to [1,99]).
        for prob,edge,odds in (
            (0.72,11.0,1.85),(0.67,8.0,2.25),(0.8,20,3.0),
            (0.59,7.5,1.70),(0.95,42,2.10),
        ):
            with self.subTest(prob=prob,odds=odds):
                expected=int(max(1,min(99,round(
                    35+prob*50+min(max(0,edge),20)-max(0,odds-2)*3))))
                self.assertEqual(normal_pick_confidence(prob,edge,odds),expected)

    def test_missing_confidence_is_derived_from_observed_pick_not_guessed(self):
        evidence=_display_model_evidence(self.pick())
        self.assertEqual(evidence,{"prob":"72","edge":"+11.0",
                                   "confidence":"82/100"})
        self.assertEqual(
            _display_model_evidence(self.pick(confidence_score=91))["confidence"],
            "91/100")
        self.assertEqual(
            _display_model_evidence(self.pick(
                _display_model={"confidence":"4/5"}))["confidence"],"4/5")

    def test_unknown_or_bad_source_remains_unknown(self):
        for changes in (
            {"probability":None},{"edge_pct":None},{"odds":None},
            {"probability":float("nan")},{"edge_pct":float("inf")},
            {"odds":1.0},{"probability":1.3},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(_display_model_evidence(
                    self.pick(**changes))["confidence"],"")
                self.assertIsNone(normal_pick_confidence(
                    changes.get("probability",0.72),
                    changes.get("edge_pct",11.0),
                    changes.get("odds",1.85)))


if __name__=="__main__":
    unittest.main(verbosity=2)
