"""Offline check of the exact user-provided NBA Single (no TG, no web)."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops
from io import BytesIO
import hashlib,unittest
import prop_hunter_owner_supplied_single as owner

ROOT=Path(__file__).resolve().parent


def qa_assets():
    logo=Image.new('RGBA',(54,54),(0,0,0,0))
    ImageDraw.Draw(logo).ellipse((4,4,50,50),fill=(10,143,202,255))
    other=Image.new('RGBA',(54,54),(0,0,0,0))
    ImageDraw.Draw(other).ellipse((4,4,50,50),fill=(154,85,214,255))
    pic=Image.new('RGBA',(146,210),(0,0,0,0))
    d=ImageDraw.Draw(pic)
    d.ellipse((45,14,99,82),fill=(203,169,139,255))
    d.polygon([(26,210),(27,139),(40,99),(98,99),(120,150),(123,210)],fill=(35,160,228,255))
    return logo,other,pic


class SourceOriginalQA(unittest.TestCase):
    def setUp(self):
        a,b,p=qa_assets()
        self.fields={
            'title':'SINGLE',
            'subtitle':'Dallas Mavericks vs Utah Jazz · Mo 23.11.2026 · 01:00',
            'teams':[('Dallas Mavericks',a),('Utah Jazz',b)],
            'row':{'name':'QA TEST ATHLETE','label':'Under 6.5 Assists',
                   'odds':'@1.74','photo':p,
                   'form':'L5 4/5 · L10 8/10 · L15 12/15',
                   'model':{'prob':'68.2%','edge':'+10.7%','confidence':'—'}},
            'footer':'Quote @1.74 · Einsatz 1u','settlement':'OFFEN',
        }

    def render(self,**kwargs):
        return owner.render(**(self.fields|kwargs))

    def test_exact_source_hash_and_only_one_time_footer_cleanup(self):
        original=Image.open(owner.SOURCE).convert('RGB')
        editable=Image.open(owner.EDITABLE).convert('RGB')
        self.assertEqual(original.size,(512,512))
        self.assertEqual(hashlib.sha256(owner.SOURCE.read_bytes()).hexdigest(),owner.SOURCE_SHA256)
        diff=ImageChops.difference(original,editable)
        box=diff.getbbox()
        self.assertIsNotNone(box)
        self.assertGreaterEqual(box[0],231)
        self.assertGreaterEqual(box[1],455)
        self.assertLessEqual(box[2],316)
        self.assertLessEqual(box[3],490)

    def test_renderer_keeps_stadium_and_gold_frames(self):
        raw=self.render()
        with Image.open(BytesIO(raw)) as im:
            self.assertEqual(im.size,(1080,1080))
            self.assertEqual(im.format,'PNG')
            image=im.convert('RGB')
        master=Image.open(owner.EDITABLE).convert('RGB').resize((1080,1080),Image.Resampling.LANCZOS)
        # Existing neon and all source art outside dynamic slots unchanged.
        for x,y in ((8,10),(480,15),(1,250),(490,260),(280,445),(340,482),
                    (180,305),(8,447),(25,485)):
            self.assertEqual(master.getpixel((round(x*1080/512),round(y*1080/512))),
                             image.getpixel((round(x*1080/512),round(y*1080/512))), (x,y))
        (ROOT/'preview_single_open.png').write_bytes(raw)

    def test_settlement_in_same_original_banner(self):
        for name in ('OFFEN','GEWONNEN','VERLOREN','PUSH','VOID'):
            raw=self.render(settlement=name)
            with Image.open(BytesIO(raw)) as im:
                self.assertEqual(im.size,(1080,1080))
            if name=='GEWONNEN':
                (ROOT/'preview_single_won.png').write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'status'):
            self.render(settlement='probably won')
        # Telegram result summaries sometimes carry numerically counted
        # winners and losers. One Single still needs exactly one true result.
        for raw, expected in (
            ("1 gewonnen · 0 verloren · +0.74u", "GEWONNEN"),
            ("0 gewonnen · 1 verloren", "VERLOREN"),
            ("1 offen · 0 gewonnen", "OFFEN"),
            ("1 void · 0 verloren", "VOID"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(owner._status(raw)[0],expected)
                self.assertTrue(self.render(settlement=raw).startswith(b"\\x89PNG"))
        for ambiguous in ("1 gewonnen · 1 verloren",
                          "0 gewonnen · 0 verloren","2 gewonnen",
                          "unverified result 1"):
            with self.subTest(ambiguous=ambiguous),self.assertRaises(ValueError):
                self.render(settlement=ambiguous)

    def test_no_fabricated_time_quote_photo_or_name(self):
        for vals in ({'subtitle':'yesterday'}, {'row':{**self.fields['row'],'odds':'@NA'}},
                     {'row':{**self.fields['row'],'photo':None}},
                     {'row':{**self.fields['row'],'name':'Test'}}):
            with self.subTest(vals=vals), self.assertRaises(ValueError):
                self.render(**vals)

    def test_real_bridge_uses_user_single_and_pixel_proof(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from prop_hunter_nba_owner_bridge import render_owner
        from prop_hunter_owner_pixel_qa import owner_pixel_provenance
        import os
        pick=SimpleNamespace(type="single",sport="NBA",market="assists",
                             player="QA TEST ATHLETE",odds=1.74,features={})
        values={"date":"23.11.2026","time":"01:00","stake":"1u",
                "odds":"@1.74","settlement":"OFFEN"}
        with patch.dict(os.environ,{
                "PH_NBA_USER_SINGLE_20261122":"1",
                "PH_NBA_OWNER_ORIGINALS":"1",
                "PH_BLOCK_OVERPAINTED_MASTERS":"1",
                "PH_ALLOW_VERIFIED_LAYERED_OWNER":"1",
                "PH_REQUIRE_TELEGRAM_SAFE_MARGIN":"1"
             }), patch("prop_hunter_original_compositor.original_card",
                       side_effect=AssertionError("Never render old 691px Single")):
            picture=render_owner(pick,"single_assists",[self.fields["row"]],
                                 self.fields["teams"],values,[])
            approved,why=owner_pixel_provenance(pick,picture)
        self.assertEqual((approved,why),(True,"source_original_pixels_verified"))
        with Image.open(BytesIO(picture)) as image:
            self.assertEqual(image.width,1080)
            self.assertGreater(image.height,1080)
        (ROOT/"preview_single_owner_telegram_safe.png").write_bytes(picture)

    def test_tampered_user_single_title_is_rejected_by_pixel_gate(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from prop_hunter_owner_pixel_qa import owner_pixel_provenance
        from prop_hunter_telegram_safe_zone import append_owner_margin
        import os
        raw=self.render()
        with Image.open(BytesIO(raw)) as im:
            source=im.convert("RGB")
            ImageDraw.Draw(source).rectangle((370,15,650,86),fill=(255,5,8))
            out=BytesIO()
            source.save(out,"PNG")
        pick=SimpleNamespace(type="single",sport="NBA",features={})
        with patch.dict(os.environ,{"PH_NBA_USER_SINGLE_20261122":"1"}):
            accepted,why=owner_pixel_provenance(pick,append_owner_margin(out.getvalue()))
        self.assertFalse(accepted)
        self.assertIn("masthead",why)

    def test_telegram_card_version_pins_original_for_settlement(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from prop_hunter_nba_owner_bridge import user_single_original_enabled
        from prop_hunter_image_cards import settled_image
        import os
        with patch.dict(os.environ,{"PH_NBA_USER_SINGLE_20261122":"1"}):
            self.assertTrue(user_single_original_enabled(
                SimpleNamespace(type="single")))
            self.assertFalse(user_single_original_enabled(
                SimpleNamespace(type="single",
                                _owner_single_master_20261122=False)))
            self.assertFalse(user_single_original_enabled({
                "type":"single","_owner_layered_original_v1":True}))
        with patch.dict(os.environ,{"PH_NBA_USER_SINGLE_20261122":"0"}):
            self.assertTrue(user_single_original_enabled(
                SimpleNamespace(type="single",
                                _owner_single_master_20261122=True)))
        captured=[]
        def capture(pick):
            captured.append(getattr(pick,"_owner_single_master_20261122",None))
            return b"QA_ONLY"
        with patch("prop_hunter_image_cards.build_for_pick",side_effect=capture):
            settled_image({"type":"single","features":{}},"Auswertung: OFFEN")
            settled_image({"type":"single","features":{},
                           "_owner_single_master_20261122":True},
                          "Auswertung: GEWONNEN")
        self.assertEqual(captured,[False,True])

    def test_no_translucent_opaque_repaint_runtime(self):
        import inspect
        code=inspect.getsource(owner.render)
        self.assertNotIn('rounded_rectangle',code)
        self.assertNotIn('alpha_composite(im,',code)
        self.assertNotIn('rectangle(',code)

if __name__=='__main__':unittest.main(verbosity=2)