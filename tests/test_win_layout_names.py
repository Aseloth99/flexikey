"""Kısaltmalardaki tuş adları öndeki pencerenin klavye düzenine göre üretilir (src/core/win_layout_names.py).

Okul dizüstünde FlexiKey oturum açılışında başlayınca hiçbir kısaltma tetiklenmiyordu, program yeniden açılınca
düzeliyordu: keyboard kütüphanesi ad tablosunu ABD düzeniyle kurmuştu, Türkçe Q'daki "i" tuşu "'" görünüyordu.
Sahte kütüphane modülü ve sahte Windows çağrılarıyla; en sonda gerçek keyboard kütüphanesi ve gerçek ToUnicodeEx ile.
"""

from __future__ import annotations

import collections
import ctypes
import os
import threading
import types
import unittest
import unittest.mock

import _support
from _support import capture_logs

from src.core import input_backend, win_layout_names
from src.core.input_backend import WindowsKeyboardBackend
from src.core.win_layout_names import DONT_CHANGE_KEYBOARD_STATE, LayoutNameTable

US, TR = 0x04090409, 0x041F041F
I_KEY, DOTLESS_KEY, DEAD_KEY = 0x28, 0x17, 0x1B       # Türkçe Q: "i", "ı", "ü" tuşunun yerinde ölü tuş (deneme için)
CHARS = {(US, I_KEY): "'", (TR, I_KEY): 'i', (US, DOTLESS_KEY): 'i', (TR, DOTLESS_KEY): 'ı', (TR, DEAD_KEY): '¨'}
DEAD = {'¨'}


class FakeApi:
    """Sahte Windows: öndeki pencerenin düzeni ``current``; ToUnicodeEx düzen + tarama koduna göre harf verir."""

    def __init__(self, current=US):
        self.current = current
        self.calls = []
        self.fail = False

    def foreground_layout(self):
        if self.fail:
            raise OSError('ön pencere okunamadı')
        return self.current

    def to_unicode_ex(self, vk, scan_code, state, buffer, size, flags, layout):
        self.calls.append((scan_code, flags, layout))
        char = CHARS.get((layout, scan_code))
        if char is None:
            return 0
        buffer.value = char
        return -1 if char in DEAD else 1

    def map_vk_to_char(self, vk, layout):
        return 0


def fake_winkeyboard():
    """keyboard._winkeyboard'ın kullanılan kısmı. _setup_name_tables kütüphanedeki gibi: tablo doluysa hiçbir şey yapmaz."""
    wk = types.SimpleNamespace()
    wk.to_name = collections.defaultdict(list)
    wk.from_name = collections.defaultdict(list)
    wk.tables_lock = threading.Lock()
    wk.keypad_keys = []
    wk.official_virtual_keys = {0x20: ('space', False)}
    wk.keyboard_state_type = ctypes.c_uint8 * 256
    wk.GetKeyNameText = lambda code, buffer, size: 0
    wk.get_event_names = lambda *entry: iter(['ESKI'])
    wk.setup_calls = 0

    def setup():
        with wk.tables_lock:
            if wk.to_name:
                return
            wk.setup_calls += 1
            for scan in (I_KEY, DOTLESS_KEY):
                entry = (scan, 0, 0, ())
                names = list(wk.get_event_names(*entry))
                wk.to_name[entry] = names
                for i, name in enumerate(names):
                    wk.from_name[name].append((i, entry))

    wk._setup_name_tables = setup
    return wk


def hook_name(wk, scan, vk=0, extended=0, modifiers=()):
    """keyboard._winkeyboard.prepare_intercept içindeki process_key'in adı bulan satırlarının aynısı."""
    entry = (scan, vk, extended, modifiers)
    if entry not in wk.to_name:
        wk.to_name[entry] = list(wk.get_event_names(*entry))
    names = wk.to_name[entry]
    return names[0] if names else None


class LayoutNamesTests(unittest.TestCase):
    def setUp(self):
        self.wk = fake_winkeyboard()
        self.kb = types.SimpleNamespace(_os_keyboard=self.wk)
        self.api = FakeApi(US)

    def install(self):
        self.assertTrue(win_layout_names.install(self.kb, api=self.api))

    def test_logon_under_us_layout_then_turkish_window(self):
        # oturum açılışı: kütüphane tabloyu ABD düzeniyle kurmuş ("i" tuşu "'")
        self.wk._setup_name_tables()
        self.assertEqual(hook_name(self.wk, I_KEY), "ESKI")
        self.install()
        self.api.current = TR
        self.assertEqual(hook_name(self.wk, I_KEY), 'i')
        self.assertEqual(hook_name(self.wk, DOTLESS_KEY), 'ı')

    def test_name_follows_the_foreground_layout(self):
        self.install()
        self.assertEqual(hook_name(self.wk, I_KEY), "'")          # ABD düzenli pencere
        self.api.current = TR
        self.assertEqual(hook_name(self.wk, I_KEY), 'i')          # Türkçe Q pencere: önbellekteki ABD adı kullanılmaz
        self.api.current = US
        self.assertEqual(hook_name(self.wk, DOTLESS_KEY), 'i')

    def test_names_are_cached_per_layout(self):
        self.install()
        self.api.current = TR
        before = len(self.api.calls)
        for _ in range(5):
            self.assertEqual(hook_name(self.wk, I_KEY), 'i')
        self.assertEqual(len(self.api.calls) - before, 1)

    def test_keyboard_state_is_not_changed(self):
        self.install()
        self.api.current = TR
        hook_name(self.wk, I_KEY)
        hook_name(self.wk, DEAD_KEY)
        self.assertTrue(self.api.calls)
        self.assertTrue(all(flags & DONT_CHANGE_KEYBOARD_STATE for _, flags, _ in self.api.calls))
        self.assertTrue(all(layout == TR for scan, _, layout in self.api.calls if scan == DEAD_KEY))

    def test_dead_key_is_named_and_cleared(self):
        self.install()
        self.api.current = TR
        self.assertEqual(hook_name(self.wk, DEAD_KEY), '¨')
        self.assertEqual(sum(1 for scan, _, _ in self.api.calls if scan == DEAD_KEY), 2)

    def test_name_to_key_table_is_built_with_the_layout_when_empty(self):
        self.api.current = TR
        self.install()
        self.assertEqual(self.wk.setup_calls, 1)
        self.assertEqual(self.wk.from_name['i'][0][1][0], I_KEY)
        self.assertEqual(self.wk.from_name['ı'][0][1][0], DOTLESS_KEY)

    def test_library_never_rebuilds_the_table(self):
        self.install()
        table = self.wk.to_name
        self.wk._setup_name_tables()                 # kanca yeniden kurulurken kütüphane çağırır
        self.assertIs(self.wk.to_name, table)
        self.assertIsInstance(table, LayoutNameTable)
        self.assertEqual(self.wk.setup_calls, 1)
        self.assertTrue(table)                       # boşken de "kurulu"

    def test_install_twice_keeps_the_table(self):
        self.install()
        table = self.wk.to_name
        names = self.wk.get_event_names
        self.install()
        self.assertIs(self.wk.to_name, table)
        self.assertIs(self.wk.get_event_names, names)

    def test_unexpected_library_is_left_alone(self):
        del self.wk.keypad_keys
        old_table, old_names = self.wk.to_name, self.wk.get_event_names
        self.assertFalse(win_layout_names.install(self.kb, api=self.api))
        self.assertIs(self.wk.to_name, old_table)
        self.assertIs(self.wk.get_event_names, old_names)
        self.assertEqual(win_layout_names.missing_names(self.kb), ['keypad_keys'])
        self.assertEqual(win_layout_names.missing_names(types.SimpleNamespace()), ['_os_keyboard'])

    def test_unreadable_foreground_keeps_the_last_layout(self):
        self.install()
        self.api.current = TR
        self.assertEqual(hook_name(self.wk, I_KEY), 'i')
        self.api.fail = True
        self.assertEqual(hook_name(self.wk, DOTLESS_KEY), 'ı')

    def test_layout_changes_are_reported_a_limited_number_of_times(self):
        changes = []
        self.assertTrue(win_layout_names.install(self.kb, api=self.api, on_change=lambda old, new: changes.append((old, new))))
        self.assertEqual(changes, [])                 # açılıştaki düzen değişim sayılmaz (backend ayrıca yazar)
        hook_name(self.wk, I_KEY)
        self.api.current = TR
        hook_name(self.wk, I_KEY)
        hook_name(self.wk, I_KEY)
        self.assertEqual(changes, [(US, TR)])
        for i in range(LayoutNameTable.MAX_CHANGE_REPORTS + 10):
            self.api.current = US if i % 2 == 0 else TR
            hook_name(self.wk, I_KEY)
        self.assertEqual(len(changes), LayoutNameTable.MAX_CHANGE_REPORTS)
        self.assertEqual(win_layout_names.layout_text(TR), '041F041F')
        self.assertEqual(win_layout_names.layout_text(0xF0020409), 'F0020409')

    def test_failing_change_report_does_not_break_the_hook(self):
        def boom(old, new):
            raise RuntimeError('günlük yazılamadı')
        self.assertTrue(win_layout_names.install(self.kb, api=self.api, on_change=boom))
        self.api.current = TR
        self.assertEqual(hook_name(self.wk, I_KEY), 'i')

    def test_missing_entry_reads_as_empty_list(self):
        self.install()
        self.assertEqual(self.wk.to_name[(0x99, 0, 0, ())], [])
        self.assertIsNone(self.wk.to_name.get((0x99, 0, 0, ())))


class BackendTests(unittest.TestCase):
    def setUp(self):
        patcher, self.log_lines = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)
        input_backend._PRIVATE_API_WARNED.clear()

    def test_fake_keyboard_module_is_not_patched(self):
        wk = fake_winkeyboard()
        table = wk.to_name
        WindowsKeyboardBackend(keyboard_module=types.SimpleNamespace(_os_keyboard=wk), pynput_module=object())
        self.assertIs(wk.to_name, table)

    def test_success_logs_the_layout_at_start(self):
        wk = fake_winkeyboard()
        kb = types.SimpleNamespace(_os_keyboard=wk)
        backend = WindowsKeyboardBackend(keyboard_module=kb, pynput_module=object())
        api = FakeApi(US)
        real_install = win_layout_names.install
        with unittest.mock.patch.object(win_layout_names, 'install',
                                        lambda module, on_change=None: real_install(module, api=api, on_change=on_change)):
            self.assertTrue(backend.install_layout_names())
        infos = [m for level, m in self.log_lines if level == 'INFO']
        self.assertTrue(any('açılıştaki düzen: 04090409' in m for m in infos), infos)
        api.current = TR
        hook_name(wk, I_KEY)
        infos = [m for level, m in self.log_lines if level == 'INFO']
        self.assertTrue(any('04090409 -> 041F041F' in m for m in infos), infos)

    def test_install_failure_is_logged_once(self):
        backend = WindowsKeyboardBackend(keyboard_module=types.SimpleNamespace(), pynput_module=object())
        self.assertFalse(backend.install_layout_names())
        self.assertFalse(backend.install_layout_names())
        warnings = [m for level, m in self.log_lines if level == 'WARNING' and '_os_keyboard' in m]
        self.assertEqual(len(warnings), 1)
        self.assertIn('_os_keyboard', warnings[0])


@unittest.skipUnless(os.name == 'nt', 'yalnızca Windows')
class RealWindowsTests(unittest.TestCase):
    """Gerçek keyboard kütüphanesi ve gerçek ToUnicodeEx (kanca kurulmaz, tuş gönderilmez)."""

    def setUp(self):
        import keyboard
        self.keyboard = keyboard
        self.wk = keyboard._os_keyboard
        saved = (self.wk.to_name, self.wk.get_event_names)

        def restore():
            self.wk.to_name, self.wk.get_event_names = saved
        self.addCleanup(restore)
        self.user32 = ctypes.WinDLL('user32')
        self.user32.MapVirtualKeyExW.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
        self.user32.MapVirtualKeyExW.restype = ctypes.c_uint

    def test_real_library_is_patched_and_names_match_the_layout(self):
        self.assertEqual(win_layout_names.missing_names(self.keyboard), [])
        self.assertTrue(win_layout_names.install(self.keyboard))
        table = self.wk.to_name
        self.assertIsInstance(table, LayoutNameTable)
        layout = table.refresh_layout()
        self.assertTrue(layout)
        vk_i = self.user32.MapVirtualKeyExW(I_KEY, 3, layout)
        vk_dotless = self.user32.MapVirtualKeyExW(DOTLESS_KEY, 3, layout)
        name_i, name_dotless = hook_name(self.wk, I_KEY, vk_i), hook_name(self.wk, DOTLESS_KEY, vk_dotless)
        if layout == TR:                              # bu bilgisayar Türkçe Q
            self.assertEqual((name_i, name_dotless), ('i', 'ı'))
        elif layout & 0xFFFF == 0x0409:
            self.assertEqual((name_i, name_dotless), ("'", 'i'))
        else:
            self.assertTrue(name_i and name_dotless)
        # ad -> tuş tablosu çalışıyor: send('ctrl+v') ve backspace bunlara dayanır
        for name in ('ctrl', 'v', 'backspace', 'enter'):
            self.assertTrue(list(self.wk.map_name(name)), name)


if __name__ == '__main__':
    unittest.main()
