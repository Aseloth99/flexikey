"""Klavye girdisi (kb.write / tus kombinasyonlari) GUI is parcacigini bloke etmemeli."""

from __future__ import annotations

import threading
import time
import unittest
from unittest import mock

import _support

from src.core import hotkey_manager
from _manager_support import ManagerTestCase


class InputOffGuiThreadTests(ManagerTestCase):
    def test_long_text_is_typed_on_background_thread_without_blocking_caller(self):
        started, release = threading.Event(), threading.Event()
        writers = []

        def slow_write(text):
            writers.append(threading.current_thread())
            started.set()
            release.wait(5)          # uzun metni / yavas kanca gidis-donusunu taklit eder

        self.kb.write.side_effect = slow_write
        t0 = time.monotonic()
        self.manager.execute_action("text", "ç" * 5000, "Ctrl+Alt+T", False)
        elapsed = time.monotonic() - t0

        self.assertTrue(started.wait(2), "yazma hic baslamadi")
        self.assertFalse(release.is_set())
        self.assertLess(elapsed, 1.0, "execute_action yazma bitene kadar bekledi (GUI donar)")
        self.assertIsNot(writers[0], threading.main_thread())
        self.assertEqual(writers[0].name, "FlexiKey-input")
        self.assertIn("text", [kind for kind, _ in self.events])        # bildirim hemen verildi
        release.set()
        self.assertTrue(hotkey_manager.INPUT_INJECTOR.wait_idle(5))
        self.kb.write.assert_called_once_with("ç" * 5000)

    def test_rich_text_is_converted_on_gui_thread_then_typed_in_background(self):
        self.manager.execute_action("text", "<p>Merhaba <b>dünya</b></p>", "Ctrl+Alt+T", True)
        hotkey_manager.INPUT_INJECTOR.wait_idle(5)
        written = self.kb.write.call_args.args[0]
        self.assertIn("Merhaba dünya", written)
        self.assertNotIn("<b>", written)

    def test_jobs_keep_submission_order(self):
        order = []
        self.kb.write.side_effect = lambda text: order.append(("write", text))
        self.kb.send.side_effect = lambda keys: order.append(("send", keys))
        self.manager.execute_action("text", "bir", "k", False)
        self.manager.execute_action("shortcut", "ctrl+x", "k", False)
        self.manager.execute_action("text", "iki", "k", False)
        self.assertTrue(hotkey_manager.INPUT_INJECTOR.wait_idle(5))
        self.assertEqual(order, [("write", "bir"), ("send", "ctrl+x"), ("write", "iki")])

    def test_typing_error_is_reported_to_user(self):
        self.kb.write.side_effect = RuntimeError("SendInput basarisiz")
        self.manager.execute_action("text", "x", "k", False)
        hotkey_manager.INPUT_INJECTOR.wait_idle(5)
        self.pump()
        errors = [text for kind, text in self.events if kind == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("SendInput basarisiz", errors[0])

    def test_shortcut_action_sleeps_on_background_thread(self):
        release = threading.Event()
        sleepers = []

        def fake_sleep(seconds):
            sleepers.append(threading.current_thread())
            release.wait(5)

        with mock.patch.object(hotkey_manager.time, "sleep", side_effect=fake_sleep):
            t0 = time.monotonic()
            self.manager.execute_action("shortcut", "ctrl+shift+t", "k", False)
            self.assertLess(time.monotonic() - t0, 1.0)           # GUI'de 60 ms uyku yok
            deadline = time.monotonic() + 2
            while not sleepers and time.monotonic() < deadline:
                threading.Event().wait(0.01)
            self.assertEqual(len(sleepers), 1)
            self.assertIsNot(sleepers[0], threading.main_thread())
            self.kb.send.assert_not_called()                      # henuz uyuyor
            release.set()
            hotkey_manager.INPUT_INJECTOR.wait_idle(5)
        self.kb.send.assert_called_once_with("ctrl+shift+t")

    def test_key_combo_commands_do_not_sleep_on_gui_thread(self):
        main_thread_sleeps = []
        real_main = threading.main_thread()
        keybd = self.fake_ctypes.windll.user32.keybd_event
        seen_threads = []
        keybd.side_effect = lambda *a: seen_threads.append(threading.current_thread())

        def fake_sleep(seconds):
            if threading.current_thread() is real_main:
                main_thread_sleeps.append(seconds)

        with mock.patch.object(hotkey_manager.time, "sleep", side_effect=fake_sleep):
            self.run_command("masaustunu_goster")                   # Win+D: _send_keys_combo (0.1 sn uyku)
            hotkey_manager.INPUT_INJECTOR.wait_idle(5)
        self.assertEqual(main_thread_sleeps, [])
        self.assertEqual(keybd.call_count, 4)                      # Win bas, D bas, D birak, Win birak
        self.assertTrue(all(th is not real_main for th in seen_threads))


if __name__ == "__main__":
    unittest.main()
