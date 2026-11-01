"""CF_HTML bayt ofsetleri, pano try/finally, pano kaydet/geri yukle.

Gercek panoya DOKUNULMAZ: win32clipboard yerine sahte (FakeClipboard) modul kullanilir.
"""

from __future__ import annotations

import re
import sys
import types
import unittest
from unittest import mock

import _support
from _support import capture_logs
from _fakes import FakeBackend

from src.core import clipboard_utils as cu

CF_UNICODETEXT = 13
CF_DIB = 8


class FakeClipboard:
    """win32clipboard'in test icin minimal taklidi."""

    def __init__(self, contents=None, fail_open=0, fail_set_for=()):
        self.formats = dict(contents or {})
        self.names = {}
        self.is_open = False
        self.open_calls = 0
        self.close_calls = 0
        self.sequence = 100
        self.fail_open = fail_open
        self.fail_set_for = set(fail_set_for)
        self.log = []

    # win32clipboard API
    def OpenClipboard(self):
        self.open_calls += 1
        if self.fail_open > 0:
            self.fail_open -= 1
            raise OSError("Erisim engellendi (baska uygulama panoyu tutuyor)")
        assert not self.is_open, "pano zaten acik"
        self.is_open = True

    def CloseClipboard(self):
        self.close_calls += 1
        self.is_open = False

    def EmptyClipboard(self):
        assert self.is_open
        self.formats.clear()
        self.sequence += 1
        self.log.append("empty")

    def SetClipboardData(self, fmt, data):
        assert self.is_open
        if fmt in self.fail_set_for:
            raise OSError("SetClipboardData basarisiz")
        self.formats[fmt] = data
        self.sequence += 1
        self.log.append(("set", fmt))

    def GetClipboardData(self, fmt):
        assert self.is_open
        return self.formats[fmt]

    def IsClipboardFormatAvailable(self, fmt):
        return fmt in self.formats

    def RegisterClipboardFormat(self, name):
        return self.names.setdefault(name, 0xC000 + len(self.names))

    def EnumClipboardFormats(self, fmt=0):
        keys = sorted(self.formats)
        if fmt == 0:
            return keys[0] if keys else 0
        later = [k for k in keys if k > fmt]
        return later[0] if later else 0

    def GetClipboardSequenceNumber(self):
        return self.sequence

    # test yardimcilari
    @property
    def html_format(self):
        return self.RegisterClipboardFormat(cu.HTML_FORMAT_NAME)


CON = types.SimpleNamespace(CF_UNICODETEXT=CF_UNICODETEXT)


def parse_header(data: bytes) -> dict[str, int]:
    header = data.split(b"<html>", 1)[0].decode("ascii")
    return {key: int(value) for key, value in re.findall(r"(\w+):(\d+)", header)}


class BuildCfHtmlTests(unittest.TestCase):
    def check_offsets(self, fragment: str):
        data = cu.build_cf_html(fragment)
        h = parse_header(data)
        self.assertEqual(h["EndHTML"], len(data))
        self.assertEqual(data[h["StartHTML"]:h["EndHTML"]][:6], b"<html>")
        self.assertTrue(data[h["StartHTML"]:h["EndHTML"]].endswith(b"</html>"))
        # Isaretler parcanin tam onunde/sonunda olmali
        self.assertEqual(data[h["StartFragment"] - len(b"<!--StartFragment-->"):h["StartFragment"]],
                         b"<!--StartFragment-->")
        self.assertEqual(data[h["EndFragment"]:h["EndFragment"] + len(b"<!--EndFragment-->")],
                         b"<!--EndFragment-->")
        # Parca, UTF-8 bayt dizisinde tam olarak kullanicinin metni
        self.assertEqual(data[h["StartFragment"]:h["EndFragment"]].decode("utf-8"), fragment)
        return h

    def test_turkish_characters_use_byte_offsets(self):
        fragment = "<p>Çağrı güncelleştirmesi: ığüşöç İĞÜŞÖÇ</p>"
        h = self.check_offsets(fragment)
        char_based_end = h["StartFragment"] + len(fragment)
        self.assertGreater(h["EndFragment"], char_based_end)   # 2 baytlik karakterler ofseti kaydirir

    def test_ascii_only(self):
        self.check_offsets("<b>merhaba</b>")

    def test_four_byte_characters(self):
        self.check_offsets("<p>emoji \U0001F600 ve ç</p>")

    def test_empty_fragment(self):
        self.check_offsets("")

    def test_lone_surrogate_does_not_raise(self):
        data = cu.build_cf_html("a\ud800b")
        self.assertEqual(parse_header(data)["EndHTML"], len(data))


class OpenCloseTests(unittest.TestCase):
    def setUp(self):
        patcher, _ = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_clipboard_closed_even_when_set_fails(self):
        cb = FakeClipboard(fail_set_for={CF_UNICODETEXT})
        with self.assertRaises(OSError):
            cu.set_clipboard_rich_text(cb, CON, "<b>x</b>", "x")
        self.assertFalse(cb.is_open)                     # eski kod burada acik birakirdi
        self.assertEqual(cb.open_calls, cb.close_calls)

    def test_open_is_retried(self):
        cb = FakeClipboard(fail_open=3)
        with mock.patch("src.core.clipboard_utils.time.sleep"):
            cu.set_clipboard_rich_text(cb, CON, "<b>x</b>", "x")
        self.assertEqual(cb.open_calls, 4)
        self.assertFalse(cb.is_open)
        self.assertEqual(cb.formats[CF_UNICODETEXT], "x")

    def test_open_failure_raises_without_close(self):
        cb = FakeClipboard(fail_open=999)
        with mock.patch("src.core.clipboard_utils.time.sleep"):
            with self.assertRaises(cu.ClipboardError):
                cu.set_clipboard_rich_text(cb, CON, "<b>x</b>", "x")
        self.assertEqual(cb.close_calls, 0)              # hic acilmadiysa kapatilmaz

    def test_html_written_as_utf8_bytes(self):
        cb = FakeClipboard()
        cu.set_clipboard_rich_text(cb, CON, "<p>çğı</p>", "çğı")
        data = cb.formats[cb.html_format]
        self.assertIsInstance(data, bytes)
        h = parse_header(data)
        self.assertEqual(data[h["StartFragment"]:h["EndFragment"]].decode("utf-8"), "<p>çğı</p>")


class SnapshotRestoreTests(unittest.TestCase):
    def setUp(self):
        patcher, self.log_lines = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_previous_text_and_html_restored(self):
        cb = FakeClipboard()
        html_fmt = cb.html_format
        cb.formats = {CF_UNICODETEXT: "kullanicinin panosu", html_fmt: b"<html>eski</html>"}
        snap = cu.snapshot_clipboard(cb, CON)
        cu.set_clipboard_rich_text(cb, CON, "<b>genisletme</b>", "genisletme")
        self.assertEqual(cb.formats[CF_UNICODETEXT], "genisletme")
        self.assertTrue(cu.restore_clipboard(cb, snap, cb.sequence))
        self.assertEqual(cb.formats, {CF_UNICODETEXT: "kullanicinin panosu", html_fmt: b"<html>eski</html>"})
        self.assertFalse(cb.is_open)

    def test_empty_clipboard_restored_to_empty(self):
        cb = FakeClipboard()
        snap = cu.snapshot_clipboard(cb, CON)
        cu.set_clipboard_rich_text(cb, CON, "<b>x</b>", "x")
        cu.restore_clipboard(cb, snap, cb.sequence)
        self.assertEqual(cb.formats, {})

    def test_user_copy_during_expansion_is_not_overwritten(self):
        cb = FakeClipboard({CF_UNICODETEXT: "eski"})
        snap = cu.snapshot_clipboard(cb, CON)
        cu.set_clipboard_rich_text(cb, CON, "<b>x</b>", "x")
        seq = cb.sequence
        cb.OpenClipboard(); cb.EmptyClipboard(); cb.SetClipboardData(CF_UNICODETEXT, "YENI KOPYA"); cb.CloseClipboard()
        self.assertFalse(cu.restore_clipboard(cb, snap, seq))
        self.assertEqual(cb.formats[CF_UNICODETEXT], "YENI KOPYA")

    def test_unsupported_formats_flag_snapshot_lossy(self):
        cb = FakeClipboard({CF_DIB: b"\x00" * 10, CF_UNICODETEXT: "x"})
        self.assertTrue(cu.snapshot_clipboard(cb, CON).lossy)
        plain = FakeClipboard({CF_UNICODETEXT: "x", 1: b"x", 16: b"\x00"})   # CF_TEXT/LOCALE sentezlenir
        self.assertFalse(cu.snapshot_clipboard(plain, CON).lossy)

    def test_restore_failure_is_swallowed_and_logged(self):
        cb = FakeClipboard({CF_UNICODETEXT: "eski"})
        snap = cu.snapshot_clipboard(cb, CON)
        cb.fail_open = 999
        with mock.patch("src.core.clipboard_utils.time.sleep"):
            self.assertFalse(cu.restore_clipboard(cb, snap))
        self.assertTrue(any(level == "ERROR" for level, _ in self.log_lines))


class PasteRichTextIntegrationTests(unittest.TestCase):
    """HotkeyWorker._paste_rich_text: sahte pano + sahte keyboard ile uctan uca."""

    def setUp(self):
        patcher, self.log_lines = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)

        from src.core import hotkey_manager
        self.hm = hotkey_manager
        self.cb = FakeClipboard({CF_UNICODETEXT: "kullanicinin panosu"})
        self.pasted_snapshot = {}

        def fake_send(keys):
            # Ctrl+V basildigi anda panoda HTML + duz metin olmali
            self.pasted_snapshot.update(self.cb.formats)

        self.kb = FakeBackend()
        self.kb.send.side_effect = fake_send
        patchers = [
            mock.patch.dict(sys.modules, {"win32clipboard": self.cb, "win32con": CON}),
            mock.patch.object(hotkey_manager.time, "sleep"),
            mock.patch.object(hotkey_manager.HotkeyWorker, "_html_to_plain_text",
                              staticmethod(lambda html: "duz metin: " + html)),
        ]
        for patcher_ in patchers:
            patcher_.start()
            self.addCleanup(patcher_.stop)
        self.worker = hotkey_manager.HotkeyWorker(backend=self.kb, clipboard=cu.Win32Clipboard())

    def test_clipboard_has_rich_content_during_paste_and_previous_restored_after(self):
        self.worker.buffer = "gizli"
        self.worker._paste_rich_text("<p>Çağrı</p>")
        self.assertEqual(self.pasted_snapshot[CF_UNICODETEXT], "duz metin: <p>Çağrı</p>")
        self.assertIn(self.cb.html_format, self.pasted_snapshot)
        self.assertEqual(self.cb.formats, {CF_UNICODETEXT: "kullanicinin panosu"})
        self.assertFalse(self.cb.is_open)
        self.assertFalse(self.worker.is_pasting)
        self.assertEqual(self.worker.buffer, "")

    def test_clipboard_restored_and_closed_when_paste_fails(self):
        self.kb.send.side_effect = RuntimeError("ctrl+v gonderilemedi")
        self.worker._paste_rich_text("<p>x</p>")
        self.kb.write.assert_called_once_with("duz metin: <p>x</p>")   # duz metne dusuldu
        self.assertEqual(self.cb.formats, {CF_UNICODETEXT: "kullanicinin panosu"})
        self.assertFalse(self.cb.is_open)
        self.assertFalse(self.worker.is_pasting)

    def test_clipboard_closed_when_setting_fails_midway(self):
        self.cb.fail_set_for = {CF_UNICODETEXT}
        self.worker._paste_rich_text("<p>x</p>")
        self.assertFalse(self.cb.is_open)
        self.assertEqual(self.cb.open_calls, self.cb.close_calls)
        self.assertFalse(self.worker.is_pasting)


if __name__ == "__main__":
    unittest.main()
