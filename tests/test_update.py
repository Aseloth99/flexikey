"""Guncelleme akisi: URL/host dogrulama, sha256, indirme (iptal dahil), paket sezgisi, zorunlu guncellemenin kurulumu.

Ag taklit edilir (_open_url mock'lanir); kurulum GERCEK self_update koduyla gecici klasorde yapilir, yeni surumun
baslatilmasi (spawn) mock'lanir.
"""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

import _support
from _support import capture_logs
from _update_support import PendingJob, SyncJob, TimerCapture, make_app, pending_info

from src import app as app_module
from src.utils import self_update, update_installer
from src.utils import updater
from src.utils.update_installer import UpdateInstaller, normalize_sha256, update_package_path
from src.utils.updater import validate_download_url

TRUSTED = "macik.com.tr"
PAYLOAD = b"PK\x03\x04 sahte guncelleme icerigi " * 100
PAYLOAD_SHA = hashlib.sha256(PAYLOAD).hexdigest()
GOOD_URL = "https://macik.com.tr/downloads/FlexiKey_1.1.0.zip"
EXTENSIONLESS_URL = "https://macik.com.tr/Pages/AppDownload?slug=flexikey&file=FlexiKey"


class ValidateUrlTests(unittest.TestCase):
    def test_accepts_https_on_trusted_host_and_subdomains(self):
        for url in (GOOD_URL, "https://cdn.macik.com.tr/x.zip", "HTTPS://MACIK.COM.TR/x.zip", EXTENSIONLESS_URL):
            self.assertEqual(validate_download_url(url, TRUSTED), url)

    def test_rejects_insecure_or_foreign_urls(self):
        bad = [
            "http://macik.com.tr/x.zip",                    # https degil
            "ftp://macik.com.tr/x.zip",
            "file:///C:/Windows/System32/calc.exe",
            "https://evil.example/x.zip",                   # guvenilmeyen host
            "https://evilmacik.com.tr/x.zip",               # sonek taklidi
            "https://macik.com.tr.evil.example/x.zip",      # onek taklidi
            "https://user:pass@macik.com.tr/x.zip",         # kimlik bilgisi
            "https://macik.com.tr@evil.example/x.zip",      # userinfo ile host gizleme
            "https:///x.zip",                               # host yok
            "", "   ", "macik.com.tr/x.zip",
        ]
        for url in bad:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_download_url(url, TRUSTED)

    def test_loopback_http_allowed_for_development_only(self):
        self.assertTrue(validate_download_url("http://127.0.0.1:8000/x.zip", TRUSTED))
        self.assertTrue(validate_download_url("http://localhost/x.zip", TRUSTED))
        with self.assertRaises(ValueError):
            validate_download_url("http://localhost.evil.example/x.zip", TRUSTED)

    def test_trusted_host_comes_from_update_api(self):
        self.assertEqual(updater.trusted_update_host(), TRUSTED)


class HelperTests(unittest.TestCase):
    def test_normalize_sha256(self):
        self.assertEqual(normalize_sha256(PAYLOAD_SHA.upper()), PAYLOAD_SHA)
        self.assertEqual(normalize_sha256(" sha256:" + PAYLOAD_SHA + " "), PAYLOAD_SHA)
        for bad in ("", "abc", "md5:" + "a" * 32, "g" * 64, PAYLOAD_SHA[:-1]):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    normalize_sha256(bad)

    def test_package_path_is_fixed_and_ignores_url_names(self):
        # Paket turu uzantidan/URL'den degil icerikten anlasilir: dosya adi hep ayni .pkg
        self.assertEqual(update_package_path("C:\\Temp"), os.path.join("C:\\Temp", "FlexiKey_Update.pkg"))
        self.assertFalse(hasattr(update_installer, "safe_update_filename"))

    def test_as_helpers_are_robust(self):
        self.assertIs(updater.as_bool("false"), False)
        self.assertIs(updater.as_bool("False"), False)
        self.assertIs(updater.as_bool("true"), True)
        self.assertIs(updater.as_bool(1), True)
        self.assertIs(updater.as_bool(None), False)
        self.assertIs(updater.as_bool(0), False)
        self.assertEqual(updater.as_size("1234"), 1234)
        self.assertEqual(updater.as_size(1234.9), 1234)
        self.assertEqual(updater.as_size("5000000000"), 5_000_000_000)
        self.assertEqual(updater.as_size("1.5e6"), 1_500_000)
        for junk in (None, "", "abc", -5, "-1", float("nan"), float("inf"), True, [], {}):
            with self.subTest(junk=junk):
                self.assertEqual(updater.as_size(junk), 0)


class FakeResponse(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))} if headers is None else headers
        self.on_read = None

    def read(self, n=-1):
        if self.on_read is not None:
            self.on_read()
        return super().read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class InstallerTestCase(unittest.TestCase):
    def setUp(self):
        patcher, self.log_lines = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name

        self.response = lambda: FakeResponse(PAYLOAD)
        self.open_url = mock.Mock(side_effect=lambda *a, **k: self.response())
        patch = mock.patch.object(update_installer, "_open_url", self.open_url)
        patch.start()
        self.addCleanup(patch.stop)

        self.installer = UpdateInstaller()
        self.installer.temp_dir = self.tmp
        self.installer.language = lambda: "tr"
        self.completed, self.failed, self.install_failed, self.started, self.progress = [], [], [], [], []
        self.installer.download_complete.connect(self.completed.append)
        self.installer.download_failed.connect(self.failed.append)
        self.installer.install_failed.connect(self.install_failed.append)
        self.installer.install_started.connect(lambda: self.started.append(True))
        self.installer.download_progress.connect(lambda *a: self.progress.append(a))

    def leftovers(self):
        return sorted(os.listdir(self.tmp))


class DownloadTests(InstallerTestCase):
    def test_insecure_or_foreign_url_is_rejected_before_any_network_access(self):
        for url in ("http://macik.com.tr/x.zip", "https://evil.example/x.zip", "file:///C:/x.zip"):
            with self.subTest(url=url):
                self.assertFalse(self.installer.download_update(url, None, PAYLOAD_SHA))
        self.open_url.assert_not_called()
        self.assertEqual(len(self.failed), 3)
        self.assertEqual(self.completed, [])
        self.assertTrue(all(m.startswith("Güvenli olmayan indirme adresi") for m in self.failed))

    def test_matching_checksum_completes(self):
        self.assertTrue(self.installer.download_update(GOOD_URL, len(PAYLOAD), "sha256:" + PAYLOAD_SHA.upper()))
        self.assertEqual(self.completed, [os.path.join(self.tmp, "FlexiKey_Update.pkg")])
        self.assertEqual(self.failed, [])
        self.assertEqual(self.leftovers(), ["FlexiKey_Update.pkg"], "kismi (.part) dosya kalmaz")

    def test_extensionless_url_downloads_to_the_pkg_name(self):
        self.assertTrue(self.installer.download_update(EXTENSIONLESS_URL, None, PAYLOAD_SHA))
        self.assertEqual(self.completed, [os.path.join(self.tmp, "FlexiKey_Update.pkg")])
        self.assertEqual(self.open_url.call_args.args[0].full_url.split("?")[0], "https://macik.com.tr/Pages/AppDownload")

    def test_checksum_mismatch_deletes_file_and_fails(self):
        wrong = hashlib.sha256(b"baska icerik").hexdigest()
        self.assertFalse(self.installer.download_update(GOOD_URL, len(PAYLOAD), wrong))
        self.assertEqual(self.completed, [])
        self.assertEqual(self.leftovers(), [])
        self.assertTrue(any("sağlama toplamı" in m for m in self.failed))

    def test_malformed_server_checksum_rejects_update_instead_of_skipping(self):
        self.assertFalse(self.installer.download_update(GOOD_URL, len(PAYLOAD), "md5:abcdef"))
        self.open_url.assert_not_called()
        self.assertEqual(self.completed, [])

    def test_no_checksum_from_server_still_downloads_but_is_logged(self):
        self.assertTrue(self.installer.download_update(GOOD_URL, len(PAYLOAD), None))
        self.assertTrue(any(level == "WARNING" and "sağlama toplamı" in msg for level, msg in self.log_lines))

    def test_html_error_page_with_200_is_rejected_by_content(self):
        self.response = lambda: FakeResponse(b"<html>404 bulunamadi</html>")
        self.assertFalse(self.installer.download_update(GOOD_URL, None, None))
        self.assertEqual(self.completed, [])
        self.assertEqual(self.leftovers(), [])
        self.assertIn("exe ya da zip değil", self.failed[0])

    def test_http_and_network_errors_are_localized(self):
        self.open_url.side_effect = urllib.error.HTTPError(GOOD_URL, 404, "Not Found", {}, None)
        self.installer.download_update(GOOD_URL, None, None)
        self.installer.language = lambda: "en"
        self.installer.download_update(GOOD_URL, None, None)
        self.assertEqual(self.failed, ["Sunucu hata döndürdü (HTTP 404).", "The server returned an error (HTTP 404)."])
        self.failed.clear()
        self.open_url.side_effect = urllib.error.URLError("getaddrinfo failed")
        self.installer.download_update(GOOD_URL, None, None)
        self.assertEqual(self.failed, ["Could not reach the server: getaddrinfo failed"])
        self.assertEqual(self.leftovers(), [])

    def test_truncated_download_fails_cleanly(self):
        data = PAYLOAD

        class Cut(FakeResponse):
            def read(self, n=-1):
                chunk = super().read(n)
                if not chunk:
                    raise OSError("baglanti kesildi")
                return chunk

        self.response = lambda: Cut(data[:1000])
        self.assertFalse(self.installer.download_update(GOOD_URL, len(data), PAYLOAD_SHA))
        self.assertEqual(self.completed, [])
        self.assertEqual(self.leftovers(), [])
        self.assertIn("baglanti kesildi", self.failed[0])

    def test_huge_or_odd_file_sizes_do_not_overflow_the_progress_signal(self):
        self.response = lambda: FakeResponse(PAYLOAD, headers={})     # Content-Length yok: bildirilen boyut kullanilir
        for size in (5_000_000_000, "5000000000", 123.0, "junk", None, -7):
            with self.subTest(size=size):
                self.progress.clear()
                self.assertTrue(self.installer.download_update(GOOD_URL, size, PAYLOAD_SHA))
                total = self.progress[0][1]
                self.assertEqual(total, updater.as_size(size))

    def test_cancel_stops_silently_and_leaves_nothing(self):
        response = FakeResponse(PAYLOAD * 50, headers={})
        response.on_read = self.installer.cancel
        self.response = lambda: response
        self.assertFalse(self.installer.download_update(GOOD_URL, None, None))
        self.assertEqual(self.completed, [])
        self.assertEqual(self.failed, [], "iptal hata sayilmaz")
        self.assertEqual(self.leftovers(), [])

    def test_a_new_download_after_cancel_is_independent_of_the_old_one(self):
        old = FakeResponse(PAYLOAD * 50, headers={})
        old.on_read = self.installer.cancel
        self.response = lambda: old
        self.installer.download_update(GOOD_URL, None, None)
        self.response = lambda: FakeResponse(PAYLOAD)
        self.assertTrue(self.installer.download_update(GOOD_URL, None, PAYLOAD_SHA))
        self.assertEqual(len(self.completed), 1)

    def test_oversized_package_is_refused_while_downloading(self):
        with mock.patch.object(self_update, "MAX_EXE_BYTES", 500):
            self.assertFalse(self.installer.download_update(GOOD_URL, None, None))
        self.assertEqual(self.leftovers(), [])
        self.assertIn("izin verilen boyuttan büyük", self.failed[0])


class PreflightTests(InstallerTestCase):
    def test_source_run_is_not_supported_inline(self):
        with mock.patch.object(update_installer, "is_frozen", return_value=False):
            self.assertIn("Kaynak koddan", self.installer.preflight_error())
            self.installer.language = lambda: "en"
            self.assertIn("running from source", self.installer.preflight_error())

    def test_unwritable_folder_is_reported_before_downloading(self):
        exe = os.path.join(self.tmp, "yok", "klasor", "FlexiKey.exe")
        message = self.installer.preflight_error(exe)
        self.assertIn(os.path.join(self.tmp, "yok", "klasor"), message)
        self.assertIn("taşıyıp", message)
        self.installer.language = lambda: "en"
        self.assertIn("Move FlexiKey to a writable folder", self.installer.preflight_error(exe))

    def test_writable_folder_passes(self):
        self.assertIsNone(self.installer.preflight_error(os.path.join(self.tmp, "FlexiKey.exe")))


class MandatoryUpdateFlowTests(unittest.TestCase):
    """Zorunlu/arka plan guncelleme: indirme -> kurulum -> temiz cikis zinciri (QApplication/ag olmadan)."""

    def setUp(self):
        patcher, self.log_lines = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)
        self.timer = TimerCapture(self)
        SyncJob.started.clear()
        patch = mock.patch.object(app_module, "BackgroundJob", SyncJob)
        patch.start()
        self.addCleanup(patch.stop)
        self.app = make_app(pending=pending_info(mandatory=True))
        self.app._quit_for_update = mock.Mock()
        self.app._ready_package = {"version": "1.1.0", "path": r"C:\Temp\FlexiKey_Update.pkg"}

    def test_mandatory_update_downloads_without_dialog(self):
        app = make_app()
        app.main_window = mock.Mock()
        with mock.patch("src.gui.update_dialog.UpdateDialog", side_effect=AssertionError("zorunlu guncelleme icin diyalog acilmamali")):
            app._on_update_available("1.1.0", GOOD_URL, "notlar", True, 123, PAYLOAD_SHA)
        self.assertIsNone(app.update_dialog)
        app.update_installer.download_update.assert_called_once_with(GOOD_URL, 123, PAYLOAD_SHA)
        app.main_window.set_update_available.assert_called_once_with("1.1.0")
        app.tray_manager.set_update_available.assert_called_once_with("1.1.0")

    def test_download_complete_without_dialog_installs_in_background_and_notifies(self):
        self.app._on_download_complete(r"C:\Temp\FlexiKey_Update.pkg")
        self.assertEqual(self.timer.delays(), [0], "diyalog yokken gecikmesiz")
        self.timer.fire()
        self.app.update_installer.install_update.assert_called_once()
        args, kwargs = self.app.update_installer.install_update.call_args
        self.assertEqual(args, (r"C:\Temp\FlexiKey_Update.pkg",))
        self.assertEqual(kwargs["visible"], False)
        self.assertEqual(kwargs["old_version"], "1.0.0")
        self.app.tray_manager.tray_icon.showMessage.assert_called_once()

    def test_install_complete_quits_cleanly_and_marks_updating(self):
        self.app._on_install_complete()
        self.app._quit_for_update.assert_called_once()
        self.assertTrue(self.app._updating)
        self.assertIsNone(self.app._ready_package)

    def test_failed_installation_does_not_quit_and_keeps_the_update_pending(self):
        self.app._on_install_failed("kurulamadi")
        self.app._quit_for_update.assert_not_called()
        self.assertFalse(self.app._updating)
        self.assertIsNotNone(self.app._pending_update, "dugme/tepsi satiri calisir kalir")
        self.app.tray_manager.tray_icon.showMessage.assert_called_once()   # diyalog yok: tepsi balonu

    def test_dialog_flow_shows_installing_state_and_no_balloon(self):
        self.app.update_dialog = mock.Mock()
        self.app._on_download_complete(r"C:\Temp\FlexiKey_Update.pkg")
        self.app.update_dialog.show_download_complete.assert_called_once()
        self.assertEqual(self.timer.delays(), [self.app.INSTALL_DELAY_MS])
        self.timer.fire()
        self.app.update_dialog.show_installing.assert_called_once()
        self.app.tray_manager.tray_icon.showMessage.assert_not_called()
        self.app.update_installer.install_update.assert_called_once()

    def test_visible_main_window_is_restored_by_the_new_version(self):
        for visible, minimized, expected in ((True, False, True), (True, True, False), (False, False, False)):
            with self.subTest(visible=visible, minimized=minimized):
                app = make_app(visible=visible, minimized=minimized, pending=pending_info(mandatory=True))
                app._ready_package = {"version": "1.1.0", "path": "x"}
                app._start_installation()
                self.assertIs(app.update_installer.install_update.call_args.kwargs["visible"], expected)

    def test_cancelled_download_is_not_installed(self):
        self.app._cancel_update_download()
        self.app._on_download_complete(r"C:\Temp\FlexiKey_Update.pkg")
        self.timer.fire()
        self.app.update_installer.install_update.assert_not_called()
        self.app.update_installer.cancel.assert_called_once()

    def test_a_second_download_is_not_started_while_one_runs(self):
        self.app.download_thread = PendingJob(None)
        self.app._start_update_download("1.1.0", GOOD_URL, 1, PAYLOAD_SHA)
        self.app.update_installer.download_update.assert_not_called()
        self.assertEqual(SyncJob.started, [])

    def test_cancelled_download_thread_no_longer_blocks_a_new_download(self):
        self.app.download_thread = PendingJob(None)
        self.app._cancel_update_download()
        self.assertIsNone(self.app.download_thread)
        self.app._start_update_download("1.1.0", GOOD_URL, 1, PAYLOAD_SHA)
        self.app.update_installer.download_update.assert_called_once()

    def test_preflight_problem_is_inline_with_a_dialog_and_never_downloads(self):
        self.app.update_installer.preflight_error.return_value = "klasor yazilamiyor"
        self.app.update_dialog = mock.Mock()
        self.app._start_update_download("1.1.0", GOOD_URL, 1, PAYLOAD_SHA)
        self.app.update_dialog.show_error.assert_called_once_with("klasor yazilamiyor")
        self.app.update_installer.download_update.assert_not_called()

    def test_preflight_problem_without_dialog_is_a_balloon(self):
        self.app.update_installer.preflight_error.return_value = "klasor yazilamiyor"
        self.app._start_update_download("1.1.0", GOOD_URL, 1, PAYLOAD_SHA)
        self.app.tray_manager.tray_icon.showMessage.assert_called_once()
        self.app.update_installer.download_update.assert_not_called()

    def test_install_is_deferred_when_the_user_came_back_but_not_for_mandatory(self):
        optional = make_app(pending=pending_info(mandatory=False))
        optional._ready_package = {"version": "1.1.0", "path": "x"}
        optional._is_idle_for_update = lambda: False
        optional._schedule_auto_update = mock.Mock()
        optional._start_installation()
        optional.update_installer.install_update.assert_not_called()
        optional._schedule_auto_update.assert_called_once()
        self.assertIsNotNone(optional._ready_package, "paket hazir bekler")

        self.app._is_idle_for_update = lambda: False
        self.app._start_installation()
        self.app.update_installer.install_update.assert_called_once()

    def test_ready_package_of_an_older_version_is_discarded_when_a_newer_one_is_offered(self):
        app = make_app(pending=pending_info("1.1.0"))
        app._ready_package = {"version": "1.1.0", "path": "x"}
        app._schedule_auto_update = mock.Mock()
        app._on_update_available("1.2.0", GOOD_URL, "", False, 1, PAYLOAD_SHA)
        self.assertIsNone(app._ready_package)
        app.update_installer.discard_package.assert_called_once()


class CheckerTestCase(unittest.TestCase):
    def setUp(self):
        patcher, self.log_lines = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)
        self.stamps = []

        class FakeSettings:
            def load_settings(inner):
                return {"language": "tr"}

            def update(inner, **kwargs):
                self.stamps.append(kwargs)

        patch = mock.patch.object(updater, "SettingsManager", FakeSettings)
        patch.start()
        self.addCleanup(patch.stop)
        self.checker = updater.UpdateChecker()
        self.offered, self.completed, self.failed_signals = [], [], []
        self.checker.update_available.connect(lambda *a: self.offered.append(a))
        self.checker.check_complete.connect(self.completed.append)
        self.checker.check_failed.connect(lambda: self.failed_signals.append(True))

    def result(self, url=GOOD_URL, **over):
        data = {"updateAvailable": True, "version": "9.9.9", "download_url": url,
                "release_notes": "", "isMandatory": True, "fileSize": 1, "checksum": PAYLOAD_SHA}
        data.update(over)
        return data


class CheckerRejectsBadUrlTests(CheckerTestCase):
    def test_update_with_untrusted_download_url_is_not_offered(self):
        for url in ("http://macik.com.tr/x.zip", "https://evil.example/x.zip"):
            with self.subTest(url=url):
                self.checker._on_worker_result(self.result(url))
        self.assertEqual(self.offered, [])
        self.assertEqual(self.completed, [False, False], "arka plan denetimi: ilk gonderim yine tetiklenir")

    def test_update_with_trusted_download_url_is_offered(self):
        self.checker._on_worker_result(self.result(GOOD_URL))
        self.assertEqual(len(self.offered), 1)
        self.assertEqual(self.offered[0][1], GOOD_URL)

    def test_manual_check_with_bad_url_reports_failure_not_up_to_date(self):
        self.checker._manual = True
        self.checker._on_worker_result(self.result("https://evil.example/x.zip"))
        self.assertEqual(self.failed_signals, [True])
        self.assertEqual(self.completed, [], "'Güncel' gosterilmemeli")


class CheckerFailureSignalTests(CheckerTestCase):
    def test_manual_network_error_emits_check_failed_only(self):
        self.checker._manual = True
        self.checker._on_worker_network_error("getaddrinfo failed")
        self.assertEqual(self.failed_signals, [True])
        self.assertEqual(self.completed, [], "eskiden burada check_complete(False) -> Ayarlar 'Güncel' gosteriyordu")

    def test_manual_parse_error_emits_check_failed_only(self):
        self.checker._manual = True
        self.checker._on_worker_error("bozuk yanit")
        self.assertEqual((self.failed_signals, self.completed), ([True], []))

    def test_background_failures_stay_silent_and_still_complete(self):
        self.checker._manual = False
        self.checker._on_worker_network_error("x")
        self.checker._on_worker_error("y")
        self.assertEqual(self.failed_signals, [])
        self.assertEqual(self.completed, [False, False])

    def test_incomplete_update_answer_is_a_failed_check(self):
        self.checker._manual = True
        self.checker._on_worker_result(self.result(version=""))
        self.checker._on_worker_result(self.result(url=""))
        self.assertEqual(self.failed_signals, [True, True])
        self.assertEqual((self.offered, self.completed), ([], []))

    def test_manual_up_to_date_still_completes_false(self):
        self.checker._manual = True
        self.checker._on_worker_result({"updateAvailable": False})
        self.assertEqual((self.completed, self.failed_signals), ([False], []))


class CheckerFieldTypeTests(CheckerTestCase):
    def test_string_false_is_not_an_update_and_string_flags_become_bools(self):
        self.checker._on_worker_result({"updateAvailable": "false", "version": "9.9.9", "download_url": GOOD_URL})
        self.assertEqual(self.offered, [])
        self.checker._on_worker_result(self.result(isMandatory="false", fileSize="1234"))
        self.assertIs(self.offered[0][3], False)
        self.assertEqual(self.offered[0][4], 1234)
        self.checker._on_worker_result(self.result(isMandatory="true"))
        self.assertIs(self.offered[1][3], True)

    def test_huge_and_junk_file_sizes_pass_through_the_signal(self):
        for size, expected in ((5_000_000_000, 5_000_000_000), ("5000000000", 5_000_000_000), (None, 0), ("abc", 0), (-3, 0), (1.5e9, 1_500_000_000)):
            with self.subTest(size=size):
                self.offered.clear()
                self.checker._on_worker_result(self.result(fileSize=size))
                self.assertEqual(self.offered[0][4], expected)

    def test_non_string_fields_do_not_crash_the_check(self):
        self.checker._on_worker_result(self.result(release_notes=None, checksum=None, version=9))
        self.assertEqual(self.offered[0][0], "9")
        self.assertEqual((self.offered[0][2], self.offered[0][5]), ("", ""))
        self.checker._on_worker_result(self.result(release_notes=["x"], checksum=12))
        self.assertEqual((self.offered[1][2], self.offered[1][5]), ("", ""))
        self.checker._on_worker_result(self.result(version="v9.9.9", checksum="  " + PAYLOAD_SHA + " "))
        self.assertEqual((self.offered[2][0], self.offered[2][5]), ("9.9.9", PAYLOAD_SHA))


class CheckerSkippedVersionTests(CheckerTestCase):
    def test_a_rolled_back_version_is_not_offered_again_but_a_newer_one_is(self):
        self.checker._skipped_version = lambda: "9.9.9"
        self.checker._on_worker_result(self.result(version="9.9.9"))
        self.assertEqual(self.offered, [])
        self.assertEqual(self.completed, [False], "'güncel' say")
        self.checker._on_worker_result(self.result(version="9.9.10"))
        self.assertEqual(self.offered[0][0], "9.9.10")

    def test_skip_marker_is_read_next_to_the_exe_only_when_frozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, "FlexiKey.exe")
            with open(exe + ".skip", "w", encoding="utf-8") as handle:
                handle.write("9.9.9")
            self.assertIsNone(self.checker._skipped_version(), "kaynaktan calisirken yok")
            with mock.patch.object(updater.sys, "frozen", True, create=True), mock.patch.object(updater.sys, "executable", exe):
                self.assertEqual(self.checker._skipped_version(), "9.9.9")

    def test_update_found_is_not_stamped_but_up_to_date_is(self):
        self.checker._on_worker_result(self.result())
        self.assertEqual(self.stamps, [], "bekleyen guncelleme varken damga atilmaz: yeniden acilista tekrar denetlenir")
        self.checker._on_worker_result({"updateAvailable": False})
        self.assertEqual(len(self.stamps), 1)
        self.assertIn("last_update_check", self.stamps[0])


if __name__ == "__main__":
    unittest.main()
