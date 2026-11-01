"""Kurulum bitince eski süreç GERÇEKTEN çıkmalı: görünür "Kuruluyor" penceresi `QApplication.quit()`'i iptal ettirmemeli.

E2E'de (gerçek exe) bulundu: pencereli akışta (tepsi "Güncelle" → Şimdi Güncelle) pencere INSTALLING durumunda kapanmayı reddeder
(`reject()` yok sayar); Qt 6'da `quit()` görünür pencereleri kapatmayı dener, reddeden varsa çıkış iptal olur → eski süreç sonsuza dek
yaşıyor, yeni süreç `--wait-pid` için 15 sn bekleyip vazgeçiyordu. Önceki birim testleri pencereyi sahte nesneyle değiştirdiği için görmedi.
"""
import types
import unittest
from unittest import mock

import _update_support as sup  # noqa: F401  (offscreen Qt, proje kökü)

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QTimer
from PyQt6.QtWidgets import QApplication

from src.gui.update_dialog import UpdateDialog


def _destroy(dialog) -> None:
    """Çıkış yolu pencereyi zaten `deleteLater` ile yok etmiş olabilir (sip.delete ikinci kez RuntimeError verir)."""
    if not sip.isdeleted(dialog):
        sip.delete(dialog)


class QuitForUpdateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication([])

    def _run_loop(self, app) -> int:
        """Olay döngüsünü çalıştırır; `_quit_for_update` çağrılır; 3 sn içinde bitmezse 99 ile zorla çıkar (test başarısız)."""
        QTimer.singleShot(0, app._quit_for_update)
        QTimer.singleShot(3000, lambda: QCoreApplication.exit(99))
        return self.qapp.exec()

    def _app_with_installing_dialog(self):
        app = sup.make_app(visible=True)
        dialog = UpdateDialog(version="1.1.0", release_notes="notlar", parent=None, lang="tr", current_version="1.0.0")
        dialog.show_installing()
        dialog.show()
        self.assertTrue(dialog.isVisible())
        app.update_dialog = dialog
        # gerçek ana pencerenin kapanış yolu: `close_app` → QApplication.quit()
        app.main_window = types.SimpleNamespace(close_app=lambda: QApplication.instance().quit(), lang="tr")
        return app, dialog

    def test_the_event_loop_ends_even_though_the_installing_dialog_refuses_to_close(self):
        app, dialog = self._app_with_installing_dialog()
        try:
            self.assertEqual(self._run_loop(app), 0, "döngü 0 ile bitmeli (99 = açık pencere çıkışı iptal ettirdi)")
        finally:
            _destroy(dialog)  # kurulum durumundaki pencere close()'u reddeder: gerçekten yok et (sonraki testlere modal pencere sızmasın)

    def test_the_update_dialog_is_hidden_before_the_process_exits(self):
        """E2E: görünür pencereyle çıkış bazı koşularda Qt kapanışında yerel `access violation` verdi (crash.log)."""
        app, dialog = self._app_with_installing_dialog()
        seen = []

        def at_exit():
            seen.append(dialog.isVisible())

        self.qapp.aboutToQuit.connect(at_exit)
        try:
            self.assertEqual(self._run_loop(app), 0)
        finally:
            self.qapp.aboutToQuit.disconnect(at_exit)
            _destroy(dialog)
        self.assertEqual(seen, [False], "çıkış anında güncelleme penceresi hâlâ görünür")

    def test_the_update_dialog_is_destroyed_while_qapplication_is_still_alive(self):
        """E2E (v3, 100'er koşu): yalnızca `hide()` çökmeyi azalttı (16/100 -> 5/100) ama BİTİRMEDİ. `hide()` `finished` sinyalini vermez:
        `_on_dialog_finished` (deleteLater) çalışmaz; HWND'li saydam pencere Python sonlandırmasına kadar yaşar ve yıkım sırası rastgele kalır
        (eski süreç `access violation` ile çıkar). Pencere çıkıştan ÖNCE (Qt `exec()` sonunda DeferredDelete'i işler) yok edilmeli."""
        app, dialog = self._app_with_installing_dialog()
        try:
            self.assertEqual(self._run_loop(app), 0)
            self.assertTrue(sip.isdeleted(dialog), "güncelleme penceresi çıkışta yok edilmedi (yalnızca gizlendi)")
            self.assertIsNone(app.update_dialog, "uygulama silinmiş pencereye referans tutmamalı")
        finally:
            _destroy(dialog)

    def test_quitting_without_an_update_dialog_still_works(self):
        app = sup.make_app(visible=True)
        app.update_dialog = None
        app.main_window = types.SimpleNamespace(close_app=lambda: QApplication.instance().quit(), lang="tr")
        self.assertEqual(self._run_loop(app), 0)

    def test_gui_objects_are_destroyed_in_a_fixed_order_before_python_finalizes(self):
        """E2E (v3): `hide()+deleteLater()` sonrası bile çökme sürdü (%0,6; düzeltmesiz %12-16). VEH yığını: Py_FinalizeEx -> PyQt6 QtCore
        atexit temizliği -> sip.pyd okuma hatası. PyQt6 sahipsiz QObject'leri (ana pencere, tepsi, 6 menü...) harita sırasıyla siler; sıra
        koşudan koşuya değişir. Güncelleme çıkışında GUI nesneleri `exec()` sonrası BİLİNEN sırayla (menüler -> tepsi -> ana pencere) yok edilir."""
        from PyQt6.QtCore import QObject
        from PyQt6.QtWidgets import QMenu, QWidget

        class Tray(QObject):
            pass

        app = sup.make_app(visible=True)
        order = []

        def track(name, obj):
            obj.destroyed.connect(lambda *_: order.append(name))
            return obj

        tray = track("tray", Tray())
        tray.menu, tray.theme_menu = track("menu", QMenu()), track("theme_menu", QMenu())
        tray.lang_menu, tray.quick_menu = track("lang_menu", QMenu()), track("quick_menu", QMenu())
        app.tray_manager = tray
        app.main_window = track("main_window", QWidget())
        app.update_dialog = track("dialog", QWidget())
        everything = [tray, tray.menu, tray.theme_menu, tray.lang_menu, tray.quick_menu, app.main_window, app.update_dialog]
        app._teardown_qt_objects()
        self.assertTrue(all(sip.isdeleted(o) for o in everything), "bazı GUI nesneleri yok edilmedi")
        self.assertEqual(order, ["dialog", "quick_menu", "lang_menu", "theme_menu", "menu", "tray", "main_window"])
        app._teardown_qt_objects()   # ikinci çağrı zararsız (silinmiş nesneler atlanır)

    def test_teardown_ignores_missing_or_fake_objects(self):
        app = sup.make_app(visible=True)   # tray_manager/main_window Mock: QObject değil
        app._teardown_qt_objects()
        app.update_dialog = None
        del app.tray_manager
        app._teardown_qt_objects()

    def test_run_tears_the_gui_down_on_every_exit_path_after_the_event_loop_ends(self):
        """E2E: aynı kapanış çökmesi güncelleme çıkışında DA, ana pencere açıkken sıradan çıkışta DA görüldü: yıkım her çıkışta, `exec()` sonrası."""
        for updating in (False, True):
            app = sup.make_app(visible=True)
            app._updating = updating
            order = []
            app.app = types.SimpleNamespace(exec=lambda: order.append("exec") or 7)
            app._instance_lock = mock.Mock()
            app._local_server = mock.Mock()
            with mock.patch.object(type(app), "_teardown_qt_objects", lambda self: order.append("teardown")):
                self.assertEqual(app.run(), 7)
            self.assertEqual(order, ["exec", "teardown"], f"_updating={updating}")

    def test_the_hard_exit_watchdog_is_armed_only_for_the_frozen_app(self):
        app, dialog = self._app_with_installing_dialog()
        try:
            with mock.patch("src.app.self_update.arm_exit_watchdog") as arm, mock.patch("src.app._is_frozen", return_value=False):
                self._run_loop(app)
            arm.assert_not_called()
            app, dialog2 = self._app_with_installing_dialog()
            with mock.patch("src.app.self_update.arm_exit_watchdog") as arm, mock.patch("src.app._is_frozen", return_value=True):
                self._run_loop(app)
            arm.assert_called_once()
            _destroy(dialog2)
        finally:
            _destroy(dialog)


if __name__ == "__main__":
    unittest.main()
