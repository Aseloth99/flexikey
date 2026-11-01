"""Pencereyi kapatmak (X / Alt+F4) uygulamayı tepsiye gizler; tamamen çıkış yalnızca Ctrl+Q / Çıkış / tepsi menüsü."""

from __future__ import annotations

import os
import pathlib
import sys
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtGui import QCloseEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


class CloseBehaviourTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _fake_window(self):
        calls = {"hidden": 0, "info": 0}
        fake = types.SimpleNamespace(
            lang="tr",
            _clear_resize_cursor=lambda: None,
            hide=lambda: calls.__setitem__("hidden", calls["hidden"] + 1),
            notification_manager=types.SimpleNamespace(info=lambda *_: calls.__setitem__("info", calls["info"] + 1)),
        )
        return fake, calls

    def test_closing_hides_to_tray_and_keeps_running(self) -> None:
        from src.gui.main_window import MainWindow

        fake, calls = self._fake_window()
        event = QCloseEvent()
        MainWindow.closeEvent(fake, event)
        self.assertFalse(event.isAccepted(), "kapatma isteği reddedilip pencere gizlenmeli")
        self.assertEqual(calls["hidden"], 1)

    def test_closing_is_allowed_while_windows_is_shutting_down(self) -> None:
        from src.gui.main_window import MainWindow

        fake, calls = self._fake_window()
        event = QCloseEvent()
        event.ignore()
        with mock.patch("PyQt6.QtGui.QGuiApplication.isSavingSession", return_value=True):
            MainWindow.closeEvent(fake, event)
        self.assertTrue(event.isAccepted(), "oturum kapanırken uygulama Windows'un kapanmasını engellememeli")
        self.assertEqual(calls["hidden"], 0)

    def test_alt_f4_is_not_bound_to_quit(self) -> None:
        source = (ROOT / "src" / "gui" / "main_window.py").read_text(encoding="utf-8")
        self.assertNotIn('QKeySequence("Alt+F4")', source)


if __name__ == "__main__":
    unittest.main()
