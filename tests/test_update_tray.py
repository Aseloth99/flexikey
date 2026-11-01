"""Tepsi menüsü: "Güncelle · vX" en üstte (altında ayırıcı), kalın, simgeli; yalnızca güncelleme bekliyorsa görünür;
menü yeniden kurulsa / dil değişse de durum korunur; tıklayınca güncelleme penceresini açtırır (doğrudan kurmaz)."""

from __future__ import annotations

import os
import pathlib
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication, QWidget

from src.gui.tray_manager import TrayManager


class FakeSettings:
    def __init__(self, lang="tr"):
        self.lang = lang

    def load_settings(self):
        return {"language": self.lang, "theme": "system"}


class FakeWindow(QWidget):
    """TrayManager'ın ana pencereden beklediği küçük yüzey."""

    def __init__(self, lang="tr"):
        super().__init__()
        self.settings_manager = FakeSettings(lang)
        self.pending_requests = 0

    def show_settings(self):
        pass

    def show_pending_update(self):
        self.pending_requests += 1

    def close_app(self):
        pass


class TrayUpdateRowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_ = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = FakeWindow()
        self.addCleanup(self.window.deleteLater)
        self.tray = TrayManager(self.window, mock.Mock(), mock.Mock())
        self.addCleanup(self.tray.tray_icon.hide)

    def visible_texts(self):
        return [("-" if a.isSeparator() else a.text()) for a in self.tray.menu.actions() if a.isVisible()]

    def test_hidden_without_a_pending_update(self):
        self.assertFalse(self.tray.update_action.isVisible())
        self.assertFalse(self.tray.update_separator.isVisible())
        self.assertNotEqual(self.visible_texts()[0], "-")
        self.assertEqual(self.visible_texts()[0], "Göster")

    def test_row_is_first_in_the_menu_with_a_separator_below(self):
        self.tray.set_update_available("1.2.3")
        actions = self.tray.menu.actions()
        self.assertIs(actions[0], self.tray.update_action, "menünün EN ÜSTÜNDE")
        self.assertTrue(actions[1].isSeparator() and actions[1].isVisible(), "altında ayırıcı")
        self.assertEqual(self.visible_texts()[:3], ["Güncelle · v1.2.3", "-", "Göster"])

    def test_row_is_bold_and_has_an_icon(self):
        self.tray.set_update_available("1.2.3")
        self.assertTrue(self.tray.update_action.font().bold())
        self.assertFalse(self.tray.update_action.icon().isNull())

    def test_old_bottom_row_is_gone(self):
        self.tray.set_update_available("1.2.3")
        self.assertFalse(any("Güncelleme mevcut" in text for text in self.visible_texts()))
        self.assertEqual(sum(1 for a in self.tray.menu.actions() if "ncelle" in a.text()), 1)

    def test_english_text(self):
        window = FakeWindow("en")
        self.addCleanup(window.deleteLater)
        tray = TrayManager(window, mock.Mock(), mock.Mock())
        self.addCleanup(tray.tray_icon.hide)
        tray.set_update_available("1.2.3")
        self.assertEqual(tray.update_action.text(), "Update · v1.2.3")

    def test_clearing_hides_row_and_separator_again(self):
        self.tray.set_update_available("1.2.3")
        self.tray.set_update_available("")
        self.assertFalse(self.tray.update_action.isVisible())
        self.assertFalse(self.tray.update_separator.isVisible())

    def test_state_survives_the_menu_being_rebuilt(self):
        """Eski hata: menü yeniden kurulunca satır gizli kalıyordu."""
        self.tray.set_update_available("1.2.3")
        old_action = self.tray.update_action
        self.tray.create_menu()
        self.assertIsNot(self.tray.update_action, old_action)
        self.assertTrue(self.tray.update_action.isVisible())
        self.assertTrue(self.tray.update_separator.isVisible())
        self.assertEqual(self.tray.update_action.text(), "Güncelle · v1.2.3")
        self.assertIs(self.tray.menu.actions()[0], self.tray.update_action)
        self.assertTrue(self.tray.update_action.font().bold())

    def test_version_set_before_the_menu_exists_is_shown_when_it_is_built(self):
        window = FakeWindow()
        self.addCleanup(window.deleteLater)
        with mock.patch.object(TrayManager, "create_menu", lambda self: None):
            tray = TrayManager(window, mock.Mock(), mock.Mock())
        self.addCleanup(tray.tray_icon.hide)
        tray.set_update_available("2.0.0")          # menü henüz yok: durum yalnızca saklanır
        TrayManager.create_menu(tray)
        self.assertTrue(tray.update_action.isVisible())
        self.assertEqual(tray.update_action.text(), "Güncelle · v2.0.0")

    def test_language_change_retranslates_the_row_and_keeps_it_visible(self):
        self.tray.set_update_available("1.2.3")
        self.window.settings_manager.lang = "en"
        self.tray.retranslate("en")
        self.assertEqual(self.tray.update_action.text(), "Update · v1.2.3")
        self.assertTrue(self.tray.update_action.isVisible())
        self.tray.retranslate("tr")
        self.assertEqual(self.tray.update_action.text(), "Güncelle · v1.2.3")

    def test_retranslate_does_not_show_the_row_without_an_update(self):
        self.tray.retranslate("en")
        self.assertFalse(self.tray.update_action.isVisible())

    def test_click_opens_the_update_window_and_does_nothing_else(self):
        self.tray.set_update_available("1.2.3")
        self.tray.update_action.trigger()
        self.assertEqual(self.window.pending_requests, 1, "güncelleme penceresi istenir; doğrudan kurulum yok")

    def test_source_has_no_direct_install_from_the_tray(self):
        text = (pathlib.Path(__file__).resolve().parents[1] / "src" / "gui" / "tray_manager.py").read_text(encoding="utf-8")
        for banned in ("install_update", "download_update", "update_installer"):
            self.assertNotIn(banned, text)


if __name__ == "__main__":
    unittest.main()
