"""Platform algılama ve platformdan bağımsız küçük yardımcılar (yalnızca standart kütüphane).

Windows, macOS ve Linux üzerinde import güvenlidir: ``ctypes.windll``, ``winreg`` gibi yalnızca
Windows'a ait şeyler burada import anında KULLANILMAZ. Platform her zaman çağrı anında okunur ve
``platform=`` parametresiyle enjekte edilebilir; böylece testler gerçek işletim sistemine bağlı kalmaz.
"""

from __future__ import annotations

import getpass
import os
import stat
import sys
from typing import Mapping, Optional

WINDOWS = "windows"
MACOS = "macos"
LINUX = "linux"

APP_NAME = "FlexiKey"
# macOS paket kimliği (Info.plist CFBundleIdentifier) ve LaunchAgent etiketi
BUNDLE_ID = "tr.com.macik.flexikey"

SESSION_X11 = "x11"
SESSION_WAYLAND = "wayland"
SESSION_TTY = "tty"
SESSION_UNKNOWN = "unknown"


def current_platform(platform: Optional[str] = None) -> str:
    """``sys.platform`` değerini WINDOWS / MACOS / LINUX'a çevirir (bilinmeyen POSIX = LINUX)."""
    value = sys.platform if platform is None else platform
    value = (value or "").lower()
    if value in (WINDOWS, MACOS, LINUX):
        return value
    if value.startswith("win") or value == "cygwin":
        return WINDOWS
    if value == "darwin":
        return MACOS
    return LINUX


def is_windows(platform: Optional[str] = None) -> bool:
    return current_platform(platform) == WINDOWS


def is_macos(platform: Optional[str] = None) -> bool:
    return current_platform(platform) == MACOS


def is_linux(platform: Optional[str] = None) -> bool:
    return current_platform(platform) == LINUX


def is_posix(platform: Optional[str] = None) -> bool:
    return current_platform(platform) != WINDOWS


def platform_label(platform: Optional[str] = None) -> str:
    return {WINDOWS: "Windows", MACOS: "macOS", LINUX: "Linux"}[current_platform(platform)]


def auto_update_supported(platform: Optional[str] = None) -> bool:
    """Otomatik yerinde güncelleme (indir + betikle değiştir + yeniden başlat) yalnızca Windows'ta var."""
    return is_windows(platform)


def linux_session_type(env: Optional[Mapping[str, str]] = None) -> str:
    """Linux oturum türü: 'x11', 'wayland', 'tty' veya 'unknown'.

    ``XDG_SESSION_TYPE`` esas alınır; boşsa ``WAYLAND_DISPLAY`` / ``DISPLAY`` ipucu olarak kullanılır.
    """
    env = os.environ if env is None else env
    declared = (env.get("XDG_SESSION_TYPE") or "").strip().lower()
    if declared in (SESSION_X11, SESSION_WAYLAND, SESSION_TTY):
        return declared
    if (env.get("WAYLAND_DISPLAY") or "").strip():
        return SESSION_WAYLAND
    if (env.get("DISPLAY") or "").strip():
        return SESSION_X11
    return SESSION_UNKNOWN


def has_x11_display(env: Optional[Mapping[str, str]] = None) -> bool:
    env = os.environ if env is None else env
    return bool((env.get("DISPLAY") or "").strip())


def current_user_token(user: Optional[str] = None) -> str:
    """Kullanıcıya özgü kısa belirteç (POSIX'te uid, yoksa kullanıcı adı)."""
    if user:
        return str(user)
    getuid = getattr(os, "getuid", None)
    if getuid is not None:
        try:
            return str(getuid())
        except OSError:
            pass
    try:
        return getpass.getuser()
    except Exception:
        return "user"


def single_instance_names(platform: Optional[str] = None, user: Optional[str] = None,
                          temp_dir: Optional[str] = None) -> tuple[str, str]:
    """(kilit dosyası yolu, yerel sunucu adı).

    Windows'ta adlar eskisiyle aynıdır. POSIX'te ortak /tmp çok kullanıcılı makinede başka
    kullanıcının örneğiyle çakışırdı: adlara uid eklenir.
    """
    import tempfile
    base = temp_dir or tempfile.gettempdir()
    if is_windows(platform):
        return os.path.join(base, f"{APP_NAME}.single.lock"), f"{APP_NAME}.SingleInstanceServer"
    token = current_user_token(user)
    return (os.path.join(base, f"{APP_NAME}.single.{token}.lock"),
            f"{APP_NAME}.SingleInstanceServer.{token}")


# ---------------------------------------------------------------- POSIX dosya izinleri
def ensure_private_dir(path: str, platform: Optional[str] = None) -> str:
    """Dizini oluşturur; POSIX'te yalnızca sahibine açık (0700) yapar. Windows'ta miras ACL'ye dokunmaz."""
    os.makedirs(path, exist_ok=True)
    if is_posix(platform):
        try:
            os.chmod(path, stat.S_IRWXU)
        except OSError:
            pass
    return path


def restrict_file(path: str, platform: Optional[str] = None) -> None:
    """POSIX'te dosyayı yalnızca sahibine okunur/yazılır (0600) yapar; hata sessizce yutulur."""
    if is_posix(platform):
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
