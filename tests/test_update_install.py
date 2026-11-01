"""Kurulum: GERCEK self_update koduyla gecici klasorde (Turkce karakterli, bosluklu, % ve ! iceren yol).

Eski .bat betigi testlerinin yerini alir: ayni guvenceler (zip icindeki exe degisir, baska dosyaya dokunulmaz, exe'siz
arsivde uygulama oldugu gibi kalir, Turkce/ozel karakterli yol calisir) betiksiz kurulum icin sinanir. Yeni surumun
baslatilmasi (spawn) mock'lanir: gercek FlexiKey.exe'ye ya da kullanicinin kopyalarina dokunulmaz.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import tempfile
import unittest
from unittest import mock

import _support
from _support import capture_logs
from _update_support import fake_pe, make_zip

from src.utils import self_update, update_installer
from src.utils.update_installer import UpdateInstaller

ROOT = pathlib.Path(__file__).resolve().parents[1]
OLD = fake_pe(0x8664, b"-eski")
NEW = fake_pe(0x8664, b"-yeni")


class InstallTestCase(unittest.TestCase):
    folder_name = "güncelleme ışık %20 !x"

    def setUp(self):
        patcher, self.log_lines = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        # Turkce karakterli, bosluklu, % ve ! iceren klasor: eski .bat betigi bunlari reddediyordu
        self.app_dir = self.root / self.folder_name / "uygulama klasörü"
        self.work = self.root / "çalışma"
        self.app_dir.mkdir(parents=True)
        self.work.mkdir(parents=True)
        self.exe = str(self.app_dir / "FlexiKey.exe")
        (self.app_dir / "FlexiKey.exe").write_bytes(OLD)
        (self.app_dir / "veri.txt").write_text("eski veri", encoding="utf-8")

        self.spawn = mock.Mock()
        patch = mock.patch.object(self_update, "spawn", self.spawn)
        patch.start()
        self.addCleanup(patch.stop)

        self.installer = UpdateInstaller()
        self.installer.temp_dir = str(self.work)
        self.installer.language = lambda: "tr"
        self.complete, self.failed, self.started = [], [], []
        self.installer.install_complete.connect(lambda: self.complete.append(True))
        self.installer.install_failed.connect(self.failed.append)
        self.installer.install_started.connect(lambda: self.started.append(True))

    def package(self, data: bytes) -> str:
        path = self.work / "FlexiKey_Update.pkg"
        path.write_bytes(data)
        return str(path)

    def install(self, data: bytes, **kwargs) -> bool:
        return self.installer.install_update(self.package(data), exe=self.exe, **kwargs)

    def app_files(self):
        return sorted(p.name for p in self.app_dir.iterdir())


class InstallTests(InstallTestCase):
    def test_zip_update_replaces_only_the_exe(self):
        zipped = make_zip({"FlexiKey/FlexiKey.exe": NEW, "FlexiKey/yeni_veri.txt": b"yeni", "FlexiKey/dll/x.dll": b"x"})  # alt klasorde
        self.assertTrue(self.install(zipped, visible=False, old_version="1.0.0"))
        self.assertEqual((self.app_dir / "FlexiKey.exe").read_bytes(), NEW)
        self.assertEqual((self.app_dir / "FlexiKey.exe.old").read_bytes(), OLD, "eski surum saglik dogrulanana dek saklanir")
        self.assertEqual((self.app_dir / "veri.txt").read_text(encoding="utf-8"), "eski veri")
        self.assertEqual(self.app_files(), ["FlexiKey.exe", "FlexiKey.exe.old", "veri.txt"], "zip'ten baska dosya yazilmaz")
        self.assertFalse((self.work / "FlexiKey_Update.pkg").exists(), "indirilen paket silinir")
        self.assertEqual((self.started, self.complete, self.failed), ([True], [True], []))

    def test_raw_exe_package_works(self):
        self.assertTrue(self.install(NEW, visible=True, old_version="1.0.0"))
        self.assertEqual((self.app_dir / "FlexiKey.exe").read_bytes(), NEW)

    def test_new_version_is_launched_with_wait_pid_and_the_window_state(self):
        self.install(NEW, visible=False, old_version="1.0.0")
        exe, args = self.spawn.call_args.args
        self.assertEqual(exe, self.exe)
        self.assertEqual(list(args), ["--wait-pid", str(os.getpid()), "--updated", "1.0.0", "--minimized"])
        self.install(NEW, visible=True, old_version="1.0.0")
        self.assertEqual(list(self.spawn.call_args.args[1])[-1], "--show-window")

    def test_archive_without_exe_fails_and_leaves_app_untouched(self):
        self.assertFalse(self.install(make_zip({"baska_dosya.txt": b"x"})))
        self.assertEqual((self.app_dir / "FlexiKey.exe").read_bytes(), OLD)
        self.assertEqual(self.app_files(), ["FlexiKey.exe", "veri.txt"], "uygulama klasorune dokunulmamali (.new/.old yok)")
        self.assertEqual(self.failed, ["Güncelleme paketinde FlexiKey.exe yok."])
        self.assertFalse((self.work / "FlexiKey_Update.pkg").exists(), "tekrar deneme yeniden indirir")
        self.spawn.assert_not_called()
        self.assertEqual(self.complete, [])

    def test_other_architecture_is_refused(self):
        self.assertFalse(self.install(fake_pe(0x014C, b"x86")))
        self.assertEqual((self.app_dir / "FlexiKey.exe").read_bytes(), OLD)
        self.assertIn("mimarisi", self.failed[0])
        self.assertEqual(self.app_files(), ["FlexiKey.exe", "veri.txt"])

    def test_package_that_is_not_an_exe_is_refused(self):
        self.assertFalse(self.install(make_zip({"FlexiKey.exe": b"MZ-sahte"})))
        self.assertIn("geçerli bir uygulama dosyası değil", self.failed[0])
        self.assertFalse(self.install(b"<html>404</html>"))
        self.assertIn("exe ya da zip değil", self.failed[1])
        self.assertEqual(self.app_files(), ["FlexiKey.exe", "veri.txt"])

    def test_error_messages_follow_the_ui_language(self):
        self.installer.language = lambda: "en"
        self.assertFalse(self.install(make_zip({"baska.txt": b"x"})))
        self.assertEqual(self.failed, ["The update package does not contain FlexiKey.exe."])

    def test_file_swapped_after_download_is_not_installed(self):
        data = make_zip({"FlexiKey.exe": NEW})
        self.installer.expected_sha256 = hashlib.sha256(data).hexdigest()
        path = self.package(data + b"TROJAN")                     # %TEMP%'te bekleyen dosya degistirildi
        self.assertFalse(self.installer.install_update(path, exe=self.exe))
        self.spawn.assert_not_called()
        self.assertEqual(self.started, [])
        self.assertEqual((self.app_dir / "FlexiKey.exe").read_bytes(), OLD)
        self.assertIn("sağlama toplamı", self.failed[0])

    def test_verified_package_installs(self):
        data = make_zip({"FlexiKey.exe": NEW})
        self.installer.expected_sha256 = hashlib.sha256(data).hexdigest()
        self.assertTrue(self.installer.install_update(self.package(data), exe=self.exe))

    def test_missing_package_is_reported(self):
        self.assertFalse(self.installer.install_update(str(self.work / "yok.pkg"), exe=self.exe))
        self.assertEqual(self.failed, ["Güncelleme dosyası bulunamadı."])

    def test_source_run_is_not_installed_inline_message(self):
        with mock.patch.object(update_installer, "is_frozen", return_value=False):
            self.assertFalse(self.installer.install_update(self.package(NEW)))
        self.assertIn("Kaynak koddan", self.failed[0])
        self.assertEqual((self.app_dir / "FlexiKey.exe").read_bytes(), OLD)

    def test_a_failing_launch_is_an_install_failure_not_a_crash(self):
        self.spawn.side_effect = self_update.PackageError("baslatilamadi", "spawn", "engellendi")
        self.assertFalse(self.install(NEW))
        self.assertEqual(self.failed, ["Yeni sürüm başlatılamadı: engellendi"])
        self.assertEqual(self.complete, [])

    def test_unexpected_error_becomes_an_install_failure(self):
        with mock.patch.object(self_update, "install_and_relaunch", side_effect=RuntimeError("beklenmeyen")):
            self.assertFalse(self.install(NEW))
        self.assertIn("Beklenmeyen hata: beklenmeyen", self.failed[0])

    def test_preflight_in_the_real_app_folder(self):
        self.assertIsNone(self.installer.preflight_error(self.exe))


class NoScriptTests(unittest.TestCase):
    """Eski betikli kurulumun (taskkill, PowerShell, xcopy, WinRAR, .rar) geri gelmediginin kaniti."""

    def test_update_sources_have_no_batch_taskkill_or_powershell(self):
        for name in ("src/utils/update_installer.py", "src/utils/self_update.py", "src/app.py"):
            text = (ROOT / name).read_text(encoding="utf-8")
            for banned in ("taskkill /", "cmd.exe", "powershell -", "Start-Process", "Expand-Archive", "xcopy", "WinRAR.exe",
                           "'.rar'", '".rar"', ".bat", "_create_updater_script"):
                self.assertNotIn(banned, text, f"{name}: {banned}")
            # Sert çıkış yalnızca self_update.arm_exit_watchdog'da (çıkış takılırsa KENDİ sürecimizi sonlandırır): başka yerde olmaz
            expected = 1 if name == "src/utils/self_update.py" else 0
            self.assertEqual(text.count("os._exit"), expected, f"{name}: os._exit")
        for name in ("src/utils/update_installer.py", "src/app.py"):
            self.assertNotIn("import subprocess", (ROOT / name).read_text(encoding="utf-8"), name)

    def test_installer_expects_the_exe_name_the_build_produces(self):
        self.assertEqual(update_installer.EXE_NAMES, ("FlexiKey.exe",))

    def test_no_message_box_in_update_code(self):
        for name in ("src/utils/update_installer.py", "src/gui/update_dialog.py", "src/utils/updater.py"):
            self.assertIsNone(re.search(r"(?:Q)?MessageBox\.(critical|warning|question|information|about)\(",
                                        (ROOT / name).read_text(encoding="utf-8")), name)
        app_text = (ROOT / "src/app.py").read_text(encoding="utf-8")
        self.assertNotIn("MessageBox", app_text, "guncelleme hatalarinda acilir kutu yok")


if __name__ == "__main__":
    unittest.main()
