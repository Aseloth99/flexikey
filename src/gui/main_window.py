"""
Ana Pencere - QKeySequenceEdit ile profesyonel klavye yakalama
"""

import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTabWidget,
    QLineEdit, QComboBox, QLabel, QDialog,
    QFormLayout, QCheckBox, QTextEdit, QDialogButtonBox,
    QFrame, QFileDialog, QKeySequenceEdit,
    QMenu, QSizePolicy, QApplication, QScrollArea, QGridLayout, QButtonGroup
)
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal, QEvent
from PyQt6.QtGui import QIcon, QKeySequence, QAction, QKeyEvent, QActionGroup, QCursor
import sys
import time
from src.utils.locales import AUTO_LANGUAGE, get_active_language, install_qt_translations, language_choices, t
from src.utils.theme_manager import (
    ACCENTS, DEFAULT_ACCENT, ORDERED_ACCENT_KEYS, accent_hex,
    create_theme_system_icon, create_theme_dark_icon, create_theme_light_icon,
    create_accent_swatch_icon, create_language_icon,
    create_globe_icon,
    create_settings_gear_icon, create_book_help_icon, create_info_about_icon,
    create_keyboard_icon, create_plus_icon, create_edit_pencil_icon,
    create_exit_icon, apply_html_editor_style
)
from src.gui.list_widgets import CardListWidget, HotkeyCard, ExpansionCard
from src.gui.message_box import MessageBox

from src.gui.toolbar_icons import strip_symbols, toolbar_icon
from src.utils.helpers import format_shortcut_for_display, get_application_path
from src.utils.settings_manager import (
    DEFAULT_SETTINGS, exportable_records, is_locked_secret, is_secret_record, register_saved_items, secret_count,
)
from src.utils import startup

try:
    import winreg
except ImportError:
    winreg = None


class EnhancedKeySequenceEdit(QLineEdit):
    """Kısayol ve tek tuşları (Win tuşu, Scroll Lock, Esc vb.) temiz ve kullanıcı dostu yakalayan gelişmiş giriş alanı."""
    
    keySequenceChanged = pyqtSignal(str)
    
    def __init__(self, parent=None, lang: str | None = None):
        super().__init__(parent)
        self._shortcut = ""
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setClearButtonEnabled(True)
        self.setPlaceholderText(t("key_capture_placeholder", lang or get_active_language()))
        self.textChanged.connect(self._on_text_changed)
        
    def _on_text_changed(self, text: str):
        if not text:
            self._shortcut = ""
            self.keySequenceChanged.emit("")
            
    def set_shortcut(self, shortcut: str):
        """Kısayolu canonical formata çevirip kaydeder ve kullanıcı dostu görüntüler."""
        if not shortcut:
            self._shortcut = ""
            self.setText("")
            return
        
        raw = str(shortcut).strip()
        lower = raw.lower()
        lower = lower.replace('meta+', 'win+').replace('windows+', 'win+').replace('cmd+', 'win+')
        if lower.startswith('meta') and '+' not in lower:
            lower = 'win'
            
        single_norm = {
            'scrolllock': 'scroll lock', 'scroll_lock': 'scroll lock',
            'printscreen': 'print screen', 'print_screen': 'print screen',
            'pageup': 'page up', 'page_up': 'page up',
            'pagedown': 'page down', 'page_down': 'page down',
            'capslock': 'caps lock', 'caps_lock': 'caps lock',
            'numlock': 'num lock', 'num_lock': 'num lock',
        }
        if '+' not in lower and lower in single_norm:
            lower = single_norm[lower]
            
        self._shortcut = lower
        display = format_shortcut_for_display(self._shortcut)
        self.setText(display)
        self.keySequenceChanged.emit(self._shortcut)
        
    def get_shortcut(self) -> str:
        return self._shortcut
        
    def setKeySequence(self, sequence):
        """Geriye uyumluluk için QKeySequence veya str kabul eder."""
        if isinstance(sequence, QKeySequence):
            self.set_shortcut(sequence.toString())
        else:
            self.set_shortcut(str(sequence) if sequence else "")
            
    def keySequence(self):
        """Geriye uyumluluk: QKeySequence nesnesi döndürür."""
        return QKeySequence(self._shortcut)
        
    def toString(self) -> str:
        return self._shortcut
        
    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()
        
        # Yalnızca modifier tuşuna basıldıysa anlık görsel geri bildirim ver
        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
            Qt.Key.Key_AltGr,
        ):
            mods = []
            if modifiers & Qt.KeyboardModifier.ControlModifier or key == Qt.Key.Key_Control:
                mods.append("Ctrl")
            if modifiers & Qt.KeyboardModifier.AltModifier or key == Qt.Key.Key_Alt:
                mods.append("Alt")
            if modifiers & Qt.KeyboardModifier.ShiftModifier or key == Qt.Key.Key_Shift:
                mods.append("Shift")
            if modifiers & Qt.KeyboardModifier.MetaModifier or key == Qt.Key.Key_Meta:
                mods.append("Win")
            if mods:
                self.setText(" + ".join(mods) + " + ...")
            event.accept()
            return
            
        # Modifier listesi oluştur
        mods_canonical = []
        mods_display = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            mods_canonical.append('ctrl')
            mods_display.append('Ctrl')
        if modifiers & Qt.KeyboardModifier.AltModifier:
            mods_canonical.append('alt')
            mods_display.append('Alt')
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            mods_canonical.append('shift')
            mods_display.append('Shift')
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            mods_canonical.append('win')
            mods_display.append('Win')
            
        canonical_key, display_key = self._resolve_key(key, event)
        if not canonical_key:
            event.accept()
            return
            
        if mods_canonical:
            final_canonical = "+".join(mods_canonical) + "+" + canonical_key
            final_display = " + ".join(mods_display) + " + " + display_key
        else:
            final_canonical = canonical_key
            final_display = display_key
            
        self._shortcut = final_canonical
        self.setText(final_display)
        self.keySequenceChanged.emit(self._shortcut)
        event.accept()
        
    def _resolve_key(self, key: int, event: QKeyEvent) -> tuple:
        """(canonical_name, display_name) döndürür."""
        special_keys = {
            Qt.Key.Key_ScrollLock: ('scroll lock', 'Scroll Lock'),
            Qt.Key.Key_Pause: ('pause', 'Pause'),
            Qt.Key.Key_Print: ('print screen', 'Print Screen'),
            Qt.Key.Key_Insert: ('insert', 'Insert'),
            Qt.Key.Key_Delete: ('delete', 'Delete'),
            Qt.Key.Key_Home: ('home', 'Home'),
            Qt.Key.Key_End: ('end', 'End'),
            Qt.Key.Key_PageUp: ('page up', 'Page Up'),
            Qt.Key.Key_PageDown: ('page down', 'Page Down'),
            Qt.Key.Key_Up: ('up', '↑'),
            Qt.Key.Key_Down: ('down', '↓'),
            Qt.Key.Key_Left: ('left', '←'),
            Qt.Key.Key_Right: ('right', '→'),
            Qt.Key.Key_Enter: ('enter', 'Enter'),
            Qt.Key.Key_Return: ('enter', 'Enter'),
            Qt.Key.Key_Tab: ('tab', 'Tab'),
            Qt.Key.Key_Backspace: ('backspace', 'Backspace'),
            Qt.Key.Key_Escape: ('esc', 'Esc'),
            Qt.Key.Key_Space: ('space', 'Space'),
            Qt.Key.Key_CapsLock: ('caps lock', 'Caps Lock'),
            Qt.Key.Key_NumLock: ('num lock', 'Num Lock'),
        }
        if key in special_keys:
            return special_keys[key]
            
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
            n = key - Qt.Key.Key_F1 + 1
            return (f"f{n}", f"F{n}")
            
        try:
            native_vk = event.nativeVirtualKey()
            if native_vk:
                if 0x30 <= native_vk <= 0x39:
                    ch = chr(native_vk)
                    return (ch, ch)
                if 0x41 <= native_vk <= 0x5A:
                    ch = chr(native_vk)
                    return (ch.lower(), ch.upper())
                if 0x60 <= native_vk <= 0x69:
                    num = str(native_vk - 0x60)
                    return (f"numpad {num}", f"Num {num}")
                vk_punct = {
                    0xBE: ('.', '.'),
                    0xBC: (',', ','),
                    0xBF: ('/', '/'),
                    0xBA: (';', ';'),
                    0xDE: ("'", "'"),
                    0xDC: ('\\', '\\'),
                    0xDB: ('[', '['),
                    0xDD: (']', ']'),
                    0xBD: ('-', '-'),
                    0xBB: ('=', '='),
                    0xC0: ('`', '`'),
                    0x6E: ('.', 'Num .'),
                    0x6A: ('*', 'Num *'),
                    0x6B: ('+', 'Num +'),
                    0x6D: ('-', 'Num -'),
                    0x6F: ('/', 'Num /'),
                }
                if native_vk in vk_punct:
                    return vk_punct[native_vk]
        except Exception:
            pass
            
        try:
            t = event.text().strip()
            if t and len(t) == 1:
                return (t.lower(), t.upper())
        except Exception:
            pass
            
        if 32 <= key <= 126:
            ch = chr(key)
            return (ch.lower(), ch.upper())
            
        try:
            key_enum = Qt.Key(key)
            name = key_enum.name if hasattr(key_enum, 'name') else None
            if name and name.startswith('Key_'):
                clean = name[4:].lower().replace('_', ' ')
                return (clean, clean.title())
        except Exception:
            pass
            
        return ("", "")


def is_system_dark_mode():
    """Sistem koyu tema mı? Windows / macOS / Linux."""
    if sys.platform == "win32" and winreg is not None:
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                0,
                winreg.KEY_READ
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 0
        except Exception:
            return True   # okunamadı: varsayılan koyu (diğer uygulamalarla aynı)
    if sys.platform == "darwin":
        try:
            import subprocess
            out = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True, timeout=3,
            )
            return "Dark" in (out.stdout or "")
        except Exception:
            return True
    theme = os.environ.get("GTK_THEME", "") + " " + os.environ.get("QT_STYLE_OVERRIDE", "")
    return "dark" in theme.lower()


def is_windows_dark_mode():
    """Eski ad — is_system_dark_mode ile aynı."""
    return is_system_dark_mode()


def fade_in_window(widget, step: float = 0.1, interval: int = 15, delay: int = 0) -> None:
    """Pencereyi yumuşakça görünür yapar (opaklık 0 -> 1).

    Zamanlayıcı pencereden UZUN yaşayabilir (hemen kapatılan/silinen pencere, testler). Silinmiş C++ nesnesine dokunmak
    RuntimeError verir; PyQt6 bunu yakalanmamış slot istisnası sayıp uygulamayı abort() ile sonlandırır (Windows'ta çıkış kodu
    0xC0000409). Bu yüzden tik içinde korunur: pencere silindiyse zincir sessizce biter."""
    try:
        widget.setWindowOpacity(0)
    except RuntimeError:
        return

    def tick():
        try:
            opacity = widget.windowOpacity()
            if opacity < 1:
                widget.setWindowOpacity(opacity + step)
                QTimer.singleShot(interval, tick)
        except RuntimeError:      # pencere bu arada silindi
            return

    if delay:
        QTimer.singleShot(delay, tick)
    else:
        tick()


def polish_widget(widget):
    """Dinamik class özelliğinin QSS'te uygulanmasını sağlar."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def apply_window_rounding(window):
    """Windows 11 DWM pencere yuvarlama niteliğini ayarlar"""
    if sys.platform == "win32":
        try:
            import ctypes
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = 2
            hwnd = int(window.winId())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(ctypes.c_int(DWMWCP_ROUND)),
                ctypes.sizeof(ctypes.c_int)
            )
        except Exception:
            pass


def apply_rounded_mask(widget, radius: int = 16):
    """Frameless pencerede içerik köşelerini yuvarlatır."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QPainterPath, QRegion
    rect = widget.rect()
    if rect.width() <= 0 or rect.height() <= 0:
        return
    path = QPainterPath()
    path.addRoundedRect(QRectF(rect), radius, radius)
    widget.setMask(QRegion(path.toFillPolygon().toPolygon()))


class IconLabel(QLabel):
    """Başlık/kart başlığı simgesi: emoji yerine vektör çizim (vurgu renginde; `refresh()` ile yeni vurguya boyanır)."""

    def __init__(self, kind: str, size: int = 18, parent=None):
        super().__init__(parent)
        self.kind = kind
        self._icon_size = size
        self.setFixedSize(size + 2, size + 2)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.refresh()

    def refresh(self) -> None:
        self.setPixmap(toolbar_icon(self.kind, accent_hex(), self._icon_size).pixmap(self._icon_size, self._icon_size))


def make_section_header(kind: str, text: str):
    """Ayar kartı başlığı: vektör simge + başlık metni. (satır widget'ı, metin etiketi, simge etiketi)"""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    icon = IconLabel(kind, 16)
    label = QLabel(text)
    label.setObjectName("section_header")
    layout.addWidget(icon)
    layout.addWidget(label)
    layout.addStretch()
    return row, label, icon


def make_hint_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint_label")
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    return label


def wrap_field_with_hint(control: QWidget, hint_text: str) -> QWidget:
    wrap = QWidget()
    wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    layout = QVBoxLayout(wrap)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    layout.addWidget(control)
    layout.addWidget(make_hint_label(hint_text))
    return wrap


class FramelessResizableDialog(QDialog):
    """Kenarlardan boyutlandırılabilen frameless diyalog tabanı."""

    _RESIZE_CORNER = 20
    _RESIZE_EDGE = 8

    def _init_frameless_resize(self):
        self._resize_edge = None
        self._resize_start = None
        self._resize_geom = None
        self._override_shape = None
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        QTimer.singleShot(0, self._enable_own_mouse_tracking)   # bağlı metot: pencere silinirse çağrı iptal olur (lambda olmaz)

    def _enable_own_mouse_tracking(self):
        self._enable_mouse_tracking(self)

    def _hit_resize_edges(self, pos):
        r = self.rect()
        x, y = pos.x(), pos.y()
        w, h = r.width(), r.height()
        if w <= 0 or h <= 0:
            return 0
        corner = self._RESIZE_CORNER
        edge = self._RESIZE_EDGE
        if x <= corner and y <= corner:
            return 1 | 4
        if x >= w - corner and y <= corner:
            return 2 | 4
        if x <= corner and y >= h - corner:
            return 1 | 8
        if x >= w - corner and y >= h - corner:
            return 2 | 8
        flags = 0
        if x <= edge:
            flags |= 1
        if x >= w - edge:
            flags |= 2
        if y <= edge:
            flags |= 4
        if y >= h - edge:
            flags |= 8
        return flags

    def _cursor_for_edge(self, edge):
        if edge in (1 | 4, 2 | 8):
            return Qt.CursorShape.SizeFDiagCursor
        if edge in (2 | 4, 1 | 8):
            return Qt.CursorShape.SizeBDiagCursor
        if edge in (1, 2):
            return Qt.CursorShape.SizeHorCursor
        if edge in (4, 8):
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def _enable_mouse_tracking(self, widget):
        if widget is None or isinstance(widget, QMenu):
            return
        widget.setMouseTracking(True)
        widget.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        for child in widget.findChildren(QWidget):
            if isinstance(child, QMenu):
                continue
            child.setMouseTracking(True)
            child.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def _clear_resize_cursor(self):
        if getattr(self, "_override_shape", None) is not None:
            QApplication.restoreOverrideCursor()
            self._override_shape = None
        self.unsetCursor()

    def _apply_edge_cursor(self, local):
        edge = self._hit_resize_edges(local)
        shape = self._cursor_for_edge(edge)
        if not edge:
            self._clear_resize_cursor()
            return edge
        if self._override_shape != shape:
            if self._override_shape is None:
                QApplication.setOverrideCursor(QCursor(shape))
            else:
                QApplication.changeOverrideCursor(QCursor(shape))
            self._override_shape = shape
        self.setCursor(shape)
        return edge

    def _event_global_pos(self, event):
        if hasattr(event, "globalPosition"):
            return event.globalPosition().toPoint()
        if hasattr(event, "globalPos"):
            return event.globalPos()
        return QCursor.pos()

    def _apply_resize_delta(self, delta):
        geom = self._resize_geom
        if geom is None or not self._resize_edge:
            return
        x, y, w, h = geom.x(), geom.y(), geom.width(), geom.height()
        min_w, min_h = self.minimumWidth(), self.minimumHeight()
        if self._resize_edge & 1:
            x = min(geom.x() + delta.x(), geom.right() - min_w + 1)
            w = geom.right() - x + 1
        if self._resize_edge & 2:
            w = max(min_w, geom.width() + delta.x())
        if self._resize_edge & 4:
            y = min(geom.y() + delta.y(), geom.bottom() - min_h + 1)
            h = geom.bottom() - y + 1
        if self._resize_edge & 8:
            h = max(min_h, geom.height() + delta.y())
        self.setGeometry(x, y, w, h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "chrome"):
            apply_rounded_mask(self.chrome, 12)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._hit_resize_edges(event.position().toPoint())
            if edge:
                self._resize_edge = edge
                self._resize_start = event.globalPosition().toPoint()
                self._resize_geom = self.geometry()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._resize_edge and self._resize_start is not None:
            self._apply_resize_delta(event.globalPosition().toPoint() - self._resize_start)
            event.accept()
            return
        self._apply_edge_cursor(pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resize_edge = None
        self._resize_start = None
        self._resize_geom = None
        self._apply_edge_cursor(self.mapFromGlobal(self._event_global_pos(event)))
        super().mouseReleaseEvent(event)

    def hideEvent(self, event):
        self._clear_resize_cursor()
        super().hideEvent(event)

    def closeEvent(self, event):
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._clear_resize_cursor()
        super().closeEvent(event)

    def eventFilter(self, watched, event):
        et = event.type()
        if et not in (
            QEvent.Type.MouseMove,
            QEvent.Type.HoverMove,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.Leave,
        ):
            return super().eventFilter(watched, event)
        if not isinstance(watched, QWidget) or watched.window() is not self:
            return super().eventFilter(watched, event)
        if et == QEvent.Type.Leave:
            if watched is self and not self._resize_edge:
                self._clear_resize_cursor()
            return super().eventFilter(watched, event)
        gp = self._event_global_pos(event)
        local = self.mapFromGlobal(gp)
        if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            edge = self._hit_resize_edges(local)
            if edge:
                self._resize_edge = edge
                self._resize_start = gp
                self._resize_geom = self.geometry()
                self._apply_edge_cursor(local)
                return True
        elif et in (QEvent.Type.MouseMove, QEvent.Type.HoverMove):
            if self._resize_edge and self._resize_start is not None:
                self._apply_resize_delta(gp - self._resize_start)
                return True
            self._apply_edge_cursor(local)
        elif et == QEvent.Type.MouseButtonRelease:
            self._resize_edge = None
            self._resize_start = None
            self._resize_geom = None
            self._apply_edge_cursor(local)
        return super().eventFilter(watched, event)


class ImportExportDialog(QDialog):
    """İçe/Dışa Aktarma Seçim Dialog'u - Modern ve Yuvarlatılmış"""
    
    def __init__(self, parent, is_export=True):
        super().__init__(parent)
        self.is_export = is_export
        self.lang = get_active_language(
            parent.settings_manager.load_settings()
            if parent and hasattr(parent, "settings_manager")
            else None
        )
        self.setWindowTitle(
            t("ie_export_title", self.lang) if is_export else t("ie_import_title", self.lang)
        )
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(440)
        self._drag_pos = None
        
        self.setup_ui()
        self.animate_entry()
    
    def showEvent(self, event):
        super().showEvent(event)
        apply_window_rounding(self)
    
    def animate_entry(self):
        fade_in_window(self, 0.1, 15)
    
    def _title_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def _title_mouse_move(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
    
    def _title_mouse_release(self, event):
        self._drag_pos = None
        event.accept()
    
    def setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(6, 6, 6, 6)
        outer_layout.setSpacing(0)
        
        self.chrome = QFrame()
        self.chrome.setObjectName("dialog_chrome")
        chrome_layout = QVBoxLayout(self.chrome)
        chrome_layout.setContentsMargins(0, 0, 0, 0)
        chrome_layout.setSpacing(0)
        
        # Title bar
        title_bar = QFrame()
        title_bar.setObjectName("title_bar")
        title_bar.setFixedHeight(38)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 8, 0)
        title_layout.setSpacing(10)

        self._title_icon = IconLabel("upload" if self.is_export else "download", 16)
        title_layout.addWidget(self._title_icon)
        
        title_label = QLabel(
            t("ie_export_title", self.lang) if self.is_export else t("ie_import_title", self.lang)
        )
        title_label.setObjectName("title_label")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        close_btn = QPushButton("×")
        close_btn.setObjectName("window_close_btn")
        close_btn.setToolTip(t("close", self.lang))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        title_layout.addWidget(close_btn)
        
        title_bar.mousePressEvent = self._title_mouse_press
        title_bar.mouseMoveEvent = self._title_mouse_move
        title_bar.mouseReleaseEvent = self._title_mouse_release
        chrome_layout.addWidget(title_bar)
        
        # İçerik Alanı
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 16)
        
        header_text = t("ie_export_header", self.lang) if self.is_export else t("ie_import_header", self.lang)
        header = QLabel(header_text)
        header.setObjectName("section_header")
        layout.addWidget(header)
        
        card = QFrame()
        card.setObjectName("card_frame")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(10)
        
        self.select_all_check = QCheckBox(t("ie_select_all", self.lang))
        self.select_all_check.setChecked(True)
        self.select_all_check.setStyleSheet("font-weight: 700;")
        self.select_all_check.toggled.connect(self.on_select_all_toggled)
        card_layout.addWidget(self.select_all_check)
        
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        card_layout.addWidget(sep)
        
        self.hotkeys_check = QCheckBox(t("ie_cat_hotkeys", self.lang))
        self.hotkeys_check.setChecked(True)
        card_layout.addWidget(self.hotkeys_check)
        
        self.expansions_check = QCheckBox(t("ie_cat_expansions", self.lang))
        self.expansions_check.setChecked(True)
        card_layout.addWidget(self.expansions_check)
        
        self.theme_check = QCheckBox(t("ie_cat_theme", self.lang))
        self.theme_check.setChecked(True)
        card_layout.addWidget(self.theme_check)
        
        self.behavior_check = QCheckBox(t("ie_cat_behavior", self.lang))
        self.behavior_check.setChecked(True)
        card_layout.addWidget(self.behavior_check)
        
        self.update_check = QCheckBox(t("ie_cat_update", self.lang))
        self.update_check.setChecked(True)
        card_layout.addWidget(self.update_check)
        
        layout.addWidget(card)
        layout.addStretch()
        
        # Butonlar
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()
        
        cancel_btn = QPushButton(t("cancel", self.lang))
        cancel_btn.setProperty("class", "secondary")
        cancel_btn.setMinimumSize(90, 36)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton(t("continue", self.lang))
        ok_btn.setProperty("class", "primary")
        ok_btn.setMinimumSize(110, 36)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        
        layout.addLayout(btn_layout)
        chrome_layout.addWidget(body, 1)
        outer_layout.addWidget(self.chrome)
    
    def on_select_all_toggled(self, checked):
        """Tümünü seç/seçimi kaldır"""
        self.hotkeys_check.setChecked(checked)
        self.expansions_check.setChecked(checked)
        self.theme_check.setChecked(checked)
        self.behavior_check.setChecked(checked)
        self.update_check.setChecked(checked)
    
    def get_selected_options(self):
        """Seçilen seçenekleri döndür"""
        return {
            'hotkeys': self.hotkeys_check.isChecked(),
            'expansions': self.expansions_check.isChecked(),
            'theme': self.theme_check.isChecked(),
            'behavior': self.behavior_check.isChecked(),
            'update': self.update_check.isChecked()
        }


class SettingsDialog(QDialog):
    """Modern ve Yuvarlatılmış (Rounded) Ayarlar Penceresi"""
    
    def __init__(self, parent, settings_manager, theme_manager, notification_manager, update_checker=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.theme_manager = theme_manager
        self.notification_manager = notification_manager
        self.update_checker = update_checker
        self.parent_window = parent

        self._saved_settings = self.settings_manager.load_settings()
        self.lang = get_active_language(self._saved_settings)
        self._initial_theme = self._saved_settings.get('theme', 'system')
        self._initial_accent = self._saved_settings.get('accent', DEFAULT_ACCENT)
        self.selected_accent = self._initial_accent
        
        self.setWindowTitle(t("settings_title", self.lang))
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumWidth(560)
        self.setMinimumHeight(0)
        
        self._drag_pos = None
        self._accent_buttons = {}
        
        self.setup_ui()
        self.load_settings()
        self.animate_entry()
        self.finished.connect(self._cleanup_update_connection)
    
    def showEvent(self, event):
        super().showEvent(event)
        apply_window_rounding(self)
    
    def _cleanup_update_connection(self):
        self._checking_updates = False
        if hasattr(self, "update_check"):
            self.update_check.cancel()
        if hasattr(self, "check_update_btn"):
            self.check_update_btn.setEnabled(True)
            self.check_update_btn.setText(t("check_updates", self.lang))
        if self.update_checker:
            try:
                self.update_checker.check_complete.disconnect(self.on_check_complete)
            except (TypeError, RuntimeError):
                pass
            try:
                self.update_checker.check_failed.disconnect(self.on_check_failed)
            except (TypeError, RuntimeError):
                pass
    
    def animate_entry(self):
        fade_in_window(self, 0.1, 15)
    
    def setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(6, 6, 6, 6)
        outer_layout.setSpacing(0)
        
        # Rounded Container Chrome
        self.chrome = QFrame()
        self.chrome.setObjectName("dialog_chrome")
        chrome_layout = QVBoxLayout(self.chrome)
        chrome_layout.setContentsMargins(0, 0, 0, 0)
        chrome_layout.setSpacing(0)
        
        # Title Bar
        title_bar = QFrame()
        title_bar.setObjectName("title_bar")
        title_bar.setFixedHeight(38)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 8, 0)
        title_layout.setSpacing(10)

        self._header_icons = []
        self._title_icon = IconLabel("gear", 16)
        self._header_icons.append(self._title_icon)
        title_layout.addWidget(self._title_icon)

        title_label = QLabel(t("settings_title", self.lang))
        title_label.setObjectName("title_label")
        title_layout.addWidget(title_label)
        
        title_layout.addStretch()
        
        close_btn = QPushButton("×")
        close_btn.setObjectName("window_close_btn")
        close_btn.setToolTip(t("cancel", self.lang))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.reject_and_restore)
        title_layout.addWidget(close_btn)
        
        title_bar.mousePressEvent = self._title_mouse_press
        title_bar.mouseMoveEvent = self._title_mouse_move
        title_bar.mouseReleaseEvent = self._title_mouse_release
        chrome_layout.addWidget(title_bar)
        
        # İçerik Alanı
        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(16, 12, 16, 8)
        body_layout.setSpacing(10)
        
        # ── 1. Görünüm & Tema Kartı ──
        appearance_card = QFrame()
        appearance_card.setObjectName("card_frame")
        appearance_layout = QVBoxLayout(appearance_card)
        appearance_layout.setContentsMargins(14, 10, 14, 12)
        appearance_layout.setSpacing(8)
        
        app_header, _label, icon = make_section_header("palette", t('appearance', self.lang))
        self._header_icons.append(icon)
        appearance_layout.addWidget(app_header)
        
        # Tema & Dil Seçimi (Yan yana)
        controls_row = QHBoxLayout()
        controls_row.setSpacing(14)
        
        # Tema
        theme_col = QVBoxLayout()
        theme_col.setSpacing(6)
        theme_label = QLabel(t("theme", self.lang))
        theme_label.setStyleSheet("font-weight: 600; font-size: 9pt;")
        theme_col.addWidget(theme_label)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([        # Sistem / Koyu / Açık (her yerde aynı sıra); indeks eşlemesi THEME_BY_INDEX
            t("theme_system", self.lang),
            t("theme_dark", self.lang),
            t("theme_light", self.lang),
        ])
        self.theme_manager.style_combo(self.theme_combo)
        self.theme_combo.currentIndexChanged.connect(self._preview_theme)
        theme_col.addWidget(self.theme_combo)
        controls_row.addLayout(theme_col, 1)
        
        # Dil
        lang_col = QVBoxLayout()
        lang_col.setSpacing(6)
        lang_label = QLabel(t("language", self.lang))
        lang_label.setStyleSheet("font-weight: 600; font-size: 9pt;")
        lang_col.addWidget(lang_label)
        
        self.lang_combo = QComboBox()
        self._populate_lang_combo()
        self.theme_manager.style_combo(self.lang_combo)
        lang_col.addWidget(self.lang_combo)
        controls_row.addLayout(lang_col, 1)
        
        appearance_layout.addLayout(controls_row)
        
        # Vurgu Rengi Seçici
        accent_col = QVBoxLayout()
        accent_col.setSpacing(8)
        accent_title_row = QHBoxLayout()
        accent_label = QLabel(t("accent_color", self.lang))
        accent_label.setStyleSheet("font-weight: 600; font-size: 9pt;")
        accent_title_row.addWidget(accent_label)
        
        self.accent_name_label = QLabel()
        self.accent_name_label.setObjectName("hint_label")
        self.accent_name_label.setStyleSheet("font-weight: 600;")
        accent_title_row.addWidget(self.accent_name_label)
        accent_title_row.addStretch()
        accent_col.addLayout(accent_title_row)
        
        # Renk Butonları Izgarası
        accent_grid = QHBoxLayout()
        accent_grid.setSpacing(10)
        accent_grid.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        for key in ORDERED_ACCENT_KEYS:
            spec = ACCENTS[key]
            btn = QPushButton()
            btn.setFixedSize(32, 32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            label = spec.get("label_tr" if getattr(self, "lang", "tr") == "tr" else "label_en", spec.get("label", key))
            btn.setToolTip(label)
            btn.clicked.connect(lambda checked, k=key: self._on_accent_selected(k))
            self._accent_buttons[key] = btn
            accent_grid.addWidget(btn)
        
        accent_col.addLayout(accent_grid)
        appearance_layout.addLayout(accent_col)
        
        body_layout.addWidget(appearance_card)
        
        # ── 2. Davranış Kartı ──
        behavior_card = QFrame()
        behavior_card.setObjectName("card_frame")
        behavior_layout = QVBoxLayout(behavior_card)
        behavior_layout.setContentsMargins(14, 10, 14, 12)
        behavior_layout.setSpacing(8)
        
        beh_header, _label, icon = make_section_header("bolt", t('behavior', self.lang))
        self._header_icons.append(icon)
        behavior_layout.addWidget(beh_header)

        self.start_min_check = QCheckBox(t("start_minimized", self.lang))
        behavior_layout.addWidget(self.start_min_check)

        self.start_at_login_check = QCheckBox(t("start_at_login", self.lang))
        self.start_at_login_check.setToolTip(t("start_at_login_tip", self.lang))
        behavior_layout.addWidget(self.start_at_login_check)
        
        self.show_notif_check = QCheckBox(t("show_notifications", self.lang))
        self.show_notif_check.setToolTip(t("show_notifications_tip", self.lang))
        behavior_layout.addWidget(self.show_notif_check)
        
        body_layout.addWidget(behavior_card)
        
        # ── 3. Yedekleme & Aktarım Kartı ──
        backup_card = QFrame()
        backup_card.setObjectName("card_frame")
        backup_layout = QVBoxLayout(backup_card)
        backup_layout.setContentsMargins(14, 10, 14, 12)
        backup_layout.setSpacing(8)
        
        backup_header, _label, icon = make_section_header("archive", t('backup_restore', self.lang))
        self._header_icons.append(icon)
        backup_layout.addWidget(backup_header)
        
        backup_hint = QLabel(t("backup_hint", self.lang))
        backup_hint.setObjectName("hint_label")
        backup_hint.setWordWrap(True)
        backup_layout.addWidget(backup_hint)
        
        backup_btn_row = QHBoxLayout()
        backup_btn_row.setSpacing(10)
        
        export_btn = QPushButton(t("export_settings_btn", self.lang))
        export_btn.setIcon(toolbar_icon("upload", self.theme_manager.get_palette()["text_secondary"]))
        export_btn.setIconSize(QSize(15, 15))
        self._backup_buttons = [(export_btn, "upload")]
        export_btn.setProperty("class", "secondary")
        polish_widget(export_btn)
        export_btn.setMinimumHeight(36)
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.clicked.connect(self._on_export_clicked)
        backup_btn_row.addWidget(export_btn)
        
        import_btn = QPushButton(t("import_settings_btn", self.lang))
        import_btn.setIcon(toolbar_icon("download", self.theme_manager.get_palette()["text_secondary"]))
        import_btn.setIconSize(QSize(15, 15))
        self._backup_buttons.append((import_btn, "download"))
        import_btn.setProperty("class", "secondary")
        polish_widget(import_btn)
        import_btn.setMinimumHeight(36)
        import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        import_btn.clicked.connect(self._on_import_clicked)
        backup_btn_row.addWidget(import_btn)
        
        backup_btn_row.addStretch()
        backup_layout.addLayout(backup_btn_row)
        
        body_layout.addWidget(backup_card)
        
        # ── 4. Güncellemeler Kartı ──
        update_card = QFrame()
        update_card.setObjectName("card_frame")
        update_layout = QVBoxLayout(update_card)
        update_layout.setContentsMargins(14, 10, 14, 12)
        update_layout.setSpacing(8)
        
        up_header, _label, icon = make_section_header("refresh", t('updates', self.lang))
        self._header_icons.append(icon)
        update_layout.addWidget(up_header)

        # iki kutu her uygulamada aynı: "Otomatik Kontrol Et" + "Otomatik Kur" (kur, kontrol kapalıyken pasif), ortak kısa ipucu
        self.auto_update_check = QCheckBox(t("auto_update_check", self.lang))
        self.auto_update_check.setToolTip(t("auto_update_tip", self.lang))
        update_layout.addWidget(self.auto_update_check)

        self.auto_update_install = QCheckBox(t("auto_update_install", self.lang))
        self.auto_update_install.setToolTip(t("auto_update_tip", self.lang))
        update_layout.addWidget(self.auto_update_install)
        self.auto_update_check.toggled.connect(self.auto_update_install.setEnabled)

        self._checking_updates = False
        up_btn_row = QHBoxLayout()
        self.check_update_btn = QPushButton(t("check_updates", self.lang))
        self.check_update_btn.setProperty("class", "secondary")
        polish_widget(self.check_update_btn)
        self.check_update_btn.setMinimumHeight(36)
        self.check_update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_update_btn.clicked.connect(self.check_for_updates)
        up_btn_row.addWidget(self.check_update_btn)
        
        from src.utils.updater import UpdateChecker
        checker = UpdateChecker()
        current_version = checker.get_current_version()
        self.update_status = QLabel(t("up_to_date", self.lang).format(current_version))
        self.update_status.setObjectName("update_status")
        from src.gui.update_check_ui import UpdateCheckAnimator
        self.update_check = UpdateCheckAnimator(self.check_update_btn, self.update_status, self)
        pending_version = getattr(self.parent_window, "update_version", "")
        if pending_version:  # sessiz denetim zaten yeni sürüm bulmuş
            self.update_status.setText(t("update_new_version", self.lang).format(version=pending_version))
        up_btn_row.addWidget(self.update_status)
        up_btn_row.addStretch()
        update_layout.addLayout(up_btn_row)
        
        if self.update_checker:
            self.update_checker.check_complete.connect(self.on_check_complete)
            self.update_checker.check_failed.connect(self.on_check_failed)
        
        body_layout.addWidget(update_card)
        chrome_layout.addWidget(body_widget, 1)
        
        # ── Alt Butonlar (Sabit Footer) ──
        footer_widget = QWidget()
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(16, 8, 16, 14)
        footer_layout.setSpacing(10)
        footer_layout.addStretch()
        
        cancel_btn = QPushButton(t("cancel", self.lang))
        cancel_btn.setProperty("class", "secondary")
        polish_widget(cancel_btn)
        cancel_btn.setMinimumSize(100, 36)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject_and_restore)
        footer_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton(t("save", self.lang))
        save_btn.setProperty("class", "primary")
        polish_widget(save_btn)
        save_btn.setMinimumSize(120, 36)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self.save_and_close)
        footer_layout.addWidget(save_btn)
        
        chrome_layout.addWidget(footer_widget)
        outer_layout.addWidget(self.chrome)
    
    def _title_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def _title_mouse_move(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
    
    def _title_mouse_release(self, event):
        self._drag_pos = None
        event.accept()
    
    def _on_accent_selected(self, accent_key: str):
        """Kullanıcı yeni bir vurgu rengi seçtiğinde"""
        self.selected_accent = accent_key
        self._update_accent_buttons_ui()
        self._preview_theme()
    
    def _update_accent_buttons_ui(self):
        """Renk butonlarının görsel durumunu güncelle"""
        # the ring has to contrast with the card behind it: white vanished on the light theme
        ring = self.theme_manager.get_palette().get('text', '#ffffff') if self.theme_manager else '#ffffff'
        for key, btn in self._accent_buttons.items():
            spec = ACCENTS.get(key, ACCENTS[DEFAULT_ACCENT])
            color = spec["accent"]
            is_selected = (key == self.selected_accent)
            
            btn.setText("")
            if is_selected:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {color};
                        border-radius: 16px;
                        border: 3px solid {ring};
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {color};
                        border-radius: 16px;
                        border: 1px solid rgba(0,0,0,0.15);
                    }}
                    QPushButton:hover {{
                        border: 2px solid {ring};
                    }}
                """)
        
        current_spec = ACCENTS.get(self.selected_accent, ACCENTS[DEFAULT_ACCENT])
        self.accent_name_label.setText(
            f"({current_spec.get('label_tr' if self.lang == 'tr' else 'label_en', current_spec['label'])})")
    
    # Tema listesi sırası Sistem / Koyu / Açık: indeks <-> ayar değeri eşlemesi TEK yerde (yükle, önizle, kaydet)
    THEME_BY_INDEX = ('system', 'dark', 'light')

    def _theme_index_for(self, theme: str) -> int:
        if theme == 'system':
            return 0
        return 2 if 'light' in theme else 1

    def _get_current_theme_target(self) -> str:
        theme = self.THEME_BY_INDEX[max(0, min(self.theme_combo.currentIndex(), 2))]
        if theme == 'system':
            return 'dark' if is_system_dark_mode() else 'light'
        return theme

    def _preview_theme(self):
        """Seçilen tema ve vurgu rengini anında canlı önizle"""
        target = self._get_current_theme_target()
        self.theme_manager.set_theme(target, self.selected_accent)
        if self._accent_buttons:
            self._update_accent_buttons_ui()  # the selection ring follows the theme's text colour
        self._refresh_icons()

    def _refresh_icons(self):
        """Başlık/kart simgeleri ve yedekleme düğmesi simgeleri güncel vurgu/tema rengiyle yeniden çizilir."""
        for icon in getattr(self, "_header_icons", []):
            icon.refresh()
        color = self.theme_manager.get_palette()["text_secondary"]
        for button, kind in getattr(self, "_backup_buttons", []):
            button.setIcon(toolbar_icon(kind, color))

    def load_settings(self):
        settings = self.settings_manager.load_settings()
        
        lang = settings.get('language', AUTO_LANGUAGE)
        self.lang_combo.blockSignals(True)
        self.theme_combo.blockSignals(True)
        lang_idx = self.lang_combo.findData(lang)
        if lang_idx >= 0:
            self.lang_combo.setCurrentIndex(lang_idx)
        
        theme = settings.get('theme', DEFAULT_SETTINGS['theme'])
        self.theme_combo.setCurrentIndex(self._theme_index_for(theme))
        self.lang_combo.blockSignals(False)
        self.theme_combo.blockSignals(False)

        self.selected_accent = settings.get('accent', DEFAULT_ACCENT)
        self._update_accent_buttons_ui()

        # yedek değerler DEFAULT_SETTINGS ile aynı (ayar anahtarı eksikse arayüz gerçek varsayılanı göstersin)
        self.start_min_check.setChecked(settings.get('start_minimized', DEFAULT_SETTINGS['start_minimized']))
        self.start_at_login_check.setChecked(self._is_startup_enabled())
        self.show_notif_check.setChecked(settings.get('show_notifications', DEFAULT_SETTINGS['show_notifications']))
        self.auto_update_check.setChecked(settings.get('auto_update_check', DEFAULT_SETTINGS['auto_update_check']))
        self.auto_update_install.setChecked(settings.get('auto_update_install', DEFAULT_SETTINGS['auto_update_install']))
        self.auto_update_install.setEnabled(self.auto_update_check.isChecked())

    def _populate_lang_combo(self, selected: str | None = None):
        if not hasattr(self, 'lang_combo'):
            return
        if selected is None and self.lang_combo.count():
            selected = self.lang_combo.currentData()
        self.lang_combo.blockSignals(True)
        self.lang_combo.clear()
        self.lang_combo.setIconSize(QSize(22, 15))
        for code, label in language_choices(include_auto=True, lang=self.lang):
            self.lang_combo.addItem(create_language_icon(code), label, code)
        if selected is not None:
            idx = self.lang_combo.findData(selected)
            if idx >= 0:
                self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.blockSignals(False)

    def reject_and_restore(self):
        """İptal edildiğinde eski tema ve vurgu rengini geri yükle"""
        if self._initial_theme == 'system':
            is_dark = is_system_dark_mode()
            actual = 'dark' if is_dark else 'light'
        else:
            actual = 'dark' if 'dark' in self._initial_theme else 'light'
        self.theme_manager.set_theme(actual, self._initial_accent)
        self.reject()
    
    def check_for_updates(self):
        """Manuel güncelleme kontrolü"""
        if not self.update_checker:
            MessageBox.warning(self, t("error", self.lang), t("updater_not_found", self.lang))
            return
        if self._checking_updates or self.update_check.running:
            return
        self._checking_updates = True
        self.update_check.start(t("checking_updates", self.lang))
        self.update_checker.check_for_updates(show_message=True)
    
    def on_check_complete(self, has_update):
        self._checking_updates = False
        from src.utils.updater import UpdateChecker
        version = UpdateChecker().get_current_version()
        if has_update:
            pending = getattr(self.parent_window, "update_version", "")
            self.update_check.finish(
                "new",
                t("update_new_version", self.lang).format(version=pending) if pending else t("update_available", self.lang),
            )
        else:
            self.update_check.finish("ok", t("up_to_date", self.lang).format(version))
    
    def on_check_failed(self):
        self._checking_updates = False
        self.update_check.finish("fail", t("update_check_failed", self.lang))
    
    def save_and_close(self):
        lang_choice = self.lang_combo.currentData() or AUTO_LANGUAGE
        saved_theme = self.THEME_BY_INDEX[max(0, min(self.theme_combo.currentIndex(), 2))]
        self.settings_manager.update(
            language=lang_choice,
            theme=saved_theme,
            accent=self.selected_accent,
            start_minimized=self.start_min_check.isChecked(),
            show_notifications=self.show_notif_check.isChecked(),
            auto_update_check=self.auto_update_check.isChecked(),
            auto_update_install=self.auto_update_install.isChecked(),
        )

        # Temayı kalıcı olarak uygula
        target = self._get_current_theme_target()
        self.theme_manager.set_theme(target, self.selected_accent)
        
        # Açılışta Başlat (Windows: Run kaydı; macOS/Linux: LaunchAgent / autostart)
        self._set_startup(self.start_at_login_check.isChecked())
        
        # Bildirimleri güncelle
        self.notification_manager.set_enabled(self.show_notif_check.isChecked())
        self.notification_manager.success(t("settings_saved", self.lang))
        self.accept()
    
    def _on_export_clicked(self):
        """Ayarları dışa aktar"""
        if hasattr(self.parent_window, 'export_settings'):
            self.parent_window.export_settings()
    
    def _on_import_clicked(self):
        """Ayarları içe aktar"""
        if hasattr(self.parent_window, 'import_settings'):
            self.parent_window.import_settings()
            self.load_settings()
    
    def _is_startup_enabled(self):
        return startup.is_enabled()

    def _set_startup(self, enable):
        try:
            startup.set_enabled(bool(enable), self.start_min_check.isChecked())
        except Exception as e:
            MessageBox.warning(self, t("error", self.lang), t("startup_error", self.lang).format(str(e)))


class CompactStackedWidget(QWidget):
    """Sadece aktif sayfayı layout'a dahil eden dinamik ve kompakt yığın widget'ı"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pages = []
        self._current_index = -1
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    def addWidget(self, widget):
        self._pages.append(widget)
        widget.hide()
        return len(self._pages) - 1

    def widget(self, index):
        return self._pages[index] if 0 <= index < len(self._pages) else None

    def currentWidget(self):
        return self._pages[self._current_index] if 0 <= self._current_index < len(self._pages) else None

    def indexOf(self, widget):
        try:
            return self._pages.index(widget)
        except ValueError:
            return -1

    def count(self):
        return len(self._pages)

    def currentIndex(self):
        return self._current_index

    def setCurrentIndex(self, index):
        if index == self._current_index or index < 0 or index >= len(self._pages):
            return
        if 0 <= self._current_index < len(self._pages):
            old = self._pages[self._current_index]
            self._layout.removeWidget(old)
            old.hide()
        self._current_index = index
        cur = self._pages[index]
        self._layout.addWidget(cur)
        cur.show()
        self.updateGeometry()


class SecretRow(QWidget):
    """Gizli (parola) değer satırı: noktalı giriş + Göster/Gizle + kısa açıklama. Kopyalama Qt tarafından zaten kapalıdır."""

    def __init__(self, lang, parent=None):
        super().__init__(parent)
        self.lang = lang
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setPlaceholderText(t("secret_placeholder", lang))
        self.edit.setMinimumHeight(38)
        row.addWidget(self.edit, 1)
        self.toggle_btn = QPushButton(t("secret_show", lang))
        self.toggle_btn.setProperty('class', 'secondary')
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setMinimumHeight(38)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.toggled.connect(self._on_toggle)
        row.addWidget(self.toggle_btn)
        column.addLayout(row)
        column.addWidget(make_hint_label(t("secret_tip", lang)))

    def _on_toggle(self, shown):
        self.edit.setEchoMode(QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password)
        self.toggle_btn.setText(t("secret_hide" if shown else "secret_show", self.lang))

    def hide_value(self):
        self.toggle_btn.setChecked(False)

    def text(self) -> str:
        return self.edit.text()

    def setText(self, value: str):
        self.edit.setText(value)

    def clear(self):
        self.edit.clear()
        self.hide_value()


def _single_line(text: str) -> str:
    return text.replace("\r", "").replace("\n", "")


class HotkeyDialog(FramelessResizableDialog):
    """Kısayol diyalogu - Modern ve Rounded"""
    
    def __init__(self, parent=None, hotkey_data=None):
        super().__init__(parent)
        self.hotkey_data = hotkey_data
        self.is_edit = hotkey_data is not None
        self.lang = getattr(parent, "lang", None) or get_active_language()
        
        self.setWindowTitle(t("hotkey_edit_title", self.lang) if self.is_edit else t("hotkey_new_title", self.lang))
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(480, 260)
        self.setMaximumHeight(900)
        self.resize(600, 420)
        
        self._drag_pos = None
        self.setup_ui()
        self._init_frameless_resize()
        
        if self.is_edit:
            self.load_data()
        
        self.animate_entry()
    
    def showEvent(self, event):
        super().showEvent(event)
        apply_window_rounding(self)
    
    def animate_entry(self):
        fade_in_window(self, 0.1, 15)
    
    def _title_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def _title_mouse_move(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
    
    def _title_mouse_release(self, event):
        self._drag_pos = None
        event.accept()
    
    def setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(6, 6, 6, 6)
        outer_layout.setSpacing(0)
        
        self.chrome = QFrame()
        self.chrome.setObjectName("dialog_chrome")
        chrome_layout = QVBoxLayout(self.chrome)
        chrome_layout.setContentsMargins(0, 0, 0, 0)
        chrome_layout.setSpacing(0)
        
        # Title bar
        title_bar = QFrame()
        title_bar.setObjectName("title_bar")
        title_bar.setFixedHeight(38)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 8, 0)
        title_layout.setSpacing(10)

        title_layout.addWidget(IconLabel("keyboard", 16))
        
        title_label = QLabel(t("hotkey_edit_title", self.lang) if self.is_edit else t("hotkey_new_title", self.lang))
        title_label.setObjectName("title_label")
        title_layout.addWidget(title_label)
        
        title_layout.addStretch()
        
        close_btn = QPushButton("×")
        close_btn.setObjectName("window_close_btn")
        close_btn.setToolTip(t("close", self.lang))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        title_layout.addWidget(close_btn)
        
        title_bar.mousePressEvent = self._title_mouse_press
        title_bar.mouseMoveEvent = self._title_mouse_move
        title_bar.mouseReleaseEvent = self._title_mouse_release
        chrome_layout.addWidget(title_bar)
        
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 8)
        
        form = QFormLayout()
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        
        self.shortcut_input = EnhancedKeySequenceEdit(lang=self.lang)
        self.shortcut_input.setFixedHeight(36)
        self.shortcut_input.setToolTip(t("hint_shortcut_key", self.lang))
        form.addRow(t("hotkey_label", self.lang), self.shortcut_input)
        
        self.action_type = QComboBox()
        self.action_type.addItems([
            t("action_text", self.lang),
            t("action_command", self.lang),
            t("action_open_url", self.lang),
            t("action_open_file", self.lang),
            t("action_run_program", self.lang),
            t("action_shortcut", self.lang),
        ])
        self.action_type.setFixedHeight(36)
        self.action_type.setToolTip(t("hint_action_type", self.lang))
        self.action_type.currentIndexChanged.connect(self.on_action_type_changed)
        form.addRow(t("action_type_label", self.lang), self.action_type)
        
        layout.addLayout(form)

        self.enabled_check = QCheckBox(t("enable_hotkey", self.lang))
        self.enabled_check.setChecked(True)
        layout.addWidget(self.enabled_check)

        params_header = QHBoxLayout()
        params_header.setSpacing(12)
        value_label = QLabel(t("params_label", self.lang))
        value_label.setObjectName("section_header")
        params_header.addWidget(value_label)
        params_header.addStretch()
        self.secret_check = QCheckBox(t("secret_label", self.lang))
        self.secret_check.setToolTip(t("secret_tip", self.lang))
        self.secret_check.toggled.connect(self.on_secret_toggle)
        params_header.addWidget(self.secret_check)
        self.rich_text_check = QCheckBox(t("rich_text_html", self.lang))
        self.rich_text_check.toggled.connect(self.on_rich_text_toggle)
        self.rich_text_check.setVisible(False)
        params_header.addWidget(self.rich_text_check)
        layout.addLayout(params_header)
        
        # Stack
        self.value_stack = CompactStackedWidget()
        
        # 1. Metin
        text_widget = QWidget()
        text_layout = QVBoxLayout(text_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText(t("text_placeholder", self.lang))
        self.text_input.setMinimumHeight(120)
        self.text_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Border'ın görünmesi için frame shape ayarla
        self.text_input.setFrameShape(QFrame.Shape.Box)
        self.text_input.setFrameShadow(QFrame.Shadow.Plain)
        # Border için document margin ayarla
        self.text_input.document().setDocumentMargin(8)
        text_layout.addWidget(self.text_input, 1)
        apply_html_editor_style(self.text_input, False)
        self.secret_row = SecretRow(self.lang)
        self.secret_row.setVisible(False)
        text_layout.addWidget(self.secret_row)
        self.value_stack.addWidget(text_widget)
        
        # 2. Sistem Komutu (2 Sütunlu Komut Matrisi)
        cmd_widget = QWidget()
        cmd_layout = QVBoxLayout(cmd_widget)
        cmd_layout.setContentsMargins(0, 0, 0, 0)
        cmd_layout.setSpacing(8)

        tm = getattr(self.parent(), "theme_manager", None)
        p = tm.get_palette() if tm else {}
        accent = p.get("accent_text", "#00ACC1")
        accent_soft = p.get("accent_soft", "#1d464b")
        surface2 = p.get("surface2", "#262626")
        surface_active = p.get("surface_active", "#303030")
        border = p.get("border", "#2e2e2e")
        text_color = p.get("text", "#f5f5f5")

        # Üst Arama ve Seçilen Komut Durum Çubuğu
        matrix_top_row = QHBoxLayout()
        matrix_top_row.setSpacing(10)

        self.matrix_search = QLineEdit()
        self.matrix_search.setPlaceholderText(t("search_command", self.lang))
        self.matrix_search.setClearButtonEnabled(True)
        self.matrix_search.setFixedHeight(34)
        self.matrix_search.textChanged.connect(self._on_matrix_filter_changed)
        matrix_top_row.addWidget(self.matrix_search, 1)

        self._matrix_status_label = QLabel()
        self._matrix_status_label.setStyleSheet(f"""
            QLabel {{
                background-color: {accent_soft};
                color: {accent};
                border: 1px solid {accent};
                border-radius: 6px;
                padding: 4px 10px;
                font-weight: 600;
                font-size: 8.5pt;
            }}
        """)
        matrix_top_row.addWidget(self._matrix_status_label)
        cmd_layout.addLayout(matrix_top_row)

        # 2 Sütunlu Komut Matrisi için Kaydırılabilir Alan
        matrix_scroll = QScrollArea()
        matrix_scroll.setWidgetResizable(True)
        matrix_scroll.setFrameShape(QFrame.Shape.NoFrame)
        matrix_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        matrix_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        matrix_scroll.setMinimumHeight(190)
        matrix_scroll.sizeHint = lambda: QSize(320, 220)

        matrix_container = QWidget()
        matrix_container_layout = QVBoxLayout(matrix_container)
        matrix_container_layout.setContentsMargins(2, 2, 8, 4)
        matrix_container_layout.setSpacing(8)

        self.system_cmd_combo = QComboBox()
        self.system_cmd_combo.hide()

        self._matrix_button_group = QButtonGroup(self)
        self._matrix_button_group.setExclusive(True)
        self._matrix_categories = []
        self._matrix_buttons = {}
        self._selected_system_command = ""

        cmd_icons = {
            "bilgisayari_kapat": "🛑", "yeniden_basla": "🔄", "uyku_modu": "🌙", "hazirda_beklet": "💤",
            "kilitle": "🔒", "oturumu_kapat": "🚪", "ekrani_kapat": "📺", "cop_kutusunu_bosalt": "🗑️",
            "ekran_goruntusu": "📸", "ekran_alintisi": "✂️", "pano_gecmisi": "📋",
            "emoji_paneli": "😀", "buyutec": "🔍", "ekran_klavyesi": "⌨️",
            "gorev_yoneticisi": "📊", "calistir": "🚀", "komut_istemi": "💻", "powershell": "⚡",
            "dosya_gezgini": "📁", "not_defteri": "📝", "hesap_makinesi": "🧮", "paint": "🎨",
            "ayarlar": "⚙", "denetim_masasi": "🎛️", "aygit_yoneticisi": "📟", "ses_karistirici": "🎚️",
            "hizmetler": "🔧",
            "chrome": "🌐", "firefox": "🦊", "edge": "🌊",
            "ses_ac": "🔊", "ses_kis": "🔉", "sesi_kapat": "🔇", "ses_maksimum": "📢", "ses_minimum": "🔈",
            "oynat_duraklat": "⏯", "sonraki_sarki": "⏭", "onceki_sarki": "⏮", "durdur": "⏹",
            "masaustunu_goster": "🖥", "tum_pencereleri_kucult": "🗕", "gorev_gorunumu": "🗔",
            "yeni_sanal_masaustu": "➕", "sonraki_masaustu": "⏩", "onceki_masaustu": "⏪",
            "sanal_masaustu_kapat": "❌", "sola_yasla": "⬅", "saga_yasla": "➡",
            "pencereyi_buyut": "🗖", "pencereyi_kapat": "✖",
            "geri": "◀", "ileri": "▶", "sayfayi_yenile": "🔄", "yeni_sekme": "➕",
            "sekmeyi_kapat": "❌", "kapatilan_sekmeyi_ac": "📑",
            "bu_bilgisayar": "💻", "indirilenler": "📥", "belgelerim": "📄", "resimlerim": "🖼",
            "muziklerim": "🎵", "videolarim": "🎬", "masaustu": "🗂️", "geri_donusum_kutusu": "🗑️",
            "kopyala": "📋", "kes": "✂", "yapistir": "📋", "tumunu_sec": "🔘",
            "geri_al": "↩", "yeniden_yap": "↪", "bul": "🔍", "kaydet": "💾", "yazdir": "🖨",
        }

        # Komutlar
        commands = [
            (t("cmd_grp_power", self.lang), ""),
            (t("cmd_shutdown", self.lang), "bilgisayari_kapat"),
            (t("cmd_restart", self.lang), "yeniden_basla"),
            (t("cmd_sleep", self.lang), "uyku_modu"),
            (t("cmd_hibernate", self.lang), "hazirda_beklet"),
            (t("cmd_lock", self.lang), "kilitle"),
            (t("cmd_logout", self.lang), "oturumu_kapat"),
            (t("cmd_turn_off_screen", self.lang), "ekrani_kapat"),
            (t("cmd_empty_recycle_bin", self.lang), "cop_kutusunu_bosalt"),

            (t("cmd_grp_screen", self.lang), ""),
            (t("cmd_screenshot", self.lang), "ekran_goruntusu"),
            (t("cmd_snipping_tool", self.lang), "ekran_alintisi"),
            (t("cmd_clipboard_history", self.lang), "pano_gecmisi"),
            (t("cmd_emoji_panel", self.lang), "emoji_paneli"),
            (t("cmd_magnifier", self.lang), "buyutec"),
            (t("cmd_on_screen_keyboard", self.lang), "ekran_klavyesi"),

            (t("cmd_grp_apps", self.lang), ""),
            (t("cmd_task_mgr", self.lang), "gorev_yoneticisi"),
            (t("cmd_run_dialog", self.lang), "calistir"),
            (t("cmd_cmd", self.lang), "komut_istemi"),
            (t("cmd_powershell", self.lang), "powershell"),
            (t("cmd_explorer", self.lang), "dosya_gezgini"),
            (t("cmd_notepad", self.lang), "not_defteri"),
            (t("cmd_calc", self.lang), "hesap_makinesi"),
            (t("cmd_paint", self.lang), "paint"),
            (t("cmd_settings", self.lang), "ayarlar"),
            (t("cmd_control_panel", self.lang), "denetim_masasi"),
            (t("cmd_device_manager", self.lang), "aygit_yoneticisi"),
            (t("cmd_volume_mixer", self.lang), "ses_karistirici"),
            (t("cmd_services", self.lang), "hizmetler"),

            (t("cmd_grp_media", self.lang), ""),
            (t("cmd_play_pause", self.lang), "oynat_duraklat"),
            (t("cmd_next_track", self.lang), "sonraki_sarki"),
            (t("cmd_prev_track", self.lang), "onceki_sarki"),
            (t("cmd_stop", self.lang), "durdur"),

            (t("cmd_grp_volume", self.lang), ""),
            (t("cmd_volume_up", self.lang), "ses_ac"),
            (t("cmd_volume_down", self.lang), "ses_kis"),
            (t("cmd_volume_mute", self.lang), "sesi_kapat"),
            (t("cmd_volume_max", self.lang), "ses_maksimum"),
            (t("cmd_volume_min", self.lang), "ses_minimum"),

            (t("cmd_grp_windows", self.lang), ""),
            (t("cmd_show_desktop", self.lang), "masaustunu_goster"),
            (t("cmd_minimize_all", self.lang), "tum_pencereleri_kucult"),
            (t("cmd_task_view", self.lang), "gorev_gorunumu"),
            (t("cmd_new_vdesktop", self.lang), "yeni_sanal_masaustu"),
            (t("cmd_next_vdesktop", self.lang), "sonraki_masaustu"),
            (t("cmd_prev_vdesktop", self.lang), "onceki_masaustu"),
            (t("cmd_close_vdesktop", self.lang), "sanal_masaustu_kapat"),
            (t("cmd_snap_left", self.lang), "sola_yasla"),
            (t("cmd_snap_right", self.lang), "saga_yasla"),
            (t("cmd_maximize_window", self.lang), "pencereyi_buyut"),
            (t("cmd_close_window", self.lang), "pencereyi_kapat"),

            (t("cmd_grp_browsers", self.lang), ""),
            (t("cmd_chrome", self.lang), "chrome"),
            (t("cmd_firefox", self.lang), "firefox"),
            (t("cmd_edge", self.lang), "edge"),

            (t("cmd_grp_browser_nav", self.lang), ""),
            (t("cmd_back", self.lang), "geri"),
            (t("cmd_forward", self.lang), "ileri"),
            (t("cmd_refresh_page", self.lang), "sayfayi_yenile"),
            (t("cmd_new_tab", self.lang), "yeni_sekme"),
            (t("cmd_close_tab", self.lang), "sekmeyi_kapat"),
            (t("cmd_reopen_tab", self.lang), "kapatilan_sekmeyi_ac"),

            (t("cmd_grp_quick_access", self.lang), ""),
            (t("cmd_this_pc", self.lang), "bu_bilgisayar"),
            (t("cmd_downloads", self.lang), "indirilenler"),
            (t("cmd_documents", self.lang), "belgelerim"),
            (t("cmd_pictures", self.lang), "resimlerim"),
            (t("cmd_music", self.lang), "muziklerim"),
            (t("cmd_videos", self.lang), "videolarim"),
            (t("cmd_desktop_folder", self.lang), "masaustu"),
            (t("cmd_recycle_bin", self.lang), "geri_donusum_kutusu"),

            (t("cmd_grp_text", self.lang), ""),
            (t("cmd_copy", self.lang), "kopyala"),
            (t("cmd_cut", self.lang), "kes"),
            (t("cmd_paste", self.lang), "yapistir"),
            (t("cmd_select_all", self.lang), "tumunu_sec"),
            (t("cmd_undo", self.lang), "geri_al"),
            (t("cmd_redo", self.lang), "yeniden_yap"),
            (t("cmd_find", self.lang), "bul"),
            (t("cmd_save", self.lang), "kaydet"),
            (t("cmd_print", self.lang), "yazdir"),
        ]

        cur_header = None
        cur_grid_widget = None
        cur_grid = None
        cur_items = []
        item_in_cat_count = 0
        first_valid_val = None

        for display, value in commands:
            if not value:
                self.system_cmd_combo.addItem(display, "")
                idx = self.system_cmd_combo.count() - 1
                self.system_cmd_combo.model().item(idx).setEnabled(False)

                if cur_header is not None and cur_grid_widget is not None:
                    self._matrix_categories.append((cur_header, cur_grid_widget, cur_items))

                clean_title = display.strip("- ").strip()
                cur_header = QLabel(clean_title)
                cur_header.setStyleSheet(f"font-weight: 700; font-size: 8.5pt; color: {accent}; margin-top: 6px; margin-bottom: 2px;")
                matrix_container_layout.addWidget(cur_header)

                cur_grid_widget = QWidget()
                cur_grid = QGridLayout(cur_grid_widget)
                cur_grid.setContentsMargins(0, 0, 0, 0)
                cur_grid.setSpacing(6)
                cur_grid.setColumnStretch(0, 1)
                cur_grid.setColumnStretch(1, 1)
                cur_grid.setColumnStretch(2, 1)
                matrix_container_layout.addWidget(cur_grid_widget)

                cur_items = []
                item_in_cat_count = 0
            else:
                self.system_cmd_combo.addItem(display, value)
                if first_valid_val is None:
                    first_valid_val = value

                row = item_in_cat_count // 3
                col = item_in_cat_count % 3
                item_in_cat_count += 1

                ico = cmd_icons.get(value, "•")
                btn = QPushButton(f"{ico}  {display}")
                btn.setCheckable(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFixedHeight(34)
                btn.setToolTip(display)
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {surface2};
                        color: {text_color};
                        border: 1px solid {border};
                        border-radius: 7px;
                        padding: 4px 8px;
                        text-align: left;
                        font-size: 8.5pt;
                    }}
                    QPushButton:hover {{
                        background-color: {surface_active};
                        border-color: {accent};
                    }}
                    QPushButton:checked {{
                        background-color: {accent_soft};
                        color: {accent};
                        border: 1.5px solid {accent};
                        font-weight: 600;
                    }}
                """)
                self._matrix_button_group.addButton(btn)
                btn.clicked.connect(lambda _, v=value, d=display: self._on_matrix_btn_clicked(v, d))

                if cur_grid is not None:
                    cur_grid.addWidget(btn, row, col)
                cur_items.append((btn, display, value))
                self._matrix_buttons[value] = (btn, display)

        if cur_header is not None and cur_grid_widget is not None:
            self._matrix_categories.append((cur_header, cur_grid_widget, cur_items))

        matrix_container_layout.addStretch()
        matrix_scroll.setWidget(matrix_container)
        cmd_layout.addWidget(matrix_scroll, 1)
        cmd_layout.addWidget(self.system_cmd_combo)
        cmd_layout.addWidget(make_hint_label(t("hint_system_cmd", self.lang)))

        if first_valid_val:
            self.set_matrix_selected(first_valid_val)

        self.value_stack.addWidget(cmd_widget)
        
        # 3. URL
        url_widget = QWidget()
        url_layout = QVBoxLayout(url_widget)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(4)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(t("example_url", self.lang))
        self.url_input.setFixedHeight(36)
        # Stil temadan alınacak
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(make_hint_label(t("hint_url", self.lang)))
        url_layout.addStretch()
        self.value_stack.addWidget(url_widget)
        
        # 4. Dosya
        file_widget = QWidget()
        file_layout = QVBoxLayout(file_widget)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(4)
        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText(t("example_file", self.lang))
        self.file_input.setFixedHeight(36)
        # Stil temadan alınacak
        file_row.addWidget(self.file_input, 1)
        self.browse_btn = QPushButton(t("browse", self.lang))
        self.browse_btn.setFixedHeight(36)
        self.browse_btn.setProperty('class', 'primary')
        self.browse_btn.clicked.connect(self.browse_file)
        file_row.addWidget(self.browse_btn)
        file_layout.addLayout(file_row)
        file_layout.addWidget(make_hint_label(t("hint_file", self.lang)))
        file_layout.addStretch()
        self.value_stack.addWidget(file_widget)
        
        # 5. Program
        prog_widget = QWidget()
        prog_layout = QVBoxLayout(prog_widget)
        prog_layout.setContentsMargins(0, 0, 0, 0)
        prog_layout.setSpacing(4)
        self.program_input = QLineEdit()
        self.program_input.setPlaceholderText(t("example_program", self.lang))
        self.program_input.setFixedHeight(36)
        # Stil temadan alınacak
        prog_layout.addWidget(self.program_input)
        prog_layout.addWidget(make_hint_label(t("hint_program", self.lang)))
        prog_layout.addStretch()
        self.value_stack.addWidget(prog_widget)
        
        # 6. Kısayol - HAZIR WIDGET
        short_widget = QWidget()
        short_layout = QVBoxLayout(short_widget)
        short_layout.setContentsMargins(0, 0, 0, 0)
        short_layout.setSpacing(4)
        self.shortcut_value = EnhancedKeySequenceEdit(lang=self.lang)
        self.shortcut_value.setFixedHeight(36)
        # Stil temadan alınacak
        short_layout.addWidget(self.shortcut_value)
        short_layout.addWidget(make_hint_label(t("hint_key_sequence", self.lang)))
        short_layout.addStretch()
        self.value_stack.addWidget(short_widget)
        
        layout.addWidget(self.value_stack, 1)

        body_layout.addWidget(content, 1)

        footer = QWidget()
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(20, 8, 20, 16)
        footer_layout.setSpacing(0)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()
        
        cancel_btn = QPushButton(t("cancel", self.lang))
        cancel_btn.setProperty('class', 'secondary')
        cancel_btn.setMinimumSize(90, 36)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton(t("save", self.lang))
        save_btn.setProperty('class', 'primary')
        save_btn.setMinimumSize(110, 36)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)
        footer_layout.addLayout(btn_layout)
        body_layout.addWidget(footer)
        
        chrome_layout.addWidget(body, 1)
        outer_layout.addWidget(self.chrome)
        
        self.on_action_type_changed(0)
    
    def on_secret_toggle(self, checked):
        """Gizli (parola) kipi: değer noktalı tek satıra taşınır; kapatılınca düz metin kutusuna döner."""
        if checked:
            self.rich_text_check.setChecked(False)
            self.secret_row.setText(_single_line(self.text_input.toPlainText()))
            self.text_input.clear()
        else:
            self.text_input.setPlainText(self.secret_row.text())
            self.secret_row.clear()
        self.text_input.setVisible(not checked)
        self.secret_row.setVisible(checked)
        self.rich_text_check.setEnabled(not checked)

    def on_rich_text_toggle(self, checked):
        """Rich text aktif/pasif"""
        apply_html_editor_style(self.text_input, checked)
        if checked:
            self.text_input.setPlaceholderText(t("placeholder_rich_text", self.lang))
        else:
            self.text_input.setPlaceholderText(t("text_placeholder", self.lang))
    
    def on_action_type_changed(self, index):
        self.value_stack.setCurrentIndex(index)
        self.rich_text_check.setVisible(index == 0)
        self.secret_check.setVisible(index == 0)
        if hasattr(self, "browse_btn"):
            self.browse_btn.setEnabled(index == 3)
        self.updateGeometry()
        # Her zaman minimumSizeHint'i alt limit olarak kullan - Qt geometriyi reddetmesin
        min_h = self.minimumSizeHint().height()
        if index == 1:
            # Sistem Komutu: 3 sütunlu matris için geniş ve uzun ferah görünüm
            self.resize(780, max(min_h, 680))
        elif index == 0:
            # Metin: metin alanı için dengeli boyut
            self.resize(620, max(min_h, 450))
        else:
            # URL, Dosya, Program, Kısayol: kompakt tek satırlık görünüm
            self.resize(580, max(min_h, 380))

    def _on_matrix_filter_changed(self, text: str):
        q = text.strip().lower()
        for cat_hdr, cat_grid_w, items in self._matrix_categories:
            cat_any = False
            for btn, name, val in items:
                match = (not q) or (q in name.lower()) or (q in val.lower())
                btn.setVisible(match)
                if match:
                    cat_any = True
            cat_hdr.setVisible(cat_any)
            cat_grid_w.setVisible(cat_any)

    def _on_matrix_btn_clicked(self, value: str, display: str):
        self._selected_system_command = value
        self._matrix_status_label.setText(f"✓ {display}")
        for i in range(self.system_cmd_combo.count()):
            if self.system_cmd_combo.itemData(i) == value:
                self.system_cmd_combo.blockSignals(True)
                self.system_cmd_combo.setCurrentIndex(i)
                self.system_cmd_combo.blockSignals(False)
                break

    def set_matrix_selected(self, value: str):
        self._selected_system_command = value
        if value in self._matrix_buttons:
            btn, display = self._matrix_buttons[value]
            btn.setChecked(True)
            self._matrix_status_label.setText(f"✓ {display}")
    
    def browse_file(self):
        if self.action_type.currentIndex() != 3:
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, t("select_file", self.lang), os.path.expanduser("~"), t("all_files", self.lang)
        )
        if file_path:
            self.file_input.setText(file_path)
    
    def load_data(self):
        # Kısayol yükleme
        shortcut_str = self.hotkey_data.get('shortcut', '')
        self.shortcut_input.set_shortcut(shortcut_str)
        
        type_map = {
            'text': 0, 'command': 1, 'open_url': 2,
            'open_file': 3, 'run_program': 4, 'shortcut': 5
        }
        
        action_type = self.hotkey_data['action_type']
        idx = type_map.get(action_type, 0)
        self.action_type.setCurrentIndex(idx)
        
        value = self.hotkey_data['action_value']
        is_rich = self.hotkey_data.get('is_rich', False)
        
        if action_type == 'text':
            if self.hotkey_data.get('is_secret') is True and not is_rich:
                self.secret_check.setChecked(True)
                self.secret_row.setText(value)
            elif is_rich:
                self.text_input.setHtml(value)
                self.rich_text_check.setChecked(True)
            else:
                self.text_input.setPlainText(value)
        elif action_type == 'command':
            for i in range(self.system_cmd_combo.count()):
                if self.system_cmd_combo.itemData(i) == value:
                    self.system_cmd_combo.setCurrentIndex(i)
                    break
            self.set_matrix_selected(value)
        elif action_type == 'open_url':
            self.url_input.setText(value)
        elif action_type == 'open_file':
            self.file_input.setText(value)
        elif action_type == 'run_program':
            self.program_input.setText(value)
        elif action_type == 'shortcut':
            self.shortcut_value.set_shortcut(value)
        
        self.enabled_check.setChecked(self.hotkey_data.get('enabled', True))
    
    def accept(self):
        if not self.shortcut_input.get_shortcut():
            MessageBox.warning(self, t("error", self.lang), t("shortcut_required", self.lang))
            return
        super().accept()

    def get_data(self):
        type_map = ['text', 'command', 'open_url', 'open_file', 'run_program', 'shortcut']
        action_type = type_map[self.action_type.currentIndex()]
        
        idx = self.value_stack.currentIndex()
        is_rich = False
        
        is_secret = False
        if idx == 0 and self.secret_check.isChecked():
            is_secret = True
            value = self.secret_row.text()
        elif idx == 0:
            is_rich = self.rich_text_check.isChecked()
            if is_rich:
                value = self.text_input.toHtml().strip()
            else:
                value = self.text_input.toPlainText().strip()
        elif idx == 1:
            value = self._selected_system_command or self.system_cmd_combo.currentData() or ""
        elif idx == 2:
            value = self.url_input.text().strip()
        elif idx == 3:
            value = self.file_input.text().strip()
        elif idx == 4:
            value = self.program_input.text().strip()
        else:
            value = self.shortcut_value.get_shortcut()
        
        shortcut_str = self.shortcut_input.get_shortcut()
        
        data = {
            'shortcut': shortcut_str,
            'action_type': action_type,
            'action_value': value,
            'enabled': self.enabled_check.isChecked(),
            'is_rich': is_rich
        }
        if is_secret:
            data['is_secret'] = True
        return data


class ExpansionDialog(FramelessResizableDialog):
    """Metin genişletme - Modern ve Rounded"""
    
    def __init__(self, parent=None, expansion_data=None):
        super().__init__(parent)
        self.expansion_data = expansion_data
        self.is_edit = expansion_data is not None
        self.lang = getattr(parent, "lang", None) or get_active_language()
        
        self.setWindowTitle(t("expansion_edit_title", self.lang) if self.is_edit else t("expansion_new_title", self.lang))
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(640, 400)
        self.resize(840, 600)
        
        self._drag_pos = None
        self.setup_ui()
        self._init_frameless_resize()
        
        if self.is_edit:
            self.load_data()
        
        self.animate_entry()
    
    def showEvent(self, event):
        super().showEvent(event)
        apply_window_rounding(self)
    
    def animate_entry(self):
        fade_in_window(self, 0.1, 15)
    
    def _title_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def _title_mouse_move(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
    
    def _title_mouse_release(self, event):
        self._drag_pos = None
        event.accept()
    
    def setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(6, 6, 6, 6)
        outer_layout.setSpacing(0)
        
        self.chrome = QFrame()
        self.chrome.setObjectName("dialog_chrome")
        chrome_layout = QVBoxLayout(self.chrome)
        chrome_layout.setContentsMargins(0, 0, 0, 0)
        chrome_layout.setSpacing(0)
        
        # Title bar
        title_bar = QFrame()
        title_bar.setObjectName("title_bar")
        title_bar.setFixedHeight(38)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 8, 0)
        title_layout.setSpacing(10)

        title_layout.addWidget(IconLabel("textdoc", 16))
        
        title_label = QLabel(t("expansion_edit_title", self.lang) if self.is_edit else t("expansion_new_title", self.lang))
        title_label.setObjectName("title_label")
        title_layout.addWidget(title_label)
        
        title_layout.addStretch()
        
        close_btn = QPushButton("×")
        close_btn.setObjectName("window_close_btn")
        close_btn.setToolTip(t("close", self.lang))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        title_layout.addWidget(close_btn)
        
        title_bar.mousePressEvent = self._title_mouse_press
        title_bar.mouseMoveEvent = self._title_mouse_move
        title_bar.mouseReleaseEvent = self._title_mouse_release
        chrome_layout.addWidget(title_bar)
        
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 8)
        
        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        
        self.trigger_input = QLineEdit()
        self.trigger_input.setPlaceholderText(t("trigger_example", self.lang))
        self.trigger_input.setMinimumHeight(38)
        form.addRow(
            t("trigger_label", self.lang),
            wrap_field_with_hint(
                self.trigger_input,
                t("hint_trigger", self.lang),
            ),
        )
        
        layout.addLayout(form)

        self.enabled_check = QCheckBox(t("enable_expansion", self.lang))
        self.enabled_check.setChecked(True)
        layout.addWidget(self.enabled_check)
        
        rep_header_layout = QHBoxLayout()
        rep_header_layout.setSpacing(12)
        rep_label = QLabel(t("expanded_label", self.lang))
        rep_label.setObjectName("section_header")
        rep_header_layout.addWidget(rep_label)
        rep_header_layout.addStretch()

        self.secret_check = QCheckBox(t("secret_label", self.lang))
        self.secret_check.setToolTip(t("secret_tip", self.lang))
        self.secret_check.toggled.connect(self.on_secret_toggle)
        rep_header_layout.addWidget(self.secret_check)

        self.rich_text_exp_check = QCheckBox(t("rich_text_html", self.lang))
        self.rich_text_exp_check.toggled.connect(self.on_rich_exp_toggle)
        rep_header_layout.addWidget(self.rich_text_exp_check)

        paste_plain_btn = self.paste_plain_btn = QPushButton(t("paste_plain", self.lang))
        paste_plain_btn.setProperty('class', 'secondary')
        paste_plain_btn.setToolTip(t("tip_paste_plain", self.lang))
        paste_plain_btn.setMaximumHeight(30)
        paste_plain_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        paste_plain_btn.clicked.connect(self.paste_plain_text)
        rep_header_layout.addWidget(paste_plain_btn)
        
        layout.addLayout(rep_header_layout)
        
        self.replacement_text = QTextEdit()
        self.replacement_text.setPlaceholderText(t("expansion_placeholder", self.lang))
        self.replacement_text.setMinimumHeight(160)
        self.replacement_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.replacement_text.document().setDocumentMargin(8)
        
        paste_plain_action = QAction(f"{t('paste_plain', self.lang)} (Ctrl+Shift+V)", self.replacement_text)
        paste_plain_action.setShortcut(QKeySequence("Ctrl+Shift+V"))
        paste_plain_action.triggered.connect(self.paste_plain_text)
        self.replacement_text.addAction(paste_plain_action)
        
        self.replacement_text.setToolTip(t("tip_expansion_text", self.lang))
        layout.addWidget(self.replacement_text, 1)
        apply_html_editor_style(self.replacement_text, False)
        self.secret_row = SecretRow(self.lang)
        self.secret_row.setVisible(False)
        layout.addWidget(self.secret_row)

        body_layout.addWidget(content, 1)

        footer = QWidget()
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(20, 8, 20, 16)
        footer_layout.setSpacing(0)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()
        
        cancel_btn = QPushButton(t("cancel", self.lang))
        cancel_btn.setProperty('class', 'secondary')
        cancel_btn.setMinimumSize(90, 36)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton(t("save", self.lang))
        save_btn.setProperty('class', 'primary')
        save_btn.setMinimumSize(110, 36)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)
        footer_layout.addLayout(btn_layout)
        body_layout.addWidget(footer)
        
        chrome_layout.addWidget(body, 1)
        outer_layout.addWidget(self.chrome)
    
    def paste_plain_text(self):
        """Biçimsiz yapıştırma - HTML/biçim kodları olmadan"""
        clipboard = QApplication.clipboard()
        
        # Önce düz metin formatını kontrol et
        mime_data = clipboard.mimeData()
        
        # Düz metin varsa onu kullan
        if mime_data.hasText():
            text = mime_data.text()
        else:
            # HTML varsa düz metne çevir
            if mime_data.hasHtml():
                from PyQt6.QtGui import QTextDocument
                doc = QTextDocument()
                doc.setHtml(mime_data.html())
                text = doc.toPlainText()
            else:
                # Son çare olarak clipboard.text() kullan
                text = clipboard.text()
        
        if text:
            # Mevcut seçimi değiştir veya cursor pozisyonuna ekle
            cursor = self.replacement_text.textCursor()
            if cursor.hasSelection():
                cursor.removeSelectedText()
            # Düz metin olarak ekle (biçim olmadan)
            cursor.insertText(text)
            self.replacement_text.setTextCursor(cursor)
    
    def on_secret_toggle(self, checked):
        """Gizli (parola) kipi: değer noktalı tek satıra taşınır; kapatılınca düz metin kutusuna döner."""
        if checked:
            self.rich_text_exp_check.setChecked(False)
            self.secret_row.setText(_single_line(self.replacement_text.toPlainText()))
            self.replacement_text.clear()
        else:
            self.replacement_text.setPlainText(self.secret_row.text())
            self.secret_row.clear()
        self.replacement_text.setVisible(not checked)
        self.secret_row.setVisible(checked)
        self.rich_text_exp_check.setEnabled(not checked)
        self.paste_plain_btn.setEnabled(not checked)

    def on_rich_exp_toggle(self, checked):
        """Rich text toggle"""
        apply_html_editor_style(self.replacement_text, checked)
        if checked:
            self.replacement_text.setPlaceholderText(t("placeholder_rich_text", self.lang))
        else:
            self.replacement_text.setPlaceholderText(t("expansion_placeholder", self.lang))
    
    def load_data(self):
        self.trigger_input.setText(self.expansion_data['trigger'])
        
        is_rich = self.expansion_data.get('is_rich', False)
        if self.expansion_data.get('is_secret') is True and not is_rich:
            self.secret_check.setChecked(True)
            self.secret_row.setText(self.expansion_data['replacement'])
        elif is_rich:
            self.replacement_text.setHtml(self.expansion_data['replacement'])
            self.rich_text_exp_check.setChecked(True)
        else:
            self.replacement_text.setPlainText(self.expansion_data['replacement'])
        
        self.enabled_check.setChecked(self.expansion_data.get('enabled', True))
    
    def get_data(self):
        is_secret = self.secret_check.isChecked()
        is_rich = False if is_secret else self.rich_text_exp_check.isChecked()
        if is_secret:
            replacement = self.secret_row.text()
        elif is_rich:
            replacement = self.replacement_text.toHtml().strip()
        else:
            replacement = self.replacement_text.toPlainText().strip()
        
        data = {
            'trigger': self.trigger_input.text().strip(),
            'replacement': replacement,
            'enabled': self.enabled_check.isChecked(),
            'is_rich': is_rich
        }
        if is_secret:
            data['is_secret'] = True
        return data


class MainWindow(QMainWindow):
    """Ana pencere - Menü bar ile"""

    update_requested = pyqtSignal()
    
    def __init__(self, settings_manager, theme_manager, hotkey_manager, notification_manager, update_checker=None):
        super().__init__()
        
        self.settings_manager = settings_manager
        self.theme_manager = theme_manager
        self.hotkey_manager = hotkey_manager
        self.notification_manager = notification_manager
        self.update_checker = update_checker
        self.lang = get_active_language(self.settings_manager.load_settings())
        install_qt_translations(self.lang)
        if self.notification_manager:
            self.notification_manager.set_language(self.lang)
        if self.hotkey_manager:
            self.hotkey_manager.set_language(self.lang)
        
        self.hotkey_manager.action_executed.connect(self.on_action_executed)
        self.theme_manager.theme_changed.connect(self.on_theme_changed)
        
        self.setWindowTitle(f"{t('app_title', self.lang)} - {t('window_subtitle', self.lang)}")
        self.setMinimumSize(720, 460)  # toolbar + tabs need 667 px (Turkish) / 704 px (English); 600 let the content get cut off
        QTimer.singleShot(0, self._fit_min_width)  # asıl asgari genişlik başlık menüsünün gerçek ölçüsünden hesaplanır
        self.resize(840, 520)
        
        # Custom title bar için frameless window (kenarlardan boyutlandırılabilir)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
        # İkon ayarla
        icon = self.get_app_icon()
        if icon:
            self.setWindowIcon(icon)
        
        self.setup_ui()
        self.setMouseTracking(True)
        self.setup_menu_bar()
        self.load_data()
        self._enable_mouse_tracking(self)
        self.animate_entry()
        try:  # follow Windows light/dark while the app is open (only matters when the theme is "system")
            QApplication.styleHints().colorSchemeChanged.connect(self._on_system_scheme_changed)
        except (AttributeError, TypeError):
            pass
        
        # Sürükle-bırak / kenar boyutlandırma
        self.dragging = False
        self.drag_position = None
        self._resize_edge = None
        self._resize_start = None
        self._resize_geom = None
        self._override_shape = None
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
    
    def _on_system_scheme_changed(self, *_):
        settings = self.settings_manager.load_settings()
        if settings.get('theme', 'system') == 'system':
            actual = 'dark' if is_windows_dark_mode() else 'light'
            self.theme_manager.set_theme(actual, settings.get('accent', DEFAULT_ACCENT))

    def get_app_icon(self):
        """Uygulama ikonunu al - EXE uyumlu"""
        try:
            # PyInstaller için
            base_path = sys._MEIPASS
        except AttributeError:
            base_path = os.path.abspath(".")
        
        icon_path = os.path.join(base_path, 'assets', 'icons', 'keyboard.png')

        if os.path.exists(icon_path):
            return QIcon(icon_path)
        
        # Icon bulunamazsa sistem ikonu kullan
        from PyQt6.QtWidgets import QApplication, QStyle
        style = QApplication.style()
        if style:
            return style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        
        return None
    
    def setup_menu_bar(self):
        """Menü çubuğu oluştur - title bar'a entegre (Uygulama, Tema, Dil, Renk, Ayarlar)"""
        if not hasattr(self, 'menu_bar_widget'):
            return
        
        menubar_layout = self.menu_bar_widget.layout()
        menubar_layout.setSpacing(4)
        
        # 1. Uygulama menüsü (Yeni kısayol / Yeni genişletme / Çıkış): dosya işlemi yok, bu yüzden "Dosya" değil uygulamanın adı
        self.file_menu_btn = QPushButton(t("menu_app", self.lang))
        self.file_menu_btn.setIcon(create_keyboard_icon())
        self.file_menu_btn.setIconSize(QSize(16, 16))
        self.file_menu_btn.setObjectName("title_menu_btn")
        self.file_menu = QMenu()
        self.create_file_menu(self.file_menu)
        self.file_menu_btn.setMenu(self.file_menu)
        menubar_layout.addWidget(self.file_menu_btn)
        
        # 2. Tema Menüsü (Doğrudan Sistem, Koyu, Açık)
        self.theme_menu_btn = QPushButton(t("theme", self.lang))
        self.theme_menu_btn.setIcon(create_theme_system_icon())
        self.theme_menu_btn.setIconSize(QSize(16, 16))
        self.theme_menu_btn.setObjectName("title_menu_btn")
        self.theme_menu = QMenu()
        self.create_theme_menu(self.theme_menu)
        self.theme_menu_btn.setMenu(self.theme_menu)
        menubar_layout.addWidget(self.theme_menu_btn)

        # 3. Dil Menüsü (Doğrudan bayraklarla)
        self.lang_menu_btn = QPushButton(t("language", self.lang))
        self.lang_menu_btn.setIcon(create_globe_icon())
        self.lang_menu_btn.setIconSize(QSize(16, 16))
        self.lang_menu_btn.setObjectName("title_menu_btn")
        self.lang_menu = QMenu()
        self.create_language_menu(self.lang_menu)
        self.lang_menu_btn.setMenu(self.lang_menu)
        menubar_layout.addWidget(self.lang_menu_btn)

        # 4. Renk Menüsü (Doğrudan 10 vurgu rengiyle)
        self.color_menu_btn = QPushButton(t("accent_color", self.lang))
        current_accent = self.settings_manager.load_settings().get('accent', DEFAULT_ACCENT)
        spec = ACCENTS.get(current_accent, ACCENTS[DEFAULT_ACCENT])
        self.color_menu_btn.setIcon(create_accent_swatch_icon(spec["accent"]))
        self.color_menu_btn.setIconSize(QSize(16, 16))
        self.color_menu_btn.setObjectName("title_menu_btn")
        self.color_menu = QMenu()
        self.create_accent_menu(self.color_menu)
        self.color_menu_btn.setMenu(self.color_menu)
        menubar_layout.addWidget(self.color_menu_btn)

        # 5. Ayarlar Menüsü (En sağda)
        self.settings_menu_btn = QPushButton(t("settings", self.lang))
        self.settings_menu_btn.setIcon(create_settings_gear_icon())
        self.settings_menu_btn.setIconSize(QSize(16, 16))
        self.settings_menu_btn.setObjectName("title_menu_btn")
        self.settings_menu = QMenu()
        self.create_settings_help_menu(self.settings_menu)
        self.settings_menu_btn.setMenu(self.settings_menu)
        menubar_layout.addWidget(self.settings_menu_btn)
    
    def create_file_menu(self, menu):
        """Uygulama menüsü (ilk menü): yeni kısayol, yeni genişletme, çıkış"""
        self.new_hotkey_action = QAction(create_plus_icon(), t("new_hotkey", self.lang), self)
        self.new_hotkey_action.setShortcut("Ctrl+N")
        self.new_hotkey_action.triggered.connect(self.add_hotkey)
        menu.addAction(self.new_hotkey_action)
        self.addAction(self.new_hotkey_action)
        
        self.new_expansion_action = QAction(create_edit_pencil_icon(), t("new_expansion", self.lang), self)
        self.new_expansion_action.setShortcut("Ctrl+Shift+N")
        self.new_expansion_action.triggered.connect(self.add_expansion)
        menu.addAction(self.new_expansion_action)
        self.addAction(self.new_expansion_action)
        
        menu.addSeparator()
        
        self.exit_action = QAction(create_exit_icon(), t("exit", self.lang), self)
        # Alt+F4 pencereyi kapatır (tepsiye gizler); uygulamayı tamamen kapatmak yalnızca Ctrl+Q / Çıkış / tepsi menüsü.
        self.exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self.exit_action.triggered.connect(self.close_app)
        menu.addAction(self.exit_action)
        self.addAction(self.exit_action)

    def create_theme_menu(self, menu):
        """Tema menüsü - doğrudan seçenekler"""
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)
        
        self.theme_system_act = QAction(create_theme_system_icon(), t("theme_system", self.lang), self)
        self.theme_system_act.setCheckable(True)
        self.theme_system_act.triggered.connect(lambda: self.apply_theme('system'))
        self.theme_group.addAction(self.theme_system_act)
        menu.addAction(self.theme_system_act)
        
        self.theme_dark_act = QAction(create_theme_dark_icon(), t("theme_dark", self.lang), self)
        self.theme_dark_act.setCheckable(True)
        self.theme_dark_act.triggered.connect(lambda: self.apply_theme('dark'))
        self.theme_group.addAction(self.theme_dark_act)
        menu.addAction(self.theme_dark_act)
        
        self.theme_light_act = QAction(create_theme_light_icon(), t("theme_light", self.lang), self)
        self.theme_light_act.setCheckable(True)
        self.theme_light_act.triggered.connect(lambda: self.apply_theme('light'))
        self.theme_group.addAction(self.theme_light_act)
        menu.addAction(self.theme_light_act)
        self._sync_theme_menu()

    def create_language_menu(self, menu):
        """Dil menüsü"""
        self.lang_group = QActionGroup(self)
        self.lang_group.setExclusive(True)
        self._lang_actions = {}
        for code, label in language_choices(include_auto=True, lang=self.lang):
            act = QAction(create_language_icon(code), label, self)
            act.setCheckable(True)
            act.triggered.connect(lambda checked=False, c=code: self.apply_language(c))
            self.lang_group.addAction(act)
            menu.addAction(act)
            self._lang_actions[code] = act
        self._sync_language_menu()

    def create_accent_menu(self, menu):
        """Vurgu rengi menüsü"""
        self.accent_group = QActionGroup(self)
        self.accent_group.setExclusive(True)
        self._accent_actions = {}
        current_accent = self.settings_manager.load_settings().get('accent', DEFAULT_ACCENT)
        for key in ORDERED_ACCENT_KEYS:
            spec = ACCENTS[key]
            is_cur = (key == current_accent)
            swatch_icon = create_accent_swatch_icon(spec["accent"])
            label = spec.get("label_tr" if self.lang == "tr" else "label_en", spec.get("label", key))
            act = QAction(swatch_icon, label, self)
            act.setCheckable(True)
            act.setChecked(is_cur)
            act.triggered.connect(lambda checked, k=key: self.apply_accent(k) if checked else None)
            self.accent_group.addAction(act)
            menu.addAction(act)
            self._accent_actions[key] = act
    
    def create_settings_help_menu(self, menu):
        """Ayarlar ve Yardım menüsü"""
        self.settings_action = QAction(create_settings_gear_icon(), t("settings", self.lang), self)
        self.settings_action.setShortcut("Ctrl+,")
        self.settings_action.triggered.connect(self.show_settings)
        menu.addAction(self.settings_action)
        self.addAction(self.settings_action)
        
        menu.addSeparator()
        
        # Yardım bölümü
        self.help_action = QAction(create_book_help_icon(), t("user_guide", self.lang), self)
        self.help_action.setShortcut("F1")
        self.help_action.triggered.connect(self.show_help)
        menu.addAction(self.help_action)
        self.addAction(self.help_action)
        
        self.about_action = QAction(create_info_about_icon(), t("about", self.lang), self)
        self.about_action.triggered.connect(self.show_about)
        menu.addAction(self.about_action)
    
    def keyPressEvent(self, event: QKeyEvent):
        """Klavye olayları"""
        if event.key() == Qt.Key.Key_Space:
            focus_widget = self.focusWidget()
            if hasattr(self, 'hotkeys_list') and hasattr(self, 'expansions_list'):
                on_hotkeys = (
                    focus_widget is self.hotkeys_list
                    or self.hotkeys_list.isAncestorOf(focus_widget)
                )
                on_expansions = (
                    focus_widget is self.expansions_list
                    or self.expansions_list.isAncestorOf(focus_widget)
                )
                if on_hotkeys or on_expansions:
                    self.toggle_current_item()
                    event.accept()
                    return
        super().keyPressEvent(event)
    
    def animate_entry(self):
        fade_in_window(self, 0.05, 15, delay=100)
    
    def showEvent(self, event):
        super().showEvent(event)
        apply_window_rounding(self)
        if hasattr(self, 'app_chrome'):
            apply_rounded_mask(self.app_chrome, 12)
        QTimer.singleShot(0, self._settle_geometry)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'app_chrome'):
            apply_rounded_mask(self.app_chrome, 12)

    def event(self, event):
        # Ekran ölçeği değişti (ör. %150'de açılmış oturuma %100'lük RDP ile bağlanıldı): boyut sonra yeniden oturtulur
        if event.type() == QEvent.Type.DevicePixelRatioChange:
            QTimer.singleShot(0, self._settle_geometry)
            QTimer.singleShot(500, self._settle_geometry)
        return super().event(event)

    def _settle_geometry(self):
        """Pencere asgari ölçüsünün altında ya da ekran dışında kalmasın.

        Ölçek değişirken (RDP bağlantısı, başka ölçekli ekrana geçiş; pencere tepsideyken de olabilir) pencere eski
        boyutunda kalıp asgari genişliğin altına düşebiliyordu: başlık menüsü ve düğme metinleri kesik, kartlar tek
        sütun. Asgari genişlik yeniden hesaplanır, pencere gerekirse büyütülür ve görünür alana alınır.
        """
        if not self.isVisible() or self.isMaximized() or self.isFullScreen() or self.isMinimized():
            return
        self._fit_min_width()
        # yalnız büyütülür; ekrandan küçültmek içeriği yine sıkıştırırdı
        need = self.size().expandedTo(self.minimumSize()).expandedTo(self.minimumSizeHint())
        screen = self.screen()
        avail = screen.availableGeometry() if screen is not None else None
        if need != self.size():
            self.resize(need)
        if avail is not None:
            frame = self.frameGeometry()
            # sol üst köşe her zaman görünür kalır (pencere ekrandan büyükse sağı/altı taşar, başlık çubuğu taşmaz)
            x = max(avail.left(), min(frame.x(), avail.right() - frame.width() + 1))
            y = max(avail.top(), min(frame.y(), avail.bottom() - frame.height() + 1))
            if (x, y) != (frame.x(), frame.y()):
                self.move(x, y)

    def _hit_resize_edges(self, pos):
        """Köşelerde geniş çapraz alan; kenarlarda ince şerit."""
        if self.isMaximized():
            return 0
        r = self.rect()
        x, y = pos.x(), pos.y()
        w, h = r.width(), r.height()
        if w <= 0 or h <= 0:
            return 0
        corner = 24
        edge = 10
        if x <= corner and y <= corner:
            return 1 | 4
        if x >= w - corner and y <= corner:
            return 2 | 4
        if x <= corner and y >= h - corner:
            return 1 | 8
        if x >= w - corner and y >= h - corner:
            return 2 | 8
        flags = 0
        if x <= edge:
            flags |= 1
        if x >= w - edge:
            flags |= 2
        if y <= edge:
            flags |= 4
        if y >= h - edge:
            flags |= 8
        return flags

    def _cursor_for_edge(self, edge):
        if edge in (1 | 4, 2 | 8):
            return Qt.CursorShape.SizeFDiagCursor
        if edge in (2 | 4, 1 | 8):
            return Qt.CursorShape.SizeBDiagCursor
        if edge in (1, 2):
            return Qt.CursorShape.SizeHorCursor
        if edge in (4, 8):
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def _enable_mouse_tracking(self, widget):
        """Köşe imleci için tüm alt widget'larda hover mouse move üretilsin."""
        if widget is None or isinstance(widget, QMenu):
            return
        widget.setMouseTracking(True)
        widget.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        for child in widget.findChildren(QWidget):
            if isinstance(child, QMenu):
                continue
            child.setMouseTracking(True)
            child.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def _clear_resize_cursor(self):
        if getattr(self, "_override_shape", None) is not None:
            QApplication.restoreOverrideCursor()
            self._override_shape = None
        self.unsetCursor()

    def _apply_edge_cursor(self, local):
        edge = self._hit_resize_edges(local)
        shape = self._cursor_for_edge(edge)
        if not edge:
            self._clear_resize_cursor()
            return edge
        if self._override_shape != shape:
            if self._override_shape is None:
                QApplication.setOverrideCursor(QCursor(shape))
            else:
                QApplication.changeOverrideCursor(QCursor(shape))
            self._override_shape = shape
        self.setCursor(shape)
        return edge

    def _event_global_pos(self, event):
        if hasattr(event, "globalPosition"):
            return event.globalPosition().toPoint()
        if hasattr(event, "globalPos"):
            return event.globalPos()
        return QCursor.pos()

    def _apply_resize_delta(self, delta):
        geom = self._resize_geom
        if geom is None or not self._resize_edge:
            return
        x, y, w, h = geom.x(), geom.y(), geom.width(), geom.height()
        min_w, min_h = self.minimumWidth(), self.minimumHeight()
        if self._resize_edge & 1:
            x = min(geom.x() + delta.x(), geom.right() - min_w + 1)
            w = geom.right() - x + 1
        if self._resize_edge & 2:
            w = max(min_w, geom.width() + delta.x())
        if self._resize_edge & 4:
            y = min(geom.y() + delta.y(), geom.bottom() - min_h + 1)
            h = geom.bottom() - y + 1
        if self._resize_edge & 8:
            h = max(min_h, geom.height() + delta.y())
        self.setGeometry(x, y, w, h)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._hit_resize_edges(event.position().toPoint())
            if edge:
                self._resize_edge = edge
                self._resize_start = event.globalPosition().toPoint()
                self._resize_geom = self.geometry()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._resize_edge and self._resize_start is not None:
            self._apply_resize_delta(event.globalPosition().toPoint() - self._resize_start)
            event.accept()
            return
        self._apply_edge_cursor(pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resize_edge = None
        self._resize_start = None
        self._resize_geom = None
        self._apply_edge_cursor(self.mapFromGlobal(self._event_global_pos(event)))
        super().mouseReleaseEvent(event)

    def hideEvent(self, event):
        self._clear_resize_cursor()
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        et = event.type()
        if et not in (
            QEvent.Type.MouseMove,
            QEvent.Type.HoverMove,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.Leave,
        ):
            return super().eventFilter(watched, event)
        if not isinstance(watched, QWidget) or watched.window() is not self:
            return super().eventFilter(watched, event)
        if et == QEvent.Type.Leave:
            if watched is self and not self._resize_edge:
                self._clear_resize_cursor()
            return super().eventFilter(watched, event)
        gp = self._event_global_pos(event)
        local = self.mapFromGlobal(gp)
        if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            edge = self._hit_resize_edges(local)
            if edge:
                self._resize_edge = edge
                self._resize_start = gp
                self._resize_geom = self.geometry()
                self._apply_edge_cursor(local)
                return True
        elif et in (QEvent.Type.MouseMove, QEvent.Type.HoverMove):
            if self._resize_edge and self._resize_start is not None:
                self._apply_resize_delta(gp - self._resize_start)
                return True
            self._apply_edge_cursor(local)
        elif et == QEvent.Type.MouseButtonRelease:
            self._resize_edge = None
            self._resize_start = None
            self._resize_geom = None
            self._apply_edge_cursor(local)
        return super().eventFilter(watched, event)

    def setup_ui(self):
        # Ana widget ve saydam dış layout
        root_widget = QWidget()
        self.setCentralWidget(root_widget)
        
        root_layout = QVBoxLayout(root_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        
        # Rounded Chrome Container
        self.app_chrome = QFrame()
        self.app_chrome.setObjectName("app_chrome")
        self.app_chrome.setMouseTracking(True)
        self.app_chrome.installEventFilter(self)
        chrome_layout = QVBoxLayout(self.app_chrome)
        chrome_layout.setContentsMargins(0, 0, 0, 0)
        chrome_layout.setSpacing(0)
        
        # Custom title bar
        title_bar = self.create_custom_title_bar()
        chrome_layout.addWidget(title_bar)

        # Uzaktan duyuru satırı (sunucu bir duyuru verene kadar gizli)
        from src.gui.notice_bar import NoticeBar
        self.notice_bar = NoticeBar()
        self.notice_bar.dismissed.connect(self._on_notice_dismissed)
        notice_wrap = QHBoxLayout()
        notice_wrap.setContentsMargins(12, 8, 12, 0)
        notice_wrap.addWidget(self.notice_bar)
        chrome_layout.addLayout(notice_wrap)
        if self.update_checker:
            self.update_checker.notice_received.connect(self.show_notice)

        # İçerik widget'ı
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(12, 10, 12, 10)
        content_layout.setSpacing(8)
        
        self.tabs = QTabWidget()
        
        self.hotkeys_widget = self.create_hotkeys_tab()
        self.tabs.addTab(self.hotkeys_widget, t("tab_hotkeys", self.lang))
        
        self.expansions_widget = self.create_expansions_tab()
        self.tabs.addTab(self.expansions_widget, t("tab_expansions", self.lang))
        self.tabs.setIconSize(QSize(16, 16))
        self._apply_tab_icons()
                
        content_layout.addWidget(self.tabs)
        chrome_layout.addWidget(content_widget, 1)
        
        root_layout.addWidget(self.app_chrome)
        
        # Durum çubuğu ayrık görünmemesi için kaldırıldı
        if self.statusBar():
            self.statusBar().hide()
    
    def create_custom_title_bar(self):
        """Custom title bar - menü bar ve window controls ile"""
        title_bar = QFrame()
        title_bar.setObjectName("title_bar")
        title_bar.setFixedHeight(38)
        title_bar.setMouseTracking(True)
        title_bar.mousePressEvent = self.title_bar_mouse_press
        title_bar.mouseMoveEvent = self.title_bar_mouse_move
        title_bar.mouseReleaseEvent = self.title_bar_mouse_release
        title_bar.mouseDoubleClickEvent = self.title_bar_double_click
        
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(14, 0, 8, 0)
        layout.setSpacing(10)
        
        # Uygulama ikonu ve başlık
        icon_label = QLabel()
        icon = self.get_app_icon()
        if icon:
            icon_label.setPixmap(icon.pixmap(20, 20))
        layout.addWidget(icon_label)
        
        title_label = QLabel("FlexiKey")
        title_label.setObjectName("title_label")
        layout.addWidget(title_label)
        
        layout.addStretch(1)
        
        # Menü bar'ı title bar'a entegre et (Ortalanmış)
        self.menu_bar_widget = QWidget()
        menu_layout = QHBoxLayout(self.menu_bar_widget)
        menu_layout.setContentsMargins(0, 0, 0, 0)
        menu_layout.setSpacing(6)
        layout.addWidget(self.menu_bar_widget)
        
        layout.addStretch(1)
        
        # Güncelleme düğmesi: sessiz denetim yeni sürüm bulursa görünür (pop-up yok)
        self.update_version = ""
        self.update_pill = QPushButton()
        self.update_pill.setObjectName("update_pill")
        self.update_pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_pill.setIconSize(QSize(14, 14))
        self.update_pill.clicked.connect(self.show_pending_update)
        self.update_pill.setVisible(False)
        layout.addWidget(self.update_pill)

        # Window controls
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(2)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        
        # Minimize button
        self.minimize_btn = QPushButton("−")
        self.minimize_btn.setObjectName("window_control_btn")
        self.minimize_btn.setToolTip(t("minimize", self.lang))
        self.minimize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.minimize_btn.clicked.connect(self.showMinimized)
        controls_layout.addWidget(self.minimize_btn)
        
        # Maximize/Restore button
        self.maximize_btn = QPushButton("□")
        self.maximize_btn.setObjectName("window_control_btn")
        self.maximize_btn.setToolTip(t("maximize", self.lang))
        self.maximize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.maximize_btn.clicked.connect(self.toggle_maximize)
        controls_layout.addWidget(self.maximize_btn)
        
        # Close button
        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("window_close_btn")
        self.close_btn.setToolTip(t("close", self.lang))
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.close)
        controls_layout.addWidget(self.close_btn)
        
        layout.addLayout(controls_layout)
        
        return title_bar
    
    def title_bar_double_click(self, event):
        """Title bar'a çift tıklandığında ekranı kapla / geri yükle"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize()
    
    def title_bar_mouse_press(self, event):
        """Title bar'a tıklandığında"""
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._hit_resize_edges(self.mapFromGlobal(event.globalPosition().toPoint()))
            if edge:
                self._resize_edge = edge
                self._resize_start = event.globalPosition().toPoint()
                self._resize_geom = self.geometry()
                event.accept()
                return
            self.dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def title_bar_mouse_move(self, event):
        """Title bar'da sürüklenirken / köşeden boyutlandırırken"""
        if self._resize_edge and self._resize_start is not None:
            self._apply_resize_delta(event.globalPosition().toPoint() - self._resize_start)
            event.accept()
            return
        local = self.mapFromGlobal(event.globalPosition().toPoint())
        self._apply_edge_cursor(local)
        if self.dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
    
    def title_bar_mouse_release(self, event):
        """Title bar'dan bırakıldığında"""
        self.dragging = False
        self._resize_edge = None
        self._resize_start = None
        self._resize_geom = None
        event.accept()
    
    def toggle_maximize(self):
        """Pencereyi büyüt/küçült"""
        if self.isMaximized():
            self.showNormal()
            self.maximize_btn.setText("□")
        else:
            self.showMaximized()
            self.maximize_btn.setText("❐")
    
    def _build_toolbar(self, prefix, add_key, on_add, on_edit, on_delete, on_toggle, on_refresh):
        """Liste araç çubuğu: [Ekle]  [Düzenle | Aktif/Pasif | Sil]  ...boşluk...  [özet hapı]  [yenile simgesi].

        Düğmelere `<prefix>_add_btn/_edit_btn/_delete_btn/_toggle_btn/_refresh_btn/_summary/_actions_group`
        adlarıyla erişilir (eski kodla uyumlu). Simge ve metinler `_apply_toolbar_labels` ile verilir.
        """
        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)
        toolbar.setContentsMargins(4, 2, 4, 8)

        add_btn = QPushButton()
        add_btn.setProperty('class', 'primary')
        add_btn.setFixedHeight(36)
        add_btn.setIconSize(QSize(14, 14))
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(lambda *_: on_add())
        toolbar.addWidget(add_btn)

        group = QFrame()
        group.setObjectName("btn_group")
        group_layout = QHBoxLayout(group)
        group_layout.setContentsMargins(3, 3, 3, 3)
        group_layout.setSpacing(0)

        def seg(css_class, handler):
            btn = QPushButton()
            btn.setProperty('class', css_class)
            btn.setFixedHeight(30)
            btn.setIconSize(QSize(15, 15))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda *_: handler())
            return btn

        edit_btn = seg('seg', on_edit)
        toggle_btn = seg('seg', on_toggle)
        delete_btn = seg('seg-danger', on_delete)
        for index, btn in enumerate((edit_btn, toggle_btn, delete_btn)):
            if index:
                sep = QFrame()
                sep.setObjectName("btn_sep")
                sep.setFixedWidth(1)
                group_layout.addWidget(sep)
            group_layout.addWidget(btn)
        toolbar.addWidget(group)
        toolbar.addStretch()

        summary = QLabel("")
        summary.setObjectName("summary_chip")
        summary.setVisible(False)
        toolbar.addWidget(summary)

        refresh_btn = QPushButton()
        refresh_btn.setProperty('class', 'icon')
        refresh_btn.setFixedSize(36, 36)
        refresh_btn.setIconSize(QSize(16, 16))
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(lambda *_: on_refresh())
        toolbar.addWidget(refresh_btn)

        setattr(self, f"{prefix}_add_btn", add_btn)
        setattr(self, f"{prefix}_edit_btn", edit_btn)
        setattr(self, f"{prefix}_toggle_btn", toggle_btn)
        setattr(self, f"{prefix}_delete_btn", delete_btn)
        setattr(self, f"{prefix}_refresh_btn", refresh_btn)
        setattr(self, f"{prefix}_summary", summary)
        setattr(self, f"{prefix}_actions_group", group)
        self._toolbar_add_keys = getattr(self, "_toolbar_add_keys", {})
        self._toolbar_add_keys[prefix] = add_key
        self._apply_toolbar_labels(prefix)
        if not getattr(self, "_toolbar_theme_hooked", False):
            self._toolbar_theme_hooked = True
            self.theme_manager.theme_changed.connect(lambda *_: self._apply_toolbar_labels())
        return toolbar

    def _toolbar_color(self) -> str:
        try:
            return self.theme_manager.get_palette()["text_secondary"]
        except Exception:
            return "#cbd5e1"

    def _apply_toolbar_labels(self, prefix=None, lang=None):
        """Araç çubuğu düğmelerinin metni (emojisiz) ve temaya uyan çizilmiş simgeleri."""
        lang = lang or self.lang
        for name in ((prefix,) if prefix else ("hotkey", "exp")):
            if not hasattr(self, f"{name}_add_btn"):
                continue
            color = self._toolbar_color()
            add_btn = getattr(self, f"{name}_add_btn")
            add_btn.setText(strip_symbols(t(self._toolbar_add_keys[name], lang)))
            add_btn.setIcon(toolbar_icon("plus", "#ffffff"))
            for suffix, key, kind in (("edit", "btn_edit", "edit"), ("toggle", "btn_toggle", "power"),
                                      ("delete", "btn_delete", "trash")):
                btn = getattr(self, f"{name}_{suffix}_btn")
                btn.setText(strip_symbols(t(key, lang)))
                btn.setIcon(toolbar_icon(kind, color))
            refresh = getattr(self, f"{name}_refresh_btn")
            refresh.setText("")
            refresh.setToolTip(strip_symbols(t("btn_refresh", lang)))
            refresh.setIcon(toolbar_icon("refresh", color))

    def _set_toolbar_has_items(self, prefix: str, has_items: bool):
        """Düğmeler her zaman görünür (keşfedilebilir); öğe/seçim yoksa pasif olur (`_update_toolbar_state`)."""
        getattr(self, f"{prefix}_actions_group").setVisible(True)
        getattr(self, f"{prefix}_refresh_btn").setVisible(True)
        self._update_toolbar_state(prefix)

    def _update_toolbar_state(self, prefix: str):
        """Seçili öğe yoksa Düzenle / Aktif-Pasif / Sil pasiftir ve ipucu ne yapılacağını söyler ("Düzenlemek için bir öğe
        seçin."). Basılınca diyalog açılmaz: düğme zaten basılamaz."""
        listing = getattr(self, "hotkeys_list" if prefix == "hotkey" else "expansions_list", None)
        if listing is None:
            return
        has_selection = listing.selected_index() >= 0
        for suffix, tip in (("edit", "select_to_edit"), ("toggle", "select_to_toggle"), ("delete", "select_to_delete")):
            button = getattr(self, f"{prefix}_{suffix}_btn", None)
            if button is None:
                continue
            button.setEnabled(has_selection)
            button.setToolTip("" if has_selection else t(tip, self.lang))

    def create_hotkeys_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)
        layout.setContentsMargins(4, 4, 4, 4)
        
        toolbar = self._build_toolbar("hotkey", "btn_short_add", self.add_hotkey, self.edit_hotkey,
                                      self.delete_hotkey, self.toggle_hotkey, self.load_hotkeys)
        layout.addLayout(toolbar)
        
        self.hotkeys_list = CardListWidget()
        self.hotkeys_list.activated.connect(lambda row: self.edit_hotkey(row))
        self._selected_hotkey_row = -1
        self.hotkeys_list.selection_changed.connect(self._on_hotkey_selection_changed)
        layout.addWidget(self.hotkeys_list, 1)
        
        return widget
    
    def create_expansions_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)
        layout.setContentsMargins(4, 4, 4, 4)
        
        toolbar = self._build_toolbar("exp", "btn_exp_add", self.add_expansion, self.edit_expansion,
                                      self.delete_expansion, self.toggle_expansion, self.load_expansions)
        layout.addLayout(toolbar)
        
        self.expansions_list = CardListWidget()
        self.expansions_list.activated.connect(lambda row: self.edit_expansion(row))
        self._selected_expansion_row = -1
        self.expansions_list.selection_changed.connect(self._on_expansion_selection_changed)
        layout.addWidget(self.expansions_list, 1)
        
        return widget
    
    def show_settings(self):
        """Ayarlar dialog'unu göster"""
        dialog = SettingsDialog(self, self.settings_manager, self.theme_manager, self.notification_manager, self.update_checker)
        if dialog.exec():
            new_lang = get_active_language(self.settings_manager.load_settings())
            if new_lang != self.lang:
                self.lang = new_lang
                self._retranslate_ui()
    
    def _retranslate_ui(self):
        """Arayüz metinlerini seçili dile göre güncelle"""
        lang = self.lang
        install_qt_translations(lang)
        QTimer.singleShot(0, self._fit_min_width)  # dil değişince menü metinlerinin genişliği değişir
        self.tabs.setTabText(0, t("tab_hotkeys", lang))
        self.tabs.setTabText(1, t("tab_expansions", lang))
        
        if hasattr(self, 'file_menu_btn'):
            self.file_menu_btn.setText(t('menu_app', lang))
            self.file_menu_btn.setIcon(create_keyboard_icon())
        if hasattr(self, 'theme_menu_btn'):
            self.theme_menu_btn.setText(t("theme", lang))
        if hasattr(self, 'lang_menu_btn'):
            self.lang_menu_btn.setText(t("language", lang))
            self.lang_menu_btn.setIcon(create_globe_icon())
        if hasattr(self, 'settings_menu_btn'):
            self.settings_menu_btn.setText(t('menu_settings', lang))
            self.settings_menu_btn.setIcon(create_settings_gear_icon())
        if hasattr(self, 'new_hotkey_action'):
            self.new_hotkey_action.setText(t("new_hotkey", lang))
        if hasattr(self, 'new_expansion_action'):
            self.new_expansion_action.setText(t("new_expansion", lang))
        if hasattr(self, 'exit_action'):
            self.exit_action.setText(t("exit", lang))
        if hasattr(self, 'settings_action'):
            self.settings_action.setText(t("settings", lang))
            self.settings_action.setIcon(create_settings_gear_icon())
        if hasattr(self, 'lang_menu'):
            self.lang_menu.setTitle(t('language', lang))
        if hasattr(self, 'color_menu_btn'):
            self.color_menu_btn.setText(t("accent_color", lang))
            current_accent = self.settings_manager.load_settings().get('accent', DEFAULT_ACCENT)
            spec = ACCENTS.get(current_accent, ACCENTS[DEFAULT_ACCENT])
            self.color_menu_btn.setIcon(create_accent_swatch_icon(spec["accent"]))
        if hasattr(self, 'accent_menu'):
            self.accent_menu.setTitle(t("accent_color", lang))
        self._sync_theme_menu()
        self._sync_language_menu()
        if hasattr(self, 'help_action'):
            self.help_action.setText(t("user_guide", lang))
        if hasattr(self, 'about_action'):
            self.about_action.setText(t("about", lang))
        self.setWindowTitle(f"{t('app_title', lang)} - {t('window_subtitle', lang)}")
        self._apply_update_pill()
        if hasattr(self, 'minimize_btn'):
            self.minimize_btn.setToolTip(t("minimize", lang))
        if hasattr(self, 'maximize_btn'):
            self.maximize_btn.setToolTip(t("maximize", lang))
        if hasattr(self, 'close_btn'):
            self.close_btn.setToolTip(t("close", lang))
            
        if hasattr(self, 'hotkey_add_btn'):
            self._apply_toolbar_labels("hotkey", lang)
            
        if hasattr(self, 'exp_add_btn'):
            self._apply_toolbar_labels("exp", lang)

        for prefix in ("hotkey", "exp"):
            self._update_toolbar_state(prefix)

        if hasattr(self, 'tray_manager') and self.tray_manager:
            self.tray_manager.retranslate(lang)
            
        self.load_hotkeys()
        self.load_expansions()
    
    def load_data(self):
        settings = self.settings_manager.load_settings()
        
        # Bildirim ayarını yükle ve uygula
        show_notif = settings.get('show_notifications', False)
        self.notification_manager.set_enabled(show_notif)
        
        # Tema yükle (sistem teması desteği - Registry'den)
        theme = settings.get('theme', 'system')
        accent = settings.get('accent', DEFAULT_ACCENT)
        if theme == 'system':
            is_dark = is_windows_dark_mode()
            actual_theme = 'dark' if is_dark else 'light'
            self.theme_manager.set_theme(actual_theme, accent)
        else:
            actual_theme = 'dark' if 'dark' in theme else 'light'
            self.theme_manager.set_theme(actual_theme, accent)
        
        self.load_hotkeys()
        self.load_expansions()
    
    def get_action_type_turkish(self, action_type: str) -> str:
        """Action type'ı dile göre çevir"""
        lang = getattr(self, 'lang', 'tr')
        type_map = {
            'text': t('action_text', lang),
            'command': t('action_command', lang),
            'open_url': t('action_open_url', lang),
            'open_file': t('action_open_file', lang),
            'run_program': t('action_run_program', lang),
            'shortcut': t('action_shortcut', lang),
        }
        return type_map.get(action_type, action_type)
    
    def get_category_name_turkish(self, category: str) -> str:
        """Kategori ismini dile göre çevir"""
        lang = getattr(self, 'lang', 'tr')
        category_map = {
            'hotkeys': t('cat_hotkeys', lang),
            'expansions': t('cat_expansions', lang),
            'theme': t('cat_theme', lang),
            'behavior': t('cat_behavior', lang),
            'update': t('cat_update', lang),
        }
        return category_map.get(category, category)
    
    def _on_hotkey_selection_changed(self, row: int):
        self._selected_hotkey_row = row
        self._update_toolbar_state("hotkey")

    def _on_expansion_selection_changed(self, row: int):
        self._selected_expansion_row = row
        self._update_toolbar_state("exp")

    def _resolve_hotkey_row(self, row=None) -> int:
        if isinstance(row, int) and row >= 0:
            return row
        idx = self.hotkeys_list.selected_index()
        if idx >= 0:
            return idx
        return getattr(self, '_selected_hotkey_row', -1)

    def _resolve_expansion_row(self, row=None) -> int:
        if isinstance(row, int) and row >= 0:
            return row
        idx = self.expansions_list.selected_index()
        if idx >= 0:
            return idx
        return getattr(self, '_selected_expansion_row', -1)

    def _site_label(self, url: str) -> str:
        from urllib.parse import urlparse
        raw = (url or "").strip()
        if not raw:
            return ""
        candidate = raw if "://" in raw else f"https://{raw}"
        parsed = urlparse(candidate)
        host = (parsed.netloc or parsed.path or raw).strip("/")
        if host.startswith("www."):
            host = host[4:]
        return host.split("/")[0] or raw[:40]

    def _short_value(self, value: str, max_len: int = 28) -> str:
        text = (value or "").replace("\r", "").replace("\n", " ").strip()
        if len(text) > max_len:
            return text[: max_len - 1] + "…"
        return text

    def _format_command_display(self, cmd_value: str) -> str:
        cmd_meta = {
            # Sistem Gücü
            "bilgisayari_kapat": ("🛑", "cmd_shutdown"), "yeniden_basla": ("🔄", "cmd_restart"),
            "uyku_modu": ("🌙", "cmd_sleep"), "hazirda_beklet": ("💤", "cmd_hibernate"),
            "kilitle": ("🔒", "cmd_lock"), "oturumu_kapat": ("🚪", "cmd_logout"),
            "ekrani_kapat": ("📺", "cmd_turn_off_screen"), "cop_kutusunu_bosalt": ("🗑️", "cmd_empty_recycle_bin"),

            # Ekran & Araçlar
            "ekran_goruntusu": ("📸", "cmd_screenshot"),
            "ekran_alintisi": ("✂️", "cmd_snipping_tool"), "pano_gecmisi": ("📋", "cmd_clipboard_history"),
            "emoji_paneli": ("😀", "cmd_emoji_panel"), "buyutec": ("🔍", "cmd_magnifier"),
            "ekran_klavyesi": ("⌨️", "cmd_on_screen_keyboard"),

            # Uygulamalar & Sistem Araçları
            "gorev_yoneticisi": ("📊", "cmd_task_mgr"), "calistir": ("🚀", "cmd_run_dialog"),
            "komut_istemi": ("💻", "cmd_cmd"), "powershell": ("⚡", "cmd_powershell"),
            "dosya_gezgini": ("📁", "cmd_explorer"), "not_defteri": ("📝", "cmd_notepad"),
            "hesap_makinesi": ("🧮", "cmd_calc"), "paint": ("🎨", "cmd_paint"),
            "ayarlar": ("⚙", "cmd_settings"), "denetim_masasi": ("🎛️", "cmd_control_panel"),
            "aygit_yoneticisi": ("📟", "cmd_device_manager"), "ses_karistirici": ("🎚️", "cmd_volume_mixer"),
            "hizmetler": ("🔧", "cmd_services"),

            # Tarayıcılar
            "chrome": ("🌐", "cmd_chrome"), "firefox": ("🦊", "cmd_firefox"), "edge": ("🌊", "cmd_edge"),

            # Ses
            "ses_ac": ("🔊", "cmd_volume_up"), "ses_kis": ("🔉", "cmd_volume_down"),
            "sesi_kapat": ("🔇", "cmd_volume_mute"), "ses_maksimum": ("📢", "cmd_volume_max"),
            "ses_minimum": ("🔈", "cmd_volume_min"),

            # Medya
            "oynat_duraklat": ("⏯", "cmd_play_pause"), "sonraki_sarki": ("⏭", "cmd_next_track"),
            "onceki_sarki": ("⏮", "cmd_prev_track"), "durdur": ("⏹", "cmd_stop"),

            # Pencere & Masaüstü
            "masaustunu_goster": ("🖥", "cmd_show_desktop"), "tum_pencereleri_kucult": ("🗕", "cmd_minimize_all"),
            "gorev_gorunumu": ("🗔", "cmd_task_view"), "yeni_sanal_masaustu": ("➕", "cmd_new_vdesktop"),
            "sonraki_masaustu": ("⏩", "cmd_next_vdesktop"), "onceki_masaustu": ("⏪", "cmd_prev_vdesktop"),
            "sanal_masaustu_kapat": ("❌", "cmd_close_vdesktop"), "sola_yasla": ("⬅", "cmd_snap_left"),
            "saga_yasla": ("➡", "cmd_snap_right"), "pencereyi_buyut": ("🗖", "cmd_maximize_window"),
            "pencereyi_kapat": ("✖", "cmd_close_window"), "pencere_degistir": ("🔁", "cmd_switch_window"),

            # Tarayıcı Gezintisi
            "geri": ("◀", "cmd_back"), "ileri": ("▶", "cmd_forward"),
            "sayfayi_yenile": ("🔄", "cmd_refresh_page"), "yeni_sekme": ("➕", "cmd_new_tab"),
            "sekmeyi_kapat": ("❌", "cmd_close_tab"), "kapatilan_sekmeyi_ac": ("📑", "cmd_reopen_tab"),

            # Hızlı Erişim
            "bu_bilgisayar": ("💻", "cmd_this_pc"), "indirilenler": ("📥", "cmd_downloads"),
            "belgelerim": ("📄", "cmd_documents"), "resimlerim": ("🖼", "cmd_pictures"),
            "muziklerim": ("🎵", "cmd_music"), "videolarim": ("🎬", "cmd_videos"),
            "masaustu": ("🗂️", "cmd_desktop_folder"), "geri_donusum_kutusu": ("🗑️", "cmd_recycle_bin"),

            # Metin & Düzenleme
            "kopyala": ("📋", "cmd_copy"), "kes": ("✂", "cmd_cut"), "yapistir": ("📋", "cmd_paste"),
            "tumunu_sec": ("🔘", "cmd_select_all"), "geri_al": ("↩", "cmd_undo"),
            "yeniden_yap": ("↪", "cmd_redo"), "bul": ("🔍", "cmd_find"),
            "kaydet": ("💾", "cmd_save"), "yazdir": ("🖨", "cmd_print"),
        }
        if cmd_value in cmd_meta:
            icon, key = cmd_meta[cmd_value]
            return f"{icon} {t(key, self.lang)}"
        return f"⚙ {cmd_value}" if cmd_value else ""

    def load_hotkeys(self, keep_row: int | None = None):
        settings = self.settings_manager.load_settings()
        hotkeys = settings.get('hotkeys', [])

        # actions on an entry only make sense once there is one
        self._set_toolbar_has_items("hotkey", bool(hotkeys))

        active_count = sum(1 for h in hotkeys if h.get('enabled', True))
        self.hotkey_summary.setText(t("summary_hotkeys", self.lang).format(n=len(hotkeys), a=active_count))
        self.hotkey_summary.setVisible(bool(hotkeys))

        if not hotkeys:
            empty_msg = t("empty_hotkeys", self.lang)
            self.hotkeys_list.show_empty(empty_msg, t("btn_short_add", self.lang), self.add_hotkey, "keyboard")
            self._selected_hotkey_row = -1
            self._update_toolbar_state("hotkey")
            return

        cards = []
        for hotkey in hotkeys:
            card = HotkeyCard()
            type_label = self.get_action_type_turkish(hotkey['action_type'])
            is_rich = bool(hotkey.get('is_rich', False) and hotkey['action_type'] == 'text')
            is_secret = hotkey['action_type'] == 'text' and is_secret_record(hotkey)
            if is_secret:
                type_label = f"🔒 {t('chip_secret', self.lang)}"
            elif is_rich:
                type_label = f"📝 {t('chip_rich_expansion', self.lang)}"
            value = hotkey.get('action_value', '')
            if is_secret:
                primary = t("secret_mask", self.lang)
            elif hotkey['action_type'] == 'command':
                primary = self._format_command_display(value)
            elif hotkey['action_type'] == 'open_url':
                primary = self._site_label(value) or value
            else:
                primary = self._short_value(value, 48) or value
            card.set_data(
                hotkey['shortcut'],
                type_label,
                primary,
                hotkey.get('enabled', True),
                is_rich=is_rich,
                state_text=t("state_active" if hotkey.get('enabled', True) else "state_passive", self.lang),
            )
            cards.append(card)
        if keep_row is not None:
            select_row = keep_row
        else:
            select_row = self.hotkeys_list.selected_index()
            if select_row < 0:
                select_row = getattr(self, '_selected_hotkey_row', 0)
        if select_row < 0:
            select_row = 0
        self.hotkeys_list.set_cards(cards, select_row=select_row)
        self._selected_hotkey_row = select_row
        self._enable_mouse_tracking(self.hotkeys_list)
    
    def _expansion_plain_text(self, exp: dict) -> str:
        repl = exp['replacement']
        if exp.get('is_rich', False):
            from PyQt6.QtGui import QTextDocument
            doc = QTextDocument()
            doc.setHtml(repl)
            repl = doc.toPlainText()
        return repl

    def load_expansions(self, keep_row: int | None = None):
        settings = self.settings_manager.load_settings()
        expansions = settings.get('expansions', [])

        self._set_toolbar_has_items("exp", bool(expansions))

        active_count = sum(1 for e in expansions if e.get('enabled', True))
        self.exp_summary.setText(t("summary_expansions", self.lang).format(n=len(expansions), a=active_count))
        self.exp_summary.setVisible(bool(expansions))

        if not expansions:
            empty_msg = t("empty_expansions", self.lang)
            self.expansions_list.show_empty(empty_msg, t("btn_exp_add", self.lang), self.add_expansion, "text")
            self._selected_expansion_row = -1
            self._update_toolbar_state("exp")
            return

        base_chip = f"📝 {t('chip_expansion', self.lang)}"
        rich_chip = f"📝 {t('chip_rich_expansion', self.lang)}"
        secret_chip = f"🔒 {t('chip_secret', self.lang)}"
        cards = []
        for exp in expansions:
            card = ExpansionCard()
            is_rich = bool(exp.get('is_rich', False))
            is_secret = is_secret_record(exp)
            card.set_data(
                exp['trigger'],
                secret_chip if is_secret else (rich_chip if is_rich else base_chip),
                t("secret_mask", self.lang) if is_secret else self._short_value(self._expansion_plain_text(exp), 64),
                exp.get('enabled', True),
                is_rich=is_rich,
                state_text=t("state_active" if exp.get('enabled', True) else "state_passive", self.lang),
            )
            cards.append(card)
        if keep_row is not None:
            select_row = keep_row
        else:
            select_row = self.expansions_list.selected_index()
            if select_row < 0:
                select_row = getattr(self, '_selected_expansion_row', 0)
        if select_row < 0:
            select_row = 0
        self.expansions_list.set_cards(cards, select_row=select_row)
        self._selected_expansion_row = select_row
        self._enable_mouse_tracking(self.expansions_list)
    
    def add_hotkey(self):
        dialog = HotkeyDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            
            if not data['shortcut'] or not data['action_value']:
                MessageBox.warning(self, t("invalid_input", self.lang), t("fill_all_fields", self.lang))
                return
            
            self.settings_manager.add_hotkey(
                data['shortcut'], data['action_type'],
                data['action_value'], data['enabled'],
                data.get('is_rich', False), is_secret=data.get('is_secret', False)
            )
            
            if data['enabled']:
                self.hotkey_manager.add_hotkey(
                    data['shortcut'], data['action_type'], data['action_value'],
                    data.get('is_rich', False), secret=data.get('is_secret', False)
                )
            
            self.load_hotkeys()
            self.notification_manager.success(t("hotkey_added", self.lang).format(format_shortcut_for_display(data['shortcut'])))
    
    def edit_hotkey(self, row=None):
        row = self._resolve_hotkey_row(row)
        if row < 0:
            return   # seçim yok: düğmeler pasif, diyalog açılmaz
        
        settings = self.settings_manager.load_settings()
        hotkey = settings['hotkeys'][row]
        
        dialog = HotkeyDialog(self, hotkey)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_data()
            
            self.hotkey_manager.remove_hotkey(hotkey['shortcut'])
            self.settings_manager.update_hotkey(hotkey['shortcut'], new_data)
            
            if new_data['enabled']:
                self.hotkey_manager.add_hotkey(
                    new_data['shortcut'], new_data['action_type'], new_data['action_value'],
                    new_data.get('is_rich', False), secret=new_data.get('is_secret', False)
                )
            
            self.load_hotkeys()
            self.notification_manager.success(t("hotkey_updated", self.lang).format(format_shortcut_for_display(new_data['shortcut'])))
    
    def delete_hotkey(self):
        row = self._resolve_hotkey_row()
        if row < 0:
            return   # seçim yok: düğmeler pasif, diyalog açılmaz
        
        reply = MessageBox.question(
            self, t("confirm_delete", self.lang),
            t("confirm_delete_hotkey", self.lang),
            MessageBox.StandardButton.Yes | MessageBox.StandardButton.No
        )
        
        if reply == MessageBox.StandardButton.Yes:
            settings = self.settings_manager.load_settings()
            hotkey = settings['hotkeys'][row]
            
            self.hotkey_manager.remove_hotkey(hotkey['shortcut'])
            self.settings_manager.remove_hotkey(hotkey['shortcut'])
            
            self.load_hotkeys()
            self.notification_manager.success(t("hotkey_deleted", self.lang).format(format_shortcut_for_display(hotkey['shortcut'])))
    
    def toggle_hotkey(self):
        row = self._resolve_hotkey_row()
        if row < 0:
            return   # seçim yok: düğmeler pasif, diyalog açılmaz

        with self.settings_manager.transaction() as settings:
            hotkey = settings['hotkeys'][row]
            hotkey['enabled'] = not hotkey.get('enabled', True)
            settings['hotkeys'][row] = hotkey

        if hotkey['enabled']:
            if not is_locked_secret(hotkey):
                self.hotkey_manager.add_hotkey(
                    hotkey['shortcut'], hotkey['action_type'], hotkey['action_value'],
                    hotkey.get('is_rich', False), secret=is_secret_record(hotkey)
                )
            self.notification_manager.success(t("hotkey_enabled", self.lang).format(format_shortcut_for_display(hotkey['shortcut'])))
        else:
            self.hotkey_manager.remove_hotkey(hotkey['shortcut'])
            self.notification_manager.info(t("hotkey_disabled", self.lang).format(format_shortcut_for_display(hotkey['shortcut'])))

        self.load_hotkeys(keep_row=row)
    
    def add_expansion(self):
        dialog = ExpansionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            
            if not data['trigger'] or not data['replacement']:
                MessageBox.warning(self, t("invalid_input", self.lang), t("fill_all_fields", self.lang))
                return
            
            self.settings_manager.add_expansion(
                data['trigger'], data['replacement'], data['enabled'],
                data.get('is_rich', False), is_secret=data.get('is_secret', False)
            )
            
            if data['enabled']:
                self.hotkey_manager.add_expansion(
                    data['trigger'], data['replacement'],
                    data.get('is_rich', False)
                )
            
            self.load_expansions()
            self.notification_manager.success(t("expansion_added", self.lang).format(data['trigger']))
    
    def edit_expansion(self, row=None):
        row = self._resolve_expansion_row(row)
        if row < 0:
            return   # seçim yok: düğmeler pasif, diyalog açılmaz
        
        settings = self.settings_manager.load_settings()
        exp = settings['expansions'][row]
        
        dialog = ExpansionDialog(self, exp)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_data()
            
            self.hotkey_manager.remove_expansion(exp['trigger'])
            self.settings_manager.update_expansion(exp['trigger'], new_data)
            
            if new_data['enabled']:
                self.hotkey_manager.add_expansion(
                    new_data['trigger'], new_data['replacement'],
                    new_data.get('is_rich', False)
                )
            
            self.load_expansions()
            self.notification_manager.success(t("expansion_updated", self.lang).format(new_data['trigger']))
    
    def delete_expansion(self):
        row = self._resolve_expansion_row()
        if row < 0:
            return   # seçim yok: düğmeler pasif, diyalog açılmaz
        
        reply = MessageBox.question(
            self, t("confirm_delete", self.lang),
            t("confirm_delete_expansion", self.lang),
            MessageBox.StandardButton.Yes | MessageBox.StandardButton.No
        )
        
        if reply == MessageBox.StandardButton.Yes:
            settings = self.settings_manager.load_settings()
            exp = settings['expansions'][row]
            
            self.hotkey_manager.remove_expansion(exp['trigger'])
            self.settings_manager.remove_expansion(exp['trigger'])
            
            self.load_expansions()
            self.notification_manager.success(t("expansion_deleted", self.lang).format(exp['trigger']))
    
    def toggle_expansion(self):
        row = self._resolve_expansion_row()
        if row < 0:
            return   # seçim yok: düğmeler pasif, diyalog açılmaz

        with self.settings_manager.transaction() as settings:
            exp = settings['expansions'][row]
            exp['enabled'] = not exp.get('enabled', True)
            settings['expansions'][row] = exp

        if exp['enabled']:
            if not is_locked_secret(exp):
                self.hotkey_manager.add_expansion(
                    exp['trigger'], exp['replacement'],
                    exp.get('is_rich', False)
                )
            self.notification_manager.success(t("expansion_enabled", self.lang).format(exp['trigger']))
        else:
            self.hotkey_manager.remove_expansion(exp['trigger'])
            self.notification_manager.info(t("expansion_disabled", self.lang).format(exp['trigger']))

        self.load_expansions(keep_row=row)
    
    def toggle_current_item(self):
        """Mevcut tab'a göre toggle"""
        if self.tabs.currentIndex() == 0:
            self.toggle_hotkey()
        elif self.tabs.currentIndex() == 1:
            self.toggle_expansion()
    
    def apply_theme(self, theme_name):
        """Tema uygula ve kaydet"""
        with self.settings_manager.transaction() as settings:
            settings['theme'] = theme_name

        accent = settings.get('accent', DEFAULT_ACCENT)
        if theme_name == 'system':
            is_dark = is_windows_dark_mode()
            target = 'dark' if is_dark else 'light'
        else:
            target = 'dark' if 'dark' in theme_name else 'light'
        
        self.theme_manager.set_theme(target, accent)
        self._sync_theme_menu()
        if hasattr(self, 'tray_manager') and self.tray_manager:
            self.tray_manager.update_theme_menu()

    def apply_language(self, lang_choice: str):
        """Dil tercihini kaydet ve arayüzü yenile."""
        with self.settings_manager.transaction() as settings:
            settings['language'] = lang_choice
        self.lang = get_active_language(settings)
        if hasattr(self, 'notification_manager') and self.notification_manager:
            self.notification_manager.set_language(self.lang)
        if hasattr(self, 'hotkey_manager') and self.hotkey_manager:
            self.hotkey_manager.set_language(self.lang)
        self._sync_language_menu()
        self._retranslate_ui()

    def _sync_theme_menu(self):
        if not hasattr(self, 'theme_system_act'):
            return
        theme = self.settings_manager.load_settings().get('theme', 'system')
        is_system = theme == 'system'
        is_dark = ('dark' in theme) and not is_system
        is_light = ('light' in theme) and not is_system
        items = (
            (self.theme_system_act, is_system, t("theme_system", self.lang), create_theme_system_icon),
            (self.theme_dark_act, is_dark, t("theme_dark", self.lang), create_theme_dark_icon),
            (self.theme_light_act, is_light, t("theme_light", self.lang), create_theme_light_icon),
        )
        for act, selected, label, icon_fn in items:
            act.setChecked(selected)
            act.setText(label)
            act.setIcon(icon_fn())

    def _populate_lang_combo(self, selected: str | None = None):
        if not hasattr(self, 'lang_combo'):
            return
        if selected is None and self.lang_combo.count():
            selected = self.lang_combo.currentData()
        self.lang_combo.blockSignals(True)
        self.lang_combo.clear()
        for code, label in language_choices(include_auto=True, lang=self.lang):
            self.lang_combo.addItem(label, code)
        if selected is not None:
            idx = self.lang_combo.findData(selected)
            if idx >= 0:
                self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.blockSignals(False)

    def _sync_language_menu(self):
        if not hasattr(self, '_lang_actions'):
            return
        choice = self.settings_manager.load_settings().get('language', AUTO_LANGUAGE)
        labels = {code: label for code, label in language_choices(include_auto=True, lang=self.lang)}
        for code, act in self._lang_actions.items():
            act.setChecked(choice == code)
            act.setText(labels.get(code, code))
            act.setIcon(create_language_icon(code))
        if hasattr(self, 'lang_menu_btn'):
            self.lang_menu_btn.setText(t("language", self.lang))
            self.lang_menu_btn.setIcon(create_globe_icon())
        if hasattr(self, 'lang_menu'):
            self.lang_menu.setIcon(create_globe_icon())

    def apply_accent(self, accent_key):
        """Vurgu rengi uygula ve kaydet"""
        self.settings_manager.update(accent=accent_key)

        self.theme_manager.set_accent(accent_key)
        if hasattr(self, '_accent_actions'):
            for k, act in self._accent_actions.items():
                is_sel = (k == accent_key)
                act.setChecked(is_sel)
                spec = ACCENTS.get(k, ACCENTS[DEFAULT_ACCENT])
                act.setIcon(create_accent_swatch_icon(spec["accent"], is_selected=False))
                act.setText(spec.get("label_tr" if self.lang == "tr" else "label_en", spec["label"]))
        if hasattr(self, 'color_menu_btn'):
            spec = ACCENTS.get(accent_key, ACCENTS[DEFAULT_ACCENT])
            self.color_menu_btn.setIcon(create_accent_swatch_icon(spec["accent"]))
    
    def toggle_theme(self):
        new_theme = self.theme_manager.toggle_theme()
        self.settings_manager.set_theme(new_theme)
    
    def on_theme_changed(self, theme, accent=None):
        """Tema/vurgu değiştiğinde: vurguya bağlı menü, sekme ve araç çubuğu simgeleri yeniden boyanır."""
        self._refresh_accent_icons()

    def _apply_tab_icons(self):
        """Sekme simgeleri (emoji yerine vektör, vurgu renginde)."""
        if hasattr(self, 'tabs'):
            self.tabs.setTabIcon(0, toolbar_icon("keyboard", accent_hex(), 16))
            self.tabs.setTabIcon(1, toolbar_icon("textdoc", accent_hex(), 16))

    def _refresh_accent_icons(self):
        """Seçili vurgu rengine göre başlık menüsü / eylem / sekme simgelerini yeniler (sabit renk yok)."""
        for name, make in (('file_menu_btn', create_keyboard_icon), ('theme_menu_btn', create_theme_system_icon),
                           ('lang_menu_btn', create_globe_icon), ('settings_menu_btn', create_settings_gear_icon)):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setIcon(make())
        for name, make in (('new_hotkey_action', create_plus_icon), ('new_expansion_action', create_edit_pencil_icon),
                           ('settings_action', create_settings_gear_icon), ('help_action', create_book_help_icon),
                           ('about_action', create_info_about_icon)):
            action = getattr(self, name, None)
            if action is not None:
                action.setIcon(make())
        self._apply_tab_icons()
        if hasattr(self, 'theme_system_act'):
            self._sync_theme_menu()
        if hasattr(self, '_lang_actions'):
            self._sync_language_menu()
    
    def on_action_executed(self, action_type, description):
        self.last_activity = time.monotonic()  # otomatik güncelleme "kullanılmıyor" ölçütü
        if action_type == 'error':
            self.notification_manager.error(description)
        else:
            self.notification_manager.info(description)
    
    def reload_settings(self):
        # Sadece kısayolları temizle (genişletmeleri değil!)
        self.hotkey_manager.clear_all()
        
        self.load_data()
        
        settings = self.settings_manager.load_settings()
        
        # Genişletmeleri temizle; kısayollar ve genişletmeler kayıt başına hata yalıtımıyla yeniden yüklenir
        self.hotkey_manager.worker.clear_expansions()
        register_saved_items(settings, self.hotkey_manager)

        self.notification_manager.success(t("settings_reloaded", self.lang))
    
    def show_notice(self, notice):
        """Sunucudan gelen duyuruyu göster (kullanıcı bu duyuruyu daha önce kapattıysa gösterme)."""
        if self.settings_manager.load_settings().get('dismissed_notice', '') == notice.id:
            return
        self.notice_bar.show_notice(notice)

    def _on_notice_dismissed(self, notice_id: str):
        self.settings_manager.update(dismissed_notice=notice_id)

    def show_about(self):
        """Hakkında diyalogu"""
        # Versiyonu updater'dan al
        if self.update_checker:
            version = self.update_checker.get_current_version()
        else:
            from src.utils.updater import UpdateChecker
            version = UpdateChecker.CURRENT_VERSION
        
        MessageBox.about(
            self, t('about', self.lang),
            f"<h3>{t('about_heading', self.lang)}</h3>"
            f"<p>{t('about_version', self.lang).format(version)}</p>"
            f"<p><b>{t('about_subtitle', self.lang)}</b></p>"
            f"<p>{t('about_description', self.lang)}</p>"
            f"<p><span style='font-size: 8.5pt;'>{t('about_copyright', self.lang)}</span></p>"
            f"<p>{self._link_html()}</p>"
        )

    def _link_html(self) -> str:
        """macik.com.tr bağlantısı: rengi temanın vurgusundan (koyuda parlak, açıkta okunur derin ton)."""
        color = self.theme_manager.get_palette()["accent_text"]
        return f"<a href='https://macik.com.tr' style='color:{color}'>macik.com.tr</a>"

    def set_update_available(self, version: str = ""):
        """Başlık çubuğundaki "Güncelle · vX" düğmesini göster/gizle (version boşsa gizler)."""
        self.update_version = version or ""
        self._apply_update_pill()

    def _apply_update_pill(self):
        if not hasattr(self, "update_pill"):
            return
        version = self.update_version
        self.update_pill.setVisible(bool(version))
        if version:
            self.update_pill.setText(t("update_pill", self.lang).format(version=version))
            self.update_pill.setToolTip(t("update_pill_tip", self.lang).format(version=version))
            self.update_pill.setIcon(toolbar_icon("update", "#ffffff"))
        QTimer.singleShot(0, self._fit_min_width)  # düğme görününce/gizlenince başlık çubuğunun gereken genişliği değişir

    def _fit_min_width(self):
        """Pencere, başlık menüsü + güncelleme düğmesi sığacak genişliğin altına inemesin (İngilizce metinler daha uzun)."""
        chrome = getattr(self, 'app_chrome', None)
        layout = chrome.layout() if chrome is not None else None
        if layout is not None:
            self.setMinimumWidth(max(720, layout.minimumSize().width()))

    def show_pending_update(self):
        """Başlık çubuğu düğmesi / tepsi menüsü: güncelleme ayrıntı penceresini açtırır."""
        self.update_requested.emit()
    
    def show_help(self):
        """Kullanım Kılavuzu diyalogu"""
        help_html = (
            f"<h3>{t('help_heading', self.lang)}</h3>"
            f"<p><b>{t('help_section_hotkeys_title', self.lang)}</b><br>"
            f"{t('help_hotkeys_step1', self.lang)}<br>"
            f"{t('help_hotkeys_step2', self.lang)}<br>"
            f"{t('help_hotkeys_step3', self.lang)}<br>"
            f"{t('help_hotkeys_step4', self.lang)}</p>"
            f"<p><b>{t('help_section_expansion_title', self.lang)}</b><br>"
            f"{t('help_expansion_step1', self.lang)}<br>"
            f"{t('help_expansion_step2', self.lang)}<br>"
            f"{t('help_expansion_step3', self.lang)}<br>"
            f"{t('help_expansion_step4', self.lang)}<br>"
            f"{t('help_expansion_step5', self.lang)}</p>"
            f"<p><b>{t('help_section_shortcuts_title', self.lang)}</b><br>"
            f"{t('help_sc_add_hotkey', self.lang)}<br>"
            f"{t('help_sc_add_expansion', self.lang)}<br>"
            f"{t('help_sc_toggle_theme', self.lang)}<br>"
            f"{t('help_sc_settings', self.lang)}<br>"
            f"{t('help_sc_refresh', self.lang)}<br>"
            f"{t('help_sc_toggle', self.lang)}<br>"
            f"{t('help_sc_guide', self.lang)}<br>"
            f"{t('help_sc_exit', self.lang)}</p>"
            f"<p>{self._link_html()}</p>"
        )
        MessageBox.about(self, t("help_title", self.lang), help_html)
    
    def export_settings(self):
        """Ayarları dışa aktar"""
        try:
            # Seçim dialog'u göster
            dialog = ImportExportDialog(self, is_export=True)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            
            options = dialog.get_selected_options()
            
            # Hiçbir şey seçilmemişse uyar
            if not any(options.values()):
                MessageBox.warning(
                    self,
                    t("warning", self.lang),
                    t("select_category", self.lang)
                )
                return
            
            from datetime import datetime
            
            # Dosya seç dialog'u
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                t("ie_export_title", self.lang),
                t("export_filename", self.lang).format(datetime.now().strftime('%Y%m%d_%H%M%S')),
                t("json_files", self.lang)
            )
            
            if not file_path:
                return
            
            # Mevcut ayarları yükle
            settings = self.settings_manager.load_settings()
            
            # Gizli (parola) öğeler: değerleri dosyada açık yazılacağı için önce sorulur
            chosen = []
            if options['hotkeys']:
                chosen += settings.get('hotkeys', [])
            if options['expansions']:
                chosen += settings.get('expansions', [])
            include_secrets = False
            secrets = secret_count(chosen)
            if secrets:
                reply = MessageBox.question(
                    self, t("export_secret_title", self.lang),
                    t("export_secret_ask", self.lang).format(secrets),
                )
                include_secrets = reply == MessageBox.StandardButton.Yes

            # Seçilen ayarları filtrele
            filtered_settings = {}

            if options['hotkeys']:
                filtered_settings['hotkeys'] = exportable_records(settings.get('hotkeys', []), include_secrets)
            if options['expansions']:
                filtered_settings['expansions'] = exportable_records(settings.get('expansions', []), include_secrets)
            if options['theme']:
                filtered_settings['theme'] = settings.get('theme', 'system')
            if options['behavior']:
                filtered_settings['start_minimized'] = settings.get('start_minimized', False)
                filtered_settings['show_notifications'] = settings.get('show_notifications', False)
            if options['update']:
                filtered_settings['update_url'] = settings.get('update_url', '')
                filtered_settings['auto_update_check'] = settings.get('auto_update_check', True)
                filtered_settings['auto_update_install'] = settings.get('auto_update_install', True)
                filtered_settings['last_update_check'] = settings.get('last_update_check', None)
            
            # Dosyaya atomik kaydet (yarım dosya / var olan dışa aktarmanın bozulması olmaz)
            from src.utils.helpers import atomic_write_json
            atomic_write_json(file_path, filtered_settings)

            # Seçilen kategorileri Türkçe'ye çevir
            selected_categories = [k for k, v in options.items() if v]
            selected_items_turkish = [self.get_category_name_turkish(cat) for cat in selected_categories]
            
            self.notification_manager.success(t("export_success", self.lang))
            MessageBox.information(
                self,
                t("info", self.lang),
                t("export_done_detail", self.lang).format(', '.join(selected_items_turkish), file_path)
            )
        except Exception as e:
            MessageBox.critical(
                self,
                t("error", self.lang),
                f"{t('export_error', self.lang)}:\n{str(e)}"
            )
    
    def import_settings(self):
        """Ayarları içe aktar"""
        import json
        try:
            # Dosya seç dialog'u
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                t("ie_import_title", self.lang),
                "",
                t("json_files", self.lang)
            )
            
            if not file_path:
                return
            
            # Dosyayı oku (Not Defteri'nin BOM'una toleranslı)
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                imported_settings = json.load(f)
            
            # Seçim dialog'u göster
            dialog = ImportExportDialog(self, is_export=False)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            
            options = dialog.get_selected_options()
            
            # Hiçbir şey seçilmemişse uyar
            if not any(options.values()):
                MessageBox.warning(
                    self,
                    t("warning", self.lang),
                    t("select_category", self.lang)
                )
                return
            
            # Kayıtları doğrula (geçersiz/bilinmeyen eylem türleri elenir) ve eylem önizlemesi hazırla
            from src.utils.settings_manager import prepare_import
            from src.core.action_policy import build_import_preview
            plan = prepare_import(imported_settings, options)
            
            # Onay al - Türkçe kategori isimleriyle
            selected_categories = [k for k, v in options.items() if v]
            selected_items_turkish = [self.get_category_name_turkish(cat) for cat in selected_categories]
            
            info_lines = []
            detail_lines = []
            risky = 0
            if 'hotkeys' in plan['updates'] or 'expansions' in plan['updates']:
                info_lines.append(t("import_preview_summary", self.lang).format(
                    len(plan['hotkeys']), len(plan['expansions'])))
            skipped = len(plan['dropped_hotkeys']) + len(plan['dropped_expansions'])
            if skipped:
                info_lines.append(t("import_preview_skipped", self.lang).format(skipped))
                detail_lines.extend(
                    f"✖ #{index}: {reason}"
                    for index, reason in plan['dropped_hotkeys'] + plan['dropped_expansions'])
            if plan['rejected']:
                info_lines.append(t("import_preview_rejected", self.lang).format(', '.join(plan['rejected'])))
            if plan['hotkeys']:
                preview = build_import_preview(plan['hotkeys'], self.lang)
                risky = preview['risky']
                if risky:
                    info_lines.append(t("import_preview_risky", self.lang).format(risky))
                shown = preview['lines'][:12]
                info_lines.append(t("import_preview_list_header", self.lang))
                info_lines.extend(shown)
                if len(preview['lines']) > len(shown):
                    info_lines.append(t("import_preview_more", self.lang).format(len(preview['lines']) - len(shown)))
                detail_lines = preview['lines'] + detail_lines
            if 'update_url' in plan['updates'] and plan['updates']['update_url']:
                info_lines.append(t("import_preview_update_url", self.lang).format(plan['updates']['update_url']))
            
            box = MessageBox(self)
            box.setIcon(MessageBox.Icon.Warning if (risky or skipped) else MessageBox.Icon.Question)
            box.setWindowTitle(t("import_confirm_title", self.lang))
            box.setText(t("import_confirm_detail", self.lang).format(', '.join(selected_items_turkish)))
            if info_lines:
                box.setInformativeText("\n".join(info_lines))
            if detail_lines:
                box.setDetailedText("\n".join(detail_lines))
            box.setStandardButtons(MessageBox.StandardButton.Yes | MessageBox.StandardButton.No)
            box.setDefaultButton(MessageBox.StandardButton.No)
            
            if box.exec() != MessageBox.StandardButton.Yes:
                return
            
            # Yalnızca doğrulanmış değerleri, kilit altında yükle-değiştir-kaydet ile uygula
            with self.settings_manager.transaction() as current_settings:
                current_settings.update(plan['updates'])
            

            # Ayarları yeniden yükle
            self.reload_settings()
            
            # Türkçe kategori isimleriyle başarı mesajı
            selected_items_turkish_final = [self.get_category_name_turkish(cat) for cat in selected_categories]
            
            self.notification_manager.success(t("import_success", self.lang))
            MessageBox.information(
                self,
                t("info", self.lang),
                t("import_done_detail", self.lang).format(', '.join(selected_items_turkish_final))
            )
        except json.JSONDecodeError:
            MessageBox.critical(
                self,
                t("error", self.lang),
                t("invalid_json_detail", self.lang)
            )
        except Exception as e:
            MessageBox.critical(
                self,
                t("error", self.lang),
                f"{t('import_error', self.lang)}:\n{str(e)}"
            )
    
    def close_app(self):
        """Uygulamayı doğrudan kapat (onaysız)"""
        try:
            self.hotkey_manager.stop()
        except Exception:
            pass
        
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().quit()
    
    def closeEvent(self, event):
        from PyQt6.QtGui import QGuiApplication
        gui_app = QGuiApplication.instance()
        if gui_app is not None and gui_app.isSavingSession():  # Windows kapanıyor/oturum bitiyor: kapanmayı engelleme
            self._clear_resize_cursor()
            event.accept()
            return
        self._clear_resize_cursor()
        event.ignore()
        self.hide()
        self.notification_manager.info(t("running_in_tray", self.lang))
