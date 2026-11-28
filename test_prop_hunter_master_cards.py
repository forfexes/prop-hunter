"""Prop Hunter cards on the clean arena master (no overpaint, no placeholders)."""
import io
import pytest
from PIL import Image, ImageDraw
import prop_hunter_master_cards as P
from prop_hunter_telegram_safe_zone import append_owner_margin


def crest(col=(20, 100, 50, 255)):
    im = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((10, 10, 290, 290), fill=col)
    return im


def person():
    im = Image.new("RGBA", (500, 700), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((150, 40, 350, 260), fill=(190, 140, 110, 255))
    d.rounded_rectangle((60, 250, 440, 700), 60, fill=(230, 230, 240, 255))
    return im


TEAMS = [("Milwaukee Bucks", crest()), ("Detroit Pistons", crest((200, 30, 50, 255)))]


def row(**k):
    return dict(dict(name="Isaiah Joe", label="UNDER 15.5", odds="@2.05",
                     form="L5 5/5 · L10 10/10 · L15 14/14",
                     model=dict(prob="68.6", edge="+19.9", confidence="89/100"), photo=person()), **k)


def size(b):
    return Image.open(io.BytesIO(b)).size


def test_single_ladder_list_render_at_master_size():
    assert size(P.render_single("POINTS", "Sa 28.11.2026 · 01:30", TEAMS, row(), "Einsatz 1u")) == (1080, 1440)
    rows = [row(label=f"Rebounds Under {x}", odds=o) for x, o in ((12.5, "@1.74"), (11.5, "@2.10"))]
    assert size(P.render_ladder("L", "Sa 28.11.2026", TEAMS, rows, "Einsatz 1u")) == (1080, 1440)
    for n in (2, 4, 6):
        rs = [row(name=f"P{i}") for i in range(n)]
        assert size(P.render_list("builder", "B", "Sa 28.11.2026", TEAMS, rs)) == (1080, 1440)


def test_missing_values_are_omitted_never_dashed(monkeypatch):
    seen = []
    real = P._text
    monkeypatch.setattr(P, "_text", lambda d, xy, t, *a, **k: (seen.append(str(t)), real(d, xy, t, *a, **k))[1])
    P.render_single("POINTS", "Sa 28.11.2026", TEAMS, row(form="", model={}), "")
    assert "—" not in seen and "-" not in seen
    assert not any(t.startswith("L5") for t in seen) and "MODELL" not in seen and "EINSATZ" not in seen


@pytest.mark.parametrize("bad", [dict(odds=None), dict(odds="x"), dict(photo=None), dict(name=""), dict(label="")])
def test_fail_closed_on_missing_real_data(bad):
    with pytest.raises(ValueError):
        P.render_single("POINTS", "Sa 28.11.2026", TEAMS, row(**bad), "")


def test_opaque_or_missing_crest_rejected():
    tile = Image.new("RGBA", (200, 200), (250, 250, 250, 255))
    with pytest.raises(ValueError):
        P.render_single("P", "Sa 28.11.2026", [("A", tile), TEAMS[1]], row(), "")
    with pytest.raises(ValueError):
        P.render_single("P", "Sa 28.11.2026", [("A", None), TEAMS[1]], row(), "")


def test_ladder_needs_one_athlete():
    with pytest.raises(ValueError):
        P.render_ladder("L", "Sa 28.11.2026", TEAMS, [row(name="A"), row(name="B")])


def test_provenance_accepts_master_with_margin_and_rejects_altered():
    png = P.render_single("POINTS", "Sa 28.11.2026", TEAMS, row(), "")
    assert P.is_master_card(png)[0] is True
    assert P.is_master_card(append_owner_margin(png))[0] is True
    im = Image.open(io.BytesIO(png)).convert("RGB")
    ImageDraw.Draw(im).rectangle((10, 10, 120, 120), fill=(255, 0, 0))
    b = io.BytesIO(); im.save(b, "PNG")
    assert P.is_master_card(b.getvalue())[0] is False


def test_handle_never_drawn_in_image():
    import inspect
    assert "@prophunter" not in inspect.getsource(P).replace('"@prophunter" not in', "")
