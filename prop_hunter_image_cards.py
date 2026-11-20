#!/usr/bin/env python3
"""PROP HUNTER premium-only image entrypoint.

Only the verified NBA premium master may produce a card image. Missing authentic
player photos, logos, bookmaker provenance or required data fail closed (None).
The legacy procedural renderer is retained as inert code for compatibility with
older imports; build_for_pick MUST NOT invoke it. Other sports await approved
premium templates. Callers must not interpret None as permission to use an old
image design. PH_IMAGE_CARDS=0 disables image generation.
"""
from __future__ import annotations

import io
import math
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
except Exception:  # Pillow fehlt -> Bildkarten aus
    Image = None

ON = os.getenv("PH_IMAGE_CARDS", "1") != "0" and Image is not None
W = 1080
CYAN = (34, 230, 238)
WHITE = (245, 250, 252)
MUTED = (150, 178, 190)
GREEN = (46, 226, 130)   # GEWONNEN
RED = (240, 78, 92)      # VERLOREN
PANEL = (10, 26, 38, 205)
HEADERS = {"User-Agent": "PropHunter-Cards/1.0 (+https://github.com/forfexes/prop-hunter)"}

# ESPN: (sport, league) je Prop-Hunter-Sportschluessel
LEAGUES = {
    "nba": ("basketball", "nba"), "wnba": ("basketball", "wnba"), "ncaab": ("basketball", "mens-college-basketball"),
    "euroleague": ("basketball", "euroleague"), "nfl": ("football", "nfl"), "ncaaf": ("football", "college-football"),
    "mlb": ("baseball", "mlb"), "nhl": ("hockey", "nhl"),
}
THEMES = {  # Hintergrundfarbe oben/unten + Linienmotiv
    "basketball": ((6, 24, 40), (3, 10, 20), "court"), "football": ((6, 30, 30), (3, 14, 16), "yard"),
    "baseball": ((8, 26, 36), (3, 12, 18), "diamond"), "hockey": ((10, 28, 44), (4, 12, 22), "ice"),
    "neutral": ((6, 22, 36), (3, 10, 18), "none"),
}
_CACHE: Dict[str, Any] = {}


def _font(size: int, bold: bool = True):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", "/Library/Fonts/Arial Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _norm(s: Any) -> str:
    t = unicodedata.normalize("NFKD", str(s or "").lower())
    return re.sub(r"[^a-z0-9]+", "", "".join(c for c in t if not unicodedata.combining(c)))


def league_of(value: Any) -> Optional[Tuple[str, str]]:
    v = str(value or "").lower().replace("_", " ")
    for key in ("wnba", "ncaab", "ncaaf", "euroleague", "nba", "nfl", "mlb", "nhl"):
        if re.search(rf"\b{key}\b", v) or f"basketball {key}" in v or f"{key}" == v.strip():
            return LEAGUES[key]
    if "college football" in v:
        return LEAGUES["ncaaf"]
    if "college basketball" in v or "ncaa basketball" in v:
        return LEAGUES["ncaab"]
    # An unspecified basketball feed may be WNBA, EuroLeague or college.
    # Never silently label it NBA and render an NBA-branded card.
    if v.strip() == "basketball":
        return None
    return None


def _get_json(url: str, params: Optional[dict] = None) -> Any:
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=8)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def _get_image(url: str) -> Optional["Image.Image"]:
    if not url:
        return None
    if url in _CACHE:
        return _CACHE[url]
    img = None
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code == 200 and r.content:
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:
        img = None
    _CACHE[url] = img
    return img


def player_photo(name: str, league: Optional[Tuple[str, str]]) -> Optional["Image.Image"]:
    if not name or not league:
        return None
    key = f"p:{league[1]}:{_norm(name)}"
    if key in _CACHE:
        return _CACHE[key]
    img = None
    data = _get_json("https://site.web.api.espn.com/apis/common/v3/search", {"query": name, "limit": 6, "type": "player"})
    for it in (data or {}).get("items") or []:
        if str(it.get("league") or "").lower() == league[1] and _norm(it.get("displayName")) == _norm(name) and it.get("id"):
            img = _get_image(f"https://a.espncdn.com/i/headshots/{league[1]}/players/full/{it['id']}.png")
            break
    _CACHE[key] = img
    return img


def team_logo(team: str, league: Optional[Tuple[str, str]]) -> Optional["Image.Image"]:
    if not team or not league:
        return None
    tkey = f"teams:{league[1]}"
    if tkey not in _CACHE:
        data = _get_json(f"https://site.api.espn.com/apis/site/v2/sports/{league[0]}/{league[1]}/teams")
        teams = []
        for grp in ((data or {}).get("sports") or [{}])[0].get("leagues", [{}])[0].get("teams", []) if data else []:
            t = grp.get("team") or {}
            logos = t.get("logos") or []
            names={_norm(t.get(k)) for k in ("displayName", "shortDisplayName", "name", "abbreviation", "nickname") if t.get(k)}
            for name in (t.get("name"),t.get("nickname")):
                if name and t.get("abbreviation"):names.add(_norm(f"{t['abbreviation']} {name}"))
            teams.append({"names": names,
                          "abbreviation": _norm(t.get("abbreviation")),
                          "nickname": _norm(t.get("nickname") or t.get("name")),
                          "logo": logos[0].get("href") if logos else None})
        _CACHE[tkey] = teams
    want = _norm(team)
    matches=[t for t in _CACHE[tkey] if want in t["names"]]
    if len(matches)!=1 and league[1]=="nba":
        # Some bookmaker feeds use PHO Suns whereas ESPN calls the same
        # team PHX Suns. A nickname alone would risk the WRONG crest:
        # accept only a verified abbreviation alias + matching nickname.
        tokens = str(team).strip().split()
        alias = {"pho":"phx", "gsw":"gs", "nyk":"ny", "nop":"no", "sas":"sa"}
        if len(tokens)>=2:
            prefix=_norm(tokens[0])
            expected=alias.get(prefix)
            nickname=_norm(" ".join(tokens[1:]))
            if expected:
                matches=[t for t in _CACHE[tkey]
                         if t["abbreviation"]==expected and
                         (nickname==t["nickname"] or nickname in t["names"])]
    return _get_image(matches[0]["logo"]) if len(matches)==1 and matches[0].get("logo") else None


# ----------------------------------------------------------------------------------------------------------------- Zeichnen
def _background(sport: str, h: int) -> "Image.Image":
    top, bottom, motif = THEMES.get(sport, THEMES["neutral"])
    img = Image.new("RGB", (W, h), top)
    px = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        px.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    glow = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for cx in range(60, W, 180):  # Flutlicht-Punkte oben
        g.ellipse([cx - 26, 10, cx + 26, 62], fill=(120, 235, 255, 90))
    if motif == "court":
        g.ellipse([W // 2 - 380, h - 330, W // 2 + 380, h + 330], outline=(34, 230, 238, 60), width=5)
        g.rectangle([W // 2 - 130, h - 260, W // 2 + 130, h], outline=(34, 230, 238, 50), width=4)
    elif motif == "yard":
        for x in range(0, W, 120):
            g.line([(x, 120), (x - 80, h)], fill=(34, 230, 238, 35), width=3)
    elif motif == "diamond":
        g.polygon([(W // 2, h - 520), (W // 2 + 360, h - 220), (W // 2, h + 80), (W // 2 - 360, h - 220)], outline=(34, 230, 238, 55))
    elif motif == "ice":
        g.ellipse([W // 2 - 200, h - 320, W // 2 + 200, h + 80], outline=(34, 230, 238, 55), width=5)
        g.line([(0, h - 120), (W, h - 120)], fill=(34, 230, 238, 40), width=4)
    # Premium arena atmosphere: roof lights, crowd stands and glossy playing floor.
    # Fully procedural: no copyrighted venue photography and no baked-in sample stats.
    stadium = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stadium, "RGBA")
    floor_y = max(300, h - 235)
    sd.polygon([(0, 100), (W, 100), (W, floor_y), (0, floor_y)],
               fill=(4, 10, 23, 75))
    for ring in range(5):
        yy = int(h * .27) + ring * 55
        if yy >= floor_y:
            break
        sd.arc((-240, yy - 140, W + 240, yy + 230), 0, 180,
               fill=(35 + ring * 8, 74 + ring * 7, 113 + ring * 5, 90), width=8)
    for row in range(max(0, (floor_y - 310) // 28)):
        yy = 315 + row * 28
        for col in range(0, W, 23):
            # Deterministic crowd lights; no randomness or external assets.
            if ((row * 37 + col * 13) % 11) < 4:
                sd.ellipse((col, yy, col + 3, yy + 3),
                           fill=(236, 179, 87, 50 + ((row + col) % 3) * 18))
    sd.polygon([(0, floor_y), (W, floor_y), (W, h), (0, h)],
               fill=(16, 30, 51, 190))
    for i in range(13):
        x = i * (W // 12)
        sd.line([(W // 2, floor_y), (x, h)], fill=(255, 197, 95, 28), width=3)
    for i in range(1, 6):
        yy = floor_y + int((h - floor_y) * i / 6)
        sd.line([(0, yy), (W, yy)], fill=(106, 169, 221, 24), width=3)
    for cx in (70, 235, 845, 1010):
        sd.ellipse((cx - 13, 65, cx + 13, 91), fill=(241, 249, 255, 230))
        sd.ellipse((cx - 37, 42, cx + 37, 114), outline=(102, 198, 255, 120), width=5)
    stadium = stadium.filter(ImageFilter.GaussianBlur(1.5))
    img = Image.alpha_composite(img.convert("RGBA"), stadium)
    glow = glow.filter(ImageFilter.GaussianBlur(6))
    img = Image.alpha_composite(img, glow)
    return img


def _original_artwork_background(sport: str, family: str, height: int) -> "Image.Image":
    """Load an original-layout, DATA-FREE background when the real asset exists.

    Never use a screenshot with prefilled players and odds as a live background:
    it would duplicate or falsify the displayed pick data. Assets must first be
    edited to preserve the reference design but remove all example data.
    """
    from prop_hunter_original_template_registry import available_template, template_location
    path = available_template(sport, family)
    if path is None:
        if os.getenv("PH_ORIGINAL_ONLY", "0") == "1":
            raise FileNotFoundError(f"Required original template not uploaded: {template_location(sport, family)}")
        return _background(sport, height)
    source = Image.open(path).convert("RGBA")
    if source.width < 700 or source.height < 650:
        raise ValueError(f"Original artwork resolution too small: {path}")
    # Preserve full original-layout canvas without substituting a new design.
    # Fit is needed for variable-height Builder/Lottery leg counts.
    return ImageOps.fit(source, (W, height), method=Image.Resampling.LANCZOS)


def _circle(img: Optional["Image.Image"], size: int, label: str) -> "Image.Image":
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    base = Image.new("RGBA", (size, size), (14, 40, 56, 255))
    if img is not None:
        im = img.copy()
        im.thumbnail((size, size))
        base.paste(im, ((size - im.width) // 2, size - im.height), im)
    else:
        d = ImageDraw.Draw(base)
        f = _font(int(size * 0.42))
        txt = (label or "?")[:1].upper()
        d.text((size // 2, size // 2), txt, font=f, fill=CYAN, anchor="mm")
    out.paste(base, (0, 0), mask)
    ImageDraw.Draw(out).ellipse([1, 1, size - 2, size - 2], outline=CYAN, width=4)
    return out


def _fit(draw, text: str, font, max_w: int) -> str:
    text = str(text)
    while text and draw.textlength(text, font=font) > max_w:
        text = text[:-2]
        if len(text) < 4:
            break
    return text


_WD_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _kickoff_text(pick) -> str:
    """Anstoss als 'So 15.11. · 19:00' in lokaler Zeit (Default Europe/Zurich).

    Liest commence_time (ISO, meist UTC) und faellt sonst auf game_date zurueck.
    Gibt '' zurueck, wenn nichts Brauchbares da ist.
    """
    from datetime import datetime, timezone

    def _get(obj, key):
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    raw = _get(pick, "commence_time")
    if not raw:
        _legs = _get(pick, "leg_details") or []
        _ts = sorted(str(l.get("commence_time")) for l in _legs
                     if isinstance(l, dict) and l.get("commence_time"))
        if _ts:
            raw = _ts[0]
    feats = _get(pick, "features") or {}
    if not raw and isinstance(feats, dict):
        raw = feats.get("commence_time") or feats.get("start_time_utc")
    has_time = bool(raw)
    if not raw:
        # 'date' is often the DATE THE TIP WAS PUBLISHED, not game day.
        # A match panel must not label the posting date as the kickoff.
        raw = _get(pick, "game_date")
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return str(raw)[:10]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        dt = dt.astimezone(ZoneInfo(os.getenv("PH_CARD_TZ", "Europe/Zurich")))
    except Exception:
        pass
    label = f"{_WD_DE[dt.weekday()]} {dt.day:02d}.{dt.month:02d}."
    if has_time:
        label += f" · {dt.hour:02d}:{dt.minute:02d}"
    return label


def _with_kickoff(subtitle: str, pick) -> str:
    """Haengt Datum/Zeit an den Subtitle (ohne Dublette, auf Kartenbreite begrenzt)."""
    ko = _kickoff_text(pick)
    if not ko:
        return subtitle
    base = (subtitle or "").strip()
    if " @@ " not in base:
        venue = _venue_text(pick)
        if venue:
            base_ko = base if ko in base else (f"{base[:46]} · {ko}" if base else ko)
            return f"{base_ko} @@ {venue}"
    if ko in base:
        return base
    return f"{base[:46]} · {ko}" if base else ko


def _venue_text(pick) -> str:
    """'Halle|Stadt' aus features['venue'] (Pick oder erstes Leg); '' wenn unbekannt."""
    def _get(obj, key):
        return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
    feats = _get(pick, "features") or {}
    v = feats.get("venue") if isinstance(feats, dict) else None
    if not v:
        for leg in (_get(pick, "leg_details") or []):
            lf = (leg or {}).get("features") or {}
            if isinstance(lf, dict) and lf.get("venue"):
                v = lf["venue"]
                break
    return str(v) if v else ""


def render(kind: str, title: str, subtitle: str, sport: str, teams: List[Tuple[str, Optional["Image.Image"]]],
           rows: List[Dict[str, Any]], footer: str = "", settlement: str = "", *, template_sport: str = "") -> bytes:
    """rows: {name, label, photo(Image|None), form(str), odds(str)}; teams: [(name, logo)] (0-2)."""
    # Always use the user's four literal GitHub JPG masters, for every league.
    # No reconstructed posters and no stale example players/odds are allowed.
    if os.getenv("PH_USE_USER_ORIGINALS", "1") != "0":
        from prop_hunter_original_compositor import original_card
        return original_card(kind, title, subtitle, sport, teams, rows,
                             footer, settlement, league_name=template_sport or sport)
    # Four distinct poster families; extra header space is reserved for portraits.
    from prop_hunter_original_template_registry import poster_family
    family = poster_family(kind)
    row_h = 250 if family == "single" else (215 if family == "ladder" else 195)
    head_h = ((780 if teams else 650) if family in ("lottery", "single") else (650 if teams else 510)) if family in ("lottery", "builder", "single") else ((580 if teams else 440) if family == "ladder" else (430 if teams else 280))
    # Hero panels extend below the team header; reserve a safe footer gutter.
    h = head_h + row_h * len(rows) + (290 if family in ("lottery", "builder") else 190)
    img = _original_artwork_background(template_sport or sport, family, h)
    accent = (193, 65, 250) if family == "lottery" else (255, 198, 70)
    d = ImageDraw.Draw(img, "RGBA")
    # Premium dark sports-dashboard identity: match approved visual references.
    gold = (255, 204, 78)
    d.rounded_rectangle([22, 18, W - 22, h - 18], 30, outline=accent + (255,), width=5)
    d.text((W // 2 + 3, 56), "PROP HUNTER", font=_font(69), fill=(184, 118, 39), anchor="mm")
    d.text((W // 2, 53), "PROP HUNTER", font=_font(69), fill=WHITE, anchor="mm")
    d.polygon([(W // 2 - 33, 12), (W // 2 - 17, 2), (W // 2, 15),
               (W // 2 + 17, 2), (W // 2 + 33, 12),
               (W // 2 + 25, 29), (W // 2 - 25, 29)], fill=gold + (245,))
    d.line([(245, 111), (W - 245, 111)], fill=gold + (230,), width=4)
    d.rounded_rectangle([150, 133, W - 150, 213], 15, fill=(26, 22, 21, 240), outline=accent + (255,), width=5)
    category = ("PRO TIP - LADDERS" if family == "ladder" else
                "LOTTERY" if family == "lottery" else
                "PRO TIP - BUILDER" if family == "builder" else "PRO TIP - SINGLE")
    d.text((W // 2, 172), category, font=_font(42), fill=gold if kind not in ("big", "super", "lottery") else accent, anchor="mm")
    d.text((W // 2, 241), _fit(d, subtitle, _font(25, False), W - 150),
           font=_font(25, False), fill=WHITE, anchor="mm")
    y = 273
    if teams:
        slots = [(W // 2 - 300, teams[0]), (W // 2 + 300, teams[1] if len(teams) > 1 else None)]
        for cx, t in slots:
            if not t:
                continue
            name, logo = t
            c = _circle(logo, 110, name)
            img.alpha_composite(c, (cx - 55, y - 10))
            team_font = _font(21 if len(name) > 16 else 24)
            d.text((cx, y + 118), _fit(d, name, team_font, 320), font=team_font, fill=WHITE, anchor="mm")
        d.text((W // 2, y + 45), "VS", font=_font(48), fill=CYAN, anchor="mm")
        y += 150
    # Portrait-led premium posters, using only the actual pick players.
    if family in ("lottery", "builder", "single", "ladder") and rows:
        hero_y = 422 if teams else 274
        # Ladder is one player with multiple price/line steps, NEVER a multi-player builder.
        hero_players = rows[:3] if family == "builder" else rows[:1]
        count = len(hero_players)
        centers = ([235] if family in ("single", "lottery") else [W // 2]) if count == 1 else ([270, 810] if count == 2 else [210, 540, 870])
        for cx, item in zip(centers, hero_players):
            size = (295 if family in ("single", "lottery") else 170) if count == 1 else 154
            portrait = _circle(item.get("photo"), size, item.get("name") or "?")
            img.alpha_composite(portrait, (cx - size // 2, hero_y - 14))
            f = _font(21 if count > 1 else 26)
            d.text((cx, hero_y + size + 8), _fit(d, item.get("name") or "", f, 280),
                   font=f, fill=WHITE, anchor="mm")
        y = max(y, hero_y + ((295 if family in ("single", "lottery") else 170) if count == 1 else 154) + 48)
    if family == "ladder" and rows:
        # Ladder stages remain distinct; do not invent a multi-player parlay.
        d.text((W // 2, y - 14), "VERIFIZIERTE STUFEN", font=_font(24),
               fill=gold, anchor="mm")

    # The Ladder uses one hero portrait; each row is a STAGE, not another player.
    # Keep the independently verified bookmaker price/form for every rung.
    if kind == "single" and rows:
        row_h = 250
    for idx, r in enumerate(rows):
        row_top = y
        d.rounded_rectangle([48, row_top, W - 48, row_top + row_h - 12], 22,
                            fill=PANEL, outline=accent + (240,), width=3)
        d.rounded_rectangle([50, row_top + 16, 59, row_top + row_h - 28], 3,
                            fill=gold + (255,))
        photo_size = 112
        if family not in ("single", "ladder"):
            ph = _circle(r.get("photo"), photo_size, r.get("name") or "?")
            img.alpha_composite(ph, (72, row_top + 14))
        x = 90 if family in ('single', 'ladder') else 242
        name_font = _font(37 if family == "single" else 32)
        display_name = (f"STUFE {idx + 1}" if family == "ladder" else (r.get("name") or ""))
        d.text((x, row_top + 39), _fit(d, display_name, name_font, 520),
               font=name_font, fill=gold if family == "ladder" else WHITE, anchor="lm")
        market = str(r.get("label") or "")
        market_font = _font(30)
        # Reserve the right column for the bookmaker price; never overprint the market.
        market_text = _fit(d, market, market_font, max(130, W - 320 - x))
        market_w = min(W - 315 - x, 30 + int(d.textlength(market_text, font=market_font)))
        d.rounded_rectangle([x, row_top + 66, x + market_w, row_top + 112], 12,
                            fill=(16, 80, 53, 245) if kind == "single" else accent + (255,),
                            outline=GREEN + (255,) if kind == "single" else accent + (255,), width=2)
        d.text((x + 12, row_top + 89), market_text, font=market_font,
               fill=WHITE if kind == "single" else (4, 20, 28), anchor="lm")
        form = str(r.get("form") or "")
        if form:
            if kind == "single":
                d.rounded_rectangle([x, row_top + 128, W - 74, row_top + 200], 12,
                                    fill=(10, 38, 39, 240), outline=GREEN + (220,), width=2)
                d.text((x + 12, row_top + 148), "FORM & STATS", font=_font(20),
                       fill=gold, anchor="lm")
                d.text((x + 12, row_top + 181),
                       _fit(d, form, _font(23, False), W - x - 110),
                       font=_font(23, False), fill=GREEN, anchor="lm")
            else:
                d.text((x, row_top + 139),
                       _fit(d, form, _font(23, False), W - x - 110),
                       font=_font(23, False), fill=GREEN, anchor="lm")
        if r.get("odds"):
            d.rounded_rectangle([W - 280, row_top + 45, W - 73, row_top + 100],
                                12, fill=(27, 25, 20, 235), outline=gold + (255,), width=3)
            d.text((W - 91, row_top + 73), _fit(d, r["odds"], _font(35), 180),
                   font=_font(35), fill=gold, anchor="rm")
        if r.get("result"):
            result = str(r["result"])
            result_color = GREEN if "GEWONNEN" in result else RED if "VERLOREN" in result else CYAN
            d.text((x, row_top + (227 if kind == 'single' else 166)), _fit(d, result, _font(22), 650),
                   font=_font(22), fill=result_color, anchor="lm")
        y += row_h
    if footer:
        d.rounded_rectangle([80, h - 125, W - 80, h - 74], 10,
                            fill=(8, 17, 29, 230), outline=gold + (255,), width=2)
        d.text((W // 2, h - 99), _fit(d, footer, _font(28), W - 190),
               font=_font(28), fill=WHITE, anchor="mm")
    if settlement:
        _sl=settlement.lower()
        _sc=(GREEN if ("gewonnen" in _sl or "+" in settlement) and "verloren" not in _sl
             else RED if ("verloren" in _sl or "-0" in settlement or "−" in settlement)
             else MUTED)
        d.text((W // 2, h - 56), _fit(d, settlement, _font(24), W - 150), font=_font(24, False), fill=_sc, anchor="mm")
    else:
        d.text((W // 2, h - 56), "AUSWERTUNG: OFFEN  ·  @prophunter", font=_font(24), fill=gold, anchor="mm")
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ----------------------------------------------------------------------------------------------------- Pick -> Karte
def _result_text(detail):
    state=str(detail.get("result") or detail.get("status") or "").lower()
    label={"win":"GEWONNEN","won":"GEWONNEN","loss":"VERLOREN","lost":"VERLOREN","push":"PUSH","void":"VOID","withdrawn":"ZURÜCKGEZOGEN"}.get(state,"")
    actual=detail.get("actual_value")
    return (f"Ist: {actual} · " if actual is not None else "")+label

def _result_color(detail):
    """GEWONNEN -> gruen, VERLOREN -> rot, sonst (Push/Void/offen) CYAN."""
    state=str(detail.get("result") or detail.get("status") or "").lower()
    if state in {"win","won"}:
        return GREEN
    if state in {"loss","lost"}:
        return RED
    return CYAN


def _form_text(features: Dict[str, Any]) -> str:
    rf = (features or {}).get("recent_form") or {}
    parts = []
    for k in ("l5", "l10", "l15"):
        w = rf.get(k) or {}
        if w.get("n"):
            parts.append(f"{k.upper()} {int(w.get('hits', 0))}/{int(w['n'])}")
    txt = "   ".join(parts)
    ml = (features or {}).get("matchup_label")
    fav = (features or {}).get("matchup_favourability")
    if ml and fav is not None and (fav >= 0.65 or fav <= 0.35):
        txt = (txt + "  ·  " if txt else "") + str(ml)
    return txt


def _label(detail: Dict[str, Any]) -> str:
    pt = detail.get("point")
    d = str(detail.get("direction") or "over").lower()
    market = re.sub(r"\s+", " ", str(detail.get("market") or "").replace("_", " ")).strip()
    # Some confirmed feeds put the actual Under/Over in the market string
    # while leaving direction blank. Never reverse an observed Under pick.
    observed_direction = re.search(r"\b(over|under)\s+[-+]?\d+(?:[.,]\d+)?\s*$",
                                   market, re.I)
    if observed_direction and not detail.get("direction"):
        d = observed_direction.group(1).lower()
    if pt is None:
        return market
    sign = "Over" if d == "over" else "Under"
    if re.search(r"\b2 plus td\b",market,re.I) and pt==1.5 and d=="over":return "2+ Touchdowns"
    kind=(detail.get("raw") or {}).get("team_builder_market")
    if kind=="moneyline":return "Sieg (inkl. OT)"
    if kind=="both_over":return f"Beide Teams Over {pt:g}"
    rest = re.sub(r"(?i)\b(over|under)\s+[\d.]+", "", market).strip()
    return f"{sign} {pt:g} {rest}".strip()


def _display_model_evidence(pick: Any) -> Dict[str, str]:
    """Format real saved model outputs, never calculate predictions from odds.

    Probabilities and edge_pct originate with the exact published pick.
    Confidence is shown only when it was actually provided by the model.
    Previously published text metrics, when present, take precedence.
    """
    def _get(key):
        return pick.get(key) if isinstance(pick,dict) else getattr(pick,key,None)
    explicit = _get("_display_model") or {}
    if not isinstance(explicit,dict):
        explicit = {}
    result={key:str(explicit[key]).strip() if explicit.get(key) not in (None,"") else ""
            for key in ("prob","edge","confidence")}
    def number(raw):
        try:
            value=float(raw)
            return value if math.isfinite(value) else None
        except (ValueError,TypeError):
            return None
    if not result["prob"]:
        probability=number(_get("probability"))
        if probability is not None and 0 <= probability <= 1:
            pct=probability*100
            result["prob"]=f"{pct:.0f}" if abs(pct-round(pct))<0.05 else f"{pct:.1f}"
    if not result["edge"]:
        edge=number(_get("edge_pct"))
        if edge is not None:
            result["edge"]=f"{edge:+.1f}"
    if not result["confidence"]:
        confidence=number(_get("confidence_score"))
        if confidence is None:
            confidence=number(_get("model_confidence"))
        if confidence is not None and 0 <= confidence <= 100:
            result["confidence"]=f"{round(confidence)}/100"
    return result


def build_for_pick(pick: Any) -> Optional[bytes]:
    """PNG-Bytes fuer einen Pick (single/ladder/betbuilder/kombi) oder None."""
    if not ON:
        return None
    try:
        typ = str(getattr(pick, "type", "") or "")
        feats = getattr(pick, "features", {}) or {}
        details = list(getattr(pick, "leg_details", None) or [])
        sport_hint = getattr(pick, "source_sport", None) or getattr(pick, "sport", None) or (details[0].get("sport") if details else None)
        league = league_of(sport_hint)
        # Fail before any ESPN network/image fetch for sports without approved masters.
        # Other sports remain text-only until their own premium masters are approved.
        if not league or league[1] != "nba":
            print("PREMIUM_ONLY_NO_VERIFIED_MASTER sport=%s type=%s" % (str(sport_hint), typ), flush=True)
            return None
        sport = league[0]
        game = str(getattr(pick, "game", "") or "")
        teams: List[Tuple[str, Optional["Image.Image"]]] = []
        cross = feats.get("combo_scope") == "cross_game"
        if " vs " in game or " @ " in game:
            parts = re.split(r"\s+(?:vs\.?|@|-)\s+", game)
            if len(parts) == 2 and not cross:
                teams = [(parts[0].strip(), team_logo(parts[0].strip(), league)), (parts[1].strip(), team_logo(parts[1].strip(), league))]
        rows: List[Dict[str, Any]] = []
        if typ == "ladder":
            name = str(getattr(pick, "player", "") or (details[0].get("player") if details else "") or "").strip()
            if not name:
                return None
            # Never publish a supposed one-player ladder that mixes athletes.
            if any(_norm(det.get("player")) != _norm(name) for det in details if det.get("player")):
                print("LADDER_REJECTED_MIXED_PLAYERS", flush=True)
                return None
            photo = player_photo(name, league)
            # Pro Stufe aus leg_details rendern: DORT stehen result + actual_value
            # nach dem Settlement (z.B. "Ist: 14 · GEWONNEN"). picks/ladder_legs
            # werden beim Settlement NICHT befuellt, nur leg_details — frueher zippte
            # die Schleife ueber picks und zeigte darum nie ein Stufen-Ergebnis.
            ladder_src = details or []
            if not ladder_src:
                # Fallback: noch nicht gesettlete Karte ohne leg_details.
                for leg in getattr(pick, "picks", None) or []:
                    ladder_src.append({"market": getattr(leg, "market", ""), "odds": getattr(leg, "odds", None)})
            for det in ladder_src:
                _odds = det.get("odds")
                rows.append({"name": name, "photo": photo,
                             "label": str(det.get("market", "")).replace("_", " "),
                             "result": _result_text(det),
                             "form": (f"L15 {int(det['gamelog_l15_hits'])}/{int(det['gamelog_l15_n'])} verfügbare Spiele" if det.get("gamelog_l15_n") else _form_text(det.get("features"))),
                             "odds": f"@{float(_odds):.2f}" if _odds else ""})
            title, subtitle = "LADDER", f"{name} · {len(rows)} Stufen"
            if not teams and game and game.lower() != "verified ladder":
                subtitle = game[:60]
        elif typ == "single":
            name = str(getattr(pick, "player", "") or "")
            rows.append({"name": name, "photo": player_photo(name, league),
                         "label": _label({"market":getattr(pick,"market","") or "","direction":getattr(pick,"direction","over"),"point":getattr(pick,"point",None)}),
                         "form": _form_text(feats), "result":_result_text(vars(pick)),
                         "model": _display_model_evidence(pick),
                         "odds": f"@{float(getattr(pick, 'odds', 0) or 0):.2f}"})
            title, subtitle = "SINGLE", game[:60] or "Pro Tip"
        else:
            if not details:
                return None
            for det in details:
                lg = league_of(det.get("sport")) or league
                nm = str(det.get("player") or "")
                rows.append({"name": nm, "photo": (team_logo(nm,lg) if det.get("kind")=="team" else player_photo(nm, lg)), "label": _label(det), "form": _form_text(det.get("features")), "result":_result_text(det),
                             "odds": f"@{float(det.get('odds') or 0):.2f}" if det.get("odds") else ""})
            title = ("MEGA LOTTERY" if len(rows) >= 9 else
                     "SUPER LOTTERY" if len(rows) >= 6 else
                     "LOTTERY" if typ in ("big", "super", "lottery") else
                     "CROSS-GAME BUILDER" if cross else
                     "SAME-GAME BUILDER" if teams else "BUILDER")
            subtitle = f"{len(rows)} Legs" + (" · mehrere Spiele" if cross else (f" · {game[:40]}" if game else ""))
        if not rows:
            return None
        subtitle = _with_kickoff(subtitle, pick)
        odds = getattr(pick, "odds", None)
        est = bool(feats.get("acca_odds_estimated_from_legs") or feats.get("builder_odds_estimated_from_legs"))
        combo = typ not in ("single", "ladder")
        verified = feats.get("combined_odds_observed") is True and bool(feats.get("combined_quote_id"))
        if combo and not verified and not getattr(pick, "_repaint_existing_photo", False):
            # Never publish a new multi-leg quote without an observed bookmaker ticket.
            return None
        if combo and not verified:
            # Already-published historical photos may be repainted for settlement.
            # Do not display their old combined price as a VERIFIED bookmaker total.
            footer = "GESAMTQUOTE UNBESTÄTIGT"
        else:
            footer = f"Quote @{float(odds):.2f}" if odds and typ != "ladder" else ""
        stake=getattr(pick,"stake",None)
        if stake is not None:footer += f" · Einsatz {float(stake):g}u"
        # Strict premium-only policy: no legacy/procedural card renderer for any sport.
        # If a verified premium master is unavailable, do not publish a replacement design.
        if league and league[1] == "nba":
            try:
                from prop_hunter_nba_premium_adapter import render_nba_pick
                png = render_nba_pick(pick, rows, teams)
                print("NBA_PREMIUM_V2_RENDER_OK type=%s legs=%d" % (typ, len(rows)), flush=True)
                return png
            except Exception as exc:
                print("NBA_PREMIUM_V2_NOT_READY type=%s reason=%s: %s" %
                      (typ, type(exc).__name__, str(exc)[:160]), flush=True)
                return None
        print("PREMIUM_ONLY_NO_VERIFIED_MASTER sport=%s type=%s" % (str(sport_hint), typ), flush=True)
        return None
    except Exception as exc:
        # Do not silently hide broken historical card data: the migration needs
        # an actionable failure class without exposing player or Telegram data.
        print(f"PROP HUNTER image render failed: type={str(getattr(pick, 'type', ''))[:32]} error={type(exc).__name__}: {str(exc)[:180]}", flush=True)
        return None



def snapshot(pick):
    """JSON-safe presentation evidence for editing the original photo later."""
    import json
    from types import SimpleNamespace
    data = {key: getattr(pick,key,None) for key in ("type","player","market","direction","point","odds","game","source_sport","sport","features","leg_details","result","actual_value","profit","stake","commence_time","game_date","date","probability","edge_pct","confidence_score","model_confidence")}
    data["picks"]=[vars(x) if isinstance(x,SimpleNamespace) else (x.model_dump() if hasattr(x,"model_dump") else dict(x) if isinstance(x,dict) else {"market":getattr(x,"market", ""),"odds":getattr(x,"odds",None)}) for x in (getattr(pick,"picks",None) or [])]
    return json.loads(json.dumps(data,default=str))


def settled_image(data, text):
    from types import SimpleNamespace
    obj=dict(data)
    obj["picks"]=[SimpleNamespace(**x) for x in obj.get("picks",[]) or []]
    summary=next((ln for ln in text.splitlines() if "Auswertung:" in ln), "")
    summary=re.sub(r"[^\w\s:.,+%/−-]", "", summary)
    summary=summary.replace("Auswertung:","Ergebnis:")
    # Emoji glyphs vary by host; explicit words keep the result readable.
    counts=[]
    for pattern,label in ((r"(\d+)✅","gewonnen"),(r"(\d+)❌","verloren"),(r"(\d+)↔","Push"),(r"(\d+)⏳","offen")):
        match=re.search(pattern,text.split("Auswertung:")[-1])
        if match and int(match[1]):counts.append(f"{match[1]} {label}")
    profit=re.search(r"[+-]\d+\.\d+u",text.split("Auswertung:")[-1])
    obj["settlement_summary"]=" · ".join(counts+([profit[0]] if profit else [])) or summary
    # Show only the original published model numbers (if present). Do not
    # infer probabilities or edges from the odds or settlement outcomes.
    def metric(pattern):
        matched=re.search(pattern,text,re.I)
        return matched.group(1).replace(",",".") if matched else None
    obj["_display_model"]={
        "prob": metric(r"\bProb\s+(\d+(?:[.,]\d+)?)\s*%"),
        "edge": metric(r"\bEdge\s+([+-]?\d+(?:[.,]\d+)?)\s*(?:%|pp)"),
        "confidence": metric(r"\bConfidence\s+(\d+\s*/\s*100)"),
    }
    # This renderer only edits an already-published Telegram photo; it is NOT
    # called by new-pick production. Old combo snapshots may lack quote provenance.
    feats = obj.get("features") or {}
    if (obj.get("type") not in ("single", "ladder")
            and not (feats.get("combined_odds_observed") is True and feats.get("combined_quote_id"))):
        obj["_repaint_existing_photo"] = True
    return build_for_pick(SimpleNamespace(**obj))
