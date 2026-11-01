"""src/app.py baglantilari: baslangicta tek bozuk kayit tum kisayollari oldurmemeli (QApplication kurmadan)."""

from __future__ import annotations

import types
import unittest

import _support
from _support import capture_logs

from src.app import FlexiKeyApp
from src.utils.settings_manager import SettingsManager, format_settings_warning


class FakeHotkeyManager:
    def __init__(self):
        self.hotkeys, self.expansions, self.started = [], [], False

    def add_hotkey(self, shortcut, action_type, action_value, is_rich=False):
        self.hotkeys.append(shortcut)

    def add_expansion(self, trigger, replacement, is_rich=False):
        self.expansions.append(trigger)

    def start(self):
        self.started = True


class StartHotkeysIsolationTests(unittest.TestCase):
    def setUp(self):
        patcher, self.log_lines = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fake_app(self, settings):
        manager = FakeHotkeyManager()
        shown = []
        app = types.SimpleNamespace(
            settings_manager=types.SimpleNamespace(load_settings=lambda: settings),
            hotkey_manager=manager,
            _show_settings_warnings=lambda: shown.append(True),
        )
        return app, manager, shown

    def test_record_without_shortcut_does_not_stop_other_hotkeys(self):
        settings = {
            "hotkeys": [
                {"shortcut": "Ctrl+1", "action_type": "text", "action_value": "a"},
                {"action_type": "text", "action_value": "KeyError: shortcut yok"},
                {"shortcut": "Ctrl+2", "action_type": "text", "action_value": "b"},
            ],
            "expansions": [
                {"replacement": "trigger yok"},
                {"trigger": "mt", "replacement": "x"},
            ],
        }
        app, manager, shown = self._fake_app(settings)
        FlexiKeyApp._start_hotkeys(app)                 # eski kod burada KeyError ile olurdu
        self.assertEqual(manager.hotkeys, ["Ctrl+1", "Ctrl+2"])
        self.assertEqual(manager.expansions, ["mt"])
        self.assertTrue(manager.started)                # dinleyici yine de baslatildi
        self.assertEqual(shown, [True])
        self.assertTrue(any(level == "ERROR" for level, _ in self.log_lines))


class SettingsWarningTextTests(unittest.TestCase):
    def test_every_warning_kind_has_text_in_both_languages(self):
        details = {
            "corrupt_restored": r"C:\x\config.json.corrupt-1",
            "corrupt_defaults": r"C:\x\config.json.corrupt-1",
            "invalid_records": r"3|C:\x\config.json",
            "read_failed_backup": r"C:\x\config.json",
            "read_failed_defaults": r"C:\x\config.json",
        }
        for lang in ("tr", "en"):
            for kind, detail in details.items():
                text = format_settings_warning(kind, detail, lang)
                self.assertNotIn("settings_warn_", text, (lang, kind))
                self.assertIn(r"C:\x\config.json", text, (lang, kind))

    def test_unknown_kind_falls_back_to_detail(self):
        self.assertEqual(format_settings_warning("yeni_tur", "ayrinti", "tr"), "ayrinti")


if __name__ == "__main__":
    unittest.main()
