"""Test yardimcilari: proje kokunu sys.path'e ekler, gercek log dizinine yazmayi engeller."""

from __future__ import annotations

import os
import pathlib
import sys
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def capture_logs() -> tuple[mock.patch, list[tuple[str, str]]]:
    """src.utils.helpers.write_log'u yakalar (%LOCALAPPDATA%'ya yazmaz).

    Kullanim:  patcher, lines = capture_logs(); patcher.start(); addCleanup(patcher.stop)
    lines: [(seviye, mesaj), ...]
    """
    lines: list[tuple[str, str]] = []

    def fake_write_log(message: str, level: str = "INFO") -> None:
        lines.append((level, message))

    return mock.patch("src.utils.helpers.write_log", side_effect=fake_write_log), lines
