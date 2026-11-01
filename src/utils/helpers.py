"""Helper functions and utilities"""

import json
import os
import sys
import tempfile
import time
import traceback
from typing import Any, Callable, Mapping, Optional, Tuple

from src.utils import keynames
from src.utils import platform_utils

APP_ID = "FlexiKey"


def _replace_with_retry(src: str, dst: str, attempts: int = 5) -> None:
    """os.replace; Windows'ta hedef anlik olarak baska surec (antivirus, eşitleme) tarafindan
    tutuluyorsa PermissionError verebilir, kisa araliklarla tekrar dener."""
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1))


def atomic_write_bytes(path: str, data: bytes, *, backup_path: Optional[str] = None,
                       backup_validator: Optional[Callable[[bytes], bool]] = None) -> None:
    """
    Dosyayi atomik yaz: ayni dizinde gecici dosyaya yaz + flush + fsync + os.replace.
    Cokme/elektrik kesintisinde hedef dosya ya eski ya yeni halinde kalir, yarim kalmaz.

    backup_path verilirse, hedef degistirilmeden ONCE mevcut icerik (backup_validator
    onaylarsa; verilmediyse her zaman) yedek dosyasina atomik olarak kopyalanir.
    """
    path = os.path.abspath(path)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

        if backup_path and os.path.isfile(path):
            try:
                with open(path, "rb") as old_handle:
                    old_data = old_handle.read()
                if backup_validator is None or backup_validator(old_data):
                    atomic_write_bytes(backup_path, old_data)
            except OSError:
                # Yedek alinamamasi asil kaydi engellemesin
                pass

        _replace_with_retry(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def atomic_write_text(path: str, text: str, *, encoding: str = "utf-8", **kwargs: Any) -> None:
    atomic_write_bytes(path, text.encode(encoding), **kwargs)


def atomic_write_json(path: str, data: Any, **kwargs: Any) -> None:
    """JSON'u once bellekte serilestirir (serilestirme hatasi dosyaya dokunmaz), sonra atomik yazar."""
    payload = json.dumps(data, indent=4, ensure_ascii=False)
    atomic_write_text(path, payload, **kwargs)


def get_application_path() -> str:
    """
    Get the base path of the application
    Handles both script run and frozen (exe) run
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled exe
        return os.path.dirname(sys.executable)
    else:
        # Running as Python script: src/utils/helpers.py -> proje kökü
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _home(home: Optional[str] = None) -> str:
    return home if home is not None else os.path.expanduser("~")


def get_user_config_dir(app_id: str = APP_ID, *, platform: Optional[str] = None,
                        environ: Optional[Mapping[str, str]] = None, home: Optional[str] = None) -> str:
    """Kalıcı ayarlar: Windows Roaming, macOS Application Support, Linux XDG."""
    env = os.environ if environ is None else environ
    plat = platform_utils.current_platform(platform)
    if plat == platform_utils.WINDOWS:
        base = env.get("APPDATA") or os.path.join(_home(home), "AppData", "Roaming")
        return os.path.join(base, app_id)
    if plat == platform_utils.MACOS:
        return os.path.join(_home(home), "Library", "Application Support", app_id)
    xdg = env.get("XDG_CONFIG_HOME") or os.path.join(_home(home), ".config")
    return os.path.join(xdg, app_id)


def get_user_data_dir(app_id: str = APP_ID, *, platform: Optional[str] = None,
                      environ: Optional[Mapping[str, str]] = None, home: Optional[str] = None) -> str:
    """Önbellek/veri: Windows Local, macOS Application Support, Linux XDG data."""
    env = os.environ if environ is None else environ
    plat = platform_utils.current_platform(platform)
    if plat == platform_utils.WINDOWS:
        base = env.get("LOCALAPPDATA") or os.path.join(_home(home), "AppData", "Local")
        return os.path.join(base, app_id)
    if plat == platform_utils.MACOS:
        return os.path.join(_home(home), "Library", "Application Support", app_id)
    xdg = env.get("XDG_DATA_HOME") or os.path.join(_home(home), ".local", "share")
    return os.path.join(xdg, app_id)


def get_user_log_dir(app_id: str = APP_ID, *, platform: Optional[str] = None,
                     environ: Optional[Mapping[str, str]] = None, home: Optional[str] = None) -> str:
    """Log dizini: Windows LOCALAPPDATA/FlexiKey/logs, macOS ~/Library/Logs/FlexiKey, Linux XDG data/logs."""
    plat = platform_utils.current_platform(platform)
    if plat == platform_utils.MACOS:
        return os.path.join(_home(home), "Library", "Logs", app_id)
    return os.path.join(get_user_data_dir(app_id, platform=plat, environ=environ, home=home), "logs")


def resolve_user_config(filename: str = "config.json", app_id: str = APP_ID,
                        app_dir: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """
    Kullanıcı config yolu ve isteğe bağlı ilk-kurulum tohumu.

    Kullanıcı dizininde config varsa tohum yok sayılır.
    Yoksa uygulama klasöründeki / CWD'deki config yalnızca ilk yükleme için kullanılır.
    """
    user_dir = get_user_config_dir(app_id)
    platform_utils.ensure_private_dir(user_dir)   # POSIX'te 0700 (ayarlar kişisel veri içerebilir)
    user_path = os.path.join(user_dir, filename)
    if os.path.isfile(user_path):
        return user_path, None

    app_dir = app_dir or get_application_path()
    seen = set()
    for candidate in (os.path.join(app_dir, filename), os.path.join(os.getcwd(), filename)):
        norm = os.path.normcase(os.path.abspath(candidate))
        if norm in seen:
            continue
        seen.add(norm)
        if os.path.isfile(candidate):
            return user_path, candidate
    return user_path, None


def format_bytes(size: int) -> str:
    """Format bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def format_speed(speed_mbps: float) -> str:
    """
    Format speed to human readable format
    Shows MB/s if >= 1 MB/s, otherwise KB/s
    
    Args:
        speed_mbps: Speed in MB/s
        
    Returns:
        Formatted speed string (e.g., "1.23 MB/s" or "512.34 KB/s")
    """
    if speed_mbps >= 1.0:
        return f"{speed_mbps:.2f} MB/s"
    else:
        # Convert to KB/s
        speed_kbps = speed_mbps * 1024.0
        return f"{speed_kbps:.2f} KB/s"


def get_log_path() -> str:
    """Uygulama log dosyasi yolu (kullanıcı veri dizini; macOS'ta ~/Library/Logs)"""
    log_dir = get_user_log_dir()
    try:
        platform_utils.ensure_private_dir(log_dir)
    except OSError:
        log_dir = os.path.join(tempfile.gettempdir(), APP_ID)
        platform_utils.ensure_private_dir(log_dir)
    return os.path.join(log_dir, "flexikey.log")


_LOGGER = None


def get_logger():
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER
    import logging
    from logging.handlers import RotatingFileHandler

    class PrivateRotatingFileHandler(RotatingFileHandler):
        """Log dosyaları (döndürülenler dahil) POSIX'te yalnızca sahibine açık (0600) oluşturulur."""

        def _open(self):
            stream = super()._open()
            platform_utils.restrict_file(self.baseFilename)
            return stream

    logger = logging.getLogger("FlexiKey")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    log_file = get_log_path()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    try:
        handler = PrivateRotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    except Exception:
        pass
    _LOGGER = logger
    return logger


def write_log(message: str, level: str = 'INFO') -> None:
    """Log dosyasina yaz (RotatingFileHandler ile)"""
    try:
        import logging
        logger = get_logger()
        lvl = getattr(logging, level.upper(), logging.INFO)
        logger.log(lvl, message)
    except Exception:
        pass


def log_error(message: str, exc: Optional[Exception] = None) -> None:
    """Hata logla"""
    detail = message
    if exc is not None:
        detail += f" | {type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    write_log(detail, 'ERROR')


def log_info(message: str) -> None:
    """Bilgi logla"""
    write_log(message, 'INFO')


def log_warning(message: str) -> None:
    """Uyari logla"""
    write_log(message, 'WARNING')


def format_shortcut_for_display(shortcut: str, platform: Optional[str] = None) -> str:
    """Kısayol metnini kullanıcı dostu formata dönüştürür (örn. win+/ -> Win + /, scroll lock -> Scroll Lock).

    "win" belirteci platforma göre gösterilir: Windows'ta Win, macOS'ta Cmd, Linux'ta Super
    (macOS'ta alt = Option). Saklanan metin değişmez; yalnızca görüntü farklıdır."""
    if not shortcut:
        return ""
    text = str(shortcut).strip()
    
    single_display = {
        'scrolllock': 'Scroll Lock', 'scroll lock': 'Scroll Lock',
        'printscreen': 'Print Screen', 'print screen': 'Print Screen',
        'pageup': 'Page Up', 'page up': 'Page Up',
        'pagedown': 'Page Down', 'page down': 'Page Down',
        'capslock': 'Caps Lock', 'caps lock': 'Caps Lock',
        'numlock': 'Num Lock', 'num lock': 'Num Lock',
        'space': 'Space', 'enter': 'Enter', 'return': 'Enter',
        'esc': 'Esc', 'escape': 'Esc', 'tab': 'Tab',
        'backspace': 'Backspace', 'delete': 'Delete', 'del': 'Delete',
        'insert': 'Insert', 'ins': 'Insert',
        'home': 'Home', 'end': 'End',
        'pause': 'Pause', 'break': 'Break',
        'up': '↑', 'down': '↓', 'left': '←', 'right': '→',
    }
    
    lower = text.lower().replace('_', ' ')
    if lower in single_display:
        return single_display[lower]
    
    parts = [p.strip() for p in text.split('+') if p.strip()]
    if not parts:
        return text
        
    part_display = {
        'period': '.',
        'comma': ',',
        'slash': '/',
        'backslash': '\\',
        'minus': '-',
        'plus': '+',
        'equal': '=',
        'semicolon': ';',
    }
    part_display.update(single_display)
    
    formatted = []
    for part in parts:
        p_low = part.lower().strip()
        modifier = keynames.canonical_modifier(p_low)
        if modifier is not None:
            formatted.append(keynames.modifier_label(modifier, platform))
        elif p_low in part_display:
            formatted.append(part_display[p_low])
        elif len(p_low) == 1:
            formatted.append(p_low.upper())
        elif p_low.startswith('f') and p_low[1:].isdigit():
            formatted.append(p_low.upper())
        else:
            formatted.append(p_low.title())
            
    return ' + '.join(formatted)
