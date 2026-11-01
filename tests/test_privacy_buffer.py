"""Gizlilik: pynput tamponu hareketsizlikte silinmeli, parola kutusunda/genisletme yokken tutulmamali.

Gercek klavye kancasi kurulmaz: Listener ve odak denetimi sahte.
"""

from __future__ import annotations

import unittest
from unittest import mock

import _support
from _support import capture_logs
from _fakes import FakeBackend

from src.core import hotkey_manager
from src.core.hotkey_manager import HotkeyWorker, RICH_BUFFER_IDLE_SECONDS, focused_control_is_password


class BufferTests(unittest.TestCase):
    def setUp(self):
        patcher, _ = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)
        self.worker = HotkeyWorker(backend=FakeBackend())
        self.worker.rich_expansions = {"mt": "<b>x</b>", "imza": "<i>y</i>"}
        self.password_focus = False
        patch = mock.patch.object(HotkeyWorker, "_focus_is_password_field",
                                  lambda this: self.password_focus)
        patch.start()
        self.addCleanup(patch.stop)

    def type_text(self, text, start=100.0, step=0.1):
        now = start
        for ch in text:
            self.worker._buffer_append(ch, now=now)
            now += step
        return now

    def test_buffer_never_holds_more_than_longest_trigger(self):
        self.type_text("parola123456789" * 10)
        self.assertLessEqual(len(self.worker.buffer), len("imza"))      # eskiden 100 karakter
        self.assertEqual(self.worker.buffer, "6789"[-4:])

    def test_idle_timeout_drops_stale_prefix(self):
        end = self.type_text("im")
        self.worker._buffer_append("z", now=end + RICH_BUFFER_IDLE_SECONDS + 1)
        self.assertEqual(self.worker.buffer, "z")             # "im" onceki oturumdan kalmisti

    def test_typing_without_pause_keeps_prefix(self):
        end = self.type_text("im")
        self.worker._buffer_append("z", now=end + 1)
        self.assertEqual(self.worker.buffer, "imz")

    def test_expire_buffer_clears_after_idle(self):
        end = self.type_text("im")
        self.assertFalse(self.worker.expire_buffer(now=end + 1))
        self.assertEqual(self.worker.buffer, "im")
        self.assertTrue(self.worker.expire_buffer(now=end + RICH_BUFFER_IDLE_SECONDS + 0.5))
        self.assertEqual(self.worker.buffer, "")

    def test_stale_word_is_not_taken_on_space(self):
        end = self.type_text("mt")
        self.assertEqual(self.worker._buffer_take_word(now=end + RICH_BUFFER_IDLE_SECONDS + 1), "")
        self.assertEqual(self.worker.buffer, "")
        end = self.type_text("mt", start=500.0)
        self.assertEqual(self.worker._buffer_take_word(now=end + 1), "mt")

    def test_nothing_buffered_without_rich_expansions(self):
        self.worker.rich_expansions = {}
        self.worker.buffer = "eski"
        self.assertFalse(self.worker._buffer_append("p", now=1.0))
        self.assertEqual(self.worker.buffer, "")               # eskiden her tus 100 karakterlik tampona giriyordu

    def test_password_field_is_not_buffered_and_clears_existing(self):
        self.type_text("mt")
        self.password_focus = True
        self.assertFalse(self.worker._buffer_append("s", now=200.0))
        self.assertEqual(self.worker.buffer, "")
        self.password_focus = False
        self.assertTrue(self.worker._buffer_append("m", now=201.0))
        self.assertEqual(self.worker.buffer, "m")


class TypedKeyCallbackTests(unittest.TestCase):
    """_start_pynput_hook'un verdigi on_key geri cagrisinin tampon/tetikleme davranisi (sahte arka uc ile).

    Arka uc yazilan tuslari ('char', c) / ('space', None) olarak normallestirir; worker pynput'a dokunmaz."""

    def setUp(self):
        patcher, _ = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)

        self.thread_cls = mock.Mock(name="Thread")
        for p in (
            mock.patch.object(hotkey_manager.threading, "Thread", self.thread_cls),
            mock.patch.object(HotkeyWorker, "_focus_is_password_field", lambda this: False),
        ):
            p.start()
            self.addCleanup(p.stop)

        self.backend = FakeBackend()
        self.worker = HotkeyWorker(backend=self.backend)
        self.worker.rich_expansions = {"mt": "<b>x</b>"}
        self.worker._start_pynput_hook()
        self.on_key = self.backend.listener.on_key

    def type_text(self, text):
        for ch in text:
            self.on_key("char", ch)

    def test_listener_is_started_through_backend(self):
        self.assertTrue(self.backend.listener.started)
        self.assertIs(self.worker.pynput_listener, self.backend.listener)

    def test_expansion_triggers_when_typed_promptly(self):
        self.type_text("mt")
        self.on_key("space", None)
        self.thread_cls.assert_called_once()

    def test_stale_trigger_does_not_expand_after_idle(self):
        self.type_text("mt")
        self.worker._buffer_last_time -= RICH_BUFFER_IDLE_SECONDS + 5      # 5 sn+ hareketsizlik
        self.on_key("space", None)
        self.thread_cls.assert_not_called()
        self.assertEqual(self.worker.buffer, "")

    def test_keystrokes_are_not_retained_when_no_rich_expansions(self):
        self.worker.rich_expansions = {}
        self.type_text("gizli parola")
        self.assertEqual(self.worker.buffer, "")

    def test_enter_does_not_expand_and_ends_the_word(self):
        # Enter cok satirli alanda satir sonu ekler; geri silme tetikleyici yerine onu silerdi
        for rich, typed in (({"mt": "<b>x</b>"}, {}), ({}, {"mt": "x"})):     # zengin ve yazilan-duz
            with self.subTest(rich=bool(rich)):
                self.thread_cls.reset_mock()
                self.worker.rich_expansions, self.worker.typed_expansions = rich, typed
                self.type_text("mt")
                self.on_key("enter", None)
                self.thread_cls.assert_not_called()
                self.assertEqual(self.worker.buffer, "")
                self.type_text("mt")
                self.on_key("space", None)
                self.thread_cls.assert_called_once()

    def test_other_keys_are_ignored(self):
        self.type_text("m")
        self.on_key("other", None)
        self.assertEqual(self.worker.buffer, "m")


class PasswordDetectionTests(unittest.TestCase):
    def fake_user32(self, class_name="Edit", style=0, focus=123, foreground=7, gui_ok=1):
        user32 = mock.Mock()
        user32.GetForegroundWindow.return_value = foreground
        user32.GetWindowThreadProcessId.return_value = 55

        def get_gui_thread_info(thread_id, ref):
            ref._obj.hwndFocus = focus
            return gui_ok

        def get_class_name(hwnd, buffer, size):
            buffer.value = class_name
            return len(class_name)

        user32.GetGUIThreadInfo.side_effect = get_gui_thread_info
        user32.GetClassNameW.side_effect = get_class_name
        user32.GetWindowLongW.return_value = style
        return user32

    def test_edit_control_with_es_password_is_detected(self):
        self.assertTrue(focused_control_is_password(self.fake_user32("Edit", 0x50010020)))
        self.assertTrue(focused_control_is_password(self.fake_user32("WindowsForms10.EDIT.app.0", 0x20)))

    def test_normal_edit_and_non_edit_controls_are_not_flagged(self):
        self.assertFalse(focused_control_is_password(self.fake_user32("Edit", 0x50010000)))
        self.assertFalse(focused_control_is_password(self.fake_user32("Button", 0x20)))   # 0x20 baska anlam

    def test_missing_window_or_focus_or_api_failure_is_not_flagged(self):
        self.assertFalse(focused_control_is_password(self.fake_user32(foreground=0)))
        self.assertFalse(focused_control_is_password(self.fake_user32(focus=0)))
        self.assertFalse(focused_control_is_password(self.fake_user32(gui_ok=0)))
        broken = mock.Mock()
        broken.GetForegroundWindow.side_effect = OSError("api")
        self.assertFalse(focused_control_is_password(broken))


if __name__ == "__main__":
    unittest.main()
