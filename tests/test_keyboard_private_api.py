"""keyboard kutuphanesinin ozel API'lerine (_hotkeys, _listener) erisim: sessiz 'pass' yerine log.

Bu erisim WindowsKeyboardBackend'e tasindi; keyboard modulu sahte bir SimpleNamespace'tir.
"""

from __future__ import annotations

import types
import unittest

import _support
from _support import capture_logs
from _fakes import FakeBackend

from src.core import input_backend
from src.core.hotkey_manager import HotkeyWorker
from src.core.input_backend import WindowsKeyboardBackend


class PrivateApiTests(unittest.TestCase):
    def setUp(self):
        patcher, self.log_lines = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)
        input_backend._PRIVATE_API_WARNED.clear()

    def use_kb(self, **attrs):
        """keyboard modulu yerine gecen sahte modulle bir Windows arka ucu kurar."""
        return WindowsKeyboardBackend(keyboard_module=types.SimpleNamespace(**attrs), pynput_module=object())

    def warnings(self, needle):
        return [m for level, m in self.log_lines if level == "WARNING" and needle in m]

    def test_missing_hotkeys_dict_is_logged_once(self):
        backend = self.use_kb(unhook_all=lambda: None)                 # _hotkeys yok (kutuphane degismis)
        backend.unhook_all()
        backend.unhook_all()
        self.assertEqual(len(self.warnings("_hotkeys")), 1)  # her yenilemede tekrar yazmaz

    def test_hotkeys_clear_failure_is_logged(self):
        class Broken:
            def clear(self):
                raise RuntimeError("degisti")
        self.use_kb(unhook_all=lambda: None, _hotkeys=Broken()).unhook_all()
        self.assertEqual(len(self.warnings("_hotkeys.clear")), 1)

    def test_hotkeys_dict_is_cleared_when_available(self):
        hotkeys = {"ctrl+a": object()}
        self.use_kb(unhook_all=lambda: None, _hotkeys=hotkeys).unhook_all()
        self.assertEqual(hotkeys, {})
        self.assertEqual(self.warnings("_hotkeys"), [])

    def test_unhook_all_failure_is_logged_as_error(self):
        def boom():
            raise OSError("kanca kaldirilamadi")
        self.use_kb(unhook_all=boom, _hotkeys={}).unhook_all()
        self.assertTrue(any(level == "ERROR" and "unhook_all" in m for level, m in self.log_lines))

    def test_missing_listener_is_logged_and_not_revived(self):
        backend = self.use_kb()
        self.assertFalse(backend.revive_if_dead())
        self.assertEqual(len(self.warnings("_listener")), 1)

    def test_listener_without_thread_attribute_is_logged(self):
        backend = self.use_kb(_listener=types.SimpleNamespace(listening=True))
        self.assertFalse(backend.revive_if_dead())
        self.assertEqual(len(self.warnings("listening_thread")), 1)

    def test_dead_listener_thread_is_revived_without_warning(self):
        listener = types.SimpleNamespace(
            listening=True, listening_thread=types.SimpleNamespace(is_alive=lambda: False))
        backend = self.use_kb(_listener=listener)
        self.assertTrue(backend.revive_if_dead())
        self.assertFalse(listener.listening)
        self.assertEqual(self.warnings("_listener"), [])

    def test_listener_not_started_yet_is_normal(self):
        backend = self.use_kb(_listener=types.SimpleNamespace(listening=False, listening_thread=None))
        self.assertFalse(backend.revive_if_dead())
        self.assertEqual(self.warnings("_listener"), [])

    def test_hard_reinstall_drops_listening_flag(self):
        listener = types.SimpleNamespace(listening=True)
        self.use_kb(_listener=listener).prepare_hard_reinstall()
        self.assertFalse(listener.listening)

    def test_worker_delegates_hook_maintenance_to_backend(self):
        backend = FakeBackend()
        worker = HotkeyWorker(backend=backend)
        worker._clear_keyboard_hotkeys()
        backend.unhook_all.assert_called_once_with()
        self.assertFalse(worker._revive_listener_if_dead())
        backend.revive_if_dead.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
