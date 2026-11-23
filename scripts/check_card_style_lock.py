"""Fail closed when original/approved owner card artwork changes without review.

Git blob SHA-1 is calculated on BYTES, not image RGB: even metadata edits
count as new artwork. No image-generation, network or Telegram side effects.
"""
from __future__ import annotations
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCKED = {
    "card_templates/approved/builder.png": "5a1a7d16eb263d86edc7e19429d4223154a8dd5b",
    "card_templates/approved/ladder.png": "59065833fa5312ffadae2aa60f95aa0b1d09d56d",
    "card_templates/approved/lottery.png": "37dac1ba5e8de42e0e7acd622e1728acdf8ca0cd",
    "card_templates/approved/single.png": "6b6065f4f1373935591463c3580cdf815b58fb1b",
    "card_templates/originals/builder.jpg": "3c9d3a86e3e359cc02818dec905a36d86c951953",
    "card_templates/originals/ladder.jpg": "a0f04af7630b00b42c3a91ff916d1c4f73aa8efd",
    "card_templates/originals/lottery.jpg": "b2a0e14945381a76eeeeb822bf899a5121dbb9e1",
    "card_templates/originals/single.jpg": "cebc01f7beca2334f694ef6ea168bd3fdbb72f65"
}


def git_blob_sha1(content: bytes) -> str:
    return hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()


def verify() -> None:
    for path, expected in LOCKED.items():
        full = ROOT / path
        if not full.is_file():
            raise AssertionError(f"Missing mandatory owner artwork: {path}")
        actual = git_blob_sha1(full.read_bytes())
        if actual != expected:
            raise AssertionError(f"Unauthorized card-style artwork change: {path}")
    print(f"CARD_STYLE_LOCK_OK: {len(LOCKED)} immutable owner artworks")


if __name__ == "__main__":
    verify()
