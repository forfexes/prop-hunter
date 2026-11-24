"""NFL card renderer using the stadium and team artwork in the offline master."""
import base64
import json
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TEAMS = dict(zip(
    "ari atl bal buf car chi cin cle dal den det gb hou ind jax kc lac lar lv mia min ne no nyg nyj phi pit sea sf tb ten wsh".split(),
    "Cardinals Falcons Ravens Bills Panthers Bears Bengals Browns Cowboys Broncos Lions Packers Texans Colts Jaguars Chiefs Chargers Rams Raiders Dolphins Vikings Patriots Saints Giants Jets Eagles Steelers Seahawks 49ers Buccaneers Titans Commanders".split(),
))
MASTER = Path(__file__).parent / "card_templates/nfl/PROP_HUNTER_NFL_Vorlagen.html"


@lru_cache(maxsize=1)
def artwork():
    data = json.loads(re.search(r"const assets=(.*);", MASTER.read_text(encoding="utf-8"))[1])
    return {
        key: Image.open(BytesIO(base64.b64decode(data[key].split(",", 1)[1]))).convert("RGBA")
        for key in (*TEAMS, "stadium", "shield")
    }


def fixture(value):
    parts = re.split(r"\s+(?:vs\.?|@|at)\s+", str(value or "").strip(), flags=re.I)
    if len(parts) != 2:
        raise ValueError("NFL fixture requires two teams")
    codes = []
    for part in parts:
        name = part.lower()
        code = next((code for code, nick in TEAMS.items()
                     if name == code or name.split()[-1:] == [nick.lower()]), None)
        if not code or code in codes:
            raise ValueError("Unknown or duplicate NFL team")
        codes.append(code)
    return tuple(codes)


def render_nfl_pick(pick, details, cards):
    kind = str(pick.type).lower()
    features = pick.features or {}
    title = {
        "single": "SINGLE", "longshot": "SINGLE", "ladder": "LADDER",
        "big": "LOTTERY", "super": "LOTTERY", "lottery": "LOTTERY",
    }.get(kind, "CROSS" if features.get("combo_scope") == "cross_game" else "BUILDER")
    player = str(getattr(pick, "player", "") or "").strip()
    assets = artwork()
    image = assets["stadium"].resize((900, 1125)).copy()
    draw = ImageDraw.Draw(image)
    white, ice, violet, navy = "#f6f9ff", "#9eeaff", "#b45bff", "#041021"

    def text(value, position, size, width=810, color=white, anchor="mm"):
        while size > 10:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", size)
            if font.getlength(value) <= width:
                break
            size -= 1
        draw.text(position, value, font=font, fill=color, anchor=anchor)

    def paste(key, center, limit):
        asset = assets[key].copy()
        asset.thumbnail(limit, Image.Resampling.LANCZOS)
        image.alpha_composite(asset, (center[0] - asset.width // 2, center[1] - asset.height // 2))

    def logos(teams, x, y, gap, size):
        paste(teams[0], (x-gap, y), (size, size))
        paste(teams[1], (x+gap, y), (size, size))

    def rule(y):
        draw.line((45, y, 855, y), fill=violet, width=2)

    def model(obj):
        values = cards._display_model_evidence(obj)
        edge = values["edge"]
        conf = values["confidence"]
        return "   ·   ".join(filter(None, (
            f"EDGE {edge.rstrip('%')}%" if edge else "",
            f"CONF {conf}" if conf else "",
        )))

    draw.rectangle((0, 0, 900, 145), fill=navy)
    text("PROP HUNTER", (450, 43), 58)
    paste("shield", (450, 109), (54, 66))
    text(title, (450, 173), 32)
    if title in {"SINGLE", "LADDER"}:
        teams = fixture(pick.game)
        if not player or any(d.get("player") and cards._norm(d["player"]) != cards._norm(player) for d in details):
            raise ValueError("NFL player identity missing or inconsistent")
        portrait = cards.player_photo(player, ("football", "nfl"))
        if portrait is not None:
            portrait = portrait.convert("RGBA")
            portrait.thumbnail((525, 425), Image.Resampling.LANCZOS)
            image.alpha_composite(portrait, ((900-portrait.width)//2, 620-portrait.height))
        logos(teams, 450, 407, 325, 135)
        draw.rectangle((0, 620, 900, 1125), fill=navy)
        text(player.upper(), (450, 665), 67)
        rule(708)
        market = str(getattr(pick, "market", "") or (details[0].get("market") if details else ""))
        if title == "SINGLE":
            text(f"PROP · {market.replace('_', ' ').upper()}", (450, 748), 35)
            draw.rectangle((200, 789, 700, 866), fill="#512198")
            label = f"{getattr(pick, 'direction', '')} {getattr(pick, 'point', '')}"
            text(label.strip().upper(), (450, 827), 46, width=470)
            text(f"QUOTE {float(pick.odds):.2f}", (450, 907), 36)
            text(model(pick), (450, 960), 27, color=ice)
            text(cards._form_text(features), (450, 1010), 27, color=ice)
            text(cards._result_text(vars(pick)), (450, 1060), 24)
        else:
            if not 2 <= len(details) <= 4:
                raise ValueError("NFL ladder requires two to four rungs")
            for i, leg in enumerate(details):
                y = 728 + i*96
                text(cards._label(leg).upper(), (52, y+16), 27, 575, anchor="lm")
                text(f"{float(leg['odds']):.2f}", (840, y+16), 29, color=ice, anchor="rm")
                stats = "   ·   ".join(filter(None, (cards._ladder_exact_form(leg), model(leg), cards._result_text(leg))))
                text(stats, (52, y+55), 24, 790, color=ice, anchor="lm")
                rule(y+78)
    else:
        if not 2 <= len(details) <= 6 or not all(str(d.get("player") or "").strip() for d in details):
            raise ValueError("NFL combo requires two to six named legs")
        games = [fixture(d.get("game") or d.get("match") or (pick.game if title == "BUILDER" else "")) for d in details]
        distinct = {frozenset(game) for game in games}
        if (title == "BUILDER" and (len(distinct) != 1 or frozenset(fixture(pick.game)) not in distinct)) or (title == "CROSS" and len(distinct) < 2):
            raise ValueError("NFL combo scope conflicts with its fixtures")
        if title == "BUILDER":
            logos(games[0], 450, 258, 113, 100)
            text("VS", (450, 258), 30)
        draw.rectangle((0, 323, 900, 1125), fill=navy)
        row_height = min(135, 600 // len(details))
        for i, (leg, game) in enumerate(zip(details, games)):
            y = 333+i*row_height
            rule(y)
            if title != "BUILDER":
                logos(game, 90, y+40, 26, 45)
            x = 55 if title == "BUILDER" else 151
            text(str(leg.get("player") or "").upper(), (x, y+20), 30, 840-x, anchor="lm")
            text(cards._label(leg), (x, y+48), 24, 840-x, anchor="lm")
            evidence = "   ·   ".join(filter(None, (cards._form_text(leg.get("features") or {}), cards._result_text(leg))))
            text(evidence, (x, y+76), 21, 840-x, color=ice, anchor="lm")
        rule(333+row_height*len(details))
        text(f"GESAMTQUOTE {float(pick.odds):.2f}", (450, 980), 49)
        text(model(pick), (450, 1040), 28, color=ice)
    output = BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()
