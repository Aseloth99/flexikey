"""Paketleme: spec (UPX kapali, surum dosyasi, stdlib exclude yok), requirements ayrimi, surum tutarliligi,
klasor duzeni (main.py + src/ + assets/) ve canli guncelleme sunucusuyla sozlesme."""

from __future__ import annotations

import ast
import os
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

import _support
from _support import ROOT

ALLOWED_STDLIB_EXCLUDES = {"tkinter"}     # kullanilmiyor; xml/email/html/ssl/http... ASLA excludes'a girmemeli


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def requirement_names(filename: str) -> set[str]:
    names = set()
    for line in read(filename).splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-r"):
            continue
        names.add(re.split(r"[<>=!~;\s\[]", line, 1)[0].lower())
    return names


def project_sources() -> list:
    """Kokteki ince giris noktasi (main.py) + src paketindeki tum moduller."""
    return [ROOT / "main.py", *sorted((ROOT / "src").rglob("*.py"))]


def third_party_imports() -> set[str]:
    local = {"src", "main"}
    found = set()
    for path in project_sources():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return {m for m in found if m not in sys.stdlib_module_names and m not in local}


class SpecTests(unittest.TestCase):
    def setUp(self):
        self.spec = read("FlexiKey.spec")

    def test_upx_is_disabled(self):
        self.assertRegex(self.spec, r"upx\s*=\s*False")
        self.assertNotRegex(self.spec, r"upx\s*=\s*True")

    def test_version_file_is_referenced_and_exists(self):
        match = re.search(r"version\s*=\s*'([^']+)'", self.spec)
        self.assertIsNotNone(match, "EXE(...) version= verilmemis")
        self.assertTrue((ROOT / match.group(1)).is_file())

    def test_no_stdlib_module_in_excludes(self):
        tree = ast.parse(self.spec)
        excludes = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "excludes" for t in node.targets):
                excludes = [elt.value for elt in node.value.elts]
        self.assertTrue(excludes)
        offenders = [m for m in excludes
                     if m.split(".")[0] in sys.stdlib_module_names and m not in ALLOWED_STDLIB_EXCLUDES]
        self.assertEqual(offenders, [], "stdlib modulu excludes'a eklenmis (calisma zamani bozulur)")


class VersionTests(unittest.TestCase):
    def test_version_file_matches_current_version(self):
        from src.utils.updater import UpdateChecker
        text = read("file_version_info.txt")
        version = UpdateChecker.CURRENT_VERSION
        parts = tuple(int(p) for p in version.split(".")) + (0,) * (4 - len(version.split(".")))
        self.assertIn(f"filevers={parts}", text)
        self.assertIn(f"prodvers={parts}", text)
        dotted = ".".join(map(str, parts))
        self.assertIn(f"StringStruct('FileVersion', '{dotted}')", text)
        self.assertIn(f"StringStruct('ProductVersion', '{dotted}')", text)

    def test_version_file_parses_with_pyinstaller_if_available(self):
        try:
            from PyInstaller.utils.win32 import versioninfo
        except Exception:
            self.skipTest("PyInstaller kurulu degil")
        info = versioninfo.load_version_info_from_text_file(str(ROOT / "file_version_info.txt"))
        # 1.0.0.0 -> MS=(1<<16)|0, LS=(0<<16)|0
        self.assertEqual((info.ffi.fileVersionMS, info.ffi.fileVersionLS), (1 << 16, 0))
        strings = {s.name: s.val for s in info.kids[0].kids[0].kids}
        self.assertEqual(strings["FileVersion"], "1.0.0.0")


class RequirementsTests(unittest.TestCase):
    def test_runtime_requirements_cover_every_third_party_import(self):
        names = requirement_names("requirements.txt")
        to_distribution = {
            "PyQt6": "pyqt6", "keyboard": "keyboard", "pynput": "pynput",
            "win32clipboard": "pywin32", "win32con": "pywin32",
        }
        for module in third_party_imports():
            self.assertIn(module, to_distribution, f"bilinmeyen ucuncu taraf import: {module}")
            self.assertIn(to_distribution[module], names, f"requirements.txt eksik: {module}")

    def test_unused_and_build_only_packages_are_not_runtime_requirements(self):
        runtime = requirement_names("requirements.txt")
        self.assertNotIn("pillow", runtime)        # hicbir yerde import edilmiyor
        self.assertNotIn("pyinstaller", runtime)   # yalnizca derleme araci
        self.assertNotIn("pyqt6-qt6", runtime)     # PyQt6 zaten ceker; ayri sabitleme surum catismasi yaratir
        self.assertNotIn("winotify", runtime)      # bildirimler src/utils/notify.py (Qt tepsi balonu); alt surec/winotify yok
        self.assertNotIn("winotify", read("FlexiKey.spec"))

    def test_dev_requirements_add_pyinstaller_on_top_of_runtime(self):
        dev_text = read("requirements-dev.txt")
        self.assertIn("-r requirements.txt", dev_text)
        self.assertIn("pyinstaller", requirement_names("requirements-dev.txt"))

    def test_build_script_installs_dev_requirements(self):
        bat = read("build.bat")
        self.assertIn("requirements-dev.txt", bat)
        self.assertNotRegex(bat, r"pip install -r requirements\.txt")


def spec_keyword(spec_text: str, call_name: str, keyword: str):
    """spec icindeki Analysis(...)/EXE(...) cagrisinin sabit (literal) anahtar sozcuk degeri."""
    for node in ast.walk(ast.parse(spec_text)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == call_name:
            for kw in node.keywords:
                if kw.arg == keyword:
                    return ast.literal_eval(kw.value)
    raise AssertionError(f"spec icinde {call_name}({keyword}=...) yok")


def spec_list(spec_text: str, name: str) -> list:
    for node in ast.walk(ast.parse(spec_text)):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"spec icinde {name} listesi yok")


class LayoutTests(unittest.TestCase):
    """Klasor duzeni (main.py + src/ + assets/): spec yollari ve kaynak aramalari gercek dosyalara inmeli."""

    def setUp(self):
        self.spec = read("FlexiKey.spec")

    def test_entry_point_is_thin_main_at_root(self):
        self.assertIn("['main.py']", self.spec)
        self.assertLess(len(read("main.py").splitlines()), 120)
        # uygulama modulleri src/ altinda; kokte yalnizca giris noktasi (ve varsa paketleme betigi) kalir
        self.assertLessEqual({p.name for p in ROOT.glob("*.py")}, {"main.py", "pack_dist.py"})

    def test_spec_data_files_and_icon_exist(self):
        for source, dest in spec_keyword(self.spec, "Analysis", "datas"):
            self.assertTrue((ROOT / source).is_file(), source)
            self.assertEqual(dest, "assets/icons")
        for icon in spec_keyword(self.spec, "EXE", "icon"):
            self.assertTrue((ROOT / icon.replace("\\", "/")).is_file(), icon)

    def test_spec_hidden_imports_name_real_project_modules(self):
        project_modules = [m for m in spec_list(self.spec, "hiddenimports") if m.startswith("src.")]
        self.assertTrue(project_modules)
        for name in project_modules:
            self.assertTrue((ROOT / (name.replace(".", "/") + ".py")).is_file(), name)

    def test_application_path_is_the_project_root_when_run_from_source(self):
        from src.utils import helpers
        self.assertEqual(pathlib.Path(helpers.get_application_path()).resolve(), ROOT.resolve())
        self.assertTrue((pathlib.Path(helpers.get_application_path()) / "main.py").is_file())

    def test_icon_lookup_finds_assets_when_run_from_source(self):
        from src.gui import notification_manager
        found = notification_manager._get_flexikey_icon_path()
        self.assertEqual(pathlib.Path(found).resolve(), (ROOT / "assets" / "icons" / "FlexiKey.ico").resolve())

    def test_icon_lookup_uses_the_bundled_png_when_frozen(self):
        # PyInstaller yalnizca assets/icons/keyboard.png'yi paketler (spec datas): bildirim ikonu o olmali.
        from src.gui import notification_manager
        with tempfile.TemporaryDirectory() as bundle, tempfile.TemporaryDirectory() as exe_dir:
            icons = pathlib.Path(bundle, "assets", "icons")
            icons.mkdir(parents=True)
            (icons / "keyboard.png").write_bytes(b"png")
            with mock.patch.object(sys, "frozen", True, create=True), \
                    mock.patch.object(sys, "_MEIPASS", bundle, create=True), \
                    mock.patch.object(sys, "executable", os.path.join(exe_dir, "FlexiKey.exe")):
                found = notification_manager._get_flexikey_icon_path()
        self.assertEqual(pathlib.Path(found), icons / "keyboard.png")

    def test_bundled_icon_files_are_valid_images(self):
        from PyQt6.QtGui import QImage
        self.assertFalse(QImage(str(ROOT / "assets" / "icons" / "keyboard.png")).isNull())
        self.assertGreater((ROOT / "assets" / "icons" / "FlexiKey.ico").stat().st_size, 0)


class UpdateContractTests(unittest.TestCase):
    """Canli guncelleme sunucusuyla sozlesme: adres, uygulama adi, exe adi ve zip duzeni degismemeli."""

    def test_server_url_app_name_and_trusted_host(self):
        from src.utils.updater import UpdateChecker, trusted_update_host
        self.assertEqual(UpdateChecker.UPDATE_CHECK_URL, "https://macik.com.tr/api/updates/check")
        self.assertEqual(UpdateChecker.APP_NAME, "FlexiKey")
        self.assertEqual(trusted_update_host(), "macik.com.tr")

    def test_installer_expects_the_exe_name_the_build_produces(self):
        self.assertIn('"FlexiKey.exe"', read("src/utils/update_installer.py"))
        self.assertIn("name='FlexiKey'", read("FlexiKey.spec"))

    def test_zip_layout_has_the_exe_at_the_archive_root(self):
        bat = read("build.bat")
        self.assertIn('z_name = "dist/FlexiKey.zip"', bat)
        self.assertIn('z.write("dist/FlexiKey.exe", "FlexiKey.exe")', bat)


if __name__ == "__main__":
    unittest.main()
