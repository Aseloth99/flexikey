"""Gizli (parola) öğeler: diskte şifreli, listede/bildirimde görünmez, dışa aktarırken sorulur.

Gerçek %APPDATA%'ya dokunulmaz (geçici dizin / geçici profil); klavye ve ctypes sahtedir. DPAPI gerçek çağrılır
(yalnızca Windows'ta; başka sistemde ilgili testler atlanır).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import _support
from _manager_support import ManagerTestCase
from test_settings_manager import SettingsTestCase

from PyQt6.QtWidgets import QApplication

from src.gui import main_window as mw
from src.gui.message_box import MessageBox
from src.utils import locales, secret_store
from src.utils.locales import t
from src.utils.settings_manager import (
    SettingsManager, exportable_records, is_locked_secret, prepare_import, register_saved_items, secret_count,
)

SECRET = "Parola!9 çğ"
needs_dpapi = unittest.skipUnless(secret_store.available(), "DPAPI yalnızca Windows'ta")
ALL = {"hotkeys": True, "expansions": True, "theme": False, "behavior": False, "update": False}


def _exp(trigger="pw", value=SECRET, secret=True, **extra):
    rec = {"trigger": trigger, "replacement": value, "enabled": True, "is_rich": False}
    if secret:
        rec["is_secret"] = True
    rec.update(extra)
    return rec


def _hk(shortcut="Ctrl+1", value=SECRET, secret=True, action="text", **extra):
    rec = {"shortcut": shortcut, "action_type": action, "action_value": value, "enabled": True, "is_rich": False}
    if secret:
        rec["is_secret"] = True
    rec.update(extra)
    return rec


@needs_dpapi
class SecretStoreTests(unittest.TestCase):
    def test_round_trip_keeps_every_character(self):
        for text in (SECRET, "a", " boşluklu ", "😀 emoji", "x" * 5000):
            blob = secret_store.protect(text)
            self.assertTrue(secret_store.is_blob(blob))
            if len(text) >= 8:
                self.assertNotIn(text[:8], blob)
            self.assertEqual(secret_store.unprotect(blob), text)

    def test_same_text_gives_different_blobs_but_both_open(self):
        a, b = secret_store.protect("aynı"), secret_store.protect("aynı")
        self.assertNotEqual(a, b)
        self.assertEqual(secret_store.unprotect(a), secret_store.unprotect(b))

    def test_broken_or_foreign_data_is_not_opened(self):
        blob = secret_store.protect(SECRET)
        self.assertIsNone(secret_store.unprotect(blob[:-8] + "AAAAAAAA"))
        self.assertIsNone(secret_store.unprotect("dpapi1:%%%"))
        self.assertIsNone(secret_store.unprotect("düz metin"))
        self.assertIsNone(secret_store.protect(""))


@needs_dpapi
class SecretSettingsTests(SettingsTestCase):
    def test_file_never_holds_the_secret_but_loading_gives_it_back(self):
        self.manager.add_expansion("pw", SECRET, True, False, is_secret=True)
        self.manager.add_hotkey("Ctrl+1", "text", SECRET + "2", True, False, is_secret=True)
        raw = self.read_bytes()
        self.assertNotIn(SECRET.encode("utf-8"), raw)
        self.assertNotIn(SECRET[:6].encode("utf-8"), raw)
        data = self.read_json()
        self.assertTrue(data["expansions"][0]["replacement"].startswith(secret_store.PREFIX))
        self.assertTrue(data["hotkeys"][0]["action_value"].startswith(secret_store.PREFIX))
        loaded = self.manager.load_settings()
        self.assertEqual(loaded["expansions"][0]["replacement"], SECRET)
        self.assertEqual(loaded["hotkeys"][0]["action_value"], SECRET + "2")
        self.assertTrue(loaded["expansions"][0]["is_secret"])

    def test_ordinary_items_stay_readable_in_the_file(self):
        self.manager.add_expansion("mail", "merhaba dünya", True, False)
        self.manager.add_expansion("pw", SECRET, True, False, is_secret=True)
        data = self.read_json()
        self.assertEqual(data["expansions"][0]["replacement"], "merhaba dünya")
        self.assertNotIn("is_secret", data["expansions"][0])

    def test_the_backup_copy_is_sealed_too(self):
        self.manager.add_expansion("pw", SECRET, True, False, is_secret=True)
        self.manager.set_theme("dark")  # ikinci kayıt: ilki .bak olur
        self.assertTrue(os.path.exists(self.manager.backup_file))
        self.assertNotIn(SECRET.encode("utf-8"), self.read_bytes(self.manager.backup_file))

    def test_the_flag_only_means_something_for_plain_text(self):
        self.manager.add_hotkey("Ctrl+2", "open_url", "https://a.b", True, False, is_secret=True)
        self.manager.add_hotkey("Ctrl+3", "text", "<b>x</b>", True, True, is_secret=True)
        self.manager.add_expansion("rich", "<b>x</b>", True, True, is_secret=True)
        for record in self.read_json()["hotkeys"] + self.read_json()["expansions"]:
            self.assertNotIn("is_secret", record)

    def test_editing_a_secret_re_seals_the_new_value(self):
        self.manager.add_expansion("pw", SECRET, True, False, is_secret=True)
        old = self.read_json()["expansions"][0]["replacement"]
        self.manager.update_expansion("pw", _exp("pw", "yeni değer"))
        new = self.read_json()["expansions"][0]["replacement"]
        self.assertNotEqual(old, new)
        self.assertEqual(self.manager.load_settings()["expansions"][0]["replacement"], "yeni değer")

    def test_unreadable_secret_is_kept_untouched_and_reported(self):
        self.manager.add_expansion("pw", SECRET, True, False, is_secret=True)
        self.manager.add_hotkey("Ctrl+1", "text", SECRET, True, False, is_secret=True)
        before = self.read_json()
        SettingsManager.pop_warnings()
        with mock.patch.object(secret_store, "unprotect", return_value=None):
            loaded = SettingsManager(settings_path=self.path).load_settings()
            exp, hk = loaded["expansions"][0], loaded["hotkeys"][0]
            self.assertEqual(exp["replacement"], "")
            self.assertTrue(is_locked_secret(exp) and is_locked_secret(hk))
            self.assertIn(("secret_locked", "2"), SettingsManager.pop_warnings())
            # an unrelated save while locked must not destroy the encrypted values
            self.manager.set_theme("light")
        after = self.read_json()
        self.assertEqual(after["expansions"], before["expansions"])
        self.assertEqual(after["hotkeys"], before["hotkeys"])
        # and they open again where they can be opened
        self.assertEqual(self.manager.load_settings()["expansions"][0]["replacement"], SECRET)

    def test_locked_items_are_not_registered(self):
        self.manager.add_expansion("pw", SECRET, True, False, is_secret=True)
        with mock.patch.object(secret_store, "unprotect", return_value=None):
            loaded = self.manager.load_settings()
        hotkey_manager = mock.Mock()
        counts = register_saved_items(loaded, hotkey_manager)
        hotkey_manager.add_expansion.assert_not_called()
        self.assertEqual(counts["expansions_failed"], 0)

    def test_saved_secret_hotkey_is_registered_as_secret(self):
        self.manager.add_hotkey("Ctrl+1", "text", SECRET, True, False, is_secret=True)
        self.manager.add_hotkey("Ctrl+2", "text", "açık", True, False)
        hotkey_manager = mock.Mock()
        register_saved_items(self.manager.load_settings(), hotkey_manager)
        calls = {c.args[0]: c.kwargs for c in hotkey_manager.add_hotkey.call_args_list}
        self.assertTrue(calls["Ctrl+1"].get("secret"))
        self.assertFalse(calls["Ctrl+2"].get("secret", False))

    def test_where_encryption_is_not_possible_the_value_is_kept_but_still_flagged(self):
        with mock.patch.object(secret_store, "protect", return_value=None):
            self.manager.add_expansion("pw", SECRET, True, False, is_secret=True)
        data = self.read_json()["expansions"][0]
        self.assertEqual(data["replacement"], SECRET)
        self.assertTrue(data["is_secret"])
        self.assertEqual(self.manager.load_settings()["expansions"][0]["replacement"], SECRET)


class SecretImportExportTests(unittest.TestCase):
    def test_import_keeps_the_flag_only_where_it_is_valid(self):
        plan = prepare_import({
            "hotkeys": [_hk("Ctrl+1"), _hk("Ctrl+2", "https://a.b", action="open_url"), _hk("Ctrl+3", "<b>x</b>", is_rich=True)],
            "expansions": [_exp("a"), _exp("b", "<i>x</i>", is_rich=True)],
        }, ALL)
        hotkeys = {h["shortcut"]: h for h in plan["hotkeys"]}
        self.assertTrue(hotkeys["Ctrl+1"]["is_secret"])
        self.assertNotIn("is_secret", hotkeys["Ctrl+2"])
        self.assertNotIn("is_secret", hotkeys["Ctrl+3"])
        exps = {e["trigger"]: e for e in plan["expansions"]}
        self.assertTrue(exps["a"]["is_secret"])
        self.assertNotIn("is_secret", exps["b"])

    def test_secret_count_ignores_locked_ones(self):
        records = [_exp("a"), _exp("b", secret=False), _exp("c", "", secret_blob="dpapi1:xx")]
        self.assertEqual(secret_count(records), 1)

    def test_export_without_permission_leaves_secrets_out_entirely(self):
        records = [_exp("a"), _exp("b", "açık", secret=False)]
        self.assertEqual([r["trigger"] for r in exportable_records(records, False)], ["b"])

    def test_export_with_permission_writes_values_but_never_the_internal_blob(self):
        records = [_exp("a"), _exp("c", "", secret_blob="dpapi1:xx")]
        out = exportable_records(records, True)
        self.assertEqual([r["trigger"] for r in out], ["a"])
        self.assertEqual(out[0]["replacement"], SECRET)
        self.assertNotIn("secret_blob", out[0])
        self.assertNotIn("secret_blob", json.dumps(exportable_records([_exp("d", secret_blob="x")], True)))


class SecretManagerTests(ManagerTestCase):
    def run_text(self, shortcut, value):
        self.manager.execute_action("text", value, shortcut, False)
        from src.core import hotkey_manager
        hotkey_manager.INPUT_INJECTOR.wait_idle()

    def test_secret_text_is_typed_but_never_named_in_the_notification(self):
        self.manager.add_hotkey("Ctrl+9", "text", SECRET, False, secret=True)
        self.run_text("Ctrl+9", SECRET)
        self.kb.write.assert_called_with(SECRET)
        kinds = [(k, text) for k, text in self.events if k == "text"]
        self.assertEqual(len(kinds), 1)
        self.assertNotIn(SECRET[:5], kinds[0][1])
        self.assertEqual(kinds[0][1], t("notif_written_secret", self.manager.lang))

    def test_an_ordinary_text_hotkey_still_names_its_text(self):
        self.manager.add_hotkey("Ctrl+8", "text", "merhaba", False)
        self.run_text("Ctrl+8", "merhaba")
        self.assertIn("merhaba", [text for k, text in self.events if k == "text"][0])

    def test_removing_or_replacing_the_hotkey_forgets_the_secret_mark(self):
        self.manager.add_hotkey("Ctrl+9", "text", SECRET, False, secret=True)
        self.manager.remove_hotkey("Ctrl+9")
        self.manager.add_hotkey("Ctrl+9", "text", "artık açık", False)
        self.run_text("Ctrl+9", "artık açık")
        self.assertIn("artık açık", [text for k, text in self.events if k == "text"][0])

    def test_no_log_line_holds_the_secret(self):
        self.manager.add_hotkey("Ctrl+9", "text", SECRET, False, secret=True)
        self.manager.add_expansion("pw", SECRET, False)
        self.run_text("Ctrl+9", SECRET)
        self.assertFalse([line for _, line in self.log_lines if SECRET[:5] in line])


class _Qt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication([])

    def setUp(self):
        self.addCleanup(MessageBox.set_test_hook, None)
        self.addCleanup(locales.set_preferred_language, locales.get_preferred_language())
        locales.set_preferred_language("tr")


class SecretDialogTests(_Qt):
    def test_hotkey_dialog_secret_mode_moves_the_text_to_a_dotted_line(self):
        d = mw.HotkeyDialog(None)
        d.text_input.setPlainText("satır1\nsatır2")
        d.secret_check.setChecked(True)
        self.assertEqual(d.secret_row.text(), "satır1satır2")
        self.assertEqual(d.text_input.toPlainText(), "", "düz metin kutusunda kalmamalı")
        self.assertTrue(d.text_input.isHidden() and not d.secret_row.isHidden())
        self.assertEqual(d.secret_row.edit.echoMode(), mw.QLineEdit.EchoMode.Password)
        self.assertFalse(d.rich_text_check.isEnabled())
        d.shortcut_input.set_shortcut("Ctrl+Alt+1")
        data = d.get_data()
        self.assertEqual((data["action_type"], data["action_value"], data["is_secret"], data["is_rich"]),
                         ("text", "satır1satır2", True, False))

    def test_hotkey_dialog_can_reveal_and_hide_on_demand(self):
        d = mw.HotkeyDialog(None)
        d.secret_check.setChecked(True)
        d.secret_row.setText(SECRET)
        d.secret_row.toggle_btn.setChecked(True)
        self.assertEqual(d.secret_row.edit.echoMode(), mw.QLineEdit.EchoMode.Normal)
        self.assertEqual(d.secret_row.toggle_btn.text(), t("secret_hide", "tr"))
        d.secret_row.toggle_btn.setChecked(False)
        self.assertEqual(d.secret_row.edit.echoMode(), mw.QLineEdit.EchoMode.Password)

    def test_editing_an_existing_secret_opens_hidden(self):
        d = mw.HotkeyDialog(None, _hk())
        self.assertTrue(d.secret_check.isChecked())
        self.assertEqual(d.secret_row.text(), SECRET)
        self.assertEqual(d.secret_row.edit.echoMode(), mw.QLineEdit.EchoMode.Password)
        self.assertEqual(d.text_input.toPlainText(), "")
        self.assertEqual(d.get_data()["action_value"], SECRET)

    def test_secret_value_is_not_trimmed(self):
        d = mw.HotkeyDialog(None)
        d.secret_check.setChecked(True)
        d.secret_row.setText("  boşluk  ")
        d.shortcut_input.set_shortcut("Ctrl+Alt+1")
        self.assertEqual(d.get_data()["action_value"], "  boşluk  ")

    def test_turning_the_mode_off_returns_the_text_and_forgets_the_flag(self):
        d = mw.HotkeyDialog(None, _hk())
        d.secret_check.setChecked(False)
        self.assertEqual(d.text_input.toPlainText(), SECRET)
        self.assertEqual(d.secret_row.text(), "")
        self.assertTrue(d.rich_text_check.isEnabled())
        d.shortcut_input.set_shortcut("Ctrl+Alt+1")
        self.assertNotIn("is_secret", d.get_data())

    def test_another_action_type_never_carries_the_flag(self):
        d = mw.HotkeyDialog(None)
        d.secret_check.setChecked(True)
        d.secret_row.setText(SECRET)
        d.action_type.setCurrentIndex(2)  # web sitesi
        d.url_input.setText("https://a.b")
        d.shortcut_input.set_shortcut("Ctrl+Alt+1")
        data = d.get_data()
        self.assertEqual(data["action_type"], "open_url")
        self.assertNotIn("is_secret", data)
        self.assertTrue(d.secret_check.isHidden(), "yalnızca metin yazarken gösterilir")

    def test_expansion_dialog_secret_mode(self):
        d = mw.ExpansionDialog(None)
        d.trigger_input.setText("pw")
        d.replacement_text.setPlainText("abc")
        d.secret_check.setChecked(True)
        self.assertEqual(d.secret_row.text(), "abc")
        self.assertFalse(d.rich_text_exp_check.isEnabled())
        self.assertFalse(d.paste_plain_btn.isEnabled())
        d.secret_row.setText(SECRET)
        data = d.get_data()
        self.assertEqual((data["replacement"], data["is_secret"], data["is_rich"]), (SECRET, True, False))
        again = mw.ExpansionDialog(None, _exp())
        self.assertTrue(again.secret_check.isChecked())
        self.assertEqual(again.secret_row.edit.echoMode(), mw.QLineEdit.EchoMode.Password)
        self.assertEqual(again.replacement_text.toPlainText(), "")
        again.secret_check.setChecked(False)
        self.assertNotIn("is_secret", again.get_data())


class SecretListTests(_Qt):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
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
        cls.window.show()
        cls.qapp.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls.window.deleteLater()
        cls.qapp.processEvents()
        cls._profile.__exit__(None, None, None)

    def _texts(self, widget):
        return " | ".join(
            f"{c._kbd_full} {c._primary_full} {c._secondary_full} {c.toolTip()}" for c in widget._cards
        )

    def test_cards_show_dots_not_the_value(self):
        data = self.settings.load_settings()
        data.update(hotkeys=[_hk("Ctrl+Alt+7"), _hk("Ctrl+Alt+8", "açıkmetin", secret=False)],
                    expansions=[_exp("pw"), _exp("mail", "ben@örnek.com", secret=False)])
        self.settings.save_settings(data)
        self.window.load_hotkeys()
        self.window.load_expansions()
        self.qapp.processEvents()
        hot, exp = self._texts(self.window.hotkeys_list), self._texts(self.window.expansions_list)
        for text in (hot, exp):
            self.assertNotIn(SECRET[:5], text)
        self.assertIn(t("secret_mask", "tr"), hot)
        self.assertIn(t("chip_secret", "tr"), hot)
        self.assertIn("açıkmetin", hot, "gizli olmayan kayıt eskisi gibi görünür")
        self.assertIn(t("secret_mask", "tr"), exp)
        self.assertIn("ben@örnek.com", exp)

    def test_a_locked_secret_shows_dots_and_does_not_break_the_list(self):
        data = self.settings.load_settings()
        data.update(hotkeys=[], expansions=[_exp("pw", "", secret_blob="dpapi1:xx")])
        self.settings.save_settings(data)
        self.window.load_expansions()
        self.qapp.processEvents()
        self.assertEqual(len(self.window.expansions_list._cards), 1)

    def test_export_asks_before_writing_secrets_and_honours_no(self):
        data = self.settings.load_settings()
        data.update(hotkeys=[_hk("Ctrl+Alt+7")], expansions=[_exp("pw"), _exp("mail", "ben@örnek.com", secret=False)])
        self.settings.save_settings(data)
        asked = []

        def run(answer):
            asked.clear()
            with tempfile.TemporaryDirectory() as raw:
                target = os.path.join(raw, "out.json")
                dialog = mock.Mock()
                dialog.exec.return_value = mw.QDialog.DialogCode.Accepted
                dialog.get_selected_options.return_value = ALL
                with mock.patch.object(mw, "ImportExportDialog", return_value=dialog), \
                        mock.patch.object(mw.QFileDialog, "getSaveFileName", return_value=(target, "")), \
                        mock.patch.object(mw.MessageBox, "question", side_effect=lambda *a, **k: asked.append(a[2]) or answer), \
                        mock.patch.object(mw.MessageBox, "information"):
                    self.window.export_settings()
                with open(target, encoding="utf-8") as handle:
                    return json.load(handle)

        no = run(MessageBox.StandardButton.No)
        self.assertEqual(len(asked), 1)
        self.assertIn("2", asked[0], "kaç gizli öğe olduğu söylenir")
        self.assertEqual(no["hotkeys"], [])
        self.assertEqual([e["trigger"] for e in no["expansions"]], ["mail"])
        self.assertNotIn(SECRET[:5], json.dumps(no, ensure_ascii=False))

        yes = run(MessageBox.StandardButton.Yes)
        self.assertEqual(yes["hotkeys"][0]["action_value"], SECRET)
        self.assertTrue(yes["hotkeys"][0]["is_secret"])
        self.assertEqual(len(yes["expansions"]), 2)

    def test_export_without_secrets_does_not_ask(self):
        data = self.settings.load_settings()
        data.update(hotkeys=[], expansions=[_exp("mail", "ben@örnek.com", secret=False)])
        self.settings.save_settings(data)
        with tempfile.TemporaryDirectory() as raw:
            dialog = mock.Mock()
            dialog.exec.return_value = mw.QDialog.DialogCode.Accepted
            dialog.get_selected_options.return_value = ALL
            with mock.patch.object(mw, "ImportExportDialog", return_value=dialog), \
                    mock.patch.object(mw.QFileDialog, "getSaveFileName", return_value=(os.path.join(raw, "o.json"), "")), \
                    mock.patch.object(mw.MessageBox, "question", side_effect=AssertionError("sorulmamalı")), \
                    mock.patch.object(mw.MessageBox, "information"):
                self.window.export_settings()


class SecretTextsTests(unittest.TestCase):
    def test_every_new_text_exists_in_both_languages(self):
        keys = ("chip_secret", "secret_label", "secret_tip", "secret_placeholder", "secret_show", "secret_hide",
                "secret_mask", "notif_written_secret", "settings_warn_secret_locked", "export_secret_title",
                "export_secret_ask", "help_expansion_step5")
        for lang in ("tr", "en"):
            for key in keys:
                self.assertNotEqual(t(key, lang), key, (lang, key))
        self.assertIn("{}", t("settings_warn_secret_locked", "tr"))
        self.assertIn("{}", t("export_secret_ask", "en"))

    def test_the_warning_reaches_the_user_with_its_count(self):
        from src.utils.settings_manager import format_settings_warning
        self.assertIn("3", format_settings_warning("secret_locked", "3", "tr"))


if __name__ == "__main__":
    unittest.main()
