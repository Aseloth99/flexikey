"""Sistem komutu / eylem türü simgeleri: emoji yerine tek tarzda çizim. Emoji Windows sürümüne göre renkli, tek renk
glif ya da boş kutu çıkıyordu (🗕 🗔 🗖 Windows 10'da pencere düğmesi gibi görünüyordu, 🪟 hiç yoktu)."""

from __future__ import annotations

import os
import re
import tempfile
import unittest

import _support  # noqa: F401  (offscreen Qt, proje kökü sys.path'te)

from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from src.core.action_policy import KNOWN_COMMANDS
from src.gui import command_icons as ci

# Emoji ve resimli simge blokları (oklar, ✓ gibi düz işaretler hariç)
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿⏩-⏿️]")


def ink(name: str) -> int:
    """Simgenin 48 px'te boyadığı piksel sayısı (boş çizim yakalansın)."""
    img = QImage(48, 48, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    ci.draw_glyph(p, name, QRectF(0, 0, 48, 48), QColor("#ffffff"))
    p.end()
    return sum(1 for y in range(48) for x in range(48) if img.pixelColor(x, y).alpha() > 40)


class GlyphTableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_every_built_in_command_has_its_own_drawing(self):
        self.assertEqual(set(ci.COMMAND_GLYPHS), set(KNOWN_COMMANDS))
        used = set(ci.COMMAND_GLYPHS.values()) | set(ci.ACTION_GLYPHS.values()) | set(ci.GROUP_GLYPHS.values())
        self.assertFalse(used - set(ci.GLYPH_NAMES), "tabloda olup çizimi olmayan simge")

    def test_every_drawing_paints_something_inside_its_box(self):
        for name in ci.GLYPH_NAMES:
            with self.subTest(name):
                self.assertGreater(ink(name), 60)

    def test_unknown_command_falls_back_to_the_gear(self):
        self.assertEqual(ci.command_glyph("benim_komutum"), "gear")
        with self.assertRaises(ValueError):
            ci.glyph_pixmap("yok_boyle_simge", "#fff")

    def test_icon_follows_the_requested_colour(self):
        pix = ci.glyph_pixmap("power", "#ff0000", 16).toImage()
        colours = {pix.pixelColor(x, y).name() for y in range(pix.height()) for x in range(pix.width())
                   if pix.pixelColor(x, y).alpha() == 255}
        self.assertEqual(colours, {"#ff0000"})


class NoEmojiInTheUiTest(unittest.TestCase):
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

        cls.mw = mw
        cls.settings = SettingsManager()
        data = cls.settings.load_settings()
        data.update(theme="dark", language="tr", expansions=[
            {"trigger": "mrb", "replacement": "Merhaba", "enabled": True},
            {"trigger": "imza", "replacement": "<b>x</b>", "is_rich": True, "enabled": True},
        ], hotkeys=[
            {"shortcut": "Ctrl+Alt+1", "action_type": "command", "action_value": "tum_pencereleri_kucult", "enabled": True},
            {"shortcut": "Ctrl+Alt+2", "action_type": "command", "action_value": "pencereyi_buyut", "enabled": False},
            {"shortcut": "Ctrl+Alt+3", "action_type": "open_url", "action_value": "https://ornek.com", "enabled": True},
            {"shortcut": "Ctrl+Alt+4", "action_type": "command", "action_value": "benim_komutum", "enabled": True},
        ])
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

    def test_command_cards_show_a_drawing_and_plain_text(self):
        cards = self.window.hotkeys_list._cards
        minimize, maximize, url, custom = cards
        self.assertEqual(minimize.secondary_icon.glyph(), "window_minimize")
        self.assertEqual(minimize.primary_icon.glyph(), "gear")
        self.assertEqual(minimize._secondary_full, "Tüm Pencereleri Küçült")
        self.assertEqual(maximize.secondary_icon.glyph(), "window_maximize")
        self.assertEqual((url.primary_icon.glyph(), url.secondary_icon.glyph()), ("globe", ""))
        self.assertTrue(url.secondary_icon.isHidden(), "komut dışı kartta ikinci satır simgesiz")
        self.assertEqual((custom.secondary_icon.glyph(), custom._secondary_full), ("gear", "benim_komutum"))
        for card in cards:
            for text in (card._primary_full, card._secondary_full):
                self.assertIsNone(EMOJI.search(text), text)

    def test_expansion_cards_carry_their_kind_as_a_drawing(self):
        plain, rich = self.window.expansions_list._cards
        self.assertEqual(plain.primary_icon.glyph(), "type")
        self.assertEqual(rich.primary_icon.glyph(), "notepad")
        self.assertIsNone(EMOJI.search(plain._primary_full + rich._primary_full))

    def test_command_picker_lists_every_command_with_a_drawn_icon(self):
        dialog = self.mw.HotkeyDialog(self.window)
        try:
            self.assertEqual(set(dialog._matrix_buttons), set(KNOWN_COMMANDS), "seçilemeyen komut kalmasın")
            for value, (button, display) in dialog._matrix_buttons.items():
                self.assertFalse(button.icon().isNull(), value)
                self.assertIsNone(EMOJI.search(button.text()), button.text())
            for i in range(dialog.action_type.count()):
                self.assertFalse(dialog.action_type.itemIcon(i).isNull())
                self.assertIsNone(EMOJI.search(dialog.action_type.itemText(i)))
            expected = {self.mw.t(key, "tr"): glyph for key, glyph in ci.GROUP_GLYPHS.items()}
            seen = {}
            for header, _grid, _items in dialog._matrix_categories:
                icon, text = header.findChildren(QLabel)
                seen[text.text()] = icon.glyph()
            self.assertEqual(seen, expected)
        finally:
            dialog.deleteLater()

    def test_a_checked_command_turns_its_icon_to_the_accent(self):
        dialog = self.mw.HotkeyDialog(self.window)
        try:
            button: QPushButton = dialog._matrix_buttons["kilitle"][0]
            off = button.icon().pixmap(16, 16).toImage()
            button.setChecked(True)
            from PyQt6.QtGui import QIcon
            on = button.icon().pixmap(16, 16, QIcon.Mode.Normal, QIcon.State.On).toImage()
            self.assertNotEqual(off, on)
        finally:
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
