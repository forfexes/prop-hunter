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

    def test_no_fabricated_time_quote_photo_or_name(self):
        for vals in ({'subtitle':'yesterday'}, {'row':{**self.fields['row'],'odds':'@NA'}},
                     {'row':{**self.fields['row'],'photo':None}},
                     {'row':{**self.fields['row'],'name':'Test'}}):
            with self.subTest(vals=vals), self.assertRaises(ValueError):
                self.render(**vals)

    def test_no_translucent_opaque_repaint_runtime(self):
        import inspect
        code=inspect.getsource(owner.render)
        self.assertNotIn('rounded_rectangle',code)
        self.assertNotIn('alpha_composite(im,',code)
        self.assertNotIn('rectangle(',code)

if __name__=='__main__':unittest.main(verbosity=2)