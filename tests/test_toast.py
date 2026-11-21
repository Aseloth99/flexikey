"""Pencere içi geri bildirim (toast): alt ortada durur, süresi dolunca kapanır, fare üstündeyken beklemeye geçer,
uzun yazıyı kısaltır (tam hâli ipucunda), eylem yalnızca bir kez ve yalnızca görünürken çalışır; Windows'ta
animasyonlar kapalıysa saydamlık geçişi yapılmaz."""

from __future__ import annotations

import unittest
from unittest import mock

import _support  # noqa: F401

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication, QWidget

from src.gui import toast as toast_mod
from src.gui.toast import Toast, toast_for


class ToastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.host = QWidget()
        self.host.resize(700, 400)
        self.host.show()
        self.app.processEvents()
        self.addCleanup(self.host.deleteLater)
        self.addCleanup(self.host.close)

    def test_one_toast_per_host_placed_bottom_center(self):
        toast = toast_for(self.host)
        self.assertIs(toast_for(self.host), toast)
        toast.show_message("Kaydedildi", "success")
        self.assertTrue(toast.isVisible())
        self.assertEqual(toast.property("kind"), "success")
        self.assertFalse(toast.action_button.isVisibleTo(toast))
        geo = toast.geometry()
        self.assertLessEqual(abs(geo.center().x() - self.host.width() // 2), 1)
        self.assertEqual(geo.bottom() + 1, self.host.height() - toast_mod.MARGIN)
        self.host.resize(500, 300)
        self.app.processEvents()
        self.assertEqual(toast.geometry().bottom() + 1, 300 - toast_mod.MARGIN, "pencere boyutu değişince yer de değişir")

    def test_timer_durations_and_hover_pause(self):
        toast = Toast(self.host)
        toast.show_message("bilgi")
        self.assertEqual(toast._timer.interval(), toast_mod.DEFAULT_MS)
        toast.show_message("silindi", action_text="Geri Al", action=lambda: None)
        self.assertEqual(toast._timer.interval(), toast_mod.ACTION_MS)
        QApplication.sendEvent(toast, QEvent(QEvent.Type.Enter))
        self.assertFalse(toast._timer.isActive(), "fare üstündeyken kapanmaz")
        QApplication.sendEvent(toast, QEvent(QEvent.Type.Leave))
        self.assertTrue(toast._timer.isActive())

    def test_action_runs_once_and_not_after_dismiss(self):
        calls = []
        toast = Toast(self.host)
        toast.show_message("silindi", action_text="Geri Al", action=lambda: calls.append(1))
        self.assertTrue(toast.has_action())
        toast.action_button.click()
        self.assertFalse(toast.trigger_action())
        self.assertEqual(calls, [1])
        toast.show_message("silindi", action_text="Geri Al", action=lambda: calls.append(2))
        toast._timer.timeout.emit()  # süre doldu
        self.assertFalse(toast.trigger_action())
        self.assertEqual(calls, [1])

    def test_long_text_is_elided_with_the_full_text_in_the_tooltip(self):
        toast = Toast(self.host)
        long_text = "Dışa aktarıldı: " + "C:/çok/uzun/klasör/" * 30 + "yedek.json"
        toast.show_message(long_text)
        self.assertNotEqual(toast.text_label.text(), long_text)
        self.assertIn("…", toast.text_label.text())
        self.assertEqual(toast.text_label.toolTip(), long_text)
        self.assertLessEqual(toast.width(), toast_mod.MAX_WIDTH)

    def test_fades_only_when_windows_animations_are_on(self):
        toast = Toast(self.host)
        with mock.patch.object(toast_mod, "_system_animations_enabled", return_value=False):
            toast.show_message("a")
            self.assertFalse(toast._fade.state() == toast._fade.State.Running)
            toast.dismiss()
            self.assertFalse(toast.isVisible(), "animasyon yoksa hemen kapanır")
        with mock.patch.object(toast_mod, "_system_animations_enabled", return_value=True):
            toast.show_message("b")
            self.assertEqual(toast._fade.state(), toast._fade.State.Running)
            self.assertEqual(toast._fade.duration(), toast_mod.FADE_MS)
            self.assertTrue(150 <= toast_mod.FADE_MS <= 250)
            toast._fade.setCurrentTime(toast_mod.FADE_MS)
            self.assertFalse(toast._effect.isEnabled(), "geçiş bitince efekt kapanır (metin keskin kalır)")


if __name__ == "__main__":
    unittest.main()
