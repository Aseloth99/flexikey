"""Ayar kaydi: atomik yazim, yedek, bozuk dosya kurtarma, sig kopya, kilit, sema dogrulama.

Hicbir test %APPDATA%'ya dokunmaz: SettingsManager(settings_path=<gecici dizin>) kullanilir.
"""

from __future__ import annotations

import glob
import json
import os
import tempfile
import threading
import unittest
from unittest import mock

import _support
from _support import capture_logs

from src.utils import helpers
from src.utils import settings_manager
from src.utils.settings_manager import SettingsManager, register_saved_items


def _hotkey(shortcut="Ctrl+1", value="calc"):
    return {"shortcut": shortcut, "action_type": "run_program",
            "action_value": value, "enabled": True, "is_rich": False}


class SettingsTestCase(unittest.TestCase):
    def setUp(self):
        patcher, self.log_lines = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.path = os.path.join(self.dir, "config.json")
        SettingsManager.pop_warnings()
        self.manager = SettingsManager(settings_path=self.path)

    def read_json(self, path=None):
        with open(path or self.path, encoding="utf-8") as handle:
            return json.load(handle)

    def read_bytes(self, path=None) -> bytes:
        with open(path or self.path, "rb") as handle:
            return handle.read()

    def write_raw(self, data: bytes, path=None):
        with open(path or self.path, "wb") as handle:
            handle.write(data)

    def files(self, pattern):
        return sorted(glob.glob(os.path.join(self.dir, pattern)))


class AtomicWriteTests(SettingsTestCase):
    def test_save_writes_valid_json_and_leaves_no_temp_files(self):
        self.assertTrue(self.manager.save_settings({"theme": "dark", "ad": "çğıöşü"}))
        self.assertEqual(self.read_json()["ad"], "çğıöşü")
        self.assertEqual(self.files("*.tmp"), [])

    def test_save_calls_fsync_before_replace(self):
        order = []
        real_fsync, real_replace = os.fsync, os.replace
        with mock.patch("src.utils.helpers.os.fsync", side_effect=lambda fd: (order.append("fsync"), real_fsync(fd))[1]), \
                mock.patch("src.utils.helpers.os.replace", side_effect=lambda a, b: (order.append("replace"), real_replace(a, b))[1]):
            self.manager.save_settings({"theme": "dark"})
        self.assertIn("fsync", order)
        self.assertIn("replace", order)
        self.assertLess(order.index("fsync"), order.index("replace"))

    def test_failed_replace_keeps_old_file_and_removes_temp(self):
        self.manager.save_settings({"theme": "old"})
        with mock.patch("src.utils.helpers.os.replace", side_effect=OSError("disk dolu")):
            self.assertFalse(self.manager.save_settings({"theme": "new"}))
        self.assertEqual(self.read_json()["theme"], "old")
        self.assertEqual(self.files("*.tmp"), [])

    def test_unserializable_settings_do_not_touch_existing_file(self):
        self.manager.save_settings({"theme": "old"})
        before = self.read_bytes()
        self.assertFalse(self.manager.save_settings({"theme": object()}))
        self.assertEqual(self.read_bytes(), before)

    def test_replace_retries_on_transient_permission_error(self):
        calls = {"n": 0}
        real_replace = os.replace

        def flaky(src, dst):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError("baska surec tutuyor")
            return real_replace(src, dst)

        with mock.patch("src.utils.helpers.os.replace", side_effect=flaky), mock.patch("src.utils.helpers.time.sleep"):
            self.assertTrue(self.manager.save_settings({"theme": "dark"}))
        self.assertEqual(self.read_json()["theme"], "dark")
        self.assertGreaterEqual(calls["n"], 3)

    def test_atomic_write_json_helper_used_for_export(self):
        target = os.path.join(self.dir, "export.json")
        helpers.atomic_write_json(target, {"hotkeys": [], "ad": "ü"})
        self.assertEqual(self.read_json(target), {"hotkeys": [], "ad": "ü"})
        with self.assertRaises(TypeError):
            helpers.atomic_write_json(target, {"x": object()})
        self.assertEqual(self.read_json(target), {"hotkeys": [], "ad": "ü"})
        self.assertEqual(self.files("*.tmp"), [])


class BackupTests(SettingsTestCase):
    def test_previous_version_saved_as_bak(self):
        self.manager.save_settings({"theme": "v1"})
        self.assertFalse(os.path.exists(self.manager.backup_file))
        self.manager.save_settings({"theme": "v2"})
        self.assertEqual(self.read_json(self.manager.backup_file)["theme"], "v1")
        self.assertEqual(self.read_json()["theme"], "v2")

    def test_corrupt_existing_file_does_not_overwrite_good_bak(self):
        self.manager.save_settings({"theme": "v1"})
        self.manager.save_settings({"theme": "v2"})     # bak = v1
        self.write_raw(b"{ bozuk")
        self.manager.save_settings({"theme": "v3"})     # bozuk dosya yedegi ezmemeli
        self.assertEqual(self.read_json(self.manager.backup_file)["theme"], "v1")


class CorruptFileTests(SettingsTestCase):
    def test_corrupt_json_is_quarantined_not_silently_overwritten(self):
        self.write_raw(b'{"hotkeys": [ {"shortcut": "Ctrl+1"')   # yarim kalmis dosya
        settings = self.manager.load_settings()
        self.assertEqual(settings["hotkeys"], [])
        self.assertEqual(settings["theme"], "system")

        saved = self.files("config.json.corrupt-*")
        self.assertEqual(len(saved), 1)
        self.assertEqual(self.read_bytes(saved[0]), b'{"hotkeys": [ {"shortcut": "Ctrl+1"')
        kinds = [kind for kind, _ in SettingsManager.pop_warnings()]
        self.assertIn("corrupt_defaults", kinds)
        self.assertTrue(any(level == "ERROR" for level, _ in self.log_lines))

        # Sonraki yuklemeler tekrar tekrar kopya uretmez
        self.manager.load_settings()
        self.assertEqual(len(self.files("config.json.corrupt-*")), 1)

    def test_corrupt_json_restored_from_bak(self):
        self.manager.save_settings({**self.manager.load_settings(), "hotkeys": [_hotkey()]})
        self.manager.save_settings({**self.manager.load_settings(), "theme": "dark"})  # bak = hotkey'li surum
        self.write_raw(b"")                                   # sifir bayt: tipik yarim yazim
        settings = self.manager.load_settings()
        self.assertEqual([h["shortcut"] for h in settings["hotkeys"]], ["Ctrl+1"])
        self.assertEqual(len(self.files("config.json.corrupt-*")), 1)
        self.assertIn("corrupt_restored", [k for k, _ in SettingsManager.pop_warnings()])
        # config.json geri yuklenen icerikle yeniden olusturuldu
        self.assertEqual([h["shortcut"] for h in self.read_json()["hotkeys"]], ["Ctrl+1"])

    def test_non_dict_root_is_treated_as_corrupt(self):
        self.write_raw(b"[1, 2, 3]")
        self.assertEqual(self.manager.load_settings()["hotkeys"], [])
        self.assertEqual(len(self.files("config.json.corrupt-*")), 1)

    def test_utf8_bom_file_loads_normally(self):
        self.write_raw(b"\xef\xbb\xbf" + json.dumps({"theme": "dark"}).encode("utf-8"))
        self.assertEqual(self.manager.load_settings()["theme"], "dark")
        self.assertEqual(self.files("config.json.corrupt-*"), [])

    def test_unreadable_file_is_not_quarantined_or_overwritten_by_load(self):
        self.manager.save_settings({"theme": "dark"})
        with mock.patch("src.utils.settings_manager.open", side_effect=PermissionError("kilit"), create=True), \
                mock.patch("src.utils.settings_manager.time.sleep"):
            settings = self.manager.load_settings()
        self.assertEqual(settings["theme"], "system")           # varsayilan donuldu
        self.assertEqual(self.files("config.json.corrupt-*"), [])
        self.assertEqual(self.read_json()["theme"], "dark")     # dosya oldugu gibi
        self.assertIn("read_failed_defaults", [k for k, _ in SettingsManager.pop_warnings()])


class ShallowCopyTests(SettingsTestCase):
    def test_add_hotkey_does_not_mutate_defaults(self):
        self.manager.add_hotkey("Ctrl+1", "run_program", "calc")      # dosya yok -> varsayilanlar
        self.assertEqual(self.manager.default_settings["hotkeys"], [])
        self.assertEqual(settings_manager.DEFAULT_SETTINGS["hotkeys"], [])
        self.assertEqual(SettingsManager(settings_path=os.path.join(self.dir, "x.json"))
                         .load_settings()["hotkeys"], [])

    def test_loaded_defaults_are_independent_copies(self):
        first = self.manager.load_settings()
        first["hotkeys"].append(_hotkey())
        second = self.manager.load_settings()
        self.assertEqual(second["hotkeys"], [])

    def test_file_missing_list_keys_gets_fresh_lists(self):
        self.write_raw(json.dumps({"theme": "dark"}).encode("utf-8"))
        settings = self.manager.load_settings()
        settings["hotkeys"].append(_hotkey())
        self.assertEqual(self.manager.default_settings["hotkeys"], [])
        self.assertEqual(self.manager.load_settings()["hotkeys"], [])


class LockTests(SettingsTestCase):
    def test_transaction_blocks_other_writers_until_done(self):
        other = SettingsManager(settings_path=self.path)   # UpdateChecker gibi ayri ornek
        entered, release = threading.Event(), threading.Event()
        finished = threading.Event()

        def holder():
            with self.manager.transaction() as settings:
                settings["theme"] = "dark"
                entered.set()
                release.wait(5)

        def writer():
            other.add_hotkey("Ctrl+9", "run_program", "calc")
            finished.set()

        t1 = threading.Thread(target=holder)
        t1.start()
        self.assertTrue(entered.wait(5))
        t2 = threading.Thread(target=writer)
        t2.start()
        self.assertFalse(finished.wait(0.3), "kilit yok: ikinci yazici ilk islem bitmeden ilerledi")
        release.set()
        t1.join(5)
        t2.join(5)
        self.assertTrue(finished.is_set())
        data = self.read_json()
        self.assertEqual(data["theme"], "dark")                       # kayip guncelleme yok
        self.assertEqual([h["shortcut"] for h in data["hotkeys"]], ["Ctrl+9"])

    def test_concurrent_add_hotkey_loses_nothing(self):
        def worker(n):
            for i in range(5):
                self.manager.add_hotkey(f"Ctrl+{n}{i}", "run_program", "calc")

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual(len(self.read_json()["hotkeys"]), 30)

    def test_transaction_does_not_save_when_block_raises(self):
        self.manager.save_settings({"theme": "dark"})
        with self.assertRaises(RuntimeError):
            with self.manager.transaction() as settings:
                settings["theme"] = "light"
                raise RuntimeError("iptal")
        self.assertEqual(self.read_json()["theme"], "dark")


class SchemaValidationTests(SettingsTestCase):
    def test_records_missing_required_keys_are_skipped_and_original_preserved(self):
        raw = {
            "hotkeys": [
                _hotkey("Ctrl+1"),
                {"action_type": "text", "action_value": "x"},          # shortcut yok
                "metin",                                                # sozluk degil
                {"shortcut": "Ctrl+2", "action_type": "text"},          # action_value yok
                _hotkey("Ctrl+3"),
            ],
            "expansions": [
                {"trigger": "mt", "replacement": "Merhaba"},
                {"replacement": "trigger yok"},
            ],
        }
        self.write_raw(json.dumps(raw).encode("utf-8"))
        settings = self.manager.load_settings()
        self.assertEqual([h["shortcut"] for h in settings["hotkeys"]], ["Ctrl+1", "Ctrl+3"])
        self.assertEqual([e["trigger"] for e in settings["expansions"]], ["mt"])
        # Diskten silinmeden once ozgun dosya saklandi, kullanici uyarildi
        saved = self.files("config.json.invalid-*")
        self.assertEqual(len(saved), 1)
        self.assertEqual(self.read_json(saved[0])["hotkeys"][1], raw["hotkeys"][1])
        self.assertIn("invalid_records", [k for k, _ in SettingsManager.pop_warnings()])
        # Tekrar yuklemek ayni kopyayi cogaltmaz
        self.manager.load_settings()
        self.assertEqual(len(self.files("config.json.invalid-*")), 1)

    def test_non_list_hotkeys_value_becomes_empty_list(self):
        self.write_raw(json.dumps({"hotkeys": "bozuk", "expansions": 5}).encode("utf-8"))
        settings = self.manager.load_settings()
        self.assertEqual(settings["hotkeys"], [])
        self.assertEqual(settings["expansions"], [])

    def test_strict_validation_rejects_unknown_action_type_and_empty_value(self):
        ok = _hotkey()
        self.assertIsNone(settings_manager.validate_hotkey_record(ok, strict=True))
        self.assertIsNotNone(settings_manager.validate_hotkey_record({**ok, "action_type": "format_c"}, strict=True))
        self.assertIsNotNone(settings_manager.validate_hotkey_record({**ok, "action_value": "  "}, strict=True))
        self.assertIsNone(settings_manager.validate_hotkey_record({**ok, "action_type": "gelecek_tur"}))  # yukleme: ileri uyum


class RegisterSavedItemsTests(unittest.TestCase):
    class FakeManager:
        def __init__(self):
            self.hotkeys, self.expansions = [], []

        def add_hotkey(self, shortcut, action_type, action_value, is_rich=False):
            if shortcut == "patlat":
                raise RuntimeError("gecersiz kisayol")
            self.hotkeys.append(shortcut)

        def add_expansion(self, trigger, replacement, is_rich=False):
            if trigger == "patlat":
                raise RuntimeError("gecersiz")
            self.expansions.append(trigger)

    def setUp(self):
        patcher, self.log_lines = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_one_bad_record_does_not_kill_the_rest(self):
        manager = self.FakeManager()
        settings = {
            "hotkeys": [
                _hotkey("Ctrl+1"),
                {"action_type": "text", "action_value": "x"},      # KeyError: 'shortcut' (eski davranis: hepsi olur)
                _hotkey("patlat"),                                 # yonetici hata firlatir
                {**_hotkey("Ctrl+9"), "enabled": False},          # pasif -> yuklenmez, hata degil
                _hotkey("Ctrl+2"),
            ],
            "expansions": [
                {"trigger": "a", "replacement": "1"},
                {"replacement": "trigger yok"},
                {"trigger": "patlat", "replacement": "2"},
                {"trigger": "b", "replacement": "3"},
            ],
        }
        counts = register_saved_items(settings, manager)
        self.assertEqual(manager.hotkeys, ["Ctrl+1", "Ctrl+2"])
        self.assertEqual(manager.expansions, ["a", "b"])
        self.assertEqual(counts, {"hotkeys": 2, "hotkeys_failed": 2, "expansions": 2, "expansions_failed": 2})
        self.assertEqual(sum(1 for level, _ in self.log_lines if level == "ERROR"), 4)

    def test_log_does_not_contain_replacement_text(self):
        manager = self.FakeManager()
        register_saved_items({"expansions": [{"trigger": "patlat", "replacement": "GIZLI-PAROLA-123"}]}, manager)
        self.assertFalse(any("GIZLI-PAROLA-123" in message for _, message in self.log_lines))


if __name__ == "__main__":
    unittest.main()
