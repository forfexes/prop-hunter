"""No-network regressions for genuine player image source hints."""
import unittest
from prop_hunter_swiss_nl_media_probe import page_candidates, inspect_image_bytes, fetch_image_metadata


class OfficialSourceImageIdentity(unittest.TestCase):
    def test_exact_alt_and_title_are_required(self):
        html = '''<html><head><meta property="og:title" content="Leonardo Genoni | EV Zug"></head>
        <body><img src="https://cms.evz.ch/media/genoni.jpg" alt="Leonardo Genoni">
        <img src="https://cms.evz.ch/media/stadium.jpg" alt="Teamheader">
        </body></html>'''
        data=page_candidates("https://www.evz.ch/players/leonardo-genoni/", html, "Leonardo Genoni")
        self.assertEqual(data["status"], "named_candidate_found")
        self.assertEqual(data["image_candidates"], ["https://cms.evz.ch/media/genoni.jpg"])

    def test_unrelated_club_page_must_not_supply_wrong_image(self):
        html='''<title>Simon Hrubec | ZSC Lions</title>
        <img src="https://cdn.example.com/other.jpg" alt="Leonardo Genoni">'''
        data=page_candidates("https://www.zsclions.ch/", html, "Leonardo Genoni")
        self.assertEqual(data["status"], "page_identity_unconfirmed")
        self.assertEqual(data["image_candidates"], [])

    def test_og_generic_banner_not_a_player_picture(self):
        html='''<meta property="og:title" content="Julien Sprunger · Fribourg-Gottéron">
        <meta property="og:image" content="https://www.gotteron.ch/logo.png">
        <img src="/news/header.jpg" alt="Team hero">'''
        data=page_candidates("https://www.gotteron.ch/news/julien",html,"Julien Sprunger")
        self.assertEqual(data["status"],"identity_verified_image_unresolved")
        self.assertEqual(data["image_candidates"],[])

    def test_data_image_or_insecure_url_not_accepted(self):
        html='''<title>Miro Aaltonen - SC Bern</title>
        <img src="data:image/png;base64,abc" alt="Miro Aaltonen">
        <img src="http://insecure.com/miro_aaltonen.jpg" alt="Miro Aaltonen">'''
        data=page_candidates("https://www.scb.ch/",html,"Miro Aaltonen")
        self.assertEqual(data["image_candidates"],[])

    def test_named_path_supported_without_alt(self):
        html='''<title>Philipp Kurashev Lausanne HC</title>
        <img src="/media/philipp_kurashev_2026.png" alt="">'''
        data=page_candidates("https://lausannehc.ch/lions/",html,"Philipp Kurashev")
        self.assertEqual(data["status"],"named_candidate_found")
        self.assertEqual(data["image_candidates"],
                         ["https://lausannehc.ch/media/philipp_kurashev_2026.png"])




class SourceBytesQA(unittest.TestCase):
    def test_real_alpha_and_opaque_image_differ_without_any_license(self):
        from io import BytesIO
        from PIL import Image
        for mode, expected in (("RGBA",True),("RGB",False)):
            with self.subTest(mode=mode):
                im=Image.new(mode,(320,400),(0,0,0,0) if mode=="RGBA" else (45,70,90))
                buf=BytesIO()
                im.save(buf,format="PNG")
                details=inspect_image_bytes(buf.getvalue())
                self.assertEqual(details["status"],"decoded")
                self.assertEqual(details["has_transparency"],expected)
                self.assertFalse(details["licensed_for_telegram"])

    def test_bad_payload_fails_closed(self):
        self.assertEqual(inspect_image_bytes(b"<html>Error</html>")["status"],"image_decode_failed")
        self.assertEqual(inspect_image_bytes(b"")["status"],"image_missing_or_exceeds_limit")

    def test_unknown_external_host_never_requested(self):
        class NoNetwork:
            def get(self,*args,**kwargs):
                raise AssertionError("must not contact arbitrary image CDN")
        result=fetch_image_metadata(NoNetwork(),"https://evil.example.org/portrait.png")
        self.assertEqual(result["status"],"untrusted_image_host")

if __name__ == "__main__":
    unittest.main()
