"""Fail-closed pixel provenance for owner-original Telegram artwork.

This checks fixed identity-bearing pixels; it does NOT pretend to perform a
human visual sign-off or OCR every dynamic field. QA-only SVGs do not qualify.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent / "card_templates"
APPROVED = ROOT / "approved"
CLEANED = ROOT / "cleaned"
ORIGINALS = ROOT / "originals"
CROP = {
    "single": (0, 390, 691, 1148),
    "ladder": (0, 336, 691, 1201),
    "builder": (0, 336, 691, 1203),
    "lottery": (0, 394, 691, 1147),
}
# The owner logo/crown is immutable for all four real NBA cards. This rectangle
# deliberately avoids player/match/market/quote/result areas.
STATIC_CROWN = (230, 5, 480, 42)


def field(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def owner_family(pick):
    kind = str(field(pick, "type", "") or "").strip().lower()
    flags = field(pick, "features", {}) or {}
    if not isinstance(flags, dict):
        return None
    if kind in ("single", "longshot"):
        return "single"
    if kind == "ladder":
        return "ladder"
    if kind in ("lottery", "big", "super", "combo", "cross", "cross_game"):
        return "lottery"
    if kind in ("betbuilder", "builder", "kombi2", "kombi3", "kombi"):
        if flags.get("combo_scope") == "cross_game":
            return "lottery"
        if flags.get("same_player_multistat"):
            return "ladder"
        return "builder"
    return None


def owner_pixel_provenance(pick, png_bytes):
    """Return (allowed, reason); never modify the original or output image."""
    family = owner_family(pick)
    if family not in CROP:
        return False, "unapproved_card_family"
    if not isinstance(png_bytes, (bytes, bytearray)):
        return False, "missing_png"
    try:
        with Image.open(APPROVED / (family + ".png")) as a, \
             Image.open(CLEANED / (family + ".png")) as c, \
             Image.open(ORIGINALS / (family + ".jpg")) as o, \
             Image.open(BytesIO(png_bytes)) as sent:
            if sent.format != "PNG" or sent.width != 1080:
                return False, "not_full_resolution_owner_png"
            master, clean = a.convert("RGB"), c.convert("RGB")
            original = o.convert("RGB").crop(CROP[family])
            if master.size != original.size or clean.size != master.size:
                return False, "owner_plate_size_mismatch"
            if ImageChops.difference(master, clean).getbbox() is not None:
                return False, "approved_master_not_current_clean_plate"
            if ImageChops.difference(
                master.crop(STATIC_CROWN),
                original.crop(STATIC_CROWN),
            ).getbbox() is not None:
                return False, "owner_original_branding_changed"
            # The real owner compositor scales the source to 1080 px with
            # LANCZOS. Compare the *same* immutable master pixels in the PNG.
            factor = 1080.0 / master.width
            box = tuple(round(v * factor) for v in STATIC_CROWN)
            exact_height = round(1080 * master.height / master.width)
            if sent.height < exact_height:
                return False, "owner_png_truncated"
            expected = master.resize(
                (1080, exact_height), Image.Resampling.LANCZOS
            ).crop(box)
            actual = sent.convert("RGB").crop(box)
            if ImageChops.difference(expected, actual).getbbox() is not None:
                return False, "owner_masthead_pixel_overlap"
    except (OSError, ValueError, SyntaxError):
        return False, "owner_pixel_artwork_unreadable"
    return True, "source_original_pixels_verified"
