"""Ana pencere kullanım iyileştirmeleri: Ctrl+T / F5 / Ctrl+F kısayolları, menüden sonra takılı hover, tepsiden geri
gelince büyütülmüş kalma, pencere içi geri bildirim (toast) ve "Geri Al", boyut/konum hatırlama, liste klavyesi ve
süzgeci (gizli değer aranamaz), yeni öğenin vurgulanması, başlık çubuğundan Aero Snap ve dışa aktarmada "Klasörü Aç".

Gerçek %APPDATA%'ya dokunulmaz (geçici profil); kısayol dinleyicisi başlatılmaz.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from unittest import mock

import _support  # noqa: F401  (proje kökü + offscreen)

from PyQt6.QtCore import QEvent, QEventLoop, QPoint, QPointF, QRect, Qt, QTimer
from PyQt6.QtGui import QCursor, QKeyEvent, QKeySequence, QMouseEvent
from PyQt6.QtWidgets import QApplication, QDialog, QPushButton

from src.gui import main_window as mw
from src.gui import window_geometry
from src.gui.hover_fix import settle_hover
from src.gui.list_widgets import CardListWidget, HotkeyCard
from src.gui.message_box import MessageBox
from src.gui.tray_manager import restore_window
from src.utils.locales import t
from src.utils.settings_manager import SettingsManager

YES = MessageBox.StandardButton.Yes
SECRET = "Gizli!Parola42"


def _hk(shortcut, value="metin", secret=False, enabled=True):
    rec = {"shortcut": shortcut, "action_type": "text", "action_value": value, "enabled": enabled, "is_rich": False}
    if secret:
        rec["is_secret"] = True
    return rec


def _exp(trigger, value="uzun metin"):
    return {"trigger": trigger, "replacement": value, "enabled": True, "is_rich": False}


def _key(widget, key, modifiers=Qt.KeyboardModifier.NoModifier):
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, key, modifiers))


def _enter(widget):
    widget.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, True)
    QApplication.sendEvent(widget, QEvent(QEvent.Type.Enter))


def _close_popup_soon(app):
    def close():
        popup = app.activePopupWidget()
        if popup is not None:
            popup.close()
        else:
            QTimer.singleShot(20, close)

    QTimer.singleShot(50, close)


class _Window(unittest.TestCase):
    """Geçici profilde gerçek bir MainWindow (sınıf başına bir tane)."""

    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication([])
        from test_consistency import _TempProfile
        from src.core.hotkey_manager import HotkeyManager
        from src.gui.notification_manager import NotificationManager
        from src.utils.theme_manager import ThemeManager
        cls._profile = _TempProfile()
        cls._profile.__enter__()
        cls.settings = SettingsManager()
        cls.settings._seed_file = None
        data = cls.settings.load_settings()
        data.update(theme="dark", language="tr", hotkeys=[], expansions=[])
        cls.settings.save_settings(data)
        cls.window = mw.MainWindow(cls.settings, ThemeManager(cls.qapp), HotkeyManager(), NotificationManager(), None)
        cls.window.resize(900, 560)
        cls.window.show()
        cls.qapp.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls.window.deleteLater()
        cls.qapp.processEvents()
        cls._profile.__exit__(None, None, None)

    def setUp(self):
        self.window.notification_manager.set_enabled(False)
        for prefix in ("hotkey", "exp"):
            self.window._close_filter(prefix)
        self.window.tabs.setCurrentIndex(0)

    def _set(self, hotkeys=(), expansions=()):
        data = self.settings.load_settings()
        data.update(hotkeys=list(hotkeys), expansions=list(expansions))
        self.settings.save_settings(data)
        self.window.load_hotkeys()
        self.window.load_expansions()
        self.qapp.processEvents()

    def _toast(self):
        toast = self.window.current_toast()
        self.assertIsNotNone(toast)
        return toast


# ---------------------------------------------------------------------------------------------------------------
class ShortcutTests(_Window):
    def test_help_shortcuts_are_really_bound(self):
        for seq in ("Ctrl+T", "F5", "Ctrl+F"):
            shortcut = self.window._window_shortcuts[seq]
            self.assertEqual(shortcut.key(), QKeySequence(seq))
            self.assertEqual(shortcut.context(), Qt.ShortcutContext.WindowShortcut)
        help_html = []
        MessageBox.set_test_hook(lambda box: help_html.append(box.text()))
        self.addCleanup(MessageBox.set_test_hook, None)
        self.window.show_help()
        for key in ("help_sc_toggle_theme", "help_sc_refresh", "help_sc_find"):
            self.assertIn(t(key, "tr"), help_html[0])

    def test_ctrl_t_toggles_light_and_dark_and_saves_it(self):
        start = self.window.theme_manager.get_current_theme()
        self.window._window_shortcuts["Ctrl+T"].activated.emit()
        other = "light" if start == "dark" else "dark"
        self.assertEqual(self.window.theme_manager.get_current_theme(), other)
        self.assertEqual(self.settings.load_settings()["theme"], other)
        self.window._window_shortcuts["Ctrl+T"].activated.emit()
        self.assertEqual(self.window.theme_manager.get_current_theme(), start)

    def test_f5_reloads_the_open_tab(self):
        with mock.patch.object(self.window, "load_hotkeys") as hot, mock.patch.object(self.window, "load_expansions") as exp:
            self.window.refresh_current_list()
            hot.assert_called_once()
            exp.assert_not_called()
            self.window.tabs.setCurrentIndex(1)
            self.window.refresh_current_list()
            exp.assert_called_once()


# ---------------------------------------------------------------------------------------------------------------
class HoverTests(_Window):
    def test_helper_clears_stale_hover_only_when_the_cursor_left(self):
        btn = QPushButton("x")
        btn.resize(40, 30)
        btn.show()
        self.addCleanup(btn.deleteLater)
        self.qapp.processEvents()
        _enter(btn)
        QCursor.setPos(btn.mapToGlobal(QPoint(5000, 5000)))
        settle_hover(btn)
        self.assertFalse(btn.underMouse())
        settle_hover(None)

    def test_title_menus_do_not_leave_their_button_hovered(self):
        for name in ("file_menu_btn", "theme_menu_btn", "lang_menu_btn", "color_menu_btn", "settings_menu_btn"):
            btn = getattr(self.window, name)
            _enter(btn)
            QCursor.setPos(self.window.mapToGlobal(QPoint(450, 400)))  # menü dışında boş bir yer
            _close_popup_soon(self.qapp)
            btn.showMenu()  # Qt 6: menü popup() ile açılır, çağrı hemen döner
            deadline = time.monotonic() + 3
            while btn.menu().isVisible() and time.monotonic() < deadline:
                self.qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
            self.assertFalse(btn.menu().isVisible())
            self.qapp.processEvents()
            self.assertFalse(btn.underMouse(), f"{name}: menü kapandıktan sonra hover kalmamalı")


# ---------------------------------------------------------------------------------------------------------------
class RestoreTests(unittest.TestCase):
    def test_restoring_a_minimized_maximized_window_keeps_it_maximized(self):
        class Fake:
            def __init__(self, state):
                self.state, self.shown = state, False

            def windowState(self):  # noqa: N802
                return self.state

            def setWindowState(self, state):  # noqa: N802
                self.state = state

            def show(self):
                self.shown = True

        w = Fake(Qt.WindowState.WindowMaximized | Qt.WindowState.WindowMinimized)
        restore_window(w)
        self.assertTrue(w.state & Qt.WindowState.WindowMaximized)
        self.assertFalse(w.state & Qt.WindowState.WindowMinimized)
        self.assertTrue(w.shown)
        w = Fake(Qt.WindowState.WindowMinimized)
        restore_window(w)
        self.assertFalse(w.state & (Qt.WindowState.WindowMinimized | Qt.WindowState.WindowMaximized))

    def test_no_show_normal_on_the_restore_paths(self):
        root = _support.ROOT
        tray = (root / "src" / "gui" / "tray_manager.py").read_text(encoding="utf-8")
        app = (root / "src" / "app.py").read_text(encoding="utf-8")
        self.assertNotIn(".showNormal(", tray)
        self.assertNotIn("main_window.showNormal(", app)


# ---------------------------------------------------------------------------------------------------------------
class ToastAndUndoTests(_Window):
    def test_in_app_feedback_is_a_toast_not_a_system_notification(self):
        self._set(hotkeys=[_hk("Ctrl+Alt+1")])
        with mock.patch.object(self.window.notification_manager, "success") as notify:
            self.window.toggle_hotkey()
            self.window.toggle_hotkey()
        notify.assert_not_called()
        toast = self._toast()
        self.assertTrue(toast.isVisible())
        self.assertIn("Ctrl + Alt + 1", toast.text_label.text())

    def test_hidden_window_falls_back_to_the_notification(self):
        fake = mock.Mock()
        fake.show_toast.return_value = False
        mw._feedback(fake, "tamam")
        fake.notification_manager.success.assert_called_once_with("tamam")

    def test_undo_puts_a_deleted_hotkey_back_at_its_place_and_registers_it(self):
        self._set(hotkeys=[_hk("Ctrl+Alt+1"), _hk("Ctrl+Alt+2", SECRET, secret=True), _hk("Ctrl+Alt+3")])
        self.window.hotkeys_list.setCurrentRow(1)
        with mock.patch.object(mw.MessageBox, "question", return_value=YES):
            self.window.delete_hotkey()
        self.assertEqual([h["shortcut"] for h in self.settings.load_settings()["hotkeys"]], ["Ctrl+Alt+1", "Ctrl+Alt+3"])
        toast = self._toast()
        self.assertEqual(toast.action_button.text(), t("toast_undo", "tr"))
        self.assertNotIn(SECRET, toast.text_label.text())
        with mock.patch.object(self.window.hotkey_manager, "add_hotkey") as register:
            self.assertTrue(toast.trigger_action())
        hotkeys = self.settings.load_settings()["hotkeys"]
        self.assertEqual([h["shortcut"] for h in hotkeys], ["Ctrl+Alt+1", "Ctrl+Alt+2", "Ctrl+Alt+3"])
        self.assertEqual(hotkeys[1]["action_value"], SECRET)
        self.assertTrue(hotkeys[1]["is_secret"])
        register.assert_called_once()
        self.assertEqual(register.call_args.kwargs.get("secret"), True)
        self.assertEqual(self.window.hotkeys_list.selected_index(), 1, "geri gelen öğe seçili")
        self.assertIs(self.window.hotkeys_list.flashing_card(), self.window.hotkeys_list._cards[1])

    def test_undo_for_expansions_and_after_timeout_nothing_happens(self):
        self._set(expansions=[_exp("aa"), _exp("bb")])
        self.window.tabs.setCurrentIndex(1)
        self.window.expansions_list.setCurrentRow(0)
        with mock.patch.object(mw.MessageBox, "question", return_value=YES):
            self.window.delete_expansion()
        toast = self._toast()
        toast.dismiss()  # süre doldu
        self.assertFalse(toast.trigger_action())
        self.assertEqual([e["trigger"] for e in self.settings.load_settings()["expansions"]], ["bb"])
        with mock.patch.object(mw.MessageBox, "question", return_value=YES):
            self.window.delete_expansion(0)
        self._toast().trigger_action()
        self.assertEqual([e["trigger"] for e in self.settings.load_settings()["expansions"]], ["bb"])

    def test_undo_does_not_duplicate_a_re_added_entry(self):
        self._set(hotkeys=[_hk("Ctrl+Alt+1")])
        self.window.hotkeys_list.setCurrentRow(0)
        with mock.patch.object(mw.MessageBox, "question", return_value=YES):
            self.window.delete_hotkey()
        toast = self._toast()
        self.settings.add_hotkey("Ctrl+Alt+1", "text", "yeni")
        toast.trigger_action()
        hotkeys = self.settings.load_settings()["hotkeys"]
        self.assertEqual([h["action_value"] for h in hotkeys], ["yeni"])
        self.assertEqual(self._toast().property("kind"), "error")

    def test_delete_key_in_the_list_deletes_with_the_same_flow(self):
        self._set(hotkeys=[_hk("Ctrl+Alt+1"), _hk("Ctrl+Alt+2")])
        self.window.hotkeys_list.setCurrentRow(1)
        with mock.patch.object(mw.MessageBox, "question", return_value=YES) as ask:
            _key(self.window.hotkeys_list, Qt.Key.Key_Delete)
        ask.assert_called_once()
        self.assertEqual([h["shortcut"] for h in self.settings.load_settings()["hotkeys"]], ["Ctrl+Alt+1"])

    def test_added_item_is_selected_and_flashed(self):
        self._set(hotkeys=[_hk(f"Ctrl+Alt+{i}") for i in range(6)])

        class FakeDialog:
            def __init__(self, *_a, **_k):
                pass

            def exec(self):
                return QDialog.DialogCode.Accepted

            def get_data(self):
                return {"shortcut": "Ctrl+Shift+9", "action_type": "text", "action_value": "x", "enabled": False}

        with mock.patch.object(mw, "HotkeyDialog", FakeDialog):
            self.window.add_hotkey()
        listing = self.window.hotkeys_list
        self.assertEqual(listing.selected_index(), 6)
        self.assertIs(listing.flashing_card(), listing._cards[6])
        self.assertTrue(listing._cards[6].property("flash"))
        listing._end_flash()
        self.assertFalse(listing._cards[6].property("flash"))

    def test_export_success_offers_open_folder(self):
        self._set(hotkeys=[_hk("Ctrl+Alt+1")])
        dialog = mock.Mock()
        dialog.exec.return_value = QDialog.DialogCode.Accepted
        dialog.get_selected_options.return_value = {"hotkeys": True, "expansions": True, "theme": False,
                                                    "behavior": False, "update": False}
        with tempfile.TemporaryDirectory() as raw:
            target = os.path.join(raw, "yedek.json")
            with mock.patch.object(mw, "ImportExportDialog", return_value=dialog), \
                    mock.patch.object(mw.QFileDialog, "getSaveFileName", return_value=(target, "")), \
                    mock.patch.object(mw.MessageBox, "information", side_effect=AssertionError("kutu açılmamalı")), \
                    mock.patch.object(mw.MessageBox, "critical", side_effect=AssertionError("hata olmamalı")):
                self.window.export_settings()
            self.assertTrue(os.path.isfile(target))
            toast = self._toast()
            self.assertIn("yedek.json", toast.text_label.text())
            self.assertEqual(toast.action_button.text(), t("open_folder", "tr"))
            with mock.patch.object(mw, "_open_containing_folder") as open_folder:
                toast.trigger_action()
            open_folder.assert_called_once_with(target)


# ---------------------------------------------------------------------------------------------------------------
class FilterTests(_Window):
    def test_ctrl_f_filters_by_visible_text_only(self):
        self._set(hotkeys=[_hk("Ctrl+Alt+1", "Merhaba dünya"), _hk("Ctrl+Alt+2", SECRET, secret=True),
                           _hk("Ctrl+Alt+3", "Teşekkürler")])
        self.window.focus_filter()
        edit = self.window.hotkey_filter
        self.assertTrue(edit.isVisible())
        listing = self.window.hotkeys_list
        edit.setText("merhaba")
        self.assertEqual(listing.visible_indices(), [0])
        edit.setText("Ctrl + Alt")
        self.assertEqual(listing.visible_indices(), [0, 1, 2])
        edit.setText(SECRET[:6])
        self.assertEqual(listing.visible_indices(), [], "gizli değer aranarak bulunamaz")
        self.assertTrue(listing.is_showing_no_results())
        self.assertFalse(self.window.hotkey_delete_btn.isEnabled(), "görünmeyen öğe silinemez")
        self.assertEqual(self.window._resolve_hotkey_row(), -1)
        _key(edit, Qt.Key.Key_Escape)
        self.assertEqual(edit.text(), "")
        self.assertFalse(edit.isVisible())
        self.assertEqual(listing.visible_indices(), [0, 1, 2])
        self.assertFalse(listing.is_showing_no_results())

    def test_filter_survives_a_reload_and_drag_is_off_while_filtering(self):
        self._set(hotkeys=[_hk("Ctrl+Alt+1", "elma"), _hk("Ctrl+Alt+2", "armut"), _hk("Ctrl+Alt+3", "elma suyu")])
        self.window.focus_filter()
        self.window.hotkey_filter.setText("elma")
        self.window.load_hotkeys()
        listing = self.window.hotkeys_list
        self.assertEqual(listing.visible_indices(), [0, 2])
        self.assertFalse(listing._cards[1].isVisibleTo(listing))
        self.assertIn(listing.selected_index(), (0, 2))


class ListKeyboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.lst = CardListWidget()
        self.lst.resize(800, 300)  # iki sütun
        cards = []
        for i in range(5):
            card = HotkeyCard()
            card.set_data(f"Ctrl+{i}", "Metin Yaz", f"kart {i}", True)
            cards.append(card)
        self.lst.set_cards(cards, select_row=0)
        self.lst.show()
        self.app.processEvents()
        self.addCleanup(self.lst.close)

    def test_arrows_move_in_the_grid_enter_edits_delete_deletes(self):
        self.assertEqual(self.lst._columns, 2)
        _key(self.lst, Qt.Key.Key_Right)
        self.assertEqual(self.lst.selected_index(), 1)
        _key(self.lst, Qt.Key.Key_Down)
        self.assertEqual(self.lst.selected_index(), 3)
        _key(self.lst, Qt.Key.Key_Down)
        self.assertEqual(self.lst.selected_index(), 3, "son satırın altına inilmez")
        _key(self.lst, Qt.Key.Key_Left)
        self.assertEqual(self.lst.selected_index(), 2)
        _key(self.lst, Qt.Key.Key_End)
        self.assertEqual(self.lst.selected_index(), 4)
        _key(self.lst, Qt.Key.Key_Home)
        self.assertEqual(self.lst.selected_index(), 0)
        activated, deleted = [], []
        self.lst.activated.connect(activated.append)
        self.lst.delete_requested.connect(deleted.append)
        _key(self.lst, Qt.Key.Key_Return)
        _key(self.lst, Qt.Key.Key_Delete)
        self.assertEqual((activated, deleted), ([0], [0]))

    def test_dropped_card_lands_with_a_short_slide_only_when_animations_are_on(self):
        from PyQt6.QtWidgets import QLabel
        from src.gui import list_widgets
        card = self.lst._cards[3]
        self.assertTrue(150 <= list_widgets.LAND_MS <= 250)
        floating = QLabel(self.lst.viewport())
        floating.resize(card.size())
        with mock.patch.object(list_widgets, "_animations_enabled", return_value=True):
            self.lst._land(floating, QPoint(0, 0), card)
        anim = floating.findChild(list_widgets.QPropertyAnimation)
        self.assertIsNotNone(anim)
        self.assertEqual(anim.duration(), list_widgets.LAND_MS)
        self.assertEqual(anim.endValue(), card.mapTo(self.lst.viewport(), QPoint(0, 0)))
        anim.setCurrentTime(list_widgets.LAND_MS)
        other = QLabel(self.lst.viewport())
        with mock.patch.object(list_widgets, "_animations_enabled", return_value=False), \
                mock.patch.object(other, "deleteLater") as delete:
            self.lst._land(other, QPoint(0, 0), card)
        delete.assert_called_once()
        self.assertIsNone(other.findChild(list_widgets.QPropertyAnimation))

    def test_arrows_skip_filtered_cards(self):
        self.lst.set_filter("kart 3")
        self.assertEqual(self.lst.selected_index(), 3)
        self.lst.set_filter("kart")
        _key(self.lst, Qt.Key.Key_Left)
        self.assertEqual(self.lst.selected_index(), 2)


# ---------------------------------------------------------------------------------------------------------------
class GeometryTests(unittest.TestCase):
    SCREENS = [QRect(0, 0, 1920, 1040), QRect(1920, 0, 1280, 984)]

    def test_offscreen_window_is_brought_back_to_the_primary_screen(self):
        rect = window_geometry.clamp_to_screens(QRect(5000, 3000, 900, 560), self.SCREENS)
        self.assertEqual(rect.size().width(), 900)
        self.assertTrue(self.SCREENS[0].contains(rect))

    def test_partly_visible_window_is_pulled_in_and_shrunk_to_fit(self):
        rect = window_geometry.clamp_to_screens(QRect(2900, -50, 1600, 1200), self.SCREENS, (720, 460))
        self.assertTrue(self.SCREENS[1].contains(rect))
        self.assertEqual((rect.width(), rect.height()), (1280, 984))
        rect = window_geometry.clamp_to_screens(QRect(100, 100, 840, 520), self.SCREENS)
        self.assertEqual(rect, QRect(100, 100, 840, 520), "görünür pencereye dokunulmaz")

    def test_bad_saved_values_are_ignored(self):
        for raw in (None, "x", {}, {"x": 1, "y": 2, "w": 0, "h": 5}, {"x": "a", "y": 0, "w": 1, "h": 1}):
            self.assertIsNone(window_geometry.geometry_from_dict(raw))
        rect, maximized = window_geometry.geometry_from_dict({"x": 1, "y": 2, "w": 3, "h": 4, "maximized": True})
        self.assertEqual((rect, maximized), (QRect(1, 2, 3, 4), True))


class GeometryPersistTests(_Window):
    def test_size_position_and_maximized_survive_a_restart(self):
        from src.core.hotkey_manager import HotkeyManager
        from src.gui.notification_manager import NotificationManager
        from src.utils.theme_manager import ThemeManager
        avail = QApplication.primaryScreen().availableGeometry()
        size = (min(930, avail.width() - 40), min(600, avail.height() - 30))  # offscreen ekranı 800x600
        self.window.showNormal()
        self.window.setGeometry(avail.x() + 20, avail.y() + 15, *size)
        self.qapp.processEvents()
        self.window.save_window_geometry()
        saved = self.settings.load_settings()[window_geometry.SETTINGS_KEY]
        self.assertEqual((saved["w"], saved["h"], saved["maximized"]), (*size, False))
        data = self.settings.load_settings()
        data[window_geometry.SETTINGS_KEY] = dict(saved, maximized=True)
        self.settings.save_settings(data)
        again = mw.MainWindow(self.settings, ThemeManager(self.qapp), HotkeyManager(), NotificationManager(), None)
        self.addCleanup(again.deleteLater)
        self.assertEqual((again.normalGeometry().width(), again.normalGeometry().height()), size)
        self.assertTrue(again.windowState() & Qt.WindowState.WindowMaximized)

    def test_hiding_to_the_tray_saves_the_geometry(self):
        self.window.showNormal()
        self.window.resize(760, 520)
        self.qapp.processEvents()
        self.window.hide()
        self.assertEqual(self.settings.load_settings()[window_geometry.SETTINGS_KEY]["w"], 760)
        self.window.show()
        self.qapp.processEvents()


# ---------------------------------------------------------------------------------------------------------------
class TitleDragTests(_Window):
    def _mouse(self, kind, global_pos, held=True):
        bar = self.window.findChild(mw.QFrame, "title_bar")
        local = bar.mapFromGlobal(global_pos)
        button = Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton
        buttons = Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton
        event = QMouseEvent(kind, QPointF(local), QPointF(global_pos), button, buttons, Qt.KeyboardModifier.NoModifier)
        handler = {QEvent.Type.MouseButtonPress: self.window.title_bar_mouse_press,
                   QEvent.Type.MouseMove: self.window.title_bar_mouse_move,
                   QEvent.Type.MouseButtonRelease: self.window.title_bar_mouse_release}[kind]
        handler(event)

    def test_dragging_the_title_bar_hands_the_move_to_windows(self):
        self.window.showNormal()
        self.qapp.processEvents()
        start = self.window.mapToGlobal(QPoint(300, 15))
        with mock.patch.object(self.window, "_start_system_move", return_value=True) as system_move:
            self._mouse(QEvent.Type.MouseButtonPress, start)
            self._mouse(QEvent.Type.MouseMove, start + QPoint(1, 0))
            system_move.assert_not_called()  # tıklama sayılır
            self._mouse(QEvent.Type.MouseMove, start + QPoint(40, 0))
            system_move.assert_called_once()
            self._mouse(QEvent.Type.MouseMove, start + QPoint(80, 0))
            system_move.assert_called_once()
        self.assertFalse(self.window.dragging)
        self._mouse(QEvent.Type.MouseButtonRelease, start + QPoint(80, 0), held=False)

    def test_without_system_move_the_window_still_moves(self):
        self.window.showNormal()
        self.qapp.processEvents()
        before = self.window.pos()
        start = self.window.mapToGlobal(QPoint(300, 15))
        with mock.patch.object(self.window, "_start_system_move", return_value=False):
            self._mouse(QEvent.Type.MouseButtonPress, start)
            self._mouse(QEvent.Type.MouseMove, start + QPoint(50, 20))
            self._mouse(QEvent.Type.MouseButtonRelease, start + QPoint(50, 20), held=False)
        self.assertEqual(self.window.pos(), before + QPoint(50, 20))


if __name__ == "__main__":
    unittest.main()
