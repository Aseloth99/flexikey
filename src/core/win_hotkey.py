"""Windows RegisterHotKey — global kanca olmadan kısayol kaydı.

keyboard kütüphanesinin WH_KEYBOARD_LL kancası RDP oturumlarında
Ctrl gibi niteleyicileri ~1 sn bekletebiliyor. RegisterHotKey yalnızca
tam kombinasyonu yakalar; Ctrl+V gibi diğer kısayollara dokunmaz.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Callable, Dict, Optional, Tuple

from PyQt6.QtCore import QAbstractNativeEventFilter

try:
    user32 = ctypes.windll.user32 if hasattr(ctypes, 'windll') else None
except Exception:
    user32 = None

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_SPECIAL_VK = {
    'scroll lock': 0x91, 'scrolllock': 0x91,
    'caps lock': 0x14, 'capslock': 0x14,
    'num lock': 0x90, 'numlock': 0x90,
    'pause': 0x13, 'break': 0x13,
    'print screen': 0x2C, 'printscreen': 0x2C,
    'insert': 0x2D, 'delete': 0x2E,
    'home': 0x24, 'end': 0x23,
    'page up': 0x21, 'pageup': 0x21,
    'page down': 0x22, 'pagedown': 0x22,
    'left': 0x25, 'up': 0x26, 'right': 0x27, 'down': 0x28,
    'space': 0x20, 'tab': 0x09,
    'enter': 0x0D, 'return': 0x0D,
    'esc': 0x1B, 'escape': 0x1B,
    'backspace': 0x08, 'back': 0x08,
    'apps': 0x5D, 'menu': 0x5D,
    'plus': 0xBB, '=': 0xBB,
    'minus': 0xBD, '-': 0xBD,
    'comma': 0xBC, ',': 0xBC,
    'period': 0xBE, '.': 0xBE,
    'slash': 0xBF, '/': 0xBF,
    'semicolon': 0xBA, ';': 0xBA,
    'quote': 0xDE, "'": 0xDE,
    'backslash': 0xDC, '\\': 0xDC,
    'bracketleft': 0xDB, '[': 0xDB,
    'bracketright': 0xDD, ']': 0xDD,
    'grave': 0xC0, '`': 0xC0,
    'numpad 0': 0x60, 'numpad0': 0x60,
    'numpad 1': 0x61, 'numpad1': 0x61,
    'numpad 2': 0x62, 'numpad2': 0x62,
    'numpad 3': 0x63, 'numpad3': 0x63,
    'numpad 4': 0x64, 'numpad4': 0x64,
    'numpad 5': 0x65, 'numpad5': 0x65,
    'numpad 6': 0x66, 'numpad6': 0x66,
    'numpad 7': 0x67, 'numpad7': 0x67,
    'numpad 8': 0x68, 'numpad8': 0x68,
    'numpad 9': 0x69, 'numpad9': 0x69,
}


def _key_to_vk(key: str) -> Optional[int]:
    key = (key or '').strip().lower()
    if not key:
        return None
    if key in _SPECIAL_VK:
        return _SPECIAL_VK[key]
    if len(key) >= 2 and key[0] == 'f' and key[1:].isdigit():
        n = int(key[1:])
        if 1 <= n <= 24:
            return 0x70 + n - 1
    if key.startswith('numpad ') and key[7:].isdigit():
        return 0x60 + int(key[7:])
    if len(key) == 1 and 'a' <= key <= 'z':
        return ord(key.upper())
    if len(key) == 1 and '0' <= key <= '9':
        return ord(key)
    try:
        if len(key) == 1:
            res = user32.VkKeyScanW(ord(key))
            if res != -1:
                vk = res & 0xFF
                if vk > 0:
                    return vk
    except Exception:
        pass
    return None


def parse_win_hotkey(normalized: str) -> Optional[Tuple[int, int]]:
    """'ctrl+alt+j' -> (modifiers, vk). Ayrıştırılamazsa None."""
    text = (normalized or '').strip().lower()
    if not text:
        return None

    mods = 0
    key = None
    if '+' in text:
        parts = [p.strip() for p in text.split('+') if p.strip()]
    else:
        parts = [text]

    for part in parts:
        if part in ('ctrl', 'control'):
            mods |= MOD_CONTROL
        elif part == 'alt':
            mods |= MOD_ALT
        elif part == 'shift':
            mods |= MOD_SHIFT
        elif part in ('win', 'windows', 'super', 'meta', 'cmd'):
            mods |= MOD_WIN
        else:
            key = part

    vk = _key_to_vk(key)
    if vk is None:
        return None
    return mods, vk


class WinHotkeyFilter(QAbstractNativeEventFilter):
    """WM_HOTKEY iletilerini Qt olay döngüsüne bağlar."""

    def __init__(self, callback: Callable[[int], None]):
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, eventType, message):
        try:
            et = bytes(eventType).decode(errors='ignore') if eventType else ''
            if et not in ('windows_generic_MSG', 'windows_dispatcher_MSG'):
                return False, 0
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self._callback(int(msg.wParam))
                return True, 1
        except Exception:
            pass
        return False, 0


class WinHotkeyTable:
    """RegisterHotKey kayıtlarını yönetir."""

    def __init__(self):
        self.hwnd = 0
        self._next_id = 1
        self._id_by_shortcut: Dict[str, int] = {}
        self._shortcut_by_id: Dict[int, str] = {}

    def set_hwnd(self, hwnd: int) -> None:
        self.hwnd = int(hwnd or 0)

    def register(self, shortcut: str, mods: int, vk: int) -> Optional[int]:
        if not user32 or not self.hwnd or not vk:
            return None
        if shortcut in self._id_by_shortcut:
            self.unregister(shortcut)

        hotkey_id = self._next_id
        self._next_id += 1
        flags = mods | MOD_NOREPEAT
        if user32.RegisterHotKey(self.hwnd, hotkey_id, flags, vk):
            self._id_by_shortcut[shortcut] = hotkey_id
            self._shortcut_by_id[hotkey_id] = shortcut
            return hotkey_id

        # MOD_NOREPEAT desteklenmeyen sistemlerde tekrarsız dene
        if flags != mods and user32.RegisterHotKey(self.hwnd, hotkey_id, mods, vk):
            self._id_by_shortcut[shortcut] = hotkey_id
            self._shortcut_by_id[hotkey_id] = shortcut
            return hotkey_id
        return None

    def unregister(self, shortcut: str) -> None:
        hotkey_id = self._id_by_shortcut.pop(shortcut, None)
        if hotkey_id is None:
            return
        self._shortcut_by_id.pop(hotkey_id, None)
        if self.hwnd and user32:
            user32.UnregisterHotKey(self.hwnd, hotkey_id)

    def shortcut_for_id(self, hotkey_id: int) -> Optional[str]:
        return self._shortcut_by_id.get(hotkey_id)

    def has(self, shortcut: str) -> bool:
        return shortcut in self._id_by_shortcut

    def clear(self) -> None:
        for shortcut in list(self._id_by_shortcut.keys()):
            self.unregister(shortcut)
