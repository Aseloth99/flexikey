"""Güncelleme penceresi artık yerel başlıklı değil: özel üst çubuklu `ChromeDialog`. Yalnızca ÇERÇEVE değişti; bu testler
çerçeveyle gelen davranışın (✕, Esc, yerleşim, tema) güncelleme akışının dayandığı davranışı bozmadığını doğrular:
indirme sürerken Esc/✕ = iptal, kurulumda kapanmaz, sinyaller ve durumlar aynı."""

from __future__ import annotations

import os
import pathlib
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

from src.gui import message_box
from src.gui.chrome_dialog import ChromeDialog
from src.gui.message_box import _CloseButton, _TitleBar
from src.gui.update_dialog import UpdateDialog

DARK = {"base": "#161616", "surface": "#1e1e1e", "surface2": "#262626", "border": "#2e2e2e", "text": "#f5f5f5",
        "text_muted": "#9c9c9c", "danger": "#ef4444", "warn": "#f59e0b", "hi": "#3c3c3c", "lo": "#0e0e0e",
        "accent": "#00ACC1", "accent2": "#00838F", "is_dark": True}
LIGHT = {**DARK, "base": "#e0e0e0", "surface": "#f5f5f5", "surface2": "#ececec", "border": "#c5c5c5", "text": "#1a1a1a",
         "text_muted": "#616161", "is_dark": False}


class ChromeUpdateDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_ = QApplication.instance() or QApplication([])

    def setUp(self):
        self.theme = {"p": DARK}
        message_box.configure(palette_provider=lambda: self.theme["p"], lang_provider=lambda: "tr")
        self.addCleanup(message_box.reset_configuration)
        self.signals = {"accepted": 0, "deferred": 0, "cancelled": 0}

    def make(self, lang="tr", mandatory=False, parent=None, show=True):
        dialog = UpdateDialog("1.2.3", "Yenilikler:\n- bir", mandatory, parent, lang, file_size=1234567, current_version="1.0.0")
        self.addCleanup(dialog.deleteLater)
        for name in self.signals:
            getattr(dialog, f"update_{name}").connect(lambda n=name: self.signals.__setitem__(n, self.signals[n] + 1))
        if show:
            dialog.show()
            self.addCleanup(dialog.hide)
        return dialog

    def esc(self, dialog):
        for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(dialog, QKeyEvent(kind, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))

    def x(self, dialog):
        dialog.findChild(_TitleBar).close_btn.click()

    # -- çerçeve ---------------------------------------------------------------------------------------------
    def test_it_is_a_frameless_chrome_dialog_with_a_custom_title_bar(self):
        dialog = self.make()
        self.assertIsInstance(dialog, ChromeDialog)
        self.assertTrue(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint, "yerel başlık çubuğu yok")
        bars = dialog.findChildren(_TitleBar)
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].height(), 38)
        self.assertEqual(dialog.windowTitle(), "Güncelleme Mevcut")
        self.assertIsNotNone(bars[0].findChild(_CloseButton))
        self.assertTrue(dialog.isModal())

    def test_content_lives_in_the_body_host_and_buttons_are_the_same(self):
        dialog = self.make()
        self.assertTrue(dialog.body_host.isAncestorOf(dialog.update_btn))
        self.assertTrue(dialog.body_host.isAncestorOf(dialog.notes_text))
        visible = [b.text() for b in dialog.findChildren(QPushButton) if b.isVisibleTo(dialog)]
        self.assertEqual(visible, ["Daha Sonra", "Şimdi Güncelle"])
        self.assertIs(dialog.retry_btn, dialog.update_btn)

    def test_minimum_content_width_is_520_and_default_size_560x460(self):
        dialog = self.make(show=False)
        self.assertEqual(dialog.minimumWidth(), 520)
        self.assertGreaterEqual(dialog.width(), 560)

    def test_show_places_the_dialog_inside_the_screen_and_over_a_visible_parent(self):
        parent = QWidget()
        parent.resize(600, 400)   # offscreen ekran 800x600: ortalanmış pencere ekran kenarına yaslanmasın
        parent.move(60, 60)
        parent.show()
        self.addCleanup(parent.close)
        dialog = self.make(parent=parent)
        avail = dialog.screen().availableGeometry()
        frame = dialog.frameGeometry()
        self.assertTrue(avail.contains(frame.topLeft()) and avail.contains(frame.bottomRight()), (avail, frame))
        center = parent.frameGeometry().center()
        self.assertLessEqual(abs(frame.center().x() - center.x()), 12)
        self.assertLessEqual(abs(frame.center().y() - center.y()), 12)

    def test_parentless_dialog_opens_on_screen(self):
        dialog = self.make()
        avail = dialog.screen().availableGeometry()
        self.assertTrue(avail.intersects(dialog.frameGeometry()))

    # -- Esc / ✕: güncelleme akışının dayandığı davranış ---------------------------------------------------------
    def test_idle_escape_and_x_defer_and_close(self):
        for close in (self.esc, self.x):
            self.signals.update(accepted=0, deferred=0, cancelled=0)
            dialog = self.make()
            close(dialog)
            self.assertFalse(dialog.isVisible())
            self.assertEqual(self.signals, {"accepted": 0, "deferred": 1, "cancelled": 0})

    def test_downloading_escape_and_x_cancel_the_download_and_close(self):
        for close in (self.esc, self.x):
            self.signals.update(accepted=0, deferred=0, cancelled=0)
            dialog = self.make()
            dialog.update_btn.click()
            self.assertEqual(dialog.state, UpdateDialog.DOWNLOADING)
            self.assertEqual(self.signals["accepted"], 1)
            close(dialog)
            self.assertFalse(dialog.isVisible())
            self.assertEqual((self.signals["cancelled"], self.signals["deferred"]), (1, 0))

    def test_installing_ignores_escape_and_x(self):
        dialog = self.make()
        dialog.show_installing()
        self.assertEqual(dialog.state, UpdateDialog.INSTALLING)
        self.esc(dialog)
        self.x(dialog)
        dialog.close()
        self.assertTrue(dialog.isVisible(), "kurulum başlayınca pencere kapanmaz")
        self.assertEqual(self.signals, {"accepted": 0, "deferred": 0, "cancelled": 0})
        self.assertEqual([b.text() for b in dialog.findChildren(QPushButton) if b.isVisibleTo(dialog)], [])

    def test_error_state_keeps_the_window_open_with_retry_and_closes_without_signals(self):
        dialog = self.make()
        dialog.update_btn.click()
        dialog.show_error("ağ koptu")
        self.assertEqual(dialog.state, UpdateDialog.ERROR)
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.retry_btn.text(), "Tekrar Dene")
        self.esc(dialog)
        self.assertFalse(dialog.isVisible())
        self.assertEqual((self.signals["cancelled"], self.signals["deferred"]), (0, 0))

    def test_mandatory_update_has_no_later_button_and_no_deferral(self):
        dialog = self.make(mandatory=True)
        self.assertFalse(dialog.later_btn.isVisibleTo(dialog))
        self.esc(dialog)
        self.assertEqual(self.signals["deferred"], 0)

    # -- tema ---------------------------------------------------------------------------------------------------
    def test_title_bar_follows_a_live_theme_change(self):
        dialog = self.make()
        self.assertTrue(dialog._pal["is_dark"])
        self.theme["p"] = LIGHT
        dialog._cd_refresh_palette()
        self.assertFalse(dialog._pal["is_dark"])
        self.assertEqual(dialog._pal["base"].lower(), "#e0e0e0")

    def test_the_frame_has_no_window_context_help_button_flag_left_to_remove(self):
        dialog = self.make(show=False)
        self.assertFalse(dialog.windowFlags() & Qt.WindowType.WindowContextHelpButtonHint)


class NoNativeTitleBarLeftTests(unittest.TestCase):
    def test_every_dialog_class_is_frameless_or_a_chrome_dialog(self):
        """Yerel başlık çubuklu QDialog kalmadı (işletim sistemi dosya seçicileri hariç)."""
        import ast

        src = pathlib.Path(__file__).resolve().parents[1] / "src"
        offenders = []
        for path in sorted(src.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
                if node.name == "FramelessResizableDialog":
                    continue        # yalnızca yeniden boyutlandırma yardımcısı; alt sınıfları bayrağı kendisi koyar
                if bases & {"QDialog", "FramelessResizableDialog"}:
                    body = ast.get_source_segment(text, node) or ""
                    if "FramelessWindowHint" not in body and not any(
                            isinstance(n, ast.Name) and n.id == "FramelessWindowHint" for n in ast.walk(node)):
                        # FramelessResizableDialog alt sınıfları (kısayol/genişletme) ana sınıftan alır; QDialog'dan doğrudan türeyenler denetlenir
                        offenders.append(f"{path.name}:{node.name}")
        # Doğrudan QDialog'dan türeyen ve Frameless bayrağını kendi gövdesinde koymayan sınıf listesi (bayrağı __init__'te
        # koyanlar zaten elenmiştir); kalan her sınıf ChromeDialog / _ChromeDialog / FramelessResizableDialog gibi bir
        # çerçeve tabanından türemeli.
        self.assertEqual(offenders, [], offenders)

    def test_update_dialog_no_longer_derives_from_the_native_qdialog(self):
        from PyQt6.QtWidgets import QDialog
        self.assertTrue(issubclass(UpdateDialog, ChromeDialog))
        self.assertIn(ChromeDialog, UpdateDialog.__mro__)
        self.assertIsNot(UpdateDialog.__bases__[0], QDialog)


if __name__ == "__main__":
    unittest.main()
