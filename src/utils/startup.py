"""Açılışta Başlat (oturum açılınca FlexiKey'i otomatik başlat).

Windows: HKCU\\...\\Run kaydı (mantık eskisiyle BİREBİR aynı; güncelleme E2E'si ve kayıt koruması buna bağlıdır, `--minimized`
bayrağı korunur). macOS ve Linux: `autostart_unix` (LaunchAgent plist / XDG autostart .desktop), yalnızca `sys.platform` dalı olarak.

Varsayılan: ilk kurulumda AÇIK (`SettingsManager.is_first_run()`), mevcut kullanıcıların ayarı değişmez.
"""

from __future__ import annotations

import os
import sys

from src.utils.helpers import get_application_path

try:
    import winreg
except ImportError:  # Windows dışı
    winreg = None

APP_NAME = "FlexiKey"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

# FlexiKey'in eski sürümlerinin macOS dosyası (com.flexikey.plist); açarken/kapatırken temizlenir.
_LEGACY_PLIST_LABELS = ("com.flexikey",)


def launch_command(minimized: bool) -> tuple[str, str, list[str]]:
    """(Windows Run değeri, çalıştırılacak program, program argümanları)."""
    args = " --minimized" if minimized else ""
    if getattr(sys, "frozen", False):
        exe_path = os.path.abspath(sys.executable)
        return f'"{exe_path}"{args}', exe_path, (["--minimized"] if minimized else [])
    main_path = os.path.join(get_application_path(), "main.py")
    python_exe = os.path.abspath(sys.executable)
    return f'"{python_exe}" "{main_path}"{args}', python_exe, [main_path] + (["--minimized"] if minimized else [])


def is_enabled() -> bool:
    if sys.platform == "win32":
        if winreg is None:
            return False
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, APP_NAME)
                winreg.CloseKey(key)
                return True
            except Exception:
                winreg.CloseKey(key)
                return False
        except Exception:
            return False
    from src.utils import autostart_unix
    return autostart_unix.is_enabled(APP_NAME, legacy_plist_labels=_LEGACY_PLIST_LABELS)


def set_enabled(enable: bool, minimized: bool) -> None:
    """Açılışta başlatmayı aç/kapat. Hata olursa istisna fırlatır (çağıran kullanıcıya bildirir)."""
    launch_cmd, program, program_args = launch_command(minimized)

    # 1. Windows: Registry
    if sys.platform == "win32":
        if winreg is None:
            return
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_cmd)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except Exception:
                pass
        winreg.CloseKey(key)
        return

    # 2. macOS (LaunchAgent) ve Linux (XDG autostart)
    from src.utils import autostart_unix
    ok = autostart_unix.set_enabled(
        APP_NAME, program, program_args, enable,
        display_name=APP_NAME, legacy_plist_labels=_LEGACY_PLIST_LABELS,
    )
    if not ok:
        raise OSError("autostart")


def apply_first_run_default(first_run: bool, frozen: bool, minimized: bool = True) -> bool:
    """İlk kurulumda (ayar dosyası hiç yokken) Açılışta Başlat'ı AÇAR. Yalnızca derlenmiş uygulamada (kaynaktan çalışan
    geliştirici kopyası kendini otomatik başlatmaya kaydetmez). Açıldıysa True; başka durumda ya da hatada False."""
    if not (first_run and frozen):
        return False
    try:
        set_enabled(True, minimized)
        return True
    except Exception:
        return False
