"""Ice/disa aktarma ve onay penceresi akislari (offscreen Qt; MessageBox.exec ve dosya diyaloglari mock'lanir).

MainWindow olusturulmaz: yontemler, gerekli alanlara sahip kucuk bir QWidget ile cagrilir.
Boylece MessageBox/enum kullaniminda calisma zamani hatasi olmadigi da dogrulanir.
"""

from __future__ import annotations

import json
import os
import tempfile
import types
import unittest
from unittest import mock

import _support
from _support import capture_logs
from _manager_support import ManagerTestCase

from PyQt6.QtWidgets import QApplication, QDialog, QWidget
from src.gui.message_box import MessageBox

from src.gui import main_window
from src.utils.settings_manager import SettingsManager

_APP = QApplication.instance() or QApplication([])
ALL = {"hotkeys": True, "expansions": True, "theme": True, "behavior": True, "update": True}
YES, NO = MessageBox.StandardButton.Yes, MessageBox.StandardButton.No


class FakeWindow(QWidget):
    lang = "tr"

    def __init__(self, manager):
        super().__init__()
        self.settings_manager = manager
        self.notification_manager = mock.Mock()
        self.reloaded = 0

    def reload_settings(self):
        self.reloaded += 1

    def get_category_name_turkish(self, category):
        return category


class FakeOptionsDialog:
    def __init__(self, parent, is_export=True):
        pass

    def exec(self):
        return QDialog.DialogCode.Accepted

    def get_selected_options(self):
        return dict(ALL)


class UiFlowTestCase(unittest.TestCase):
    def setUp(self):
        patcher, self.log_lines = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        SettingsManager.pop_warnings()
        self.manager = SettingsManager(settings_path=os.path.join(self.dir, "config.json"))
        self.window = FakeWindow(self.manager)
        self.addCleanup(self.window.deleteLater)

        self.boxes = []
        self.answer = YES

        def fake_exec(box):
            self.boxes.append(box)
            return self.answer

        for p in (
            mock.patch.object(main_window, "ImportExportDialog", FakeOptionsDialog),
            mock.patch.object(MessageBox, "exec", fake_exec),
            mock.patch.object(MessageBox, "information"),
            mock.patch.object(MessageBox, "warning"),
            mock.patch.object(MessageBox, "critical"),
        ):
            p.start()
            self.addCleanup(p.stop)

    def write_import_file(self, data):
        path = os.path.join(self.dir, "import.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        return path

    def run_import(self, data):
        path = self.write_import_file(data)
        with mock.patch.object(main_window.QFileDialog, "getOpenFileName", return_value=(path, "")):
            main_window.MainWindow.import_settings(self.window)


class ImportFlowTests(UiFlowTestCase):
    IMPORT = {
        "hotkeys": [
            {"shortcut": "Ctrl+1", "action_type": "text", "action_value": "merhaba"},
            {"shortcut": "Ctrl+2", "action_type": "command", "action_value": "bilgisayari_kapat"},
            {"shortcut": "Ctrl+3", "action_type": "run_program", "action_value": "powershell -enc AAAA"},
            {"shortcut": "Ctrl+4", "action_type": "komik_tur", "action_value": "x"},
            {"action_type": "text", "action_value": "shortcut yok"},
        ],
        "expansions": [{"trigger": "mt", "replacement": "x"}],
        "update_url": "http://evil.example/u",
        "theme": "dark",
    }

    def test_confirmation_shows_action_list_and_risk_counts(self):
        self.run_import(self.IMPORT)
        self.assertEqual(len(self.boxes), 1)
        box = self.boxes[0]
        info, detail = box.informativeText(), box.detailedText()
        self.assertIn("3 kısayol", info)                         # yalniz gecerli kayitlar
        self.assertIn("2 kayıt atlanacak", info)
        self.assertIn("2 eylem riskli", info)                    # kapat + powershell
        self.assertIn("Bilgisayarı Kapat", info)
        self.assertIn("powershell -enc AAAA", detail)
        self.assertIn("update_url", info)                        # http update_url yoksayilacak
        self.assertEqual(box.icon(), MessageBox.Icon.Warning)
        self.assertEqual(box.defaultButton(), box.button(NO))

    def test_accepting_applies_only_validated_values_under_lock(self):
        self.run_import(self.IMPORT)
        settings = self.manager.load_settings()
        self.assertEqual([h["shortcut"] for h in settings["hotkeys"]], ["Ctrl+1", "Ctrl+2", "Ctrl+3"])
        self.assertEqual(settings["theme"], "dark")
        self.assertEqual(settings["update_url"], "")             # http adresi uygulanmadi
        self.assertEqual([e["trigger"] for e in settings["expansions"]], ["mt"])
        self.assertEqual(self.window.reloaded, 1)

    def test_declining_changes_nothing(self):
        self.manager.save_settings({**self.manager.load_settings(), "theme": "light"})
        before = self.manager.load_settings()
        self.answer = NO
        self.run_import(self.IMPORT)
        self.assertEqual(self.manager.load_settings(), before)
        self.assertEqual(self.window.reloaded, 0)

    def test_safe_import_uses_question_icon_without_risk_text(self):
        self.run_import({"hotkeys": [{"shortcut": "Ctrl+1", "action_type": "text", "action_value": "a"}]})
        box = self.boxes[0]
        self.assertEqual(box.icon(), MessageBox.Icon.Question)
        self.assertNotIn("riskli", box.informativeText())

    def test_non_dict_file_reports_error_and_changes_nothing(self):
        self.run_import([1, 2, 3])
        MessageBox.critical.assert_called_once()
        self.assertEqual(self.boxes, [])
        self.assertFalse(os.path.exists(self.manager.settings_file))

    def test_invalid_json_shows_invalid_json_message(self):
        path = os.path.join(self.dir, "bad.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{ bozuk")
        with mock.patch.object(main_window.QFileDialog, "getOpenFileName", return_value=(path, "")):
            main_window.MainWindow.import_settings(self.window)
        MessageBox.critical.assert_called_once()
        self.assertIn("JSON", MessageBox.critical.call_args.args[2])


class ExportFlowTests(UiFlowTestCase):
    def test_export_is_atomic_and_filtered(self):
        self.manager.add_hotkey("Ctrl+1", "text", "çğıöşü", True, False)
        target = os.path.join(self.dir, "out", "export.json")
        os.makedirs(os.path.dirname(target))
        with mock.patch.object(main_window.QFileDialog, "getSaveFileName", return_value=(target, "")):
            main_window.MainWindow.export_settings(self.window)
        with open(target, encoding="utf-8") as handle:
            exported = json.load(handle)
        self.assertEqual(exported["hotkeys"][0]["action_value"], "çğıöşü")
        self.assertEqual([n for n in os.listdir(os.path.dirname(target)) if n.endswith(".tmp")], [])
        MessageBox.critical.assert_not_called()

    def test_failed_export_keeps_previous_file(self):
        target = os.path.join(self.dir, "export.json")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write('{"onceki": true}')
        with mock.patch.object(main_window.QFileDialog, "getSaveFileName", return_value=(target, "")), \
                mock.patch("src.utils.helpers.os.replace", side_effect=OSError("disk dolu")):
            main_window.MainWindow.export_settings(self.window)
        with open(target, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), '{"onceki": true}')       # yarim/bozuk dosya yok
        MessageBox.critical.assert_called_once()
        self.assertEqual([n for n in os.listdir(self.dir) if n.endswith(".tmp")], [])


class DefaultConfirmDialogTests(ManagerTestCase):
    """HotkeyManager._ask_user_to_confirm: gercek MessageBox olusturulur, exec mock'lanir."""

    def run_confirm(self, answer):
        shown = []

        def fake_exec(box):
            shown.append(box)
            return answer

        with mock.patch.object(MessageBox, "exec", fake_exec):
            result = self.manager._ask_user_to_confirm("bilgisayari_kapat")
        return result, shown

    def test_yes_confirms_no_declines(self):
        self.assertTrue(self.run_confirm(YES)[0])
        self.assertFalse(self.run_confirm(NO)[0])

    def test_dialog_defaults_to_no_and_names_the_action(self):
        _, shown = self.run_confirm(NO)
        box = shown[0]
        self.assertEqual(box.defaultButton(), box.button(NO))
        self.assertEqual(box.escapeButton(), box.button(NO))
        self.assertIn("Bilgisayarı Kapat", box.text())
        self.assertEqual(box.icon(), MessageBox.Icon.Warning)

    def test_recycle_bin_dialog_mentions_permanent_deletion(self):
        shown = []
        with mock.patch.object(MessageBox, "exec", lambda box: (shown.append(box), NO)[1]):
            self.manager._ask_user_to_confirm("cop_kutusunu_bosalt")
        self.assertIn("kalıcı", shown[0].informativeText())

    def test_dialog_refused_outside_gui_thread(self):
        import threading
        result = []
        thread = threading.Thread(target=lambda: result.append(self.manager._ask_user_to_confirm("bilgisayari_kapat")))
        def must_not_run(box):
            raise AssertionError("GUI disi")

        with mock.patch.object(MessageBox, "exec", must_not_run):
            thread.start()
            thread.join(5)
        self.assertEqual(result, [False])


class StartupWarningTests(unittest.TestCase):
    def test_settings_warnings_are_shown_via_tray_even_if_notifications_disabled(self):
        from src.app import FlexiKeyApp
        SettingsManager.pop_warnings()
        SettingsManager._warn("corrupt_defaults", r"C:\x\config.json.corrupt-1")
        app = object.__new__(FlexiKeyApp)
        app.main_window = mock.Mock(lang="tr")
        app.tray_manager = mock.Mock()
        patcher, _ = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)
        app._show_settings_warnings()
        app.tray_manager.tray_icon.showMessage.assert_called_once()
        title, message = app.tray_manager.tray_icon.showMessage.call_args.args[:2]
        self.assertIn("Uyarısı", title)   # başlıklar her kelime büyük harf (Title Case)
        self.assertIn(r"C:\x\config.json.corrupt-1", message)
        app._show_settings_warnings()                               # ikinci cagri tekrar gostermez
        app.tray_manager.tray_icon.showMessage.assert_called_once()


if __name__ == "__main__":
    unittest.main()
