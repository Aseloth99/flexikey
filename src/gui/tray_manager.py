"""
Tray Manager - Sistem tepsisi yönetimi (Türkçe)
"""

import os
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction, QPixmap, QCursor, QGuiApplication, QActionGroup
from PyQt6.QtCore import QObject, Qt, QPoint, QSize, QTimer

from src.gui.toolbar_icons import toolbar_icon
from src.utils.helpers import get_application_path
from src.utils.theme_manager import accent_hex


class TrayManager(QObject):
    """Sistem tepsisi yöneticisi"""

    def __init__(self, main_window, theme_manager, hotkey_manager):
        super().__init__()
        self.main_window = main_window
        self.theme_manager = theme_manager
        self.hotkey_manager = hotkey_manager

        self.tray_icon = QSystemTrayIcon(self.main_window)
        self.update_action = None
        self.update_separator = None
        self.update_version = ""   # bekleyen güncellemenin sürümü (boş: yok); menü yeniden kurulsa da durum buradan gelir
        self.menu = None

        # İkon ayarla - EXE uyumlu
        icon = self.get_tray_icon()
        self.tray_icon.setIcon(icon)
        
        self.create_menu()
        self.tray_icon.activated.connect(self.on_tray_activated)
        try:   # tema/vurgu değişince menü simgeleri yeni vurguya boyansın
            self.theme_manager.theme_changed.connect(self.refresh_icons)
        except Exception:
            pass
        self.tray_icon.show()
    
    def create_menu(self):
        """Tepsi menüsünü oluştur"""
        from src.utils.locales import get_active_language, language_choices, t
        from src.utils.theme_manager import (
            create_theme_system_icon, create_theme_dark_icon, create_theme_light_icon,
            create_language_icon, create_globe_icon, create_settings_gear_icon, create_eye_icon,
            create_door_exit_icon, create_bolt_icon,
        )

        settings = self.main_window.settings_manager.load_settings()
        lang = get_active_language(settings)
        menu = QMenu()
        menu.setObjectName("tray_menu")
        self.menu = menu

        # En üstte "Güncelle · vX" (kalın, simgeli) ve altında ayırıcı; yalnızca güncelleme bekliyorsa görünür.
        # Tıklayınca doğrudan kurmaz: güncelleme penceresini açar (sürüm notları, boyut, "Şimdi Güncelle").
        self.update_action = QAction(toolbar_icon("update", accent_hex()), "", menu)
        update_font = self.update_action.font()
        update_font.setBold(True)
        self.update_action.setFont(update_font)
        self.update_action.triggered.connect(self.show_update_window)
        menu.addAction(self.update_action)
        self.update_separator = menu.addSeparator()
        self._apply_update_state(lang)

        # Göster/Gizle: pencere durumuna göre DİNAMİK (menü her açılışta yeniden okunur)
        self.show_action = QAction(
            create_eye_icon(), t("tray_hide", lang) if self.main_window.isVisible() else t("tray_show", lang), menu)
        self.show_action.triggered.connect(self.toggle_window)
        menu.addAction(self.show_action)

        self.settings_action = QAction(create_settings_gear_icon(), t("settings", lang), menu)
        self.settings_action.triggered.connect(self.main_window.show_settings)
        menu.addAction(self.settings_action)
        
        self.theme_menu = menu.addMenu(t("theme", lang))
        self.theme_menu.setIcon(create_theme_system_icon())
        self.theme_group = QActionGroup(menu)
        self.theme_group.setExclusive(True)

        self.system_action = QAction(create_theme_system_icon(), t("theme_system", lang), menu)
        self.system_action.setCheckable(True)
        self.system_action.triggered.connect(lambda: self.change_theme('system'))
        self.theme_group.addAction(self.system_action)
        self.theme_menu.addAction(self.system_action)
        
        self.dark_action = QAction(create_theme_dark_icon(), t("theme_dark", lang), menu)
        self.dark_action.setCheckable(True)
        self.dark_action.triggered.connect(lambda: self.change_theme('dark'))
        self.theme_group.addAction(self.dark_action)
        self.theme_menu.addAction(self.dark_action)

        self.light_action = QAction(create_theme_light_icon(), t("theme_light", lang), menu)
        self.light_action.setCheckable(True)
        self.light_action.triggered.connect(lambda: self.change_theme('light'))
        self.theme_group.addAction(self.light_action)
        self.theme_menu.addAction(self.light_action)
        
        self.update_theme_menu()

        self.lang_menu = menu.addMenu(t("language", lang))
        self.lang_menu.setIcon(create_globe_icon())
        self.lang_group = QActionGroup(menu)
        self.lang_group.setExclusive(True)

        self._lang_actions: dict[str, QAction] = {}
        for code, label in language_choices(include_auto=True, lang=lang):
            act = QAction(create_language_icon(code), label, menu)
            act.setCheckable(True)
            act.triggered.connect(lambda checked=False, c=code: self.change_language(c))
            self.lang_group.addAction(act)
            self.lang_menu.addAction(act)
            self._lang_actions[code] = act
        self.update_language_menu()
        
        menu.addSeparator()
        
        self.quick_menu = menu.addMenu(t("tray_quick_actions", lang))
        self.quick_menu.setIcon(create_bolt_icon())
        
        self.disable_all_action = QAction(t("tray_disable_all", lang), menu)
        self.disable_all_action.triggered.connect(self.disable_all_hotkeys)
        self.quick_menu.addAction(self.disable_all_action)
        
        self.reload_config_action = QAction(t("tray_reload_config", lang), menu)
        self.reload_config_action.triggered.connect(self.reload_configuration)
        self.quick_menu.addAction(self.reload_config_action)
        
        menu.addSeparator()

        self.exit_action = QAction(create_door_exit_icon("#ef4444"), t("tray_exit", lang), menu)
        self.exit_action.triggered.connect(self.exit_application)
        menu.addAction(self.exit_action)

        menu.aboutToShow.connect(self._on_menu_about_to_show)
        self.theme_menu.aboutToShow.connect(self._refresh_selection_menus)
        self.lang_menu.aboutToShow.connect(self._refresh_selection_menus)
        self.tray_icon.setContextMenu(menu)

    def set_update_available(self, version: str = ""):
        """Bekleyen güncellemeyi tepsi menüsünün en üstünde "Güncelle · vX" olarak göster (version boşsa gizle).
        Durum burada tutulur: menü sonradan (yeniden) kurulsa da satır doğru görünür."""
        self.update_version = str(version or "")
        self._apply_update_state()

    def _apply_update_state(self, lang: str | None = None):
        if self.update_action is None:
            return
        from src.utils.locales import get_active_language, t
        visible = bool(self.update_version)
        if visible:
            if lang is None:
                lang = get_active_language(self.main_window.settings_manager.load_settings())
            self.update_action.setText(t("tray_update_now", lang).format(version=self.update_version))
        self.update_action.setVisible(visible)
        if self.update_separator is not None:
            self.update_separator.setVisible(visible)

    def show_update_window(self):
        """Tepsideki "Güncelle · vX": güncelleme penceresini açtırır (ana pencere gizliyken de uygulama öne getirir)."""
        self.main_window.show_pending_update()

    def get_tray_icon(self):
        """Tray ikonu al - EXE uyumlu"""
        import sys

        icon_rel = os.path.join('assets', 'icons', 'keyboard.png')
        icon_paths = []

        # Önce PyInstaller bundle içinde ara
        try:
            base_path = sys._MEIPASS
            icon_paths.append(os.path.join(base_path, icon_rel))
        except AttributeError:
            pass

        # Sonra uygulama klasöründe ara (kaynaktan çalışırken proje kökü)
        icon_paths.append(os.path.join(get_application_path(), icon_rel))

        # Son olarak mevcut çalışma dizininde ara
        icon_paths.append(os.path.join(os.path.abspath("."), icon_rel))

        # İlk bulunan icon'u kullan
        for icon_path in icon_paths:
            if os.path.exists(icon_path):
                icon = QIcon(icon_path)
                # Tray icon için uygun boyutları ekle (16x16, 32x32)
                pixmap = QPixmap(icon_path)
                if not pixmap.isNull():
                    # Farklı boyutlarda icon ekle
                    icon.addPixmap(pixmap.scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation), QIcon.Mode.Normal, QIcon.State.Off)
                    icon.addPixmap(pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation), QIcon.Mode.Normal, QIcon.State.Off)
                return icon
        
        # Icon bulunamazsa sistem ikonu kullan
        # (assets/icons/keyboard.png dosyası bulunamadıysa)
        from PyQt6.QtWidgets import QStyle
        style = self.main_window.style()
        if style:
            return style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        
        # Son çare: boş icon
        return QIcon()
    
    def on_tray_activated(self, reason):
        """Simgeye TEK tık (ya da çift tık) pencereyi açar / öne getirir (Windows alışkanlığı). Gizlemek için menüdeki "Gizle"."""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window()

    def show_window(self):
        """Pencereyi göster ve öne getir (simge durumundaysa eski boyutuna döndür)."""
        window = self.main_window
        if window.isMinimized():
            window.showNormal()
        else:
            window.show()
        window.raise_()
        window.activateWindow()
        self._sync_show_action()

    def _sync_show_action(self):
        """"Göster" / "Gizle" etiketi pencerenin gerçek durumuna uysun (tepsiye gizleme, simge tıklaması, güncelleme vb.)."""
        if not hasattr(self, "show_action"):
            return
        from src.utils.locales import get_active_language, t
        lang = get_active_language(self.main_window.settings_manager.load_settings())
        self.show_action.setText(t("tray_hide", lang) if self.main_window.isVisible() else t("tray_show", lang))

    def refresh_icons(self, *_):
        """Vurgu/tema değişince vurguya bağlı menü simgelerini yeniden boyar."""
        from src.utils.theme_manager import create_bolt_icon, create_eye_icon, create_globe_icon, create_settings_gear_icon
        if self.update_action is not None:
            self.update_action.setIcon(toolbar_icon("update", accent_hex()))
        for name, make in (("show_action", create_eye_icon), ("settings_action", create_settings_gear_icon)):
            action = getattr(self, name, None)
            if action is not None:
                action.setIcon(make())
        for name, make in (("lang_menu", create_globe_icon), ("quick_menu", create_bolt_icon)):
            menu = getattr(self, name, None)
            if menu is not None:
                menu.setIcon(make())
        if hasattr(self, "system_action"):
            self.update_theme_menu()
        if hasattr(self, "_lang_actions"):
            self.update_language_menu()

    def _tray_menu_pos(self) -> QPoint:
        pos = QCursor.pos()
        hint = self.menu.sizeHint() if self.menu is not None else QSize(160, 200)
        width = hint.width()
        height = hint.height()
        screen = QGuiApplication.screenAt(pos)
        if screen is not None:
            bounds = screen.availableGeometry()
            x = min(max(pos.x(), bounds.left()), max(bounds.left(), bounds.right() - width))
            y = min(max(pos.y(), bounds.top()), max(bounds.top(), bounds.bottom() - height))
            return QPoint(x, y)
        return pos

    def _fix_tray_menu_pos(self):
        """Windows DPI sapmasında menüyü imleç yanına çek."""
        pos = self._tray_menu_pos()
        QTimer.singleShot(0, lambda p=pos: self.menu.move(p) if self.menu else None)

    def _refresh_selection_menus(self):
        self.update_theme_menu()
        self.update_language_menu()

    def _on_menu_about_to_show(self):
        self._sync_show_action()
        self._refresh_selection_menus()
        self._fix_tray_menu_pos()
    
    def toggle_window(self):
        """Pencereyi göster/gizle"""
        from src.utils.locales import get_active_language, t
        lang = get_active_language(self.main_window.settings_manager.load_settings())
        if self.main_window.isVisible():
            self.main_window.hide()
            self.show_action.setText(t("tray_show", lang))
        else:
            self.main_window.show()
            self.main_window.activateWindow()
            self.show_action.setText(t("tray_hide", lang))
    
    def change_theme(self, theme):
        """Temayı değiştir ve kaydet"""
        if hasattr(self.main_window, "apply_theme"):
            self.main_window.apply_theme(theme)
        else:
            self.theme_manager.set_theme(theme)
        self.update_theme_menu()

    def change_language(self, lang_choice):
        if hasattr(self.main_window, "apply_language"):
            self.main_window.apply_language(lang_choice)
        self.update_language_menu()
    
    def update_theme_menu(self):
        """Tema menüsünü güncelle"""
        from src.utils.locales import get_active_language, t
        from src.utils.theme_manager import (
            create_theme_system_icon, create_theme_dark_icon, create_theme_light_icon,
        )
        saved = "system"
        try:
            saved = self.main_window.settings_manager.load_settings().get("theme", "system")
        except Exception:
            pass
        lang = get_active_language(self.main_window.settings_manager.load_settings())
        is_system = saved == "system"
        is_dark = ("dark" in saved) and not is_system
        is_light = ("light" in saved) and not is_system
        pairs = (
            (self.system_action, is_system, t("theme_system", lang), create_theme_system_icon),
            (self.dark_action, is_dark, t("theme_dark", lang), create_theme_dark_icon),
            (self.light_action, is_light, t("theme_light", lang), create_theme_light_icon),
        )
        for act, selected, label, icon_fn in pairs:
            act.setChecked(selected)
            act.setText(label)
            act.setIcon(icon_fn())

    def update_language_menu(self):
        from src.utils.locales import AUTO_LANGUAGE, get_active_language, language_choices
        from src.utils.theme_manager import create_language_icon, create_globe_icon
        settings = self.main_window.settings_manager.load_settings()
        choice = settings.get("language", AUTO_LANGUAGE)
        lang = get_active_language(settings)
        labels = {code: label for code, label in language_choices(include_auto=True, lang=lang)}
        for code, act in getattr(self, "_lang_actions", {}).items():
            act.setChecked(choice == code)
            act.setText(labels.get(code, code))
            act.setIcon(create_language_icon(code))
        if hasattr(self, "lang_menu"):
            self.lang_menu.setIcon(create_globe_icon())

    def retranslate(self, lang: str):
        from src.utils.locales import t
        visible = self.main_window.isVisible()
        self.show_action.setText(t("tray_hide", lang) if visible else t("tray_show", lang))
        if hasattr(self, "settings_action"):
            self.settings_action.setText(t("settings", lang))
        if hasattr(self, "theme_menu"):
            self.theme_menu.setTitle(t("theme", lang))
        if hasattr(self, "lang_menu"):
            self.lang_menu.setTitle(t("language", lang))
        if hasattr(self, "quick_menu"):
            self.quick_menu.setTitle(t("tray_quick_actions", lang))
        if hasattr(self, "disable_all_action"):
            self.disable_all_action.setText(t("tray_disable_all", lang))
        if hasattr(self, "reload_config_action"):
            self.reload_config_action.setText(t("tray_reload_config", lang))
        self._apply_update_state(lang)
        if hasattr(self, "exit_action"):
            self.exit_action.setText(t("tray_exit", lang))
        self.update_theme_menu()
        self.update_language_menu()
    
    def disable_all_hotkeys(self):
        """Tüm kısayolları devre dışı bırak"""
        self.hotkey_manager.clear_all()
        from src.utils.locales import t, get_active_language
        lang = get_active_language(self.main_window.settings_manager.load_settings())
        self.show_message(t("tray_hotkeys_disabled", lang), t("tray_hotkeys_disabled_msg", lang))
    
    def reload_configuration(self):
        """Yapılandırmayı yeniden yükle"""
        self.main_window.reload_settings()
        from src.utils.locales import t, get_active_language
        lang = get_active_language(self.main_window.settings_manager.load_settings())
        self.show_message(t("tray_config_updated", lang), t("tray_config_updated_msg", lang))
    
    def exit_application(self):
        """Uygulamadan çık"""
        # Ana pencereden çıkış fonksiyonunu çağır
        self.main_window.close_app()
    
    def show_message(self, title, message, icon=QSystemTrayIcon.MessageIcon.Information):
        """Tepsi bildirimi göster"""
        self.tray_icon.showMessage(title, message, icon, 3000)
