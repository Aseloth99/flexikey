"""Başlık çubuğundaki İLK menü "Dosya" olmamalı: içinde dosya işlemi yok (Yeni Kısayol, Yeni Genişletme, Çıkış).
"Uygulama" / "App" adıyla ve klavye simgesiyle gösterilir (başlıkta zaten "FlexiKey" yazıyor); dil değişince de doğru kalır."""

from __future__ import annotations

import os
import tempfile
import unittest

import _support  # noqa: F401  (offscreen Qt, proje kökü sys.path'te)

from PyQt6.QtWidgets import QApplication


class AppMenuTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls._saved = {k: os.environ.get(k) for k in ("APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME")}
        for key in cls._saved:
            os.environ[key] = cls._tmp.name
        cls.app = QApplication.instance() or QApplication([])
        from src.core.hotkey_manager import HotkeyManager
        from src.gui import main_window as mw
        from src.gui.notification_manager import NotificationManager
        from src.utils.settings_manager import SettingsManager
        from src.utils.theme_manager import ThemeManager

        cls.settings = SettingsManager()
        data = cls.settings.load_settings()
        data.update(theme="dark", language="tr", hotkeys=[], expansions=[])
        cls.settings.save_settings(data)
        cls.window = mw.MainWindow(cls.settings, ThemeManager(cls.app), HotkeyManager(), NotificationManager(), None)
        cls.window.show()
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls.window.deleteLater()
        cls.app.processEvents()
        for key, value in cls._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls._tmp.cleanup()

    def test_the_first_menu_is_the_app_menu_not_file(self):
        for lang, expected in (("tr", "Uygulama"), ("en", "App")):
            self.window.apply_language(lang)
            self.app.processEvents()
            text = self.window.file_menu_btn.text()
            self.assertEqual(text, expected, lang)
            self.assertNotIn(text.lower(), ("dosya", "file"))
            self.assertFalse(self.window.file_menu_btn.icon().isNull())

    def test_the_menu_holds_the_app_level_actions_only(self):
        labels = [a.text() for a in self.window.file_menu.actions() if not a.isSeparator()]
        self.assertEqual(len(labels), 3, labels)
        self.assertIs(self.window.file_menu.actions()[0], self.window.new_hotkey_action)
        self.assertEqual(self.window.exit_action.shortcut().toString(), "Ctrl+Q")

    def test_no_translation_still_calls_it_file(self):
        from src.utils.locales import LOCALES
        for lang, table in LOCALES.items():
            self.assertNotIn("menu_file", table, lang)
            self.assertNotIn(table["menu_app"].lower(), ("dosya", "file"), lang)


if __name__ == "__main__":
    unittest.main()
