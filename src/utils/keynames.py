"""Kısayol/tuş adları: taşınabilir (kanonik) biçim, takma adlar ve platforma göre görüntüleme.

Ayarlarda saklanan kısayol metni işletim sistemlerinden bağımsızdır: "win" belirteci Windows'ta Win
tuşu, Linux'ta Super, macOS'ta Cmd anlamına gelir. Bir platformda yazılmış ayar dosyası diğerinde
aynen yüklenir; çeviri yalnızca (a) ekranda gösterirken ve (b) arka uca kaydederken yapılır.

Qt veya işletim sistemi API'si kullanılmaz (saf Python).
"""

from __future__ import annotations

from typing import NamedTuple, Optional, Tuple

from src.utils import platform_utils

MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")

_MODIFIER_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl", "ctl": "ctrl",
    "alt": "alt", "option": "alt", "opt": "alt",
    "shift": "shift",
    "win": "win", "windows": "win", "super": "win", "meta": "win", "cmd": "win", "command": "win",
}

_KEY_ALIASES = {
    "scrolllock": "scroll lock", "scroll_lock": "scroll lock",
    "printscreen": "print screen", "print_screen": "print screen", "prtsc": "print screen",
    "pageup": "page up", "page_up": "page up", "pgup": "page up",
    "pagedown": "page down", "page_down": "page down", "pgdn": "page down",
    "capslock": "caps lock", "caps_lock": "caps lock",
    "numlock": "num lock", "num_lock": "num lock",
    "return": "enter", "escape": "esc", "del": "delete", "ins": "insert",
    "spacebar": "space", "back": "backspace", "break": "pause",
    "plus": "+", "minus": "-", "equal": "=", "equals": "=", "comma": ",", "period": ".",
    "slash": "/", "backslash": "\\", "semicolon": ";", "quote": "'",
    "bracketleft": "[", "bracketright": "]", "grave": "`",
}

# Platforma göre değiştirici etiketleri (ekranda gösterim)
_MODIFIER_LABELS = {
    platform_utils.WINDOWS: {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win"},
    platform_utils.MACOS: {"ctrl": "Ctrl", "alt": "Option", "shift": "Shift", "win": "Cmd"},
    platform_utils.LINUX: {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Super"},
}


class ParsedShortcut(NamedTuple):
    modifiers: Tuple[str, ...]      # MODIFIER_ORDER sırasında, tekrarsız
    key: Optional[str]              # kanonik tuş adı; yalnızca değiştirici varsa None


def canonical_modifier(name: str) -> Optional[str]:
    """'Cmd', 'super', 'Windows', 'meta' -> 'win' (ve benzerleri); değiştirici değilse None."""
    return _MODIFIER_ALIASES.get((name or "").strip().lower())


def canonical_key_name(name: str) -> str:
    key = (name or "").strip().lower()
    return _KEY_ALIASES.get(key, key)


def parse_shortcut(text: str) -> ParsedShortcut:
    """'Ctrl+Win+Page_Up' -> (('ctrl','win'), 'page up'). Geçersizse ValueError.

    Tek bir ana tuş ve en çok dört değiştiriciye izin verilir. 'ctrl++' / '+' artı tuşunu belirtir.
    """
    raw = (text or "").strip().lower()
    if not raw:
        raise ValueError("Kısayol boş")
    if raw == "+":
        raw = "plus"
    elif raw.endswith("++"):
        raw = raw[:-2] + "+plus"
    mods = set()
    key: Optional[str] = None
    for part in (p.strip() for p in raw.split("+")):
        if not part:
            continue
        modifier = canonical_modifier(part)
        if modifier is not None:
            mods.add(modifier)
            continue
        if key is not None:
            raise ValueError(f"Birden fazla ana tuş: {text!r}")
        key = canonical_key_name(part)
    if key is None and not mods:
        raise ValueError("Kısayol boş")
    return ParsedShortcut(tuple(m for m in MODIFIER_ORDER if m in mods), key)


def modifier_label(modifier: str, platform: Optional[str] = None) -> str:
    """Değiştirici adının o platformdaki görüntü etiketi ('win' -> Win / Cmd / Super)."""
    labels = _MODIFIER_LABELS[platform_utils.current_platform(platform)]
    return labels.get(canonical_modifier(modifier) or modifier, modifier)
