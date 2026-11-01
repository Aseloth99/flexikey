"""Uçtan uca (süreç içi): yerel HTTP sunucusu + GERÇEK UpdateInstaller + GERÇEK arka plan iş parçacıkları + GERÇEK
güncelleme penceresi + GERÇEK self_update (geçici klasörde). Yeni sürümün başlatılması (spawn) mock'lanır.

Amaç: iş parçacığından ana iş parçacığına sinyallerin ulaştığını, pencere durumlarının sırayla ilerlediğini, hatada
pencerenin açık kalıp "Tekrar dene"nin çalıştığını ve iptalde kurulum yapılmadığını kanıtlamak. Gerçek macik.com.tr'ye
istek atılmaz (yalnızca 127.0.0.1)."""

from __future__ import annotations

import hashlib
import http.server
import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication
from src.gui.message_box import MessageBox

import _support
from _support import capture_logs
from _update_support import fake_pe, make_app, make_zip, pending_info

from src import app as app_module
from src.gui.update_dialog import UpdateDialog
from src.utils import self_update, update_installer
from src.utils.update_installer import UpdateInstaller

OLD = fake_pe(0x8664, b"-eski")
NEW = fake_pe(0x8664, b"-yeni")
ZIP = make_zip({"FlexiKey/FlexiKey.exe": NEW, "FlexiKey/readme.txt": b"x"})


class Handler(http.server.BaseHTTPRequestHandler):
    routes: dict = {}
    slow: set = set()
    hits: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        self.hits.append(path)
        body = self.routes.get(path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            if path in self.slow:
                for i in range(0, len(body), 64):
                    self.wfile.write(body[i:i + 64])
                    self.wfile.flush()
                    time.sleep(0.03)
            else:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


class IntegrationCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication([])
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        patcher, self.log_lines = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("critical", "warning", "question", "information"):
            p = mock.patch.object(MessageBox, name, side_effect=AssertionError("açılır kutu"))
            p.start()
            self.addCleanup(p.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.app_dir = self.root / "uygulama klasörü ışık"
        self.app_dir.mkdir()
        self.exe = str(self.app_dir / "FlexiKey.exe")
        (self.app_dir / "FlexiKey.exe").write_bytes(OLD)
        Handler.routes = {"/zip-no-extension": ZIP, "/raw": NEW, "/html": b"<html>404</html>", "/slow": ZIP * 20}
        Handler.slow = {"/slow"}
        Handler.hits = []

        self.spawn = mock.Mock()
        for p in (mock.patch.object(self_update, "spawn", self.spawn),
                  mock.patch.object(update_installer, "is_frozen", return_value=True),
                  mock.patch.object(update_installer, "current_exe", return_value=self.exe),
                  mock.patch.object(app_module, "_is_frozen", return_value=True)):
            p.start()
            self.addCleanup(p.stop)

        self.app = make_app(pending=pending_info())
        self.installer = UpdateInstaller(language=lambda: "tr")
        self.installer.temp_dir = str(self.root)
        self.app.update_installer = self.installer
        for signal, slot in ((self.installer.download_progress, self.app._on_download_progress),
                             (self.installer.download_complete, self.app._on_download_complete),
                             (self.installer.download_failed, self.app._on_download_failed),
                             (self.installer.install_started, self.app._on_install_started),
                             (self.installer.install_complete, self.app._on_install_complete),
                             (self.installer.install_failed, self.app._on_install_failed)):
            signal.connect(slot)
        self.quit_calls = []
        self.app._quit_for_update = lambda: self.quit_calls.append(True)
        self.app._is_idle_for_update = lambda: True
        self.app._schedule_auto_update = mock.Mock()
        self.dialog = None

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def pending(self, path, data=None, checksum=None, mandatory=False):
        data = ZIP if data is None else data
        info = pending_info(checksum=hashlib.sha256(data).hexdigest() if checksum is None else checksum, mandatory=mandatory, size=len(data))
        info["download_url"] = self.url(path)
        self.app._pending_update = info
        return info

    def open_dialog(self):
        self.dialog = UpdateDialog("1.1.0", "notlar", False, None, "tr", file_size=len(ZIP), current_version="1.0.0")
        self.addCleanup(self.dialog.hide)
        self.app.update_dialog = self.dialog
        self.dialog.update_accepted.connect(self.app._on_dialog_update_accepted)
        self.dialog.update_cancelled.connect(self.app._cancel_update_download)
        self.dialog.show()
        return self.dialog

    def wait_for(self, condition, timeout=20.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            QCoreApplication.processEvents()
            if condition():
                return True
            time.sleep(0.01)
        return False

    def exe_bytes(self):
        return (self.app_dir / "FlexiKey.exe").read_bytes()


class SilentFlowTests(IntegrationCase):
    def test_background_update_downloads_installs_and_quits_cleanly(self):
        info = self.pending("/zip-no-extension", mandatory=True)          # uzantısız adres + zip
        self.app._start_update_download(info["version"], info["download_url"], info["file_size"], info["checksum"])
        self.assertTrue(self.wait_for(lambda: self.quit_calls), "kurulum sonrası temiz çıkış istenmeli")
        self.assertEqual(self.exe_bytes(), NEW)
        self.assertEqual((self.app_dir / "FlexiKey.exe.old").read_bytes(), OLD)
        self.assertEqual(sorted(os.listdir(self.app_dir)), ["FlexiKey.exe", "FlexiKey.exe.old"], "zip'ten başka dosya yazılmadı")
        exe, args = self.spawn.call_args.args
        self.assertEqual((exe, list(args)[-1]), (self.exe, "--minimized"))
        self.assertTrue(self.app._updating)
        self.assertEqual([p for p in os.listdir(self.root) if p != self.app_dir.name], [], "%TEMP% artığı yok")

    def test_raw_exe_package_installs(self):
        info = self.pending("/raw", data=NEW, mandatory=True)
        self.app._start_update_download(info["version"], info["download_url"], info["file_size"], info["checksum"])
        self.assertTrue(self.wait_for(lambda: self.quit_calls))
        self.assertEqual(self.exe_bytes(), NEW)

    def test_wrong_checksum_never_installs_and_notifies_without_a_popup(self):
        info = self.pending("/zip-no-extension", checksum="0" * 64, mandatory=True)
        self.app._start_update_download(info["version"], info["download_url"], info["file_size"], info["checksum"])
        self.assertTrue(self.wait_for(lambda: self.app.tray_manager.tray_icon.showMessage.called))
        self.assertEqual(self.exe_bytes(), OLD)
        self.assertEqual(self.quit_calls, [])
        self.spawn.assert_not_called()
        self.assertIsNotNone(self.app._pending_update, "pill/tepsi öğesi çalışır kalır")
        self.assertEqual(os.listdir(self.root), [self.app_dir.name], "artık dosya yok (.part dahil)")

    def test_optional_install_waits_when_the_user_came_back(self):
        info = self.pending("/raw", data=NEW)
        idle = [False]
        self.app._is_idle_for_update = lambda: idle[0]
        self.app._start_update_download(info["version"], info["download_url"], info["file_size"], info["checksum"])
        self.assertTrue(self.wait_for(lambda: self.app._schedule_auto_update.called))
        self.assertEqual(self.exe_bytes(), OLD)
        self.assertEqual(self.quit_calls, [])
        self.assertTrue(self.app._has_ready_package(), "paket hazır bekler")
        idle[0] = True
        self.app._start_installation()                                   # boşta olunca (yoklama bunu çağırır)
        self.assertTrue(self.wait_for(lambda: self.quit_calls))
        self.assertEqual(self.exe_bytes(), NEW)


class DialogFlowTests(IntegrationCase):
    def test_idle_to_downloading_to_installing_and_quit(self):
        self.pending("/zip-no-extension")
        dialog = self.open_dialog()
        states = []
        self.app._on_download_progress = self.app._on_download_progress   # gerçek yöntem
        dialog.update_btn.click()
        self.assertEqual(dialog.state, UpdateDialog.DOWNLOADING)
        self.assertTrue(self.wait_for(lambda: dialog.state == UpdateDialog.INSTALLING or bool(self.quit_calls)))
        self.assertTrue(self.wait_for(lambda: self.quit_calls))
        self.assertEqual(self.exe_bytes(), NEW)
        self.assertEqual(list(self.spawn.call_args.args[1])[-1], "--minimized", "ana pencere gizliyken gizli")
        self.app.tray_manager.tray_icon.showMessage.assert_not_called()

    def test_visible_main_window_gets_show_window_flag(self):
        self.app.main_window.isVisible.return_value = True
        self.pending("/raw", data=NEW)
        dialog = self.open_dialog()
        dialog.update_btn.click()
        self.assertTrue(self.wait_for(lambda: self.quit_calls))
        self.assertEqual(list(self.spawn.call_args.args[1])[-1], "--show-window")

    def test_failure_keeps_the_window_open_and_retry_succeeds(self):
        self.pending("/zip-no-extension", checksum="f" * 64)             # sunucu yanlış sağlama toplamı bildiriyor
        dialog = self.open_dialog()
        dialog.update_btn.click()
        self.assertTrue(self.wait_for(lambda: dialog.state == UpdateDialog.ERROR))
        self.assertTrue(dialog.isVisible())
        self.assertIn("Güncelleme tamamlanamadı:", dialog.error_label.text())
        self.assertIn("sağlama toplamı", dialog.error_label.text())
        self.assertEqual(self.exe_bytes(), OLD)
        self.assertIsNone(self.app.download_thread)
        # sunucu düzeldi: "Tekrar dene"
        self.pending("/zip-no-extension")
        dialog.retry_btn.click()
        self.assertTrue(self.wait_for(lambda: self.quit_calls))
        self.assertEqual(self.exe_bytes(), NEW)

    def test_html_error_page_and_404_are_inline_errors(self):
        for path, expected in (("/html", "exe ya da zip değil"), ("/yok", "HTTP 404")):
            with self.subTest(path=path):
                self.pending(path, checksum="")
                self.app._pending_update["checksum"] = ""
                dialog = self.open_dialog()
                dialog.update_btn.click()
                self.assertTrue(self.wait_for(lambda: dialog.state == UpdateDialog.ERROR))
                self.assertIn(expected, dialog.error_label.text())
                dialog.hide()
                self.app.update_dialog = None
        self.assertEqual(self.exe_bytes(), OLD)

    def test_cancelling_while_downloading_never_installs_and_a_new_download_works(self):
        info = self.pending("/slow", data=ZIP * 20)
        dialog = self.open_dialog()
        dialog.update_btn.click()
        self.assertTrue(self.wait_for(lambda: self.app._last_progress[0] > 0), "indirme başladı")
        dialog.close()                                                     # Esc/X = iptal + kapat
        self.assertFalse(dialog.isVisible())
        self.assertTrue(self.app._update_cancelled)
        self.assertIsNone(self.app.download_thread)
        time.sleep(0.5)
        QCoreApplication.processEvents()
        self.assertEqual(self.quit_calls, [], "pencere kapanınca uygulama habersiz yeniden başlamamalı")
        self.assertEqual(self.exe_bytes(), OLD)
        self.spawn.assert_not_called()
        # hemen yeni indirme başlatılabilir (eski iş parçacığı yenisine karışmaz)
        self.app.update_dialog = None
        self.pending("/raw", data=NEW)
        self.app._start_update_download("1.1.0", self.url("/raw"), len(NEW), hashlib.sha256(NEW).hexdigest())
        self.assertTrue(self.wait_for(lambda: self.quit_calls))
        self.assertEqual(self.exe_bytes(), NEW)
        self.assertEqual([p for p in os.listdir(self.root) if p != self.app_dir.name], [])

    def test_double_click_does_not_start_two_downloads(self):
        self.pending("/slow", data=ZIP * 20)
        dialog = self.open_dialog()
        dialog.update_btn.click()
        dialog._on_update()
        dialog._on_update()
        self.assertTrue(self.wait_for(lambda: self.app._last_progress[0] > 0))
        self.assertEqual(Handler.hits, ["/slow"], "tek indirme: sunucuya tek istek")
        self.app._cancel_update_download()
        dialog.hide()

    def test_unwritable_folder_is_reported_before_downloading(self):
        self.pending("/raw", data=NEW)
        dialog = self.open_dialog()
        with mock.patch.object(update_installer, "current_exe", return_value=str(self.app_dir / "yok" / "FlexiKey.exe")):
            dialog.update_btn.click()
        self.assertEqual(dialog.state, UpdateDialog.ERROR)
        self.assertIn("yazılamıyor", dialog.error_label.text())
        self.assertIsNone(self.app.download_thread, "indirme hiç başlamadı")


if __name__ == "__main__":
    unittest.main()
