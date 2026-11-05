import unittest
from unittest.mock import Mock
import prop_hunter_bwin_us_probe as p

class BwinUSProbeTests(unittest.TestCase):
    def test_no_unverified_quotes_when_unconfigured(self):
        original=p.SPORT_IDS
        try:
            p.SPORT_IDS={k:"" for k in original}
            result=p.probe()
            self.assertTrue(all(x["player_prop_quotes"]==0 for x in result.values()))
        finally:p.SPORT_IDS=original
    def test_catalog_does_not_publish_prices(self):
        original=p.SPORT_IDS
        try:
            p.SPORT_IDS={"NBA":"test"}
            session=Mock()
            response=Mock()
            response.json.return_value={"fixtures":[{"id":123,"odds":999}]}
            session.get.return_value=response
            result=p.probe(session)
            self.assertEqual(result["NBA"]["fixtures"],1)
            self.assertEqual(result["NBA"]["player_prop_quotes"],0)
        finally:p.SPORT_IDS=original

if __name__=="__main__":unittest.main()
