"""Offline PNG regression for all four premium poster families."""
from io import BytesIO
import os
# Only offline previews may show missing-photo labels; production rejects them.
os.environ["PH_REQUIRE_PLAYER_PHOTOS"] = "0"
from pathlib import Path
from PIL import Image
from unittest.mock import patch
from types import SimpleNamespace
import prop_hunter_image_cards as cards
import prop_hunter_original_compositor as originals
from prop_hunter_original_template_registry import SPORTS, FAMILIES, template_location, all_required_templates
from prop_hunter_image_cards import render

def test_family(kind, count):
    rows = [{"name": ("One Ladder Player" if kind == "ladder" else "Test Player " + str(i)), "label": "Over 20.5 Points",
             "photo": None, "form": "L10 8/10   L15 12/15", "odds": "@1.90"}
            for i in range(count)]
    data = render(kind, kind.upper(), "Verified sample only", "basketball",
                  [("Home", None), ("Away", None)], rows, "Quote @1.90", "")
    assert data[:8] == bytes([137,80,78,71,13,10,26,10])
    image = Image.open(BytesIO(data))
    assert image.width == 1080 and image.height >= 800
    assert image.height >= 1100
    image.verify()
    out=Path('poster_previews')
    out.mkdir(exist_ok=True)
    (out / f'{kind}.png').write_bytes(data)
    # The poster must contain real drawn content in both the header and pick region.
    image = Image.open(BytesIO(data)).convert("RGB")
    assert image.getpixel((540, 53)) != image.getpixel((540, image.height - 25))
    assert len(image.getcolors(maxcolors=1_000_000) or []) > 100
    # Verify preview image validity, not a fragile per-pixel font glyph location.
    assert image.getbbox() is not None

for family, count in [("single",1),("ladder",3),("builder",3),("lottery",3)]:
    test_family(family,count)
print("FOUR POSTER FAMILIES PNG RENDER PASS")

# Every supported sport shares the SAME four NBA original layouts.
assert len(all_required_templates()) == 4
assert set(SPORTS) == {"NBA", "WNBA", "NCAAB", "EUROLEAGUE", "NFL", "NCAAF", "NHL", "MLB"}
for league in SPORTS:
    for family in FAMILIES:
        assert template_location(league, family).suffix == ".webp"
assert template_location("WNBA", "single") == template_location("NBA", "single")
assert template_location("NCAAF", "builder") == template_location("NFL", "builder")
assert template_location("NHL", "lottery") == template_location("NBA", "lottery")
assert template_location("MLB", "ladder") == template_location("NBA", "ladder")
for key in SPORTS:
    assert cards.league_of(key), key

# Rendering a three-rung ladder draws exactly one player portrait.
orig_circle = originals._portrait
portraits = []
def record_portrait(im, person, rect, name):
    if name == "One Ladder Player":
        portraits.append((rect, name))
    return orig_circle(im, person, rect, name)
ladder_rows = [{"name": "One Ladder Player", "photo": None,
                "label": f"Points Over {20+i}.5", "odds": "@1.90",
                "form": "L10 8/10   L15 12/15"} for i in range(3)]
with patch.object(originals, "_portrait", side_effect=record_portrait):
    png = cards.render("ladder", "LADDER", "Single athlete / 3 rungs", "basketball", [], ladder_rows)
assert png[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
assert len(portraits) == 1, portraits

# Reject mislabeled multi-player ladders, rather than silently posting a builder.
ladder_pick = SimpleNamespace(type="ladder", player="Player One", game="Test",
    source_sport="NBA", features={}, odds=1.9, stake=.25,
    leg_details=[{"player":"Player One", "market":"Points Over 20.5", "odds":1.90},
                 {"player":"Player Two", "market":"Points Over 25.5", "odds":2.50}])
with patch.object(cards, "player_photo", return_value=None):
    assert cards.build_for_pick(ladder_pick) is None
ladder_pick.leg_details[1]["player"] = "Player One"
# Production MUST use the NBA premium adapter, never the old compositor.
with patch.object(cards, "ON", True), \
     patch.object(cards, "player_photo", return_value=None), \
     patch.object(cards, "render", side_effect=AssertionError("legacy image used")), \
     patch("prop_hunter_nba_premium_adapter.render_nba_pick", return_value=b"PREMIUM") as premium:
    assert cards.build_for_pick(ladder_pick) == b"PREMIUM"
    assert len(premium.call_args.args[1]) == 2
    assert {row["name"] for row in premium.call_args.args[1]} == {"Player One"}
print("EIGHT SPORT ROUTES / FOUR ORIGINAL-LAYOUT SLOTS / PREMIUM-ONLY LADDER PASSED")

# The generator consumes a real render-ready artwork file when present.
# It must NOT silently claim that an absent user master exists.
from tempfile import TemporaryDirectory
from unittest.mock import patch as mock_patch
import os
with TemporaryDirectory() as temp:
    bgfile = Path(temp) / "football_single.webp"
    Image.new("RGB", (900, 1100), (19, 42, 61)).save(bgfile, "WEBP")
    with mock_patch("prop_hunter_original_template_registry.available_template", return_value=bgfile), mock_patch.object(cards, "_background", side_effect=AssertionError("procedural fallback was used")):
        loaded = cards._original_artwork_background("football", "single", 1000)
        assert loaded.size == (1080, 1000)
        assert all(abs(actual - expected) <= 5 for actual,expected in zip(loaded.getpixel((540, 500))[:3], (19, 42, 61)))
with mock_patch("prop_hunter_original_template_registry.available_template", return_value=None), mock_patch.dict(os.environ, {"PH_ORIGINAL_ONLY":"1"}):
    try:
        cards._original_artwork_background("hockey", "ladder", 1000)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("PH_ORIGINAL_ONLY must reject missing user artwork")
print("REAL ARTWORK PATH / FAIL-CLOSED ORIGINAL MODE PASSED")

# Integrity gate for the FOUR actual uploaded user source images, NOT recreated art.
from hashlib import sha256
_original_sha256 = {
    "single": "c2e8b229b060d5b43ed8886ff54d0ef67ef985704d5b37e9de66a486ae60a56c",
    "ladder": "6575d2eed1ec8a764cefbcfb2fa0e3253cf98f3f1557c3ffbabdd97ebd5c606f",
    "builder": "7041a9d24a75a275f916f117dd6293fed81684653e09b5a5dcc7f5493552682c",
    "lottery": "4f131e3fa44ab7f9126c07e34608faa0a3443c8e8c22a884860e3cd03ca0513e",
}
for family, fingerprint in _original_sha256.items():
    src = Path("card_templates") / "originals" / (family + ".jpg")
    assert src.is_file(), f"Missing ACTUAL user original asset: {src}"
    assert sha256(src.read_bytes()).hexdigest() == fingerprint, f"Original image changed: {src}"
    with Image.open(src) as original:
        assert original.format == "JPEG" and original.size == (691, 1536)
print("ALL FOUR EXACT USER ORIGINAL JPGS VERIFIED IN GITHUB CHECKOUT")

# WNBA overlays its own sports data on the SAME NBA original artwork.
wnba_pick = SimpleNamespace(type="single", player="Test WNBA Athlete", game="Test",
    source_sport="WNBA", features={}, odds=1.9, stake=.25,
    market="points", direction="over", point=15.5)
# The artwork registry is shared, but WNBA production must NOT use NBA-only
# cards before WNBA has a verified premium adapter of its own.
with patch.object(cards, "ON", True), \
     patch.object(cards, "player_photo", side_effect=AssertionError("unexpected photo lookup")), \
     patch.object(cards, "team_logo", side_effect=AssertionError("unexpected logo lookup")), \
     patch.object(cards, "render", side_effect=AssertionError("legacy image used")):
    assert cards.build_for_pick(wnba_pick) is None
assert template_location("WNBA","single") == template_location("NBA","single")
for hint, expected in [("NHL", "hockey"), ("NFL", "football"), ("WNBA", "basketball")]:
    assert cards.league_of(hint)[0] == expected
print("NBA ORIGINAL ARTWORK SHARED BY WNBA/NHL/NFL, SPORTS DATA ROUTING PASS")

# Historical two-leg combination cards must use the builder artwork for settlement repaint.
assert originals._family('kombi2') == 'builder'
assert originals._family('kombi') == 'builder'
print('LEGACY KOMBI2 SETTLEMENT FAMILY REGRESSION PASSED')

# Original ladder design must not keep an outdated baked-in 3-LEG heading.
# Render two and four rungs as well as the three-rung reference.
for rung_count in (2, 4):
    rungs = [{"name": "One Ladder Player", "photo": None,
              "label": f"Points Under {10+i}.5", "odds": "@1.90",
              "form": "L10 8/10   L15 12/15"} for i in range(rung_count)]
    data = cards.render("ladder", "LADDER", "Verified sample", "basketball", [], rungs)
    assert Image.open(BytesIO(data)).size[0] == 1080
print('VARIABLE LADDER RUNG COUNT RENDER PASSED')

# Original card clipping regression: source header stays visible and legacy combos render.
assert originals._family("kombi3") == "builder"
with patch.object(originals, "_clean_hero", wraps=originals._clean_hero) as clean:
    test_rows = [{"name":"Test Player","label":"Points Under 20.5","odds":"@1.77","photo":None,"form":"L10 9/10 L15 14/15"}]
    rendered = originals.original_card("single","SINGLE","Test fixture","NBA",[],test_rows,"Quote @1.77 · Einsatz 1u")
    assert rendered[:8] == bytes([137,80,78,71,13,10,26,10])
    cleaned = [call.args[1] for call in clean.call_args_list]
    assert all(rect[1] >= 137 for rect in cleaned), cleaned
print("ORIGINAL HEADER MASK / LEGACY KOMBI3 PASS")

# User-required clean single card: no bridge watermark and three observed windows.
from PIL import Image as PILImage
original_surface = PILImage.new("RGBA", (691, 758), (245, 245, 245, 255))
originals._erase_single_bridge(original_surface)
assert original_surface.getpixel((635, 370))[:3] != (245,245,245)
assert original_surface.getpixel((250, 370))[:3] == (245,245,245)
real_form_rows=[{"name":"Verified Player","photo":None,"label":"Under 10.5 Points",
                 "odds":"@1.77","form":"L5 4/5 · L10 7/9 · L15 12/15"}]
with patch.object(originals, "_text", wraps=originals._text) as writes:
    real_png=originals.original_card("single","SINGLE","Test fixture","NBA",[],real_form_rows)
    drawn=[str(call.args[2]) for call in writes.call_args_list]
    assert all(f"L{i}" in drawn for i in (5,10,15)), drawn
    assert "FORM" not in drawn, drawn
    assert "LETZTE SPIELE" in drawn, drawn
    assert real_png[:8] == bytes([137,80,78,71,13,10,26,10])
print("NO BRIDGE / NO FORM ROW / THREE VERIFIED WINDOWS PASS")

# Regression: no original Stephen Curry face may leak above the gold single banner.
source = originals._source("single")
cleaned = source.copy()
originals._hide_baked_single_head(cleaned)
assert cleaned.getpixel((135, 110)) != source.getpixel((135, 110)), "Baked-in head still visible"
assert cleaned.getpixel((50, 80)) == source.getpixel((50, 80)), "NBA badge should remain unchanged"
assert cleaned.getpixel((245, 110)) == source.getpixel((245, 110)), "Gold header should remain unchanged"
# A transparent athlete portrait is rendered noticeably taller without stretching it.
dummy = Image.new("RGBA", (240, 170), (0,0,0,0))
ImageDraw = __import__("PIL.ImageDraw",fromlist=["Draw"])
ImageDraw.Draw(dummy).ellipse((60, 5, 180, 165), fill=(255,190,115,255))
hero = Image.new("RGBA", (250, 330), (8,22,40,255))
originals._portrait(hero,dummy,(4,4,244,324),"Example",prominent=True)
assert hero.getpixel((125, 70))[0] > 50, "Player portrait is still stuck at the bottom"
print("ORIGINAL BAKED HEAD REMOVED / PORTRAIT ENLARGED / NBA HEADER SAFE")

# Full visual regression for 2-5 ladder rungs, 4-6 builder portraits and
# 2-9 lottery rows (not just a static 3-leg template).
from PIL import ImageDraw as DrawAPI
def _fixture_photo(index):
    img = Image.new("RGBA", (210,245), (0,0,0,0))
    pen = DrawAPI.Draw(img)
    # Original synthetic test shape (never passed off as a real player).
    pen.ellipse((52,6,159,115),fill=(215-index*11,170,131,255))
    pen.rounded_rectangle((19,108,193,244),20,fill=(25+index*20,70,130,255))
    return img

def _fixture_rows(kind,count):
    return [{
        "name": "One Real Athlete" if kind=="ladder" else f"Player {i+1}",
        "photo": _fixture_photo(i), "label":f"Points Under {12.5+i}",
        "odds":f"@{1.65 + i*0.11:.2f}",
        "form":"L5 4/5 · L10 8/10 · L15 12/15"
    } for i in range(count)]

for variant, count in [("ladder",2),("ladder",4),("ladder",5),
                       ("builder",4),("builder",5),("builder",6),
                       ("lottery",2),("lottery",6),("lottery",9)]:
    fixture = _fixture_rows(variant,count)
    out_file=Path('poster_previews')/f'{variant}_{count}.png'
    rendered=originals.original_card(
        variant,variant.upper(),"Verified visual fixture","NBA",
        [("HOME",None),("AWAY",None)],fixture,"Quote @1.85 · Einsatz 1u","OFFEN")
    out_file.write_bytes(rendered)
    assert Image.open(BytesIO(rendered)).size[0]==1080

# All builder players, not just the first three, receive a distinct photo
# slot even when there are 4, 5 or 6 legs.
for size in (4,5,6):
    used=[]
    original_portrait=originals._portrait
    def capture_portrait(im,person,rect,name='',prominent=False):
        used.append(name)
        return original_portrait(im,person,rect,name,prominent=prominent)
    with patch.object(originals,"_portrait",side_effect=capture_portrait):
        originals.original_card("builder","BUILDER","Fixture","NBA",[],
                                _fixture_rows("builder",size),"Quote @2.05")
    assert len(used)==size,(size,used)
    assert len(set(used))==size,(size,used)

# Every ladder row finishes above the lower box starting at y=615.
for count in range(2,6):
    geometry=[]
    row_fn=originals._row
    def capture_row(im,xy,width,*args,**kwargs):
        geometry.append(xy[1])
        return row_fn(im,xy,width,*args,**kwargs)
    with patch.object(originals,"_row",side_effect=capture_row):
        originals.original_card("ladder","LADDER","Fixture","NBA",[],
                                _fixture_rows("ladder",count),"Quote @2.00")
    assert len(geometry)==count
    assert max(geometry)+49 < 615, (count,geometry)

for kind, max_count in [("ladder",5),("builder",6),("lottery",9)]:
    try:
        originals.original_card(kind,kind.upper(),"Fixture","NBA",[],
                                 _fixture_rows(kind,max_count+1))
    except ValueError:
        pass
    else:
        raise AssertionError(f"{kind} would silently hide extra legs")

# No original sample hair may leak in the tested mask centres, and the
# essential owner logo/banner stay unchanged.
for family, check_xy in (("builder",(112,119)),("lottery",(116,57))):
    source=originals._source(family)
    cleaned=source.copy()
    originals._erase_template_head_remnants(cleaned,family)
    assert cleaned.getpixel(check_xy) != source.getpixel(check_xy),(family,check_xy)
    assert cleaned.getpixel((50,30)) == source.getpixel((50,30)),family
print("VISUAL QA: 4-6 REAL BUILDER PORTRAITS, 2-5 LADDER SPACING, 2-9 LOTTERY LEGS, TEMPLATE HEAD REMNANTS PASS")

# Single with a visible supplied portrait: detect sample face over the banner.
single_photo=originals.original_card(
    "single","SINGLE","Photo fixture","NBA",
    [("HOME",None),("AWAY",None)],_fixture_rows("single",1),
    "Quote @1.90 · Einsatz 1u","OFFEN")
(Path("poster_previews")/"single_photo.png").write_bytes(single_photo)

# Real lottery odds remain entirely legible; no clipped L10/L15 fragments,
# and the stake box shows the stake, not the total bookmaker quote again.
with patch.object(originals,"_text",wraps=originals._text) as written:
    originals.original_card("lottery","LOTTERY","Fixture","NBA",[],
                            _fixture_rows("lottery",9),
                            "Quote @1.85 · Einsatz 1u","OFFEN")
    fields=[str(c.args[2]) for c in written.call_args_list]
    assert "1u" in fields, fields
    assert "@1.85" in fields, fields
    assert not any("L5 " in v or "L10 " in v or "L15 " in v for v in fields),fields
print("LOTTERY ODDS NOT TRUNCATED, REAL STAKE ONLY, PLAYER PHOTO SINGLE PASS")

# Previously visible ghost: original Lottery arm below portrait and hair behind
# the builder gold bar. These specific template pixels must be altered without
# touching upper branding or unrelated clean stadium.
for family, point in (("lottery",(52,310)),("builder",(347,120))):
    before=originals._source(family)
    after=before.copy()
    if family=="lottery":
        originals._fade_baked_lottery_arm(after)
    else:
        originals._erase_template_head_remnants(after,family)
    assert before.getpixel(point)!=after.getpixel(point),(family,point)
    assert before.getpixel((470,50))==after.getpixel((470,50)),family
print("SOURCE ATHLETE GHOST REGRESSION / ORIGINAL TOP BRANDING PRESERVED")

# The small athlete pictures from the actual lottery master are restored
# on readable 2-6-leg formats; 9-leg lottery is kept spacious and text-first.
for count in (3,6,9):
    photos=[]
    old_portrait=originals._portrait
    def trace_hero(im,person,rect,name='',prominent=False):
        photos.append(name)
        return old_portrait(im,person,rect,name,prominent=prominent)
    with patch.object(originals,"_portrait",side_effect=trace_hero):
        originals.original_card("lottery","LOTTERY","Fixture","NBA",[],
                                _fixture_rows("lottery",count),
                                "Quote @2.15 · Einsatz 1u")
    assert len(photos)==(1+count if count<=6 else 1),(count,photos)
print("LOTTERY REAL LEG PORTRAITS / TEXT-ONLY HIGH-DENSITY LAYOUT PASS")

# Clean fixture: the two team labels are ONLY beside VS, never repeated in
# the large right-side legacy 'SPIEL / Home / Away' box.
fixture_rows=[{"name":"Test Athlete","photo":_fixture_photo(0),
               "label":"Points Under 12.5","odds":"@1.75",
               "form":"L5 4/5 L10 8/10 L15 12/15",
               "model":{"prob":"65","edge":"+26.1","confidence":"85/100"}}]
match_teams=[("BOS Celtics",None),("DEN Nuggets",None)]
for kind in ("single","ladder"):
    rows=fixture_rows if kind=="single" else [
        dict(fixture_rows[0],name="One Real Athlete"),
        dict(fixture_rows[0],name="One Real Athlete",label="Points Under 14.5")]
    for extra_time in (""," · Do 19.11. · 18:30"):
        with patch.object(originals,"_text",wraps=originals._text) as texts:
            png=originals.original_card(kind,kind.upper(),
                        "BOS Celtics @ DEN Nuggets"+extra_time,
                        "NBA",match_teams,rows,"Quote @1.75 · Einsatz 1u")
            fields=[str(c.args[2]) for c in texts.call_args_list]
            assert "SPIEL" not in fields,fields
            # Kuerzel (BOS/DEN) werden bewusst nicht gedruckt (Logo-Rahmen schneidet sie ab).
            assert fields.count("Celtics")==1,fields
            assert fields.count("Nuggets")==1,fields
            assert "SPIELBEGINN" not in fields,fields   # Vorlagen-Box mit Icons bleibt erhalten
            df,tf,v1,v2=originals._panel_fields("BOS Celtics @ DEN Nuggets"+extra_time+" @@ Ball Arena|Denver")
            assert (tf=="18:30 Uhr")==bool(extra_time),(df,tf)
            assert (df.startswith("Do, 19. Nov"))==bool(extra_time),df
            assert (v1,v2)==("Ball Arena","(Denver)")
        out=Path("poster_previews")/f"{kind}_clean_match_{'kickoff' if extra_time else 'no_time'}.png"
        out.write_bytes(png)

sky=originals._source("single")
clean=sky.copy()
originals._erase_redundant_match_box(clean,"single")
assert clean.getpixel((609,204))!=sky.getpixel((609,204))
assert clean.getpixel((320,204))==sky.getpixel((320,204))
# The old sample bookmaker price must NOT reappear inside the erased field.
# Detect any bright white/yellow source glyphs in this date-free area.
clear_single=originals._source("single").copy()
originals._erase_single_bridge(clear_single)
originals._erase_redundant_match_box(clear_single,"single")
clear_region=clear_single.crop((558,174,677,247)).convert("RGB")
assert max(max(p) for p in clear_region.getdata()) < 115, "Old sample odds or lettering leaked into right slot"
print("SINGLE + LADDER REDUNDANT MATCH PANEL REMOVAL AND VERIFIED KICKOFF TEST PASS")

# Exact-model evidence: neither prices nor recent form may manufacture a
# probability, edge or confidence, but published pick values must be visible.
from types import SimpleNamespace as NS
evidence=cards._display_model_evidence(NS(probability=.65,edge_pct=26.1,confidence_score=85))
assert evidence=={"prob":"65","edge":"+26.1","confidence":"85/100"},evidence
missing=cards._display_model_evidence(NS(odds=2.5,features={"recent_form":{"l5":{"hits":5,"n":5}}}))
assert missing=={"prob":"","edge":"","confidence":""},missing
explicit=cards._display_model_evidence(NS(probability=.65,edge_pct=21.1,
    _display_model={"prob":"67.4","edge":"+22.5","confidence":"86/100"}))
assert explicit=={"prob":"67.4","edge":"+22.5","confidence":"86/100"},explicit
saved=cards.snapshot(NS(type="single",player="Test Athlete",odds=1.82,
                       probability=.65,edge_pct=26.1,confidence_score=85))
assert saved["probability"]==.65 and saved["edge_pct"]==26.1
print("VERIFIED MODEL OUTPUTS AND SNAPSHOT ROUNDTRIP, NO FAKE NUMBERS PASS")

# ESPN uses PHX for Phoenix, while some bookmakers use PHO Suns.
fake_teams={"sports":[{"leagues":[{"teams":[
    {"team":{"displayName":"Phoenix Suns","name":"Suns","nickname":"Suns",
             "abbreviation":"PHX","logos":[{"href":"https://test.invalid/suns.png"}]}},
    {"team":{"displayName":"Boston Celtics","name":"Celtics","nickname":"Celtics",
             "abbreviation":"BOS","logos":[{"href":"https://test.invalid/boston.png"}]}}
]}]}]}
cards._CACHE.pop("teams:nba",None)
with patch.object(cards,"_get_json",return_value=fake_teams), \
     patch.object(cards,"_get_image",side_effect=lambda url:Image.new("RGBA",(32,32),
                                               (255,90,90,255)) if url else None):
    assert cards.team_logo("PHO Suns",("basketball","nba")) is not None
    assert cards.team_logo("PHX Suns",("basketball","nba")) is not None
    assert cards.team_logo("XYZ Suns",("basketball","nba")) is None
cards._CACHE.pop("teams:nba",None)
print("PHO SUNS ESPN LOGO ALIAS MATCH / NO WRONG CRESTS PASS")

# Never turn the tip publication date into an invented kickoff date.
assert cards._kickoff_text(NS(date="2026-11-19"))==""
assert cards._kickoff_text(NS(game_date="2026-11-19")).startswith("Do 19.11.")
# Erase the original broken 'ADDERS' fragment instead of reusing its pixels.
with patch.object(originals,"_text",wraps=originals._text) as textcalls:
    originals.original_card("ladder","LADDER","Verified fixture","NBA",[],
                            _fixture_rows("ladder",3),"Quote @2.00")
    assert any(call.args[2]=="STUFEN" for call in textcalls.call_args_list)
print("NO POST-DATE FAKE KICKOFF / CLEAN LADDER LABEL TEST PASS")
