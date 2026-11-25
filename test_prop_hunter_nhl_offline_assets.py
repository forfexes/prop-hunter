import pytest
from PIL import Image, ImageDraw
from prop_hunter_nhl_offline_assets import resolve_single,official_portrait_url
from prop_hunter_nhl_offline_layout import render

URL="https://assets.nhle.com/mugs/nhl/20262027/TOR/1234567.png"
PLAYER={"id":1234567,"firstName":{"default":"QA"},"lastName":{"default":"Player"},"headshot":URL}
def roster(*rows): return {"forwards":list(rows)}
def transparent():
    im=Image.new("RGBA",(100,100),(0,0,0,0))
    ImageDraw.Draw(im).rectangle((20,20,80,80),fill=(10,10,10,255))
    return im

def test_exact_fixture_and_asset_embedding():
    calls=[]
    def photo(url):
        calls.append(url)
        return transparent()
    def logo(code,league):
        calls.append((code,league))
        return transparent()
    assets=resolve_single(player="QA Player",player_team="TOR",home="TOR",away="COL",
         rosters={"TOR":roster(PLAYER)},load_photo=photo,load_logo=logo,player_id=1234567)
    assert calls==[URL,("TOR",("hockey","nhl")),("COL",("hockey","nhl"))]
    assert render("single",[{}],assets=assets).count("data:image/png;base64,")==3

@pytest.mark.parametrize("change",[
    {"player_team":"NYR"},{"player_team":"COL"},{"player":"Different Player"},
    {"player_id":123},{"home":"COL"},{"away":"UNKNOWN"}
])
def test_identity_errors_prevent_all_downloads(change):
    kwargs=dict(player="QA Player",player_team="TOR",home="TOR",away="COL",
         rosters={"TOR":roster(PLAYER)},player_id=1234567)
    kwargs.update(change)
    def unexpected(*args): pytest.fail("No image download for invalid identity")
    with pytest.raises(ValueError):
        resolve_single(**kwargs,load_photo=unexpected,load_logo=unexpected)

def test_ambiguous_and_wrong_portrait_url():
    with pytest.raises(ValueError): official_portrait_url(roster(PLAYER,PLAYER),"QA Player")
    with pytest.raises(ValueError): official_portrait_url(roster({**PLAYER,"headshot":URL.replace("1234567","987")}),"QA Player")
    with pytest.raises(ValueError): official_portrait_url(roster({**PLAYER,"headshot":URL.replace("assets.nhle.com","untrusted.invalid")}),"QA Player")
