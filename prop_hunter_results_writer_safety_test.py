#!/usr/bin/env python3
"""Offline safety checks for the shared Telegram-card settlement history writer."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import prophunter_results as writer

with TemporaryDirectory() as directory:
    path = Path(directory) / "picks_history.json"
    with patch.object(writer, "HISTORY", path):
        assert writer._load_history() == []
        original = [{"date": "2026-11-18", "cards": [
            {"message_id": 7001, "media_type": "photo", "card_design_version": 6}
        ]}]
        writer._save_history(original)
        assert writer._load_history() == original
        previous_bytes = path.read_bytes()

        # Simulate an interrupted atomic rename: old committed history survives.
        with patch.object(writer.os, "replace", side_effect=OSError("injected interruption")):
            try:
                writer._save_history([{"date": "2026-11-19", "cards": []}])
            except OSError:
                pass
            else:
                raise AssertionError("Injected interruption unexpectedly succeeded")
        assert path.read_bytes() == previous_bytes
        assert not list(path.parent.glob(".picks_history.json.*.tmp"))

        # Fail closed on broken or structurally invalid history.
        for invalid in ("{broken", "{}", "null"):
            path.write_text(invalid, encoding="utf-8")
            try:
                writer._load_history()
            except RuntimeError:
                pass
            else:
                raise AssertionError(f"Invalid history accepted: {invalid}")
            assert path.read_text(encoding="utf-8") == invalid

        path.write_text(json.dumps(original), encoding="utf-8")
        assert writer._load_history()[0]["cards"][0]["message_id"] == 7001

print("PROP HUNTER ATOMIC HISTORY WRITER / CORRUPTION FAIL-CLOSED PASSED")
