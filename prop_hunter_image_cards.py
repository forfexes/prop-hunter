#!/usr/bin/env python3
"""Bildkarten fuer PROP HUNTER (Single, Same-Game-Builder, Cross-Game-Builder, Ladder).

Arena-Hintergrund je Sportart (prozedural, keine fremden Bilder), Teamwappen, Spielerfotos und Formwerte
(L5/L10/L15) aus den bereits gepruefte Pick-Daten. Fotos/Wappen kommen aus der oeffentlichen ESPN-API; fehlt eines,
erscheint ein neutraler Platzhalter. Jeder Fehler -> None, der Aufrufer sendet dann die normale Textkarte.
Abschalten: PH_IMAGE_CARDS=0
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
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except Exception:  # Pillow fehlt -> Bildkarten aus
    Image = None

ON = os.getenv("PH_IMAGE_CARDS", "1") != "0" and Image is not None
W = 1080
CYAN = (34, 230, 238)
WHITE = (245, 250, 252)
MUTED = (150, 178, 190)
PANEL = (10, 26, 38, 205)
HEADERS = {"User-Agent": "PropHunter-Cards/1.0 (+https://github.com/forfexes/prop-hunter)"}

# ESPN: (sport, league) je Prop-Hunter-Sportschluessel
LEAGUES = {
    "nba": ("basketball", "nba"), "wnba": ("basketball", "wnba"), "nfl": ("football", "nfl"),
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
    for key in ("wnba", "nba", "nfl", "mlb", "nhl"):
        if re.search(rf"\b{key}\b", v) or f"basketball {key}" in v or f"{key}" == v.strip():
            return LEAGUES[key]
    if "basketball" in v:
        return LEAGUES["nba"]
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
            teams.append({"names": {_norm(t.get(k)) for k in ("displayName", "shortDisplayName", "name", "abbreviation", "nickname", "location") if t.get(k)},
                          "logo": logos[0].get("href") if logos else None})
        _CACHE[tkey] = teams
    want = _norm(team)
    for t in _CACHE[tkey]:
        if want in t["names"]:
            return _get_image(t["logo"])
    return None


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
    glow = glow.filter(ImageFilter.GaussianBlur(6))
    img = Image.alpha_composite(img.convert("RGBA"), glow)
    return img


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


def render(kind: str, title: str, subtitle: str, sport: str, teams: List[Tuple[str, Optional["Image.Image"]]],
           rows: List[Dict[str, Any]], footer: str = "", settlement: str = "") -> bytes:
    """rows: {name, label, photo(Image|None), form(str), odds(str)}; teams: [(name, logo)] (0-2)."""
    row_h = 195
    head_h = 430 if teams else 280
    h = head_h + row_h * len(rows) + 190
    img = _background(sport, h)
    d = ImageDraw.Draw(img, "RGBA")
    d.text((W // 2, 62), "PROP HUNTER", font=_font(62), fill=WHITE, anchor="mm")
    d.rounded_rectangle([40, 120, W - 40, h - 30], 28, outline=CYAN + (255,), width=4)
    d.text((W // 2, 170), title, font=_font(54), fill=CYAN, anchor="mm")
    d.text((W // 2, 222), subtitle, font=_font(30, False), fill=MUTED, anchor="mm")
    y = 262
    if teams:
        slots = [(W // 2 - 300, teams[0]), (W // 2 + 300, teams[1] if len(teams) > 1 else None)]
        for cx, t in slots:
            if not t:
                continue
            name, logo = t
            c = _circle(logo, 110, name)
            img.alpha_composite(c, (cx - 55, y - 10))
            d.text((cx, y + 118), _fit(d, name, _font(26), 260), font=_font(26), fill=WHITE, anchor="mm")
        d.text((W // 2, y + 45), "VS", font=_font(48), fill=CYAN, anchor="mm")
        y += 150
    for r in rows:
        d.rounded_rectangle([70, y, W - 70, y + row_h - 12], 22, fill=PANEL, outline=(34, 230, 238, 110), width=2)
        ph = _circle(r.get("photo"), 112, r.get("name") or "?")
        img.alpha_composite(ph, (92, y + 11))
        d.text((232, y + 38), _fit(d, r.get("name") or "", _font(36), 520), font=_font(36), fill=WHITE, anchor="lm")
        d.rounded_rectangle([232, y + 66, 232 + min(560, 24 + int(d.textlength(r.get("label") or "", font=_font(30)))), y + 108], 12, fill=CYAN + (255,))
        d.text((244, y + 87), _fit(d, r.get("label") or "", _font(30), 540), font=_font(30), fill=(4, 20, 28), anchor="lm")
        if r.get("form"):
            d.text((232, y + 134), r["form"], font=_font(24, False), fill=MUTED, anchor="lm")
        if r.get("odds"):
            d.text((W - 100, y + 62), r["odds"], font=_font(40), fill=CYAN, anchor="rm")
        if r.get("result"):
            d.text((232,y+164),_fit(d,r["result"],_font(23),640),font=_font(23),fill=CYAN,anchor="lm")
        y += row_h
    if footer:
        d.text((W // 2, h - 92), _fit(d, footer, _font(30), W - 160), font=_font(30), fill=WHITE, anchor="mm")
    d.text((W // 2, h - 56), (_fit(d, settlement, _font(24), W - 150) if settlement else "Auswertung: offen"), font=_font(24, False), fill=MUTED, anchor="mm")
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ----------------------------------------------------------------------------------------------------- Pick -> Karte
def _result_text(detail):
    state=str(detail.get("result") or detail.get("status") or "").lower()
    label={"win":"GEWONNEN","won":"GEWONNEN","loss":"VERLOREN","lost":"VERLOREN","push":"PUSH","void":"VOID","withdrawn":"ZURÜCKGEZOGEN"}.get(state,"")
    actual=detail.get("actual_value")
    return (f"Ist: {actual} · " if actual is not None else "")+label


def _form_text(features: Dict[str, Any]) -> str:
    rf = (features or {}).get("recent_form") or {}
    parts = []
    for k in ("l5", "l10", "l15"):
        w = rf.get(k) or {}
        if w.get("n"):
            parts.append(f"{k.upper()} {int(w.get('hits', 0))}/{int(w['n'])}")
    return "   ".join(parts)


def _label(detail: Dict[str, Any]) -> str:
    pt = detail.get("point")
    d = str(detail.get("direction") or "over").lower()
    market = re.sub(r"\s+", " ", str(detail.get("market") or "")).strip()
    if pt is None:
        return market
    sign = "Over" if d == "over" else "Under"
    rest = re.sub(r"(?i)^(over|under)\s+[\d.]+\s*", "", market)
    return f"{sign} {pt:g} {rest}".strip()


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
        sport = league[0] if league else "neutral"
        game = str(getattr(pick, "game", "") or "")
        teams: List[Tuple[str, Optional["Image.Image"]]] = []
        cross = feats.get("combo_scope") == "cross_game"
        if " vs " in game or " @ " in game:
            parts = re.split(r"\s+(?:vs\.?|@|-)\s+", game)
            if len(parts) == 2 and not cross:
                teams = [(parts[0].strip(), team_logo(parts[0].strip(), league)), (parts[1].strip(), team_logo(parts[1].strip(), league))]
        rows: List[Dict[str, Any]] = []
        if typ == "ladder":
            name = str(getattr(pick, "player", "") or "")
            photo = player_photo(name, league)
            for leg, det in zip(getattr(pick, "picks", None) or [], details or [{}] * len(getattr(pick, "picks", None) or [])):
                rows.append({"name": name, "photo": photo, "label": str(getattr(leg, "market", "")),
                             "result":_result_text(det), "form": (f"L15 {int(det['gamelog_l15_hits'])}/{int(det['gamelog_l15_n'])}" if det.get("gamelog_l15_n") else _form_text(det.get("features"))),
                             "odds": f"@{float(leg.odds):.2f}"})
            title, subtitle = "PLAYER LADDER", "Ein Spieler · mehrere Stufen"
            if not teams and game and game.lower() != "verified ladder":
                subtitle = game[:60]
        elif typ == "single":
            name = str(getattr(pick, "player", "") or "")
            _market_with_line = lambda market, direction, point: f"{market} {direction} {point:g}" if point is not None else str(market)
            rows.append({"name": name, "photo": player_photo(name, league),
                         "label": _market_with_line(getattr(pick, "market", "") or "", getattr(pick, "direction", "over"), getattr(pick, "point", None)),
                         "form": _form_text(feats), "result":_result_text(vars(pick)), "odds": f"@{float(getattr(pick, 'odds', 0) or 0):.2f}"})
            title, subtitle = "SINGLE", game[:60] or "Pro Tip"
        else:
            if not details:
                return None
            for det in details:
                lg = league_of(det.get("sport")) or league
                nm = str(det.get("player") or "")
                rows.append({"name": nm, "photo": player_photo(nm, lg), "label": _label(det), "form": _form_text(det.get("features")), "result":_result_text(det),
                             "odds": f"@{float(det.get('odds') or 0):.2f}" if det.get("odds") else ""})
            title = "CROSS-GAME BUILDER" if cross else ("SAME-GAME BUILDER" if teams else "BUILDER")
            subtitle = f"{len(rows)} Legs" + (" · mehrere Spiele" if cross else (f" · {game[:40]}" if game else ""))
        if not rows:
            return None
        odds = getattr(pick, "odds", None)
        est = bool(feats.get("acca_odds_estimated_from_legs") or feats.get("builder_odds_estimated_from_legs"))
        footer = "Bestätigte Book-Quote prüfen" if est else (f"Quote @{float(odds):.2f}" if odds and typ != "ladder" else "")
        return render(typ, title, subtitle, sport, teams, rows[:7], footer, getattr(pick,"settlement_summary", ""))
    except Exception:
        return None



def snapshot(pick):
    """JSON-safe presentation evidence for editing the original photo later."""
    import json
    from types import SimpleNamespace
    data = {key: getattr(pick,key,None) for key in ("type","player","market","direction","point","odds","game","source_sport","sport","features","leg_details","result","actual_value","profit")}
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
    return build_for_pick(SimpleNamespace(**obj))
