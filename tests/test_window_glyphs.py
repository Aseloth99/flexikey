"""Başlık çubuğu: büyüt/geri yükle düğmesi pencere durumunu (her yoldan gelen değişimde) gösterir, vektör glif çizilir;
güncelleme beklerken simge durumuna küçült düğmesinin solunda metinsiz ↑ simge düğmesi çıkar."""

from __future__ import annotations

import pathlib
import unittest
from unittest import mock

import _support  # noqa: F401  (offscreen Qt, proje kökü sys.path'te)

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication

from src.gui import chrome_dialog
from src.gui import main_window as mw
from src.gui import message_box
from src.gui import window_glyphs as wg
from src.gui.chrome_dialog import ChromeDialog, _MaxButton
from src.gui.notification_manager import NotificationManager
from src.utils import locales
from src.utils.settings_manager import SettingsManager
from src.utils.theme_manager import ORDERED_ACCENT_KEYS, ThemeManager, _build_palette

from test_consistency import _TempProfile


def _render(glyph: str, scale: int = 2) -> QImage:
    """Glifi 32 ızgarasında `scale` kat büyüklükte saydam zemine beyaz çizer."""
    size = int(wg.GRID) * scale
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    wg.paint_glyph(painter, QRectF(0, 0, size, size), glyph, QColor("#ffffff"), box=size)
    painter.end()
    return image


def _ink(image: QImage, x: float, y: float, scale: int = 2) -> int:
    """32 ızgarasındaki (x, y) noktasının örtücülüğü (alfa)."""
    return image.pixelColor(int(x * scale), int(y * scale)).alpha()


def _luminance(hex_color: str) -> float:
    def channel(c: float) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    color = QColor(hex_color)
    return 0.2126 * channel(color.red()) + 0.7152 * channel(color.green()) + 0.0722 * channel(color.blue())


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class GlyphDrawingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_ = QApplication.instance() or QApplication([])

    def test_maximize_is_one_outlined_square(self):
        image = _render(wg.MAXIMIZE)
        self.assertGreater(_ink(image, 8.5, 16), 128)    # sol kenar
        self.assertGreater(_ink(image, 23.5, 16), 128)   # sağ kenar
        self.assertGreater(_ink(image, 16, 8.5), 128)    # üst kenar
        self.assertEqual(_ink(image, 16, 16), 0)         # içi boş (fırça yok)

    def test_restore_back_square_does_not_show_through_the_front_square(self):
        image = _render(wg.RESTORE)
        self.assertGreater(_ink(image, 8, 18), 128)      # ön kare sol kenar
        self.assertGreater(_ink(image, 14, 24), 128)     # ön kare alt kenar
        self.assertGreater(_ink(image, 18, 7.5), 128)    # arka kare üst kenar
        self.assertGreater(_ink(image, 24, 14), 128)     # arka kare sağ kenar
        self.assertGreater(_ink(image, 11.5, 9.5), 128)  # arka kare sol kenarı, ön karenin üstünde kalan parça
        # arka karenin ön karenin içinde kalan kenarları çizilmez (çizgiler kesişmez)
        self.assertEqual(_ink(image, 11.5, 17), 0)
        self.assertEqual(_ink(image, 15, 20), 0)

    def test_update_arrow_has_a_stem_and_a_head(self):
        image = _render(wg.UPDATE)
        self.assertGreater(_ink(image, 16, 20), 128)
        self.assertGreater(_ink(image, 16, 10), 128)
        self.assertGreater(_ink(image, 12, 13), 128)
        self.assertGreater(_ink(image, 20, 13), 128)
        self.assertEqual(_ink(image, 10, 22), 0)

    def test_update_arrow_accent_reads_on_both_title_bars(self):
        # Başlık zemini `surface`; ↑ her vurgu ve temada en az 3:1 karşıtlıkta, okunabildiği yerde vurgunun kendi tonu
        for is_dark in (True, False):
            for accent in ORDERED_ACCENT_KEYS:
                pal = _build_palette(is_dark, accent)
                ink = wg.readable_accent(pal).name()
                self.assertGreaterEqual(_contrast(ink, pal["surface"]), 3.0, (is_dark, accent, ink))
                if _contrast(pal["accent_text"], pal["surface"]) >= 3.0:
                    self.assertEqual(ink, QColor(pal["accent_text"]).name(), (is_dark, accent))


class MainTitleBarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_ = QApplication.instance() or QApplication([])
        cls._profile = _TempProfile()
        cls._profile.__enter__()
        from src.core.hotkey_manager import HotkeyManager
        cls.settings = SettingsManager()
        cls.settings._seed_file = None
        data = cls.settings.load_settings()
        data.update(theme="dark", language="tr", hotkeys=[], expansions=[])
        cls.settings.save_settings(data)
        cls.window = mw.MainWindow(cls.settings, ThemeManager(cls.app_), HotkeyManager(), NotificationManager(), None)
        cls.window.show()
        cls.app_.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.window.hide()
        cls.window.deleteLater()
        cls.app_.processEvents()
        cls._profile.__exit__(None, None, None)

    def setUp(self):
        self.addCleanup(message_box.reset_configuration)
        self.addCleanup(locales.set_preferred_language, locales.get_preferred_language())
        self.window.lang = "tr"
        self.window.showNormal()
        self.window.set_update_available("")
        self.app_.processEvents()

    def tearDown(self):
        self.window.showNormal()
        self.window.set_update_available("")
        self.window.lang = "tr"
        self.app_.processEvents()

    # -- büyüt / geri yükle -------------------------------------------------------------------------------------
    def test_glyph_follows_window_state_changes_that_bypass_the_toggle(self):
        button = self.window.maximize_btn
        self.assertEqual((button.text(), button.glyph()), ("", wg.MAXIMIZE))
        with mock.patch.object(self.window, "toggle_maximize", side_effect=AssertionError("toggle")):
            self.window.showMaximized()                    # Win+↑ / Aero Snap / görev çubuğu gibi dışarıdan
            self.assertEqual(button.glyph(), wg.RESTORE)
            self.window.setWindowState(Qt.WindowState.WindowNoState)
            self.assertEqual(button.glyph(), wg.MAXIMIZE)

    def test_title_bar_double_click_and_button_switch_the_glyph(self):
        button = self.window.maximize_btn
        button.click()
        self.assertEqual(button.glyph(), wg.RESTORE)
        button.click()
        self.assertEqual(button.glyph(), wg.MAXIMIZE)

    def test_tooltip_follows_state_and_language(self):
        button = self.window.maximize_btn
        self.assertEqual(button.toolTip(), "Ekranı Kapla")
        self.window.showMaximized()
        self.assertEqual(button.toolTip(), "Geri Yükle")
        self.window.lang = "en"
        self.window._retranslate_ui()
        self.assertEqual(button.toolTip(), "Restore Down")
        self.window.showNormal()
        self.assertEqual(button.toolTip(), "Maximize")
        self.window.lang = "tr"
        self.window._retranslate_ui()
        self.assertEqual(button.toolTip(), "Ekranı Kapla")

    def test_maximize_glyph_uses_the_neighbouring_ink(self):
        pal = self.window.theme_manager.get_palette()
        self.assertEqual(self.window.maximize_btn.ink().name(), QColor(pal["text_muted"]).name())

    # -- ↑ güncelleme simgesi -----------------------------------------------------------------------------------
    def test_update_button_is_hidden_without_a_pending_update(self):
        self.assertTrue(self.window.update_btn.isHidden())

    def test_update_button_sits_left_of_minimize_with_the_same_size_and_no_text(self):
        self.window.set_update_available("1.2.3")
        self.app_.processEvents()
        up, minimize = self.window.update_btn, self.window.minimize_btn
        self.assertFalse(up.isHidden())
        self.assertEqual(up.text(), "")
        self.assertEqual(up.glyph(), wg.UPDATE)
        self.assertEqual(up.size(), minimize.size())
        self.assertEqual(up.size(), self.window.maximize_btn.size())
        layout = minimize.parentWidget().layout()
        controls = [layout.itemAt(i).layout() for i in range(layout.count()) if layout.itemAt(i).layout()]
        order = [controls[-1].itemAt(i).widget() for i in range(controls[-1].count())]
        self.assertEqual(order, [up, minimize, self.window.maximize_btn, self.window.close_btn])
        self.assertLess(up.geometry().right(), minimize.geometry().left())
        self.assertEqual(up.geometry().center().y(), minimize.geometry().center().y())

    def test_update_button_tooltip_name_and_accent(self):
        self.window.set_update_available("1.2.3")
        up = self.window.update_btn
        self.assertEqual(up.toolTip(), "Yeni sürüm v1.2.3 hazır; ayrıntılar ve kurulum için tıklayın")
        self.assertEqual(up.accessibleName(), "Güncelle")
        self.assertEqual(up.ink().name(), wg.readable_accent(self.window.theme_manager.get_palette()).name())
        self.window.lang = "en"
        self.window._retranslate_ui()
        self.assertEqual(up.toolTip(), "Version v1.2.3 is ready; click for details and installation")
        self.assertEqual(up.accessibleName(), "Update")

    def test_update_button_opens_the_same_update_window_without_installing(self):
        self.window.set_update_available("1.2.3")
        requested = []
        self.window.update_requested.connect(lambda: requested.append(1))
        with mock.patch.object(type(self.window), "show_pending_update",
                               autospec=True, side_effect=mw.MainWindow.show_pending_update) as opened:
            self.window.update_btn.click()
        opened.assert_called_once()
        self.assertEqual(requested, [1])

    def test_update_button_hides_again_when_no_update_waits(self):
        self.window.set_update_available("1.2.3")
        self.window.set_update_available("")
        self.assertTrue(self.window.update_btn.isHidden())


class ChromeDialogMaxButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_ = QApplication.instance() or QApplication([])

    def setUp(self):
        self.addCleanup(message_box.reset_configuration)

    def test_dialog_max_button_draws_vector_glyphs_and_follows_state(self):
        dialog = ChromeDialog(resizable=True)
        dialog.resize(400, 300)
        dialog.show()
        self.addCleanup(dialog.hide)
        button = dialog.findChild(_MaxButton)
        self.assertEqual(button.glyph(), wg.MAXIMIZE)
        dialog.showMaximized()
        self.assertEqual(button.glyph(), wg.RESTORE)
        dialog.showNormal()
        self.assertEqual(button.glyph(), wg.MAXIMIZE)
        button.set_maximized(True)
        self.assertTrue(button.is_maximized())
        self.assertEqual(button.glyph(), wg.RESTORE)

    def test_dialog_max_button_paints_through_paint_glyph(self):
        button = _MaxButton(message_box.current_palette())
        glyphs = []   # yalnızca glif adı tutulur (ressam nesnesini saklamak, çizim bittikten sonra çökmeye yol açar)
        with mock.patch("src.gui.chrome_dialog.paint_glyph", new=lambda _p, _r, glyph, _c: glyphs.append(glyph)):
            button.grab()
            button.set_maximized(True)
            button.grab()
        self.assertEqual(glyphs, [wg.MAXIMIZE, wg.RESTORE])
        button.set_maximized(False)
        image = button.grab().toImage()
        corner = image.pixelColor(0, 0)
        row = image.height() // 2
        self.assertTrue(any(image.pixelColor(x, row) != corner for x in range(image.width())))  # glif çizildi
        source = pathlib.Path(chrome_dialog.__file__).read_text(encoding="utf-8")
        self.assertNotIn("drawText", source)  # metin glifi ("□"/"❐") değil
        self.assertNotIn('"❐"', source)


if __name__ == "__main__":
    unittest.main()
