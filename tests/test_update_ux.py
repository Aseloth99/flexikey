"""Güncelleme deneyimi: pop-up yok; başlık çubuğunda "Güncelle · vX" düğmesi; kullanılmıyorken otomatik kurulum."""

from __future__ import annotations

import os
import pathlib
import sys
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication, QPushButton
from src.gui.message_box import MessageBox

import _support  # noqa: F401
from _support import capture_logs
from _update_support import PendingJob, make_app, pending_info

from src import app as app_module
from src.app import FlexiKeyApp
from src.gui import main_window as mw


class IdleRuleTest(unittest.TestCase):
    def test_truth_table(self):
        idle = FlexiKeyApp.update_is_idle
        self.assertFalse(idle(True, False, 9999), "pencere ekrandayken (öndeyse de arkadaysa da) kurulmaz")
        self.assertFalse(idle(False, True, 9999), "açık bir diyalog varken kurulmaz")
        self.assertFalse(idle(False, False, 30), "son kısayol kullanımı yeniyse kurulmaz")
        self.assertTrue(idle(False, False, 300), "pencere gizli + uzun süredir kullanılmıyor -> uygun")
        self.assertTrue(idle(False, False, float("inf")), "hiç kısayol kullanılmadıysa uygun")


class OnUpdateAvailableTest(unittest.TestCase):
    def setUp(self):
        patcher, _ = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)

    def _app(self):
        app = make_app()
        app._schedule_auto_update = mock.Mock()
        app._start_silent_update = mock.Mock()
        return app

    def test_optional_update_shows_button_and_never_a_dialog(self):
        app = self._app()
        with mock.patch("src.gui.update_dialog.UpdateDialog", side_effect=AssertionError("pop-up açılmamalı")):
            app._on_update_available("1.0.1", "https://x", "notlar", False, 100, "ab")
        app.main_window.set_update_available.assert_called_once_with("1.0.1")
        app.tray_manager.set_update_available.assert_called_once_with("1.0.1")
        app._schedule_auto_update.assert_called_once()
        app._start_silent_update.assert_not_called()    # isteğe bağlı güncelleme kullanıcı/otomatik ayar olmadan kurulmaz
        self.assertEqual(app._pending_update["version"], "1.0.1")

    def test_mandatory_update_installs_in_background_without_dialog(self):
        app = self._app()
        app._on_update_available("2.0.0", "https://x", "", True, 100, "ab")
        app._start_silent_update.assert_called_once()
        app._schedule_auto_update.assert_not_called()


class AutoUpdateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_ = QApplication.instance() or QApplication([])

    def setUp(self):
        patcher, _ = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)
        patch = mock.patch.object(app_module, "_is_frozen", return_value=True)
        patch.start()
        self.addCleanup(patch.stop)

    def _fake(self, *, enabled, idle, pending=True):
        app = make_app(pending=pending_info(checksum="a" * 64) if pending else None)
        app._auto_update_enabled = lambda: enabled
        app._is_idle_for_update = lambda: idle
        app._start_silent_update = mock.Mock()
        app._start_installation = mock.Mock()
        return app

    def test_installs_only_when_enabled_idle_and_pending(self):
        for enabled, idle, pending, expect in (
            (True, True, True, True),
            (False, True, True, False),
            (True, False, True, False),
            (True, True, False, False),
        ):
            app = self._fake(enabled=enabled, idle=idle, pending=pending)
            app._try_auto_update()
            self.assertEqual(app._start_silent_update.called, expect, (enabled, idle, pending))

    def test_update_without_a_checksum_is_never_installed_automatically(self):
        for checksum in ("", None, "abc", "zz" * 32):
            app = self._fake(enabled=True, idle=True)
            app._pending_update["checksum"] = checksum
            app._try_auto_update()
            app._start_silent_update.assert_not_called()
        app = self._fake(enabled=True, idle=True)
        app._pending_update["checksum"] = "sha256:" + "B" * 64
        app._try_auto_update()
        app._start_silent_update.assert_called_once()

    def test_a_declined_version_is_not_installed_automatically_but_a_newer_one_is(self):
        app = self._fake(enabled=True, idle=True)
        app.settings_manager.load_settings.return_value = {"declined_update_version": "1.1.0"}
        app._auto_update_timer = mock.Mock()
        app._try_auto_update()
        app._start_silent_update.assert_not_called()
        app._auto_update_timer.stop.assert_called_once()
        app = self._fake(enabled=True, idle=True)
        app.settings_manager.load_settings.return_value = {"declined_update_version": "1.0.9"}
        app._try_auto_update()
        app._start_silent_update.assert_called_once()

    def test_a_mandatory_update_ignores_the_declined_version(self):
        app = self._fake(enabled=True, idle=True)
        app._pending_update["is_mandatory"] = True
        app.settings_manager.load_settings.return_value = {"declined_update_version": "1.1.0"}
        app._try_auto_update()
        app._start_silent_update.assert_called_once()

    def test_cancelling_a_download_counts_as_not_now(self):
        app = self._fake(enabled=True, idle=True)
        app._cancel_update_download()
        app.settings_manager.update.assert_called_with(declined_update_version="1.1.0")

    def test_does_not_start_a_second_download(self):
        app = self._fake(enabled=True, idle=True)
        app.download_thread = PendingJob(None)
        app._try_auto_update()
        app._start_silent_update.assert_not_called()

    def test_not_while_the_update_window_is_open(self):
        app = self._fake(enabled=True, idle=True)
        app.update_dialog = mock.Mock()
        app._try_auto_update()
        app._start_silent_update.assert_not_called()

    def test_source_run_never_auto_installs(self):
        with mock.patch.object(app_module, "_is_frozen", return_value=False):
            app = self._fake(enabled=True, idle=True)
            app._auto_update_timer = mock.Mock()
            app._try_auto_update()
        app._start_silent_update.assert_not_called()
        app._auto_update_timer.stop.assert_called_once()

    def test_a_ready_package_is_installed_when_idle_again_without_downloading_twice(self):
        app = self._fake(enabled=True, idle=True)
        app._ready_package = {"version": "1.1.0", "path": __file__}   # var olan bir dosya
        app._pending_update["checksum"] = ""                         # hazir paket icin sağlama toplamı sarti aranmaz
        app._try_auto_update()
        app._start_installation.assert_called_once()
        app._start_silent_update.assert_not_called()

    def test_scheduler_does_nothing_when_auto_install_is_off(self):
        app = make_app()
        app._auto_update_enabled = lambda: False
        app._schedule_auto_update()
        self.assertIsNone(app._auto_update_timer)

    def test_scheduler_polls_until_idle(self):
        app = make_app()
        app._auto_update_enabled = lambda: True
        with mock.patch.object(app_module, "QTimer") as qtimer:
            qtimer.return_value.isActive.return_value = False
            app._schedule_auto_update()
            qtimer.return_value.start.assert_called_once_with(FlexiKeyApp.AUTO_UPDATE_POLL_MS)
            qtimer.singleShot.assert_called_once()


class SystemInputCountsAsActivityTest(unittest.TestCase):
    """Genişletme/sessiz komut/medya tuşu action_executed yaymaz: sistemdeki son girdi de kullanım sayılır."""

    @classmethod
    def setUpClass(cls):
        cls.app_ = QApplication.instance() or QApplication([])

    def _idle(self, system_idle, dialog=None):
        app = types.SimpleNamespace(
            main_window=types.SimpleNamespace(last_activity=0.0, isVisible=lambda: False, isMinimized=lambda: False),
            update_is_idle=FlexiKeyApp.update_is_idle, IDLE_SECONDS=FlexiKeyApp.IDLE_SECONDS,
            _system_idle_seconds=FlexiKeyApp._system_idle_seconds, update_dialog=dialog,
        )
        with mock.patch.object(sys, "platform", "win32"), \
             mock.patch("src.core.win_input.system_idle_seconds", return_value=system_idle):
            return FlexiKeyApp._is_idle_for_update(app)

    def test_recent_system_input_blocks_auto_install(self):
        self.assertFalse(self._idle(5.0), "kısayol hiç kullanılmamış olsa da kullanıcı az önce yazıyordu")
        self.assertFalse(self._idle(0.0), "son girdi okunamadı: meşgul say")
        self.assertTrue(self._idle(600.0))

    def test_an_open_update_window_is_never_idle(self):
        self.assertFalse(self._idle(600.0, dialog=object()))


class BackgroundInstallNoticeTest(unittest.TestCase):
    def _notify(self, mandatory, lang):
        app = make_app(lang=lang, pending={"version": "1.0.1", "is_mandatory": mandatory})
        with mock.patch("src.app.log_info"):
            app._notify_mandatory_install()
        return app.tray_manager.tray_icon.showMessage.call_args.args[1]

    def test_optional_auto_install_is_not_announced_as_mandatory(self):
        from src.utils.locales import t

        for lang in ("tr", "en"):
            self.assertEqual(self._notify(False, lang), t("update_auto_installing", lang))
            self.assertEqual(self._notify(True, lang), t("update_mandatory_installing", lang))
        self.assertNotIn("Zorunlu", self._notify(False, "tr"))
        self.assertNotIn("mandatory", self._notify(False, "en"))


class SilentFailureTest(unittest.TestCase):
    def setUp(self):
        patcher, _ = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_background_download_failure_has_no_modal(self):
        app = make_app(pending=pending_info())
        with mock.patch.object(MessageBox, "critical", side_effect=AssertionError("modal açılmamalı")), \
             mock.patch.object(MessageBox, "warning", side_effect=AssertionError("modal açılmamalı")):
            app._on_download_failed("ağ koptu")
        app.tray_manager.tray_icon.showMessage.assert_called_once()
        self.assertIsNotNone(app._pending_update, "düğme/tepsi satırı yeniden denemek için durur")

    def test_failure_with_the_window_open_is_inline_and_keeps_the_window(self):
        app = make_app(pending=pending_info())
        app.update_dialog = mock.Mock()
        with mock.patch.object(MessageBox, "critical", side_effect=AssertionError("modal açılmamalı")):
            app._on_download_failed("ağ koptu")
            app._on_install_failed("kurulamadı")
        self.assertEqual([c.args for c in app.update_dialog.show_error.call_args_list], [("ağ koptu",), ("kurulamadı",)])
        app.update_dialog.reject.assert_not_called()
        app.update_dialog.close.assert_not_called()
        app.tray_manager.tray_icon.showMessage.assert_not_called()


class SettingsUpdateButtonTest(unittest.TestCase):
    """Bekleyen güncelleme başlık çubuğunda değil (menüyü sıkıştırıyordu), Ayarlar > Güncellemeler'de "↑ Güncelle · vX"
    düğmesiyle gösterilir (PulseTray'deki gibi)."""

    @classmethod
    def setUpClass(cls):
        cls.app_ = QApplication.instance() or QApplication([])

    def _fake_dialog(self, lang="tr"):
        from PyQt6.QtWidgets import QLabel

        dialog = types.SimpleNamespace(lang=lang, update_open_btn=QPushButton(), update_status=QLabel("Güncel"))
        dialog.show_pending_update = lambda v: mw.SettingsDialog.show_pending_update(dialog, v)
        return dialog

    def test_the_title_bar_has_no_update_button(self):
        source = (pathlib.Path(mw.__file__)).read_text(encoding="utf-8")
        self.assertNotIn("update_pill = QPushButton", source)
        self.assertNotIn("_apply_update_pill", source)

    def test_the_button_replaces_the_status_while_an_update_waits(self):
        dialog = self._fake_dialog()
        dialog.show_pending_update("1.2.3")
        self.assertFalse(dialog.update_open_btn.isHidden())
        self.assertTrue(dialog.update_status.isHidden())
        self.assertEqual(dialog.update_open_btn.text(), "↑  Güncelle · v1.2.3")
        dialog.show_pending_update("")
        self.assertTrue(dialog.update_open_btn.isHidden())
        self.assertFalse(dialog.update_status.isHidden())

    def test_the_button_text_follows_the_language(self):
        dialog = self._fake_dialog("en")
        dialog.show_pending_update("1.2.3")
        self.assertEqual(dialog.update_open_btn.text(), "↑  Update · v1.2.3")

    def test_a_new_version_reaches_an_open_settings_dialog(self):
        dialog = self._fake_dialog()
        window = types.SimpleNamespace(update_version="", findChildren=lambda cls: [dialog])
        mw.MainWindow.set_update_available(window, "1.2.3")
        self.assertEqual(window.update_version, "1.2.3")
        self.assertFalse(dialog.update_open_btn.isHidden())

    def test_the_button_closes_settings_then_opens_the_update_window(self):
        calls = []
        window = types.SimpleNamespace(show_pending_update=lambda: calls.append("open"))
        dialog = types.SimpleNamespace(parent_window=window, reject=lambda: calls.append("close"))
        with mock.patch.object(mw.QTimer, "singleShot", side_effect=lambda ms, fn: fn()):
            mw.SettingsDialog._open_pending_update(dialog)
        self.assertEqual(calls, ["close", "open"])


class CheckerHasNoPopupsTest(unittest.TestCase):
    def test_manual_check_results_never_open_message_boxes(self):
        from src.utils.updater import UpdateChecker

        with mock.patch.object(MessageBox, "information", side_effect=AssertionError("pop-up")), \
             mock.patch.object(MessageBox, "warning", side_effect=AssertionError("pop-up")):
            UpdateChecker._show_info(object(), "başlık", "metin")
            UpdateChecker._show_warning(object(), "başlık", "metin")


class DefaultsTest(unittest.TestCase):
    def test_auto_install_is_on_by_default(self):
        from src.utils.settings_manager import DEFAULT_SETTINGS

        self.assertIs(DEFAULT_SETTINGS["auto_update_install"], True)


class LocaleTest(unittest.TestCase):
    NEW_KEYS = ("tray_update_now", "update_size_line", "update_failed_inline", "update_retry", "update_installed_toast",
                "update_source_run", "update_err_not_writable", "update_err_checksum_download", "update_err_http")

    def test_new_strings_exist_in_both_languages(self):
        from src.utils.locales import t

        for lang in ("tr", "en"):
            for key in ("update_pill", "update_pill_tip", "auto_update_install",
                        "auto_update_tip", "update_auto_failed", "check_updates") + self.NEW_KEYS:
                self.assertNotEqual(t(key, lang), key, (lang, key))
        self.assertEqual(t("check_updates", "tr"), "Kontrol Et")   # her kelime büyük harf (Title Case)

    def test_spec_texts(self):
        from src.utils.locales import t

        self.assertEqual(t("tray_update_now", "tr").format(version="1.2.3"), "Güncelle · v1.2.3")
        self.assertEqual(t("tray_update_now", "en").format(version="1.2.3"), "Update · v1.2.3")
        self.assertEqual(t("update_size_line", "tr").format(size="9 MB"), "İndirme boyutu: 9 MB")
        self.assertEqual(t("update_size_line", "en").format(size="9 MB"), "Download size: 9 MB")
        self.assertEqual(t("update_failed_inline", "tr").format(error="x"), "Güncelleme tamamlanamadı: x")
        self.assertEqual(t("update_failed_inline", "en").format(error="x"), "The update could not be completed: x")
        self.assertEqual(t("update_installed_toast", "tr").format(app="FlexiKey", version="1.2.3"), "FlexiKey v1.2.3 sürümüne güncellendi.")
        self.assertEqual(t("update_installed_toast", "en").format(app="FlexiKey", version="1.2.3"), "FlexiKey was updated to v1.2.3.")
        self.assertEqual((t("update_retry", "tr"), t("update_retry", "en")), ("Tekrar Dene", "Try Again"))

    def test_package_error_codes_all_have_texts_in_both_languages(self):
        from src.utils.locales import t

        for code in ("read", "not_package", "too_big", "no_exe", "bad_zip", "write", "not_pe", "arch", "not_writable",
                     "swap", "swap2", "spawn"):
            for lang in ("tr", "en"):
                self.assertNotEqual(t(f"update_err_{code}", lang), f"update_err_{code}", (lang, code))

    def test_old_popup_texts_are_gone(self):
        from src.utils.locales import LOCALES

        for lang in LOCALES:
            for key in ("tray_update_available", "update_cancel_confirm", "download_failed_net", "install_failed_admin"):
                self.assertNotIn(key, LOCALES[lang])


if __name__ == "__main__":
    unittest.main()
