"""Fail-closed pixel provenance for owner-original Telegram artwork.

This checks fixed identity-bearing pixels; it does NOT pretend to perform a
human visual sign-off or OCR every dynamic field. QA-only SVGs do not qualify.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import hashlib
import os

from prop_hunter_telegram_safe_zone import split_owner_margin
from prop_hunter_nba_owner_bridge import user_single_original_enabled

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
# NBA shield at top-left belongs to the owner, just like the PROP HUNTER
# crown. Neither may be replaced, painted over or regenerated.
STATIC_NBA_SHIELD = (33, 12, 93, 110)
STATIC_BRAND_PATCHES = (STATIC_CROWN, STATIC_NBA_SHIELD)


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
    # The user supplied a *different* 512x512 SINGLE source on 22.11.26:
    # no comparison against the unrelated old 691px stadium header.
    if (family == "single" and str(field(pick,"type","")).strip().lower()=="single"
            and user_single_original_enabled(pick)):
        try:
            from prop_hunter_owner_supplied_single import SOURCE, EDITABLE, SOURCE_SHA256
            if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=SOURCE_SHA256:
                return False, "owner_new_single_source_changed"
            with Image.open(SOURCE) as original, Image.open(EDITABLE) as clean, \
                 Image.open(BytesIO(png_bytes)) as sent:
                if original.size!=(512,512) or clean.size!=(512,512):
                    return False, "owner_new_single_source_size_changed"
                # Derived master only removes the original baked OFFEN word.
                discrepancy=ImageChops.difference(original.convert("RGB"),
                                                   clean.convert("RGB")).getbbox()
                if (not discrepancy or discrepancy[0]<231 or discrepancy[1]<455
                        or discrepancy[2]>316 or discrepancy[3]>490):
                    return False, "owner_new_single_clean_plate_overpainted"
                if sent.format!="PNG" or sent.width!=1080:
                    return False, "not_full_resolution_owner_png"
                try:
                    body, has_margin=split_owner_margin(sent,(1080,))
                except ValueError:
                    return False, "owner_telegram_margin_missing_or_modified"
                if (os.getenv("PH_REQUIRE_TELEGRAM_SAFE_MARGIN","0")=="1"
                        and not has_margin):
                    return False, "owner_telegram_margin_missing"
                expected=clean.convert("RGB").resize((1080,1080),
                                                       Image.Resampling.LANCZOS)
                # Preserve both immutable owner marks: original header
                # AND the actual NBA shield, no fabricated replacement.
                for source_patch in ((140,2,385,64),(12,2,58,55)):
                    region=tuple(round(v*1080/512) for v in source_patch)
                    if ImageChops.difference(expected.crop(region),
                                             body.crop(region)).getbbox():
                        return False, "owner_new_single_masthead_pixel_overlap"
            return True, "source_original_pixels_verified"
        except (ValueError,OSError,SyntaxError):
            return False, "owner_new_single_source_unreadable"
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
            # Only the known immutable crown is pixel-identical to the
            # historical JPEG screenshot. The approved PNG shield can carry
            # old JPEG/source-cleanup differences. Its outbound pixels still
            # must match the approved clean master exactly (see below).
            if ImageChops.difference(
                master.crop(STATIC_CROWN),
                original.crop(STATIC_CROWN)
            ).getbbox() is not None:
                return False, "owner_original_branding_changed"
            # The original Single/Ladder/Builder/Lottery scales its immutable
            # crown with LANCZOS. When the six-stage Ladder adds an owner-derived
            # EMPTY 120px stadium band, the vertical scaling ratio changes by a
            # tiny rounding amount. Comparing that image against the 865px
            # *unextended* resized plate falsely rejects genuine pixels.
            # Reconstruct the exact source-layer geometry before resampling,
            # rather than weakening pixel equality or allowing a legacy mask.
            factor = 1080.0 / master.width
            boxes = [tuple(round(v*factor) for v in patch)
                     for patch in STATIC_BRAND_PATCHES]
            exact_height = round(1080 * master.height / master.width)
            permitted = [exact_height]
            if family == "ladder" and master.size == (691, 865):
                permitted.append(round(1080 * (master.height + 120) / master.width))
            try:
                owner_body, has_safe_margin = split_owner_margin(sent, tuple(permitted))
            except ValueError:
                return False, "owner_telegram_margin_missing_or_modified"
            if (os.getenv("PH_REQUIRE_TELEGRAM_SAFE_MARGIN", "0") == "1"
                    and not has_safe_margin):
                return False, "owner_telegram_margin_missing"
            comparison = master
            if family == "ladder" and owner_body.height != exact_height:
                extra, cut = 120, 730
                allowed_height = round(1080 * (master.height + extra) / master.width)
                if master.size != (691, 865) or owner_body.height != allowed_height:
                    return False, "unapproved_ladder_extension"
                comparison = Image.new(
                    "RGB", (691, 865 + extra), (3, 15, 29)
                )
                comparison.paste(master.crop((0, 0, 691, cut)), (0, 0))
                comparison.paste(master.crop((0, 515, 691, 635)), (0, cut))
                comparison.paste(
                    master.crop((0, cut, 691, 865)), (0, cut + extra)
                )
            expected = comparison.resize(
                (1080, owner_body.height if family == "ladder" else exact_height),
                Image.Resampling.LANCZOS
            )
            for box in boxes:
                actual = owner_body.crop(box)
                if ImageChops.difference(expected.crop(box), actual).getbbox() is not None:
                    return False, "owner_masthead_pixel_overlap"
    except (OSError, ValueError, SyntaxError):
        return False, "owner_pixel_artwork_unreadable"
    return True, "source_original_pixels_verified"
