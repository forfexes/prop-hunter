"""Head/forehead pixels must survive original NBA multi-athlete photo slots.

A genuine transparent athlete cutout is fitted only into the prescribed
dynamic slot. No new outline, cover-up or alteration of the stadium plate.
"""
import unittest

from PIL import Image, ImageDraw, ImageChops
from prop_hunter_original_compositor import _background_portrait


def portrait(pad=0):
    pic=Image.new("RGBA",(110+2*pad,300+2*pad),(0,0,0,0))
    draw=ImageDraw.Draw(pic)
    draw.rectangle((pad+20,pad,pad+89,pad+299),
                   fill=(28,116,208,255))
    # The top red pixels represent the scalp and forehead: the old wide-slot
    # 'max' scaling and negative y offset cropped them entirely.
    draw.rectangle((pad+20,pad,pad+89,pad+78),
                   fill=(243,28,43,255))
    return pic


class OriginalPortraitNoHeadCrop(unittest.TestCase):
    def test_no_head_crop_in_builder_ladder_or_lottery_slots(self):
        for rect in ((10,10,210,160),(18,12,168,126),
                     (10,10,180,220),(12,15,212,145)):
            with self.subTest(rect=rect):
                background=Image.new("RGBA",(240,250),(5,14,26,255))
                before=background.copy()
                self.assertTrue(_background_portrait(
                    background,portrait(),rect))
                x0,y0,x1,y1=rect
                mid=(x0+x1)//2
                scalp=background.getpixel((mid,y0+5))
                self.assertGreater(scalp[0],220,
                    "Athlete forehead/head clipped by narrow visual slot")
                for pt in ((0,0),(238,20),(2,220),(238,248)):
                    self.assertEqual(background.getpixel(pt),before.getpixel(pt))

    def test_transparent_outside_padding_changes_no_pixels(self):
        a=Image.new("RGBA",(240,250),(5,14,26,255))
        b=a.copy()
        rect=(10,10,210,160)
        self.assertTrue(_background_portrait(a,portrait(0),rect))
        self.assertTrue(_background_portrait(b,portrait(80),rect))
        self.assertIsNone(ImageChops.difference(a,b).getbbox())

    def test_no_fake_opaque_photo_or_empty_player(self):
        canvas=Image.new("RGBA",(240,250),(5,14,26,255))
        opaque=Image.new("RGB",(100,150),(230,160,70))
        self.assertFalse(_background_portrait(canvas,opaque,
                                              (10,10,210,160)))
        self.assertFalse(_background_portrait(canvas,None,(10,10,210,160)))
        self.assertEqual(canvas.getpixel((80,50)),(5,14,26,255))


if __name__=="__main__":
    unittest.main(verbosity=2)
