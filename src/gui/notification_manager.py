import os
import sys
from PyQt6.QtWidgets import QSystemTrayIcon
from PyQt6.QtCore import QObject

from src.utils.helpers import get_application_path
from src.utils.notify import Notifier


def _get_flexikey_icon_path() -> str:
    """FlexiKey uygulama ikonunun mutlak yolunu bulur."""
    base_dirs = []
    if getattr(sys, "frozen", False):
        base_dirs.append(getattr(sys, "_MEIPASS", ""))
        base_dirs.append(os.path.dirname(sys.executable))
    base_dirs.append(get_application_path())
    for b in base_dirs:
        if not b:
            continue
        for sub in [
            os.path.join(b, "assets", "icons", "FlexiKey.ico"),
            os.path.join(b, "assets", "icons", "keyboard.png"),
        ]:
            if os.path.exists(sub):
                return os.path.abspath(sub)
    return ""


class NotificationManager(QObject):
    """Masaüstü bildirim yöneticisi. Tek yol `Notifier` (src/utils/notify.py): Qt'nin çapraz platform tepsi balonu;
    macOS'ta osascript, Linux'ta notify-send yedeği. `show_notifications` ayarı (`enabled`) önceki gibi geçittir."""

    def __init__(self, tray_icon: QSystemTrayIcon = None):
        super().__init__()
        self.tray_icon = tray_icon
        self.enabled = False  # Varsayılan kapalı
        self._lang = "tr"
        self._notifier = Notifier(
            "FlexiKey",
            tray_provider=lambda: self.tray_icon,
            icon_provider=lambda: _get_flexikey_icon_path() or None,   # Linux notify-send simge dosyası olarak kullanır
            enabled_provider=lambda: self.enabled,
        )

    def set_tray_icon(self, tray_icon: QSystemTrayIcon):
        """Tray icon'u ayarla"""
        self.tray_icon = tray_icon

    def set_language(self, lang: str):
        """Bildirim başlıkları için dil ayarla"""
        self._lang = lang

    def show(self, title: str, message: str, icon_type: str = 'info', duration: int = 3000):
        """Masaüstü bildirimi göster (ayar kapalıysa hiçbir şey yapmaz)."""
        if not self.enabled:
            return
        self._notifier.notify(title, message, critical=(icon_type == 'error'), timeout_ms=duration)

    def info(self, message: str, duration: int = 3000):
        """Bilgi bildirimi"""
        from src.utils.locales import t
        self.show(t("app_title", self._lang), message, 'info', duration)
    
    def success(self, message: str, duration: int = 3000):
        """Başarı bildirimi"""
        from src.utils.locales import t
        self.show(t("notif_success", self._lang), message, 'success', duration)
    
    def warning(self, message: str, duration: int = 3000):
        """Uyarı bildirimi"""
        from src.utils.locales import t
        self.show(t("notif_warning", self._lang), message, 'warning', duration)
    
    def error(self, message: str, duration: int = 3000):
        """Hata bildirimi"""
        from src.utils.locales import t
        self.show(t("notif_error", self._lang), message, 'error', duration)
    
    def set_enabled(self, enabled: bool):
        """Bildirimleri aç/kapa"""
        self.enabled = enabled
    
    def is_enabled(self) -> bool:
        """Bildirim durumu"""
        return self.enabled
