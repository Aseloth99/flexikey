"""Windows'a özgü girdi/sistem yardımcıları (ctypes / user32 / shell32).

Import güvenlidir (macOS ve Linux'ta da): ``ctypes.windll`` yalnızca fonksiyonların içinde ve
``sys.platform == 'win32'`` denetiminden sonra kullanılır; diğer platformlarda fonksiyonlar pasiftir.
hotkey_manager (komut tablosu, kanca sağlık sınaması, parola alanı denetimi) bu modülü kullanır.
"""

from __future__ import annotations

import ctypes
import sys
import time

from src.core.input_injector import INPUT_INJECTOR


def _is_windows() -> bool:
    return sys.platform == 'win32' and hasattr(ctypes, 'windll')


def ensure_utf8_console() -> None:
    """Windows konsol kodlaması: log/print çıktısında Türkçe karakterler bozulmasın."""
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass


def send_vk(vk_code: int):
    """Windows API ile anında, sıfır gecikmeli tuş gönderimi (diğer platformlarda pasif)"""
    if _is_windows():
        try:
            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)
        except Exception:
            pass


def send_vk_burst(vk_code: int, count: int = 50):
    """50 kademe ses/eylemi yapay bekleme olmadan 1 milisaniyede uygula"""
    if _is_windows():
        try:
            for _ in range(count):
                ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
                ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)
        except Exception:
            pass


def send_keys_combo(vk_code: int, modifiers: list = None):
    """Tuş kombinasyonunu GUI iş parçacığını bekletmeden (arka planda, sıralı) gönderir"""
    if _is_windows():
        INPUT_INJECTOR.submit(lambda: send_keys_combo_blocking(vk_code, modifiers))


def send_keys_combo_blocking(vk_code: int, modifiers: list = None):
    """Windows API ile temiz, sıfır gecikmeli ve güvenilir tuş kombinasyonu gönderimi"""
    if _is_windows():
        try:
            import time
            user32 = ctypes.windll.user32
            KEYEVENTF_KEYUP = 0x0002
            KEYEVENTF_EXTENDEDKEY = 0x0001

            # Tetikleyici tuşun basılı durumundan çıkması için küçük bekleme
            time.sleep(0.06)

            mods = modifiers or []
            # Modifier tuşlarına bas
            for m in mods:
                flags = KEYEVENTF_EXTENDEDKEY if m in (0x5B, 0x5C) else 0
                user32.keybd_event(m, 0, flags, 0)

            # Ana tuşa bas
            vk_flags = KEYEVENTF_EXTENDEDKEY if vk_code in (0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x2C, 0x5B, 0x5C) else 0
            user32.keybd_event(vk_code, 0, vk_flags, 0)
            time.sleep(0.02)
            user32.keybd_event(vk_code, 0, vk_flags | KEYEVENTF_KEYUP, 0)
            time.sleep(0.02)

            # Modifier tuşlarını bırak
            for m in reversed(mods):
                flags = KEYEVENTF_EXTENDEDKEY if m in (0x5B, 0x5C) else 0
                user32.keybd_event(m, 0, flags | KEYEVENTF_KEYUP, 0)
        except Exception:
            pass


_GWL_STYLE = -16
_ES_PASSWORD = 0x0020


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong), ("flags", ctypes.c_ulong),
        ("hwndActive", ctypes.c_void_p), ("hwndFocus", ctypes.c_void_p),
        ("hwndCapture", ctypes.c_void_p), ("hwndMenuOwner", ctypes.c_void_p),
        ("hwndMoveSize", ctypes.c_void_p), ("hwndCaret", ctypes.c_void_p),
        ("rcCaret", ctypes.c_long * 4),
    ]


def focused_control_is_password(user32=None) -> bool:
    """Odaktaki denetim klasik Win32 parola kutusu (ES_PASSWORD) mu? EN İYİ ÇABA.

    SINIR: yalnızca standart Edit/RichEdit tabanlı denetimleri tanır. Tarayıcılar (Chromium,
    Firefox), UWP/WPF/Electron ve özel çizimli alanlar kendi denetimlerini çizdiğinden parola
    alanları BURADAN GÖRÜNMEZ. Yükseltilmiş (yönetici) pencerelerde ise UIPI yüzünden zaten
    tuş olayı alınamaz. Güvenilir tespit olmadığı için asıl koruma tampon zaman aşımıdır.

    macOS/Linux'ta parola alanı tespit edilmez (False): macOS parola alanlarında "Secure Event
    Input" ile olayları zaten uygulamalardan saklar; Linux/X11'de koruma yalnızca tampon zaman aşımıdır.
    """
    try:
        if user32 is None:
            if not _is_windows():
                return False
            user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        thread_id = user32.GetWindowThreadProcessId(hwnd, None)
        info = _GUITHREADINFO()
        info.cbSize = ctypes.sizeof(_GUITHREADINFO)
        if not user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
            return False
        focus = info.hwndFocus
        if not focus:
            return False
        name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(focus, name, 256)
        if 'edit' not in name.value.lower():
            return False
        return bool(user32.GetWindowLongW(focus, _GWL_STYLE) & _ES_PASSWORD)
    except Exception:
        return False


def system_idle_seconds(user32=None, kernel32=None) -> float:
    """Kullanicinin bilgisayara en son dokunmasindan bu yana gecen sure.

    dwTime 32 bitlik tick sayisidir (~49,7 gunde basa sarar): fark 32 bitte alinir. Eskiden
    GetTickCount64'ten cikariliyordu; uzun sure acik kalan sistemde sure ~49 gun cikip kanca
    saglik sinamasi hic calismiyordu."""
    try:
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        if user32 is None:
            user32 = ctypes.windll.user32
        if kernel32 is None:
            kernel32 = ctypes.windll.kernel32
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0

        get_ticks = kernel32.GetTickCount
        get_ticks.restype = ctypes.c_uint32
        return ((get_ticks() - info.dwTime) & 0xFFFFFFFF) / 1000.0
    except Exception:
        return 0.0


def send_probe_key() -> None:
    """VK_NONAME (0xFC): hicbir uygulamada etkisi olmayan rezerve tus (kanca sagligi sinamasi).
    Hata firlatir; cagiran temizler."""
    ctypes.windll.user32.keybd_event(0xFC, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0xFC, 0, 2, 0)  # KEYEVENTF_KEYUP


def lock_workstation() -> None:
    if _is_windows():
        try:
            ctypes.windll.user32.LockWorkStation()
        except Exception:
            pass


def turn_off_screen() -> None:
    if _is_windows():
        try:
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        except Exception:
            pass


def empty_recycle_bin() -> None:
    if _is_windows():
        try:
            ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)
        except Exception:
            pass
