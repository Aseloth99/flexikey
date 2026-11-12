"""Platform algilama, kullanici dizinleri (Windows/macOS/Linux) ve POSIX dosya izinleri.

Platform enjekte edilir (platform=...); gercek ev dizinine/APPDATA'ya dokunulmaz.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

import _support

from src.utils import helpers
from src.utils import platform_utils as pu


class DetectPlatformTests(unittest.TestCase):
    def test_sys_platform_values_map_to_three_families(self):
        cases = {
            "win32": pu.WINDOWS, "cygwin": pu.WINDOWS,
            "darwin": pu.MACOS,
            "linux": pu.LINUX, "linux2": pu.LINUX, "freebsd14": pu.LINUX,
            pu.WINDOWS: pu.WINDOWS, pu.MACOS: pu.MACOS, pu.LINUX: pu.LINUX,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(pu.current_platform(raw), expected)

    def test_default_reads_sys_platform_at_call_time(self):
        for raw, family in (("win32", pu.WINDOWS), ("darwin", pu.MACOS), ("linux", pu.LINUX)):
            with self.subTest(raw=raw), mock.patch.object(sys, "platform", raw):
                self.assertEqual(pu.current_platform(), family)
                self.assertEqual(pu.is_windows(), family == pu.WINDOWS)
                self.assertEqual(pu.is_macos(), family == pu.MACOS)
                self.assertEqual(pu.is_linux(), family == pu.LINUX)
                self.assertEqual(pu.is_posix(), family != pu.WINDOWS)

    def test_only_windows_supports_automatic_update(self):
        self.assertTrue(pu.auto_update_supported("win32"))
        self.assertFalse(pu.auto_update_supported("darwin"))
        self.assertFalse(pu.auto_update_supported("linux"))


class SessionTypeTests(unittest.TestCase):
    def test_declared_session_type_wins(self):
        self.assertEqual(pu.linux_session_type({"XDG_SESSION_TYPE": "Wayland", "DISPLAY": ":0"}), pu.SESSION_WAYLAND)
        self.assertEqual(pu.linux_session_type({"XDG_SESSION_TYPE": "x11"}), pu.SESSION_X11)
        self.assertEqual(pu.linux_session_type({"XDG_SESSION_TYPE": "tty"}), pu.SESSION_TTY)

    def test_hints_used_when_type_is_missing_or_unknown(self):
        self.assertEqual(pu.linux_session_type({"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}), pu.SESSION_WAYLAND)
        self.assertEqual(pu.linux_session_type({"DISPLAY": ":1"}), pu.SESSION_X11)
        self.assertEqual(pu.linux_session_type({"XDG_SESSION_TYPE": "mir", "DISPLAY": ":1"}), pu.SESSION_X11)
        self.assertEqual(pu.linux_session_type({}), pu.SESSION_UNKNOWN)

    def test_x11_display_detection(self):
        self.assertTrue(pu.has_x11_display({"DISPLAY": ":0"}))
        self.assertFalse(pu.has_x11_display({"DISPLAY": "  "}))
        self.assertFalse(pu.has_x11_display({}))


class SingleInstanceNameTests(unittest.TestCase):
    def test_windows_names_are_unchanged(self):
        lock, server = pu.single_instance_names("win32", temp_dir="T")
        self.assertEqual(lock, os.path.join("T", "FlexiKey.single.lock"))
        self.assertEqual(server, "FlexiKey.SingleInstanceServer")

    def test_posix_names_are_per_user(self):
        for plat in ("darwin", "linux"):
            lock_a, server_a = pu.single_instance_names(plat, user="1000", temp_dir="T")
            lock_b, server_b = pu.single_instance_names(plat, user="1001", temp_dir="T")
            self.assertNotEqual(lock_a, lock_b)
            self.assertNotEqual(server_a, server_b)
            self.assertIn("1000", server_a)


class UserDirectoryTests(unittest.TestCase):
    HOME = os.path.join(os.sep, "home", "ayse")

    def dirs(self, platform, environ):
        kw = dict(platform=platform, environ=environ, home=self.HOME)
        return (helpers.get_user_config_dir(**kw), helpers.get_user_data_dir(**kw), helpers.get_user_log_dir(**kw))

    def test_windows_uses_appdata_and_localappdata(self):
        env = {"APPDATA": "R", "LOCALAPPDATA": "L"}
        config, data, log = self.dirs("win32", env)
        self.assertEqual(config, os.path.join("R", "FlexiKey"))
        self.assertEqual(data, os.path.join("L", "FlexiKey"))
        self.assertEqual(log, os.path.join("L", "FlexiKey", "logs"))        # eski konumla ayni

    def test_windows_falls_back_to_profile_when_env_missing(self):
        config, data, _ = self.dirs("win32", {})
        self.assertEqual(config, os.path.join(self.HOME, "AppData", "Roaming", "FlexiKey"))
        self.assertEqual(data, os.path.join(self.HOME, "AppData", "Local", "FlexiKey"))

    def test_macos_uses_library_dirs(self):
        config, data, log = self.dirs("darwin", {"XDG_CONFIG_HOME": "yoksayilir"})
        support = os.path.join(self.HOME, "Library", "Application Support", "FlexiKey")
        self.assertEqual((config, data), (support, support))
        self.assertEqual(log, os.path.join(self.HOME, "Library", "Logs", "FlexiKey"))

    def test_linux_follows_xdg_variables_and_defaults(self):
        config, data, log = self.dirs("linux", {"XDG_CONFIG_HOME": "/x/cfg", "XDG_DATA_HOME": "/x/data"})
        self.assertEqual(config, os.path.join("/x/cfg", "FlexiKey"))
        self.assertEqual(data, os.path.join("/x/data", "FlexiKey"))
        self.assertEqual(log, os.path.join("/x/data", "FlexiKey", "logs"))
        config, data, _ = self.dirs("linux", {})
        self.assertEqual(config, os.path.join(self.HOME, ".config", "FlexiKey"))
        self.assertEqual(data, os.path.join(self.HOME, ".local", "share", "FlexiKey"))


@unittest.skipIf(sys.platform == "win32", "POSIX dosya izinleri (chmod) Windows'ta anlamsiz")
class PosixPermissionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name

    def mode(self, path):
        return stat.S_IMODE(os.stat(path).st_mode)

    def test_private_dir_and_file_helpers(self):
        target = os.path.join(self.tmp, "a", "FlexiKey")
        pu.ensure_private_dir(target)
        self.assertEqual(self.mode(target), 0o700)
        path = os.path.join(target, "x.txt")
        with open(path, "w") as handle:
            handle.write("x")
        os.chmod(path, 0o644)
        pu.restrict_file(path)
        self.assertEqual(self.mode(path), 0o600)

    def test_windows_branch_never_chmods(self):
        target = os.path.join(self.tmp, "w")
        with mock.patch("src.utils.platform_utils.os.chmod") as chmod:
            pu.ensure_private_dir(target, platform="win32")
            pu.restrict_file(target, platform="win32")
        chmod.assert_not_called()

    def test_atomic_write_keeps_settings_file_private_and_replaces_loose_permissions(self):
        path = os.path.join(self.tmp, "cfg", "config.json")
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as handle:
            handle.write("{}")
        os.chmod(path, 0o666)                       # eski surumden kalma genis izin
        helpers.atomic_write_text(path, '{"a": 1}', backup_path=path + ".bak")
        self.assertEqual(self.mode(path), 0o600)
        self.assertEqual(self.mode(path + ".bak"), 0o600)

    def test_resolve_user_config_creates_private_config_dir(self):
        home = os.path.join(self.tmp, "home")
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": os.path.join(home, "cfg")}), \
                mock.patch.object(sys, "platform", "linux"), \
                mock.patch.object(helpers.os, "getcwd", return_value=self.tmp):
            user_path, seed = helpers.resolve_user_config(app_dir=self.tmp)
        self.assertEqual(os.path.dirname(user_path), os.path.join(home, "cfg", "FlexiKey"))
        self.assertEqual(self.mode(os.path.dirname(user_path)), 0o700)
        self.assertIsNone(seed)

    def test_log_file_and_dir_are_private(self):
        helpers._LOGGER = None
        self.addCleanup(setattr, helpers, "_LOGGER", None)
        env = {k: v for k, v in os.environ.items() if k != "FLEXIKEY_LOG_DIR"}
        with mock.patch.dict(os.environ, env, clear=True),                 mock.patch.object(helpers, "get_user_log_dir", return_value=os.path.join(self.tmp, "logs")):
            helpers.write_log("deneme satiri")
            logger = helpers.get_logger()
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)
        log_dir = os.path.join(self.tmp, "logs")
        self.assertEqual(self.mode(log_dir), 0o700)
        self.assertEqual(self.mode(os.path.join(log_dir, "flexikey.log")), 0o600)


if __name__ == "__main__":
    unittest.main()
