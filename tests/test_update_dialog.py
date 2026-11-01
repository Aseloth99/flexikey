"""Güncelleme penceresi durumları: boşta -> indirme -> kurma -> hata -> tekrar dene; kapatınca iptal; açılır kutu yok."""

from __future__ import annotations

import os
import pathlib
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QWidget
from src.gui.message_box import MessageBox

from src.gui.update_dialog import UpdateDialog


def texts(dialog, cls=QLabel):
    return [w.text() for w in dialog.findChildren(cls) if w.isVisibleTo(dialog) and w.text()]


class DialogTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_ = QApplication.instance() or QApplication([])

    def setUp(self):
        for name in ("critical", "warning", "question", "information", "about"):
            patch = mock.patch.object(MessageBox, name, side_effect=AssertionError(f"MessageBox.{name} açılmamalı"))
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(MessageBox, "exec", side_effect=AssertionError("MessageBox açılmamalı"))
        patch.start()
        self.addCleanup(patch.stop)
        self.signals = {"accepted": 0, "deferred": 0, "cancelled": 0}

    def make(self, lang="tr", notes="Yenilikler:\n- bir", size=12_345_678, mandatory=False, show=True):
        dialog = UpdateDialog("1.2.3", notes, mandatory, None, lang, file_size=size, current_version="1.0.0")
        self.addCleanup(dialog.deleteLater)
        dialog.update_accepted.connect(lambda: self.signals.__setitem__("accepted", self.signals["accepted"] + 1))
        dialog.update_deferred.connect(lambda: self.signals.__setitem__("deferred", self.signals["deferred"] + 1))
        dialog.update_cancelled.connect(lambda: self.signals.__setitem__("cancelled", self.signals["cancelled"] + 1))
        if show:
            dialog.show()
            self.addCleanup(dialog.hide)   # kurulum durumundaki pencere close() ile kapanmaz: gizle (modal kalmasın)
        return dialog

    def press(self, dialog, key):
        for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(dialog, QKeyEvent(kind, key, Qt.KeyboardModifier.NoModifier))


class IdleStateTests(DialogTestCase):
    def test_shows_version_size_notes_and_two_buttons(self):
        dialog = self.make()
        shown = texts(dialog)
        self.assertIn("FlexiKey Sürüm 1.2.3 Mevcut!", shown)
        self.assertIn("Mevcut sürüm: 1.0.0 → Yeni sürüm: 1.2.3", shown)
        self.assertIn("İndirme boyutu: 11.77 MB", shown)
        self.assertEqual(dialog.notes_text.toPlainText().splitlines(), ["Yenilikler:", "- bir"])
        self.assertEqual(texts(dialog, QPushButton), ["Daha Sonra", "Şimdi Güncelle"])
        self.assertEqual(dialog.state, UpdateDialog.IDLE)
        self.assertFalse(dialog.progress_bar.isVisibleTo(dialog))
        self.assertFalse(dialog.error_label.isVisibleTo(dialog))

    def test_english_texts(self):
        dialog = self.make(lang="en")
        shown = texts(dialog)
        self.assertIn("Download size: 11.77 MB", shown)
        self.assertEqual(texts(dialog, QPushButton), ["Later", "Update Now"])

    def test_size_line_is_hidden_when_unknown_or_invalid(self):
        for size in (None, 0, -5, "junk"):
            with self.subTest(size=size):
                dialog = self.make(size=size)
                self.assertFalse(dialog.size_label.isVisibleTo(dialog))
                self.assertFalse(any("boyutu" in text for text in texts(dialog)))

    def test_huge_sizes_are_formatted(self):
        dialog = self.make(size=5_000_000_000)
        self.assertIn("İndirme boyutu: 4.66 GB", texts(dialog))

    def test_html_notes_are_rendered_and_empty_notes_fall_back(self):
        self.assertNotIn("<li>", self.make(notes="<ul><li>madde</li></ul>").notes_text.toPlainText())
        self.assertTrue(self.make(notes="").notes_text.toPlainText().strip())

    def test_mandatory_has_no_later_button_and_closing_is_not_a_deferral(self):
        dialog = self.make(mandatory=True)
        self.assertEqual(texts(dialog, QPushButton), ["Şimdi Güncelle"])
        dialog.reject()
        self.assertEqual(self.signals["deferred"], 0)

    def test_current_version_defaults_to_the_class_constant_without_a_checker(self):
        from src.utils.updater import UpdateChecker
        with mock.patch("src.utils.updater.UpdateChecker.__init__", side_effect=AssertionError("denetleyici açılmamalı")):
            dialog = UpdateDialog("2.0.0", "", False, None, "tr")
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.current_version, UpdateChecker.CURRENT_VERSION)


class DownloadStateTests(DialogTestCase):
    def test_update_click_starts_downloading_once(self):
        dialog = self.make()
        dialog.update_btn.click()
        self.assertEqual(self.signals["accepted"], 1)
        self.assertEqual(dialog.state, UpdateDialog.DOWNLOADING)
        self.assertTrue(dialog.progress_bar.isVisibleTo(dialog))
        self.assertEqual(dialog.progress_label.text(), "İndiriliyor…")
        self.assertEqual(texts(dialog, QPushButton), ["İptal"])
        dialog._on_update()                                   # ikinci tıklama (örn. çift tık)
        self.assertEqual(self.signals["accepted"], 1)

    def test_progress_shows_bytes_percent_and_speed(self):
        dialog = self.make()
        dialog.update_btn.click()
        dialog.update_download_progress(5_000_000, 10_000_000, 2.5)
        self.assertEqual(dialog.progress_bar.value(), 50)
        self.assertEqual(dialog.progress_label.text(), "4.77 MB / 9.54 MB (50%) - 2.50 MB/s")
        dialog.update_download_progress(1024, 0, 0.0)          # toplam bilinmiyor: belirsiz çubuk
        self.assertEqual(dialog.progress_bar.maximum(), 0)
        self.assertEqual(dialog.progress_label.text(), "1.00 KB indirildi")
        dialog.update_download_progress(5_000_000_000, 5_000_000_000, 1.0)   # 2 GB üstü: taşma yok
        self.assertEqual(dialog.progress_bar.value(), 100)

    def test_then_installing_has_no_buttons_and_a_busy_bar(self):
        dialog = self.make()
        dialog.update_btn.click()
        dialog.show_download_complete()
        self.assertEqual(dialog.progress_label.text(), "İndirme tamamlandı!")
        dialog.show_installing()
        self.assertEqual(dialog.state, UpdateDialog.INSTALLING)
        self.assertEqual(texts(dialog, QPushButton), [])
        self.assertEqual(dialog.progress_bar.maximum(), 0)
        self.assertIn("Kuruluyor", " ".join(texts(dialog)))
        dialog.show_restarting()
        self.assertIn("yeniden başlatılıyor", dialog.status_label.text())

    def test_attaching_to_a_running_background_download(self):
        dialog = self.make()
        dialog.show_downloading()
        dialog.update_download_progress(1_000_000, 2_000_000, 1.0)
        self.assertEqual(dialog.state, UpdateDialog.DOWNLOADING)
        self.assertEqual(dialog.progress_bar.value(), 50)


class ErrorStateTests(DialogTestCase):
    def test_error_is_inline_and_the_window_stays_open_with_retry(self):
        dialog = self.make()
        dialog.update_btn.click()
        dialog.show_error("sunucu yanıt vermedi")
        self.assertTrue(dialog.isVisible(), "pencere açık kalır")
        self.assertEqual(dialog.state, UpdateDialog.ERROR)
        self.assertTrue(dialog.error_label.isVisibleTo(dialog))
        self.assertEqual(dialog.error_label.text(), "Güncelleme tamamlanamadı: sunucu yanıt vermedi")
        self.assertEqual(texts(dialog, QPushButton), ["Daha Sonra", "Tekrar Dene"])
        self.assertFalse(dialog.progress_bar.isVisibleTo(dialog))

    def test_retry_runs_the_flow_again_and_hides_the_error(self):
        dialog = self.make()
        dialog.update_btn.click()
        dialog.show_error("x")
        dialog.retry_btn.click()
        self.assertEqual(self.signals["accepted"], 2)
        self.assertEqual(dialog.state, UpdateDialog.DOWNLOADING)
        self.assertFalse(dialog.error_label.isVisibleTo(dialog))
        dialog.show_error("yine")
        dialog.update_download_progress(0, 0, 0)
        self.assertTrue(dialog.error_label.isVisibleTo(dialog))

    def test_english_error_and_retry(self):
        dialog = self.make(lang="en")
        dialog.show_error("boom")
        self.assertEqual(dialog.error_label.text(), "The update could not be completed: boom")
        self.assertEqual(texts(dialog, QPushButton), ["Later", "Try Again"])

    def test_error_text_is_plain_not_markup(self):
        dialog = self.make()
        dialog.show_error("<urlopen error <b>x</b>>")
        self.assertEqual(dialog.error_label.textFormat(), Qt.TextFormat.PlainText)
        self.assertIn("<b>x</b>", dialog.error_label.text())

    def test_closing_after_an_error_is_neither_cancel_nor_deferral(self):
        dialog = self.make()
        dialog.update_btn.click()
        dialog.show_error("x")
        dialog.later_btn.click()
        self.assertFalse(dialog.isVisible())
        self.assertEqual((self.signals["cancelled"], self.signals["deferred"]), (0, 0))


class CloseBehaviourTests(DialogTestCase):
    def test_later_button_defers_exactly_once_and_closes(self):
        dialog = self.make()
        dialog.later_btn.click()
        self.assertFalse(dialog.isVisible())
        self.assertEqual((self.signals["deferred"], self.signals["cancelled"]), (1, 0))

    def test_escape_while_idle_defers(self):
        dialog = self.make()
        self.press(dialog, Qt.Key.Key_Escape)
        self.assertFalse(dialog.isVisible())
        self.assertEqual(self.signals["deferred"], 1)

    def test_closing_while_downloading_cancels_and_closes_without_asking(self):
        for how in ("escape", "x", "cancel_button"):
            with self.subTest(how=how):
                self.signals.update(accepted=0, deferred=0, cancelled=0)
                dialog = self.make()
                dialog.update_btn.click()
                if how == "escape":
                    self.press(dialog, Qt.Key.Key_Escape)
                elif how == "x":
                    dialog.close()
                else:
                    dialog.cancel_btn.click()
                self.assertFalse(dialog.isVisible())
                self.assertEqual((self.signals["cancelled"], self.signals["deferred"]), (1, 0))

    def test_closing_while_installing_is_ignored(self):
        dialog = self.make()
        dialog.update_btn.click()
        dialog.show_installing()
        self.press(dialog, Qt.Key.Key_Escape)
        dialog.close()
        dialog.reject()
        self.assertTrue(dialog.isVisible(), "kurulum geri alınamaz")
        self.assertEqual((self.signals["cancelled"], self.signals["deferred"]), (0, 0))

    def test_window_is_modal_and_has_no_help_button(self):
        dialog = self.make()
        self.assertTrue(dialog.isModal())
        self.assertFalse(dialog.windowFlags() & Qt.WindowType.WindowContextHelpButtonHint)

    def test_dialog_never_uses_a_message_box(self):
        dialog = self.make()
        dialog.update_btn.click()
        dialog.show_error("x")
        dialog.retry_btn.click()
        dialog.close()          # tüm bu yollarda MessageBox çağrısı AssertionError verirdi


class OpenFromAppTests(DialogTestCase):
    """Tepsi/başlık düğmesi -> FlexiKeyApp.show_pending_update: pencere açılır (doğrudan kurmaz), öne gelir, tekil kalır."""

    def setUp(self):
        super().setUp()
        from _support import capture_logs
        patcher, _ = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_app(self, visible=False):
        from _update_support import make_app, pending_info
        app = make_app(pending=pending_info(size=9_000_000))

        class Window(QWidget):
            lang = "tr"

        window = Window()
        if visible:
            window.show()
        self.addCleanup(window.hide)
        app.main_window = window
        return app

    def open(self, app):
        app.show_pending_update()
        dialog = app.update_dialog
        self.addCleanup(lambda: dialog.hide() if dialog is not None else None)
        return dialog

    def test_hidden_main_window_opens_an_ownerless_dialog_and_raises_it(self):
        app = self.make_app(visible=False)
        with mock.patch.object(UpdateDialog, "raise_") as raise_, mock.patch.object(UpdateDialog, "activateWindow") as activate:
            dialog = self.open(app)
        self.assertIsNotNone(dialog)
        self.assertIsNone(dialog.parent(), "ana pencere gizliyken sahipsiz: görev çubuğunda kendi düğmesi olur")
        self.assertTrue(dialog.isVisible())
        raise_.assert_called_once()
        activate.assert_called_once()
        self.assertIn("İndirme boyutu: 8.58 MB", texts(dialog))
        app.update_installer.download_update.assert_not_called()     # açmak kurmaz/indirmez

    def test_visible_main_window_owns_the_dialog(self):
        app = self.make_app(visible=True)
        dialog = self.open(app)
        self.assertIs(dialog.parent(), app.main_window)

    def test_second_request_reuses_the_open_dialog(self):
        app = self.make_app()
        first = self.open(app)
        with mock.patch.object(UpdateDialog, "raise_") as raise_:
            app.show_pending_update()
        self.assertIs(app.update_dialog, first)
        raise_.assert_called_once()

    def test_nothing_without_a_pending_update(self):
        app = self.make_app()
        app._pending_update = None
        app.show_pending_update()
        self.assertIsNone(app.update_dialog)

    def test_closing_clears_the_reference_and_remembers_the_deferral(self):
        app = self.make_app()
        dialog = self.open(app)
        dialog.later_btn.click()
        QApplication.processEvents()
        self.assertIsNone(app.update_dialog)
        app.settings_manager.update.assert_called_with(declined_update_version="1.1.0")
        app.tray_manager.set_update_available.assert_called_with("1.1.0")   # tepsi satırı beklemeye devam eder

    def test_opening_during_a_silent_download_attaches_to_it(self):
        from _update_support import PendingJob
        app = self.make_app()
        app.download_thread = PendingJob(None)
        app._last_progress = (2_000_000, 4_000_000, 1.5)
        dialog = self.open(app)
        self.assertEqual(dialog.state, UpdateDialog.DOWNLOADING)
        self.assertEqual(dialog.progress_bar.value(), 50)
        dialog.close()                                           # kapatınca indirme iptal
        app.update_installer.cancel.assert_called_once()
        self.assertIsNone(app.download_thread)

    def test_opening_during_an_install_shows_the_installing_state(self):
        from _update_support import PendingJob
        app = self.make_app()
        app.install_thread = PendingJob(None)
        dialog = self.open(app)
        self.assertEqual(dialog.state, UpdateDialog.INSTALLING)

    def test_update_button_with_a_ready_package_installs_without_downloading_again(self):
        app = self.make_app()
        app._ready_package = {"version": "1.1.0", "path": __file__}
        app._start_installation = mock.Mock()
        with mock.patch("src.app.QTimer") as qtimer:
            dialog = self.open(app)
            dialog.update_btn.click()
            qtimer.singleShot.assert_called_once()
            qtimer.singleShot.call_args.args[1]()
        app.update_installer.download_update.assert_not_called()
        app._start_installation.assert_called_once()


if __name__ == "__main__":
    unittest.main()
