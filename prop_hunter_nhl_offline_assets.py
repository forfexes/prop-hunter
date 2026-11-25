"""Resolve NHL card assets from explicit fixture identities; offline-testable.

No production routing. The caller supplies official roster data and image
loaders. Do not infer a player's team from a name or a generic hockey label.
"""
from io import BytesIO
import re
import unicodedata
from urllib.parse import urlsplit
from PIL import Image

GROUPS=("forwards","defensemen","goalies")
HOSTS={"assets.nhle.com","cdn.nhle.com"}

def name_key(value):
    value=unicodedata.normalize("NFKD",str(value or ""))
    return "".join(c.casefold() for c in value if c.isalnum())

def localized(value):
    return value.get("default","") if isinstance(value,dict) else str(value or "")

def team_code(value):
    code=str(value or "").upper().strip()
    if not re.fullmatch(r"[A-Z]{3}",code):
        raise ValueError("Explicit NHL team abbreviation required")
    return code

def official_portrait_url(roster,player,expected_id=None):
    key=name_key(player)
    if not key or not isinstance(roster,dict):
        raise ValueError("Missing roster identity")
    matches=[]
    for group in GROUPS:
        for row in roster.get(group) or []:
            name=localized(row.get("firstName"))+" "+localized(row.get("lastName"))
            if name_key(name)==key:
                matches.append(row)
    if len(matches)!=1:
        raise ValueError("Player not uniquely present in the supplied NHL roster")
    row=matches[0]
    pid=row.get("id")
    if isinstance(pid,bool) or not str(pid or "").isdigit():
        raise ValueError("Missing official player ID")
    if expected_id is not None and str(pid)!=str(expected_id):
        raise ValueError("Player ID mismatch")
    url=str(row.get("headshot") or "")
    p=urlsplit(url)
    if p.scheme!="https" or p.hostname not in HOSTS or p.username or p.password or p.port or not p.path.lower().endswith(".png"):
        raise ValueError("Unverified official NHL portrait URL")
    # NHL headshots are named by numeric player ID.
    if p.path.rsplit("/",1)[-1]!=str(pid)+".png":
        raise ValueError("Portrait URL does not match official player ID")
    return url

def transparent_png(image):
    if isinstance(image,(bytes,bytearray)):
        with Image.open(BytesIO(image)) as src:
            if src.format!="PNG":
                raise ValueError("PNG required")
            image=src.convert("RGBA")
    if not isinstance(image,Image.Image) or min(image.size)<64 or max(image.size)>4096:
        raise ValueError("Missing or invalid asset")
    rgba=image.convert("RGBA")
    lo,hi=rgba.getchannel("A").getextrema()
    if lo!=0 or hi==0:
        raise ValueError("Transparent, non-empty asset required")
    out=BytesIO()
    rgba.save(out,format="PNG")
    return out.getvalue()

def resolve_single(*,player,player_team,home,away,rosters,load_photo,load_logo,player_id=None):
    home,away,player_team=map(team_code,(home,away,player_team))
    if home==away or player_team not in (home,away):
        raise ValueError("Player team must match the exact NHL fixture")
    if not isinstance(rosters,dict) or player_team not in rosters:
        raise ValueError("No verified roster for player's team")
    url=official_portrait_url(rosters[player_team],player,player_id)
    assets={"player":transparent_png(load_photo(url)),
            "home":transparent_png(load_logo(home,("hockey","nhl"))),
            "away":transparent_png(load_logo(away,("hockey","nhl")))}
    return assets


def resolve_legs(kind, legs, *, rosters, load_photo, load_logo):
    """Validate all leg identities first, then reuse only identical source assets."""
    legs=list(legs)
    if kind not in ("ladder","builder","kombi","cross","lottery") or not 2<=len(legs)<=6:
        raise ValueError("Invalid NHL multi-leg card")
    planned=[]
    for leg in legs:
        home,away,team=map(team_code,(leg.get("home"),leg.get("away"),leg.get("player_team")))
        if home==away or team not in (home,away) or team not in rosters:
            raise ValueError("Unverified NHL leg fixture or roster")
        url=official_portrait_url(rosters[team],leg.get("player"),leg.get("player_id"))
        planned.append((home,away,url))
    games={(home,away) for home,away,_ in planned}
    if kind in ("ladder","builder") and len(games)!=1:
        raise ValueError("Same-game card contains different fixtures")
    if kind=="ladder" and len({url for _,_,url in planned})!=1:
        raise ValueError("Ladder contains different players")
    if kind=="cross" and len(games)<2:
        raise ValueError("Cross requires different fixtures")
    photos,logos,assets={},{},{}
    for i,(home,away,url) in enumerate(planned):
        if url not in photos:
            photos[url]=transparent_png(load_photo(url))
        for team in (home,away):
            if team not in logos:
                logos[team]=transparent_png(load_logo(team,("hockey","nhl")))
        assets.update({f"leg_{i}_player":photos[url],f"leg_{i}_home":logos[home],
                       f"leg_{i}_away":logos[away]})
    return assets
