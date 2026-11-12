"""Ekran ölçeği değişince (ör. %150'de açılmış oturuma %100'lük RDP ile bağlanınca) pencere asgari genişliğin altında
kalıyordu: başlık menüsü ("Uygulam", "Ayarla") ve araç çubuğu düğmeleri kesik görünüyordu. Ölçek değişimi ya da
gösterim sonrası pencere yeniden asgari ölçüye ve görünür alana oturtulmalı."""

from __future__ import annotations

import os
import tempfile
import unittest

import _support  # noqa: F401  (offscreen Qt, proje kökü sys.path'te)

from PyQt6.QtCore import QEvent, QSize
from PyQt6.QtWidgets import QApplication


class SettleGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls._saved = {k: os.environ.get(k) for k in ("APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME")}
        for key in cls._saved:
            os.environ[key] = cls._tmp.name
        cls.app = QApplication.instance() or QApplication([])
        from src.core.hotkey_manager import HotkeyManager
        from src.gui import main_window as mw
        from src.gui.notification_manager import NotificationManager
        from src.utils.settings_manager import SettingsManager
        from src.utils.theme_manager import ThemeManager

        cls.settings = SettingsManager()
        data = cls.settings.load_settings()
        data.update(theme="dark", language="tr", hotkeys=[], expansions=[])
        cls.settings.save_settings(data)
        cls.window = mw.MainWindow(cls.settings, ThemeManager(cls.app), HotkeyManager(), NotificationManager(), None)
        cls.window.show()
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls.window.deleteLater()
        cls.app.processEvents()
        for key, value in cls._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls._tmp.cleanup()

    def test_a_scale_change_schedules_settling(self):
        calls = []
        self.window._settle_geometry = lambda: calls.append(1)
        try:
            self.app.sendEvent(self.window, QEvent(QEvent.Type.DevicePixelRatioChange))
            for _ in range(3):
                self.app.processEvents()
            self.assertTrue(calls, "ölçek değişimi pencereyi yeniden oturtmadı")
        finally:
            del self.window._settle_geometry

    def test_a_window_below_its_minimum_is_grown_back(self):
        # Windows ölçek geçişinde pencereyi asgari ölçünün altına bırakabiliyor (Qt kendi yeniden boyutlamasında
        # buna izin vermez); o durumda gereken ölçü düzene göre büyüktür.
        w = self.window
        want = QSize(w.width() + 60, w.height() + 40)
        w.minimumSizeHint = lambda: want
        try:
            w._settle_geometry()
            self.app.processEvents()
            self.assertGreaterEqual(w.width(), min(want.width(), w.screen().availableGeometry().width()))
        finally:
            del w.minimumSizeHint

    def test_the_title_menu_fits(self):
        self.window._settle_geometry()
        self.app.processEvents()
        for btn in self.window.menu_bar_widget.findChildren(type(self.window.file_menu_btn)):
            if btn.isVisible():
                self.assertGreaterEqual(btn.width(), btn.minimumSizeHint().width(), btn.text())

    def test_the_window_is_pulled_back_on_screen(self):
        screen = self.window.screen().availableGeometry()
        self.window.move(screen.right() + 400, screen.bottom() + 400)
        self.window._settle_geometry()
        frame = self.window.frameGeometry()
        self.assertTrue(screen.contains(frame.topLeft()))


if __name__ == "__main__":
    unittest.main()
