"""Güncellemeden sonraki açılış: --wait-pid, --show-window / --minimized, --updated bildirimi, başlangıç koruması
(startup_guard), sağlıklı sayma (confirm_healthy), `visible` hesabı ve temiz çıkış."""

from __future__ import annotations

import pathlib
import sys
import time
import unittest
from unittest import mock

import _support
from _support import capture_logs
from _update_support import TimerCapture, make_app

from src import app as app_module
from src.utils import self_update

ROOT = pathlib.Path(__file__).resolve().parents[1]


class WindowStateTests(unittest.TestCase):
    """load_settings: pencere açık mı gizli mi başlar."""

    def setUp(self):
        patcher, _ = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)

    def start(self, argv, start_minimized):
        app = make_app()
        app.settings_manager.load_settings.return_value = {"theme": "dark", "accent": "blue", "start_minimized": start_minimized}
        app.theme_manager = mock.Mock()
        with mock.patch.object(sys, "argv", ["FlexiKey.exe", *argv]):
            app.load_settings()
        return app.main_window

    def test_show_window_overrides_start_minimized_setting(self):
        window = self.start(["--wait-pid", "1", "--updated", "1.0.0", "--show-window"], start_minimized=True)
        window.show.assert_called_once()
        window.hide.assert_not_called()

    def test_minimized_flag_keeps_the_window_hidden(self):
        for setting in (True, False):
            window = self.start(["--wait-pid", "1", "--updated", "1.0.0", "--minimized"], start_minimized=setting)
            window.hide.assert_called_once()
            window.show.assert_not_called()

    def test_plain_start_follows_the_setting(self):
        self.start([], True).hide.assert_called_once()
        self.start([], False).show.assert_called_once()


class AnnounceUpdatedTests(unittest.TestCase):
    def setUp(self):
        patcher, self.log_lines = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)

    def announce(self, old, lang="tr"):
        app = make_app(lang=lang)
        app._updated_from = old
        app._announce_updated()
        return app.tray_manager.tray_icon.showMessage

    def test_balloon_names_the_new_version_in_both_languages(self):
        from src.utils.updater import UpdateChecker
        version = UpdateChecker.CURRENT_VERSION
        show = self.announce("0.9.0", "tr")
        show.assert_called_once()
        self.assertEqual(show.call_args.args[1], f"FlexiKey v{version} sürümüne güncellendi.")
        show = self.announce("0.9.0", "en")
        self.assertEqual(show.call_args.args[1], f"FlexiKey was updated to v{version}.")

    def test_no_balloon_without_the_updated_flag_or_for_the_same_version(self):
        from src.utils.updater import UpdateChecker
        self.announce(None).assert_not_called()
        self.announce(UpdateChecker.CURRENT_VERSION).assert_not_called()

    def test_flag_is_parsed_from_argv(self):
        self.assertEqual(self_update.updated_from(["FlexiKey.exe", "--wait-pid", "5", "--updated", "1.0.0", "--minimized"]), "1.0.0")
        self.assertIsNone(self_update.updated_from(["FlexiKey.exe", "--minimized"]))


class StartupGuardTests(unittest.TestCase):
    def setUp(self):
        patcher, self.log_lines = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)
        self.timer = TimerCapture(self)
        self.app = make_app()
        self.app._instance_lock = mock.Mock()
        self.app.app = mock.Mock()

    def run_guard(self, result, frozen=True):
        with mock.patch.object(app_module, "_is_frozen", return_value=frozen), \
             mock.patch.object(app_module, "_own_exe", return_value=r"C:\Uygulama\FlexiKey.exe"), \
             mock.patch.object(self_update, "startup_guard", return_value=result) as guard, \
             mock.patch.object(self_update, "spawn") as spawn:
            try:
                self.app._self_update_startup()
                exited = False
            except SystemExit as e:
                exited = e.code == 0
        return guard, spawn, exited

    def test_rolled_back_version_relaunches_the_previous_one_and_exits(self):
        guard, spawn, exited = self.run_guard(self_update.Guard.ROLLED_BACK)
        from src.utils.updater import UpdateChecker
        guard.assert_called_once_with(r"C:\Uygulama\FlexiKey.exe", UpdateChecker.CURRENT_VERSION)
        spawn.assert_called_once_with(r"C:\Uygulama\FlexiKey.exe", ["--minimized"])
        self.app._instance_lock.unlock.assert_called_once()   # geri gelen sürüm kilidi alabilsin
        self.assertTrue(exited)

    def test_probation_continues_and_schedules_the_health_check(self):
        guard, spawn, exited = self.run_guard(self_update.Guard.PROBATION)
        self.assertFalse(exited)
        spawn.assert_not_called()
        self.assertEqual(self.timer.delays(), [self_update.HEALTHY_AFTER_SECONDS * 1000])
        self.app.app.aboutToQuit.connect.assert_called_once()

    def test_normal_start_also_schedules_it(self):
        guard, spawn, exited = self.run_guard(self_update.Guard.NORMAL)
        self.assertEqual(self.timer.delays(), [self_update.HEALTHY_AFTER_SECONDS * 1000])

    def test_source_run_skips_the_guard_entirely(self):
        guard, spawn, exited = self.run_guard(self_update.Guard.ROLLED_BACK, frozen=False)
        guard.assert_not_called()
        self.assertFalse(exited)
        self.assertEqual(self.timer.delays(), [])

    def test_guard_runs_after_the_single_instance_lock_and_main_waits_before_everything(self):
        """İkinci başlatma kilitte takılıp çıkıyorsa 'açılış' sayılmamalı; wait-pid ise kilitten ÖNCE beklemeli."""
        source = (ROOT / "src" / "app.py").read_text(encoding="utf-8")
        init = source[source.index("def __init__"):source.index("def _lang")]
        self.assertLess(init.index("tryLock"), init.index("_self_update_startup()"))
        self.assertLess(init.index("_self_update_startup()"), init.index("QLocalServer()"))
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertLess(main.index("wait_for_previous_instance"), main.index("FlexiKeyApp()"))
        self.assertLess(main.index("wait_for_previous_instance"), main.index("time.sleep"))
        self.assertIn("not after_update", main, "güncelleme sonrası 2 sn başlangıç beklemesi atlanır")


class HealthyTests(unittest.TestCase):
    def setUp(self):
        patcher, _ = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)
        self.confirm = mock.patch.object(self_update, "confirm_healthy")
        self.confirm_mock = self.confirm.start()
        self.addCleanup(self.confirm.stop)
        for p in (mock.patch.object(app_module, "_is_frozen", return_value=True),
                  mock.patch.object(app_module, "_own_exe", return_value=r"C:\Uygulama\FlexiKey.exe")):
            p.start()
            self.addCleanup(p.stop)
        self.app = make_app()

    def test_timer_confirms_a_healthy_version(self):
        self.app._confirm_healthy()
        self.confirm_mock.assert_called_once_with(r"C:\Uygulama\FlexiKey.exe")

    def test_clean_exit_after_ten_seconds_confirms(self):
        self.app._started_at = time.monotonic() - 11
        self.app._on_about_to_quit()
        self.confirm_mock.assert_called_once()
        self.app.update_installer.cancel.assert_called_once()   # sürmekte olan indirme bırakılır

    def test_early_exit_does_not_confirm(self):
        self.app._started_at = time.monotonic() - 3
        self.app._on_about_to_quit()
        self.confirm_mock.assert_not_called()

    def test_the_process_that_updated_itself_never_confirms(self):
        """Kendini güncelleyip çıkan süreç, yeni sürümün 'deneme' yan dosyalarını (.old) silmemeli."""
        self.app._started_at = time.monotonic() - 600
        self.app._updating = True
        self.app._on_about_to_quit()
        self.app._confirm_healthy()
        self.confirm_mock.assert_not_called()

    def test_source_run_never_touches_side_files(self):
        with mock.patch.object(app_module, "_is_frozen", return_value=False):
            self.app._started_at = time.monotonic() - 600
            self.app._on_about_to_quit()
            self.app._confirm_healthy()
        self.confirm_mock.assert_not_called()


class VisibleAndCleanExitTests(unittest.TestCase):
    def setUp(self):
        patcher, _ = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_visible_means_shown_and_not_minimized(self):
        for shown, minimized, expected in ((True, False, True), (True, True, False), (False, False, False), (False, True, False)):
            app = make_app(visible=shown, minimized=minimized)
            self.assertIs(app._window_visible(), expected, (shown, minimized))

    def test_quit_for_update_uses_the_normal_exit_path_not_a_kill(self):
        app = make_app()
        app._quit_for_update()
        app.update_checker.stop.assert_called_once()
        app.main_window.close_app.assert_called_once()   # kısayol dinleyicisini durdurur + QApplication.quit()

    def test_quit_falls_back_to_qapplication_quit(self):
        app = make_app()
        app.main_window = object()
        with mock.patch.object(app_module.QApplication, "quit") as quit_:
            app._quit_for_update()
        quit_.assert_called_once()

    def test_install_complete_quits_and_marks_the_process_as_updating(self):
        app = make_app()
        app._quit_for_update = mock.Mock()
        app.update_dialog = mock.Mock()
        app._on_install_complete()
        app.update_dialog.show_restarting.assert_called_once()
        app._quit_for_update.assert_called_once()
        self.assertTrue(app._updating)


if __name__ == "__main__":
    unittest.main()
