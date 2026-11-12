"""
FlexiKey - Modern Fluent Design System & Theme Manager
Temiz, minimalist, sezgisel arayüz ve dinamik vurgu rengi (accent color) desteği.
"""

from __future__ import annotations

import os
import math
import tempfile
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal, Qt, QRectF, QPointF
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath, QPolygonF

# ─────────────────────────────────────────────
# Programatik İkon Üreticileri (Lumina stili)
# ─────────────────────────────────────────────
# Seçili vurgunun menü/simge rengi (koyuda `accent`, açıkta okunur olan derin ton). `ThemeManager.set_theme` günceller;
# simge üreticileri renk verilmezse bunu kullanır (sabit gök mavisi yok).
_ACTIVE_ACCENT = "#00ACC1"
_ACTIVE_ACCENT_BASE = "#00ACC1"   # vurgunun kendisi (düğme/odak çizgisi); `_ACTIVE_ACCENT` ise metin/simge tonu


def accent_hex() -> str:
    return _ACTIVE_ACCENT


def _mix(color: str, base: str, amount: float) -> str:
    """`color`'ın `amount` oranında `base` üzerine karışımı (opak #RRGGBB)."""
    c, b = _hex_rgb(color), _hex_rgb(base)
    return "#" + "".join(f"{round(cv * amount + bv * (1 - amount)):02x}" for cv, bv in zip(c, b))


def _hex_rgb(color: str) -> tuple[int, int, int]:
    h = color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


_CHECKMARK_PATH: str | None = None

def get_checkmark_icon_path() -> str:
    """QCheckBox için beyaz onay işareti (checkmark) görseli oluşturur ve yolunu döner."""
    global _CHECKMARK_PATH
    if _CHECKMARK_PATH and os.path.exists(_CHECKMARK_PATH):
        return _CHECKMARK_PATH
    
    tmp_path = os.path.join(tempfile.gettempdir(), 'flexikey_check_white.png')
    pix = QPixmap(16, 16)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#ffffff"), 2.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawLine(3, 8, 6, 11)
    p.drawLine(6, 11, 13, 4)
    p.end()
    pix.save(tmp_path)
    _CHECKMARK_PATH = tmp_path.replace('\\', '/')
    return _CHECKMARK_PATH


def _tick(p: QPainter, color: str, width: float) -> None:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawLine(5, 10, 8, 13)
    p.drawLine(8, 13, 14, 6)


_ICON_SCALE = 2  # menü simgeleri 2x çözünürlükte basılır (yüksek DPI'da keskin kalır)


def _icon_canvas(size: int = 20) -> tuple[QPixmap, QPainter]:
    pix = QPixmap(size * _ICON_SCALE, size * _ICON_SCALE)
    pix.fill(Qt.GlobalColor.transparent)
    pix.setDevicePixelRatio(_ICON_SCALE)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pix, p


# Tema simgeleri (Sistem / Koyu / Açık): vurguya değil nötr/anlamsal renge bağlıdır (güneş sarı, ay ve sistem gri).
# Aynı çizim ve renkler MediaCompressor, TransferTCP ve Lumina'da da vardır; renk/is_selected parametreleri eski
# çağrı imzaları bozulmasın diye durur ve yok sayılır.
def create_theme_system_icon(is_selected: bool = False, color_hex: str | None = None) -> QIcon:
    """Sistem teması ikonu: yarısı açık / yarısı koyu daire (nötr gri, ince kenarlıklı)"""
    pix, p = _icon_canvas()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor("#6f6f6f")))
    p.drawEllipse(QRectF(2.0, 2.0, 16.0, 16.0))
    p.setBrush(QBrush(QColor("#f2f2f2")))
    p.drawPie(QRectF(2.0, 2.0, 16.0, 16.0), 90 * 16, 180 * 16)
    p.setPen(QPen(QColor("#8c8c8c"), 1.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(2.5, 2.5, 15.0, 15.0))
    p.end()
    return QIcon(pix)


def create_theme_dark_icon(is_selected: bool = False, color_hex: str | None = None) -> QIcon:
    """Koyu tema hilal ikonu (orta gri; iki daire farkıyla gerçek hilal, zemin rengine bağlı değil)"""
    pix, p = _icon_canvas()
    moon = QPainterPath()
    moon.addEllipse(QRectF(3.0, 3.0, 14.0, 14.0))
    bite = QPainterPath()
    bite.addEllipse(QRectF(7.6, 1.2, 12.0, 12.0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor("#9a9a9a")))
    p.drawPath(moon.subtracted(bite))
    p.end()
    return QIcon(pix)


def create_theme_light_icon(is_selected: bool = False, color_hex: str | None = None) -> QIcon:
    """Açık tema güneş ikonu (sarı)"""
    pix, p = _icon_canvas()
    p.setPen(QPen(QColor("#f59e0b"), 1.6))
    p.setBrush(QBrush(QColor("#fbbf24")))
    p.drawEllipse(QRectF(5.0, 5.0, 10.0, 10.0))
    for ang in range(0, 360, 45):
        p.save()
        p.translate(10, 10)
        p.rotate(ang)
        p.drawLine(QPointF(0, -9), QPointF(0, -7))
        p.restore()
    p.end()
    return QIcon(pix)


def create_accent_swatch_icon(color_hex: str, size: int = 16, is_selected: bool = False) -> QIcon:
    """Belirtilen renkte yuvarlatılmış kare renk örneği (diğer uygulamalarla aynı şekil)"""
    pix, p = _icon_canvas(size)
    p.setPen(QPen(QColor(color_hex).darker(115), 1))
    p.setBrush(QBrush(QColor(color_hex)))
    p.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), 4, 4)
    p.end()
    return QIcon(pix)


_FLAG_ICONS_CACHE: dict[str, QIcon] = {}


def create_language_icon(code: str = "auto", is_selected: bool = False) -> QIcon:
    """Windows emoji bayrakları desteklemediği için gerçek vektörel bayrak ikonu döner."""
    if QApplication.instance() is None:
        return QIcon()

    raw_key = (code or "auto").lower()
    is_auto = raw_key in ("auto", "", "none")

    badge_color = accent_hex()
    if is_auto:
        from src.utils.locales import get_system_language
        detected = get_system_language() or "tr"
        code_key = (detected or "tr").lower()
        cache_key = f"auto_{code_key}_{badge_color}"
    else:
        code_key = raw_key
        cache_key = code_key

    if not is_selected and cache_key in _FLAG_ICONS_CACHE:
        return _FLAG_ICONS_CACHE[cache_key]

    w, h = 48, 32
    pix = QPixmap(w, h)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    clip = QPainterPath()
    clip.addRoundedRect(QRectF(1.0, 1.0, w - 2, h - 2), 5.0, 5.0)
    p.setClipPath(clip)

    if code_key == "tr":
        p.fillRect(QRectF(0, 0, w, h), QColor("#E30A17"))

        # Hilal
        c_outer = QPainterPath()
        c_outer.addEllipse(QPointF(w * 0.38, h * 0.5), h * 0.32, h * 0.32)
        c_inner = QPainterPath()
        c_inner.addEllipse(QPointF(w * 0.45, h * 0.5), h * 0.25, h * 0.25)
        p.fillPath(c_outer.subtracted(c_inner), QColor("#ffffff"))

        # Yıldız
        star_center = QPointF(w * 0.63, h * 0.5)
        star_r_out = h * 0.14
        star_r_in = star_r_out * 0.382
        pts = []
        angle_offset = -math.pi / 2
        for i in range(10):
            r = star_r_out if i % 2 == 0 else star_r_in
            a = angle_offset + i * math.pi / 5
            pts.append(QPointF(star_center.x() + r * math.cos(a), star_center.y() + r * math.sin(a)))
        star_path = QPainterPath()
        star_path.addPolygon(QPolygonF(pts))
        p.fillPath(star_path, QColor("#ffffff"))

    elif code_key in ("en", "us"):
        stripe_h = h / 7.0
        for i in range(7):
            col = QColor("#B22234") if i % 2 == 0 else QColor("#FFFFFF")
            p.fillRect(QRectF(0, i * stripe_h, w, stripe_h + 0.5), col)
        canton_w = w * 0.45
        canton_h = stripe_h * 4.0
        p.fillRect(QRectF(0, 0, canton_w, canton_h), QColor("#3C3B6E"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FFFFFF"))
        for r in range(2):
            for c in range(3):
                sx = canton_w * 0.2 + c * (canton_w * 0.3)
                sy = canton_h * 0.28 + r * (canton_h * 0.44)
                p.drawEllipse(QPointF(sx, sy), 1.4, 1.4)
    else:
        p.fillRect(QRectF(0, 0, w, h), QColor("#2a2a2a"))
        cx, cy = w / 2.0, h / 2.0
        r = min(w, h) * 0.4
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(accent_hex()))
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(QPen(QColor("#ffffff"), 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))
        p.drawLine(QPointF(cx, cy - r), QPointF(cx, cy + r))
        p.drawEllipse(QPointF(cx, cy), r * 0.5, r)

    # Otomatik mod rozeti (Sağ üst köşede şık mavi mini küre)
    if is_auto:
        p.setClipping(False)
        badge_cx, badge_cy, badge_r = w - 8.5, 8.5, 5.5
        p.setPen(QPen(QColor("#ffffff"), 1.2))
        p.setBrush(QColor(badge_color))
        p.drawEllipse(QPointF(badge_cx, badge_cy), badge_r, badge_r)
        p.setPen(QPen(QColor("#ffffff"), 0.9))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(badge_cx - badge_r + 1.0, badge_cy), QPointF(badge_cx + badge_r - 1.0, badge_cy))
        p.drawLine(QPointF(badge_cx, badge_cy - badge_r + 1.0), QPointF(badge_cx, badge_cy + badge_r - 1.0))
        p.drawEllipse(QPointF(badge_cx, badge_cy), badge_r * 0.5, badge_r * 0.9)

    # Açık ve koyu temalarda sınırları belirginleştiren zarif kontur
    p.setClipping(False)
    p.setPen(QPen(QColor(0, 0, 0, 70), 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(1.0, 1.0, w - 2, h - 2), 5.0, 5.0)

    p.end()
    icon = QIcon(pix)
    if not is_selected:
        _FLAG_ICONS_CACHE[cache_key] = icon
    return icon


HTML_EDITOR_STYLE = """
QTextEdit {
    background-color: #ffffff;
    color: #1a1a1a;
    border: 1px solid #c5c5c5;
    border-radius: 9px;
    padding: 8px 12px;
    font-size: 10pt;
    selection-background-color: __SEL__;
    selection-color: #1a1a1a;
}
QTextEdit:hover {
    border-color: #9e9e9e;
}
QTextEdit:focus {
    border: 2px solid __ACCENT__;
    padding: 7px 11px;
}
"""


def apply_html_editor_style(editor, enabled: bool) -> None:
    """Zengin metin (HTML) alanı her zaman açık zeminde kalsın."""
    from PyQt6.QtGui import QPalette, QColor
    if enabled:
        accent = _ACTIVE_ACCENT_BASE
        editor.setStyleSheet(HTML_EDITOR_STYLE.replace("__ACCENT__", accent).replace("__SEL__", _mix(accent, "#ffffff", 0.28)))
        pal = editor.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#1a1a1a"))
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#616161"))
        editor.setPalette(pal)
        editor.setAcceptRichText(True)
    else:
        editor.setStyleSheet("")
        editor.setPalette(QApplication.palette())
        editor.setAcceptRichText(False)


def create_settings_gear_icon(color_hex: str | None = None) -> QIcon:
    """Dişli / ayarlar ikonu (renk verilmezse vurgu)"""
    color_hex = color_hex or accent_hex()
    pix, pt = _icon_canvas()
    pt.setPen(Qt.PenStyle.NoPen)
    pt.setBrush(QBrush(QColor(color_hex)))
    pt.drawEllipse(QRectF(5.6, 5.6, 8.8, 8.8))
    for ang in range(0, 360, 45):
        pt.save()
        pt.translate(10, 10)
        pt.rotate(ang)
        pt.drawRoundedRect(QRectF(-1.5, -8.6, 3.0, 4.6), 0.8, 0.8)
        pt.restore()
    pt.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)  # gerçek (saydam) göbek deliği
    pt.drawEllipse(QRectF(7.6, 7.6, 4.8, 4.8))
    pt.end()
    icon = QIcon()
    icon.addPixmap(pix, QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(pix, QIcon.Mode.Active, QIcon.State.Off)
    icon.addPixmap(pix, QIcon.Mode.Selected, QIcon.State.Off)
    icon.addPixmap(pix, QIcon.Mode.Disabled, QIcon.State.Off)
    icon.setIsMask(False)
    return icon


def create_book_help_icon(color_hex: str | None = None) -> QIcon:
    """Açık kitap / yardım ikonu"""
    color_hex = color_hex or accent_hex()
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    pt = QPainter(pix)
    pt.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color_hex), 1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pt.setPen(pen)
    pt.setBrush(Qt.BrushStyle.NoBrush)
    pt.drawRoundedRect(QRectF(3, 4, 6.5, 12), 1, 1)
    pt.drawRoundedRect(QRectF(10.5, 4, 6.5, 12), 1, 1)
    pt.drawLine(QPointF(5, 7.5), QPointF(8, 7.5))
    pt.drawLine(QPointF(5, 10.5), QPointF(8, 10.5))
    pt.drawLine(QPointF(12, 7.5), QPointF(15, 7.5))
    pt.drawLine(QPointF(12, 10.5), QPointF(15, 10.5))
    pt.end()
    return QIcon(pix)


def create_info_about_icon(color_hex: str | None = None) -> QIcon:
    """Yuvarlak bilgi / hakkında ikonu"""
    color_hex = color_hex or accent_hex()
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    pt = QPainter(pix)
    pt.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color_hex), 1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pt.setPen(pen)
    pt.setBrush(Qt.BrushStyle.NoBrush)
    pt.drawEllipse(QRectF(2.5, 2.5, 15, 15))
    pt.drawLine(QPointF(10, 9.5), QPointF(10, 13.5))
    pt.setBrush(QBrush(QColor(color_hex)))
    pt.setPen(Qt.PenStyle.NoPen)
    pt.drawEllipse(QRectF(9.2, 6, 1.8, 1.8))
    pt.end()
    return QIcon(pix)


def create_globe_icon(color_hex: str | None = None, size: int = 20) -> QIcon:
    """Dil menüsü için küre ikonu (renk verilmezse vurgu)"""
    color_hex = color_hex or accent_hex()
    pix, p = _icon_canvas(size)
    pen = QPen(QColor(color_hex), 1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    r = (size - 4) / 2.0
    cx, cy = size / 2.0, size / 2.0
    p.drawEllipse(QPointF(cx, cy), r, r)
    p.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))
    p.drawLine(QPointF(cx, cy - r), QPointF(cx, cy + r))
    p.drawEllipse(QPointF(cx, cy), r * 0.55, r)
    p.end()
    return QIcon(pix)


def create_eye_icon(color_hex: str | None = None) -> QIcon:
    """Göster / Gizle için göz ikonu"""
    color_hex = color_hex or accent_hex()
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    pt = QPainter(pix)
    pt.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color_hex), 1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pt.setPen(pen)
    pt.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(2.5, 10.0)
    path.cubicTo(6.0, 4.5, 14.0, 4.5, 17.5, 10.0)
    path.cubicTo(14.0, 15.5, 6.0, 15.5, 2.5, 10.0)
    pt.drawPath(path)
    pt.setBrush(QBrush(QColor(color_hex)))
    pt.drawEllipse(QPointF(10.0, 10.0), 2.6, 2.6)
    pt.end()
    return QIcon(pix)


def create_door_exit_icon(color_hex: str = "#ef4444") -> QIcon:
    """Çıkış kapı/ok ikonu"""
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    pt = QPainter(pix)
    pt.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color_hex), 1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pt.setPen(pen)
    pt.setBrush(Qt.BrushStyle.NoBrush)
    # Kapı çerçevesi
    pt.drawPolyline([QPointF(9.0, 3.5), QPointF(3.5, 3.5), QPointF(3.5, 16.5), QPointF(9.0, 16.5)])
    # Çıkış oku
    pt.drawLine(QPointF(7.0, 10.0), QPointF(16.5, 10.0))
    pt.drawLine(QPointF(13.0, 6.5), QPointF(16.5, 10.0))
    pt.drawLine(QPointF(13.0, 13.5), QPointF(16.5, 10.0))
    pt.end()
    return QIcon(pix)


def create_bolt_icon(color_hex: str | None = None) -> QIcon:
    """Hızlı İşlemler için şimşek ikonu"""
    color_hex = color_hex or accent_hex()
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    pt = QPainter(pix)
    pt.setRenderHint(QPainter.RenderHint.Antialiasing)
    pt.setPen(Qt.PenStyle.NoPen)
    pt.setBrush(QBrush(QColor(color_hex)))
    pts = [
        QPointF(11.5, 2.5),
        QPointF(5.5, 10.5),
        QPointF(10.0, 10.5),
        QPointF(8.5, 17.5),
        QPointF(14.5, 9.5),
        QPointF(10.0, 9.5),
    ]
    pt.drawPolygon(QPolygonF(pts))
    pt.end()
    return QIcon(pix)


def create_keyboard_icon(color_hex: str | None = None) -> QIcon:
    """Klavye ikonu (uygulama menüsü): gövde ve tuş sıraları"""
    color_hex = color_hex or accent_hex()
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    pt = QPainter(pix)
    pt.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(color_hex)
    pen = QPen(color, 1.5)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pt.setPen(pen)
    pt.setBrush(Qt.BrushStyle.NoBrush)
    pt.drawRoundedRect(QRectF(1.8, 4.6, 16.4, 10.8), 2.2, 2.2)
    pt.setPen(Qt.PenStyle.NoPen)
    pt.setBrush(QBrush(color))
    for row, y in ((4, 7.0), (4, 9.6)):
        for i in range(row):
            pt.drawRoundedRect(QRectF(4.2 + i * 3.3, y, 2.0, 1.6), 0.5, 0.5)
    pt.drawRoundedRect(QRectF(6.0, 12.2, 8.0, 1.6), 0.6, 0.6)
    pt.end()
    icon = QIcon()
    icon.addPixmap(pix, QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(pix, QIcon.Mode.Active, QIcon.State.Off)
    icon.addPixmap(pix, QIcon.Mode.Selected, QIcon.State.Off)
    icon.addPixmap(pix, QIcon.Mode.Disabled, QIcon.State.Off)
    icon.setIsMask(False)
    return icon


def create_plus_icon(color_hex: str | None = None) -> QIcon:
    """Artı / Ekle ikonu"""
    color_hex = color_hex or accent_hex()
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    pt = QPainter(pix)
    pt.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color_hex), 2.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pt.setPen(pen)
    pt.drawLine(QPointF(10, 4.5), QPointF(10, 15.5))
    pt.drawLine(QPointF(4.5, 10), QPointF(15.5, 10))
    pt.end()
    return QIcon(pix)


def create_edit_pencil_icon(color_hex: str | None = None) -> QIcon:
    """Düzenle / Kalem ikonu"""
    color_hex = color_hex or accent_hex()
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    pt = QPainter(pix)
    pt.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color_hex), 1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pt.setPen(pen)
    pt.drawLine(QPointF(4.5, 15.5), QPointF(7.5, 15.5))
    pt.drawLine(QPointF(4.5, 15.5), QPointF(4.5, 12.5))
    pt.drawLine(QPointF(4.5, 12.5), QPointF(13.5, 3.5))
    pt.drawLine(QPointF(13.5, 3.5), QPointF(16.5, 6.5))
    pt.drawLine(QPointF(16.5, 6.5), QPointF(7.5, 15.5))
    pt.end()
    return QIcon(pix)


def create_exit_icon(color_hex: str = "#ef4444") -> QIcon:
    """Çıkış ikonu"""
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    pt = QPainter(pix)
    pt.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color_hex), 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pt.setPen(pen)
    pt.drawLine(QPointF(4, 3.5), QPointF(11, 3.5))
    pt.drawLine(QPointF(4, 3.5), QPointF(4, 16.5))
    pt.drawLine(QPointF(4, 16.5), QPointF(11, 16.5))
    pt.drawLine(QPointF(9, 10), QPointF(17, 10))
    pt.drawLine(QPointF(14, 7), QPointF(17, 10))
    pt.drawLine(QPointF(14, 13), QPointF(17, 10))
    pt.end()
    return QIcon(pix)


def get_chevron_down_icon_path(color_hex: str = "#757575") -> str:
    """QComboBox için aşağı ok / chevron görseli üretir ve dosya yolunu döner."""
    clean = color_hex.lstrip('#')
    path = os.path.join(tempfile.gettempdir(), f"fk_chev_{clean}.png")
    pix = QPixmap(16, 16)
    pix.fill(Qt.GlobalColor.transparent)
    pt = QPainter(pix)
    pt.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color_hex), 2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pt.setPen(pen)
    pt.drawLine(QPointF(3.5, 6), QPointF(8, 10.5))
    pt.drawLine(QPointF(8, 10.5), QPointF(12.5, 6))
    pt.end()
    pix.save(path)
    return path.replace('\\', '/')

# ─────────────────────────────────────────────
# Vurgu Renkleri Paleti
# ─────────────────────────────────────────────
# Vurgu renkleri: MediaCompressor (`ACCENTS`) ve TransferTCP ile AYNI Material hex ailesi; aynı "Turkuaz" her uygulamada aynı renk.
# accent/accent2: dolgu ve koyu ton, hi_dark/hi_light: koyu/açık temada üst-sol vurgu çizgisi.
ACCENTS: dict[str, dict[str, str]] = {
    "cyan": {
        "label": "Turkuaz",
        "label_tr": "Turkuaz",
        "label_en": "Cyan",
        "accent": "#00ACC1",
        "accent2": "#00838F",
        "hi_dark": "#4DD0E1",
        "hi_light": "#80DEEA",
    },
    "blue": {
        "label": "Mavi",
        "label_tr": "Mavi",
        "label_en": "Blue",
        "accent": "#2196F3",
        "accent2": "#1976D2",
        "hi_dark": "#42A5F5",
        "hi_light": "#90CAF9",
    },
    "teal": {
        "label": "Zümrüt",
        "label_tr": "Zümrüt",
        "label_en": "Teal",
        "accent": "#00897B",
        "accent2": "#00695C",
        "hi_dark": "#4DB6AC",
        "hi_light": "#80CBC4",
    },
    "indigo": {
        "label": "İndigo",
        "label_tr": "İndigo",
        "label_en": "Indigo",
        "accent": "#3F51B5",
        "accent2": "#303F9F",
        "hi_dark": "#7986CB",
        "hi_light": "#9FA8DA",
    },
    "violet": {
        "label": "Mor",
        "label_tr": "Mor",
        "label_en": "Violet",
        "accent": "#7C4DFF",
        "accent2": "#651FFF",
        "hi_dark": "#B388FF",
        "hi_light": "#D1C4E9",
    },
    "rose": {
        "label": "Gül",
        "label_tr": "Gül",
        "label_en": "Rose",
        "accent": "#E91E63",
        "accent2": "#C2185B",
        "hi_dark": "#F06292",
        "hi_light": "#F8BBD0",
    },
    "orange": {
        "label": "Kehribar",
        "label_tr": "Kehribar",
        "label_en": "Amber",
        "accent": "#FB8C00",
        "accent2": "#EF6C00",
        "hi_dark": "#FFB74D",
        "hi_light": "#FFE0B2",
    },
    "red": {
        "label": "Kırmızı",
        "label_tr": "Kırmızı",
        "label_en": "Red",
        "accent": "#E53935",
        "accent2": "#C62828",
        "hi_dark": "#EF5350",
        "hi_light": "#FFCDD2",
    },
    "green": {
        "label": "Yeşil",
        "label_tr": "Yeşil",
        "label_en": "Green",
        "accent": "#43A047",
        "accent2": "#2E7D32",
        "hi_dark": "#66BB6A",
        "hi_light": "#C8E6C9",
    },
    "yellow": {
        "label": "Sarı",
        "label_tr": "Sarı",
        "label_en": "Yellow",
        "accent": "#F9A825",
        "accent2": "#F57F17",
        "hi_dark": "#FDD835",
        "hi_light": "#FFF59D",
    },
}

# Geriye dönük uyumluluk takma adları (eski config kayıtları için)
ACCENTS["purple"] = ACCENTS["violet"]
ACCENTS["emerald"] = ACCENTS["teal"]
ACCENTS["amber"] = ACCENTS["orange"]
ACCENTS["crimson"] = ACCENTS["red"]

# Standart menü ve buton sıralaması
ORDERED_ACCENT_KEYS = ["cyan", "blue", "teal", "indigo", "violet", "rose", "orange", "red", "green", "yellow"]

DEFAULT_ACCENT = "cyan"

# ─────────────────────────────────────────────
# Açık ve Koyu Taban Paletleri
# ─────────────────────────────────────────────
LIGHT_BASE = {
    # Nötr gri (MediaCompressor `LIGHT` ailesi): base #e0e0e0, raised #f5f5f5, sunken #d8d8d8, surface #ececec,
    # border #c5c5c5, text #1a1a1a, muted #616161. Eski soğuk mavi-gri/slate tonları kaldırıldı.
    "base":             "#e0e0e0",
    "raised":           "#f5f5f5",
    "sunken":           "#d8d8d8",
    "surface":          "#f5f5f5",   # kartlar, başlık çubuğu, giriş alanları (MC raised)
    "surface2":         "#ececec",   # düğmeler, satırlar (MC surface)
    "surface_active":   "#d8d8d8",   # üzerine gelme / basılı (MC sunken)
    "border":           "#c5c5c5",
    "border_strong":    "#b0b0b0",
    "text":             "#1a1a1a",
    "text_secondary":   "#3d3d3d",
    "text_muted":       "#616161",
    "danger":           "#e53935",
    "danger_hover":     "#c62828",
    "danger_soft":      "#fbe4e3",
    "danger_text":      "#b3261e",
    "success":          "#43A047",
    "success_soft":     "#e0eedf",
    "success_text":     "#1b6e36",  # küçük koyu yazı için (açık zeminde yeşil 3:1 kalıyordu)
    "hi":               "#ffffff",
    "lo":               "#bdbdbd",
    "warn":             "#8A5300",
    "selected_text":    "#ffffff",
}

DARK_BASE = {
    # Nötr gri tonlar (TransferTCP/Lumina/MediaCompressor ile aynı aile); eski lacivert tonlar kaldırıldı.
    "base":             "#161616",
    "raised":           "#262626",
    "sunken":           "#121212",
    "surface":          "#1e1e1e",
    "surface2":         "#262626",
    "surface_active":   "#303030",
    "border":           "#2e2e2e",
    "border_strong":    "#454545",
    "text":             "#f5f5f5",
    "text_secondary":   "#d2d2d2",
    "text_muted":       "#9c9c9c",
    "danger":           "#ef4444",
    "danger_hover":     "#dc2626",
    "danger_soft":      "#3a1818",
    "danger_text":      "#f87171",
    "success":          "#22c55e",
    "success_soft":     "#122b1e",
    "success_text":     "#4ade80",
    "hi":               "#3c3c3c",
    "lo":               "#0e0e0e",
    "warn":             "#f59e0b",
    "selected_text":    "#ffffff",
}


def _build_palette(is_dark: bool, accent_key: str) -> dict:
    spec = ACCENTS.get(accent_key) or ACCENTS[DEFAULT_ACCENT]
    base = dict(DARK_BASE if is_dark else LIGHT_BASE)
    accent = spec["accent"]
    base["accent"] = accent
    base["accent2"] = spec["accent2"]
    base["accent_hi"] = spec["hi_dark"] if is_dark else spec["hi_light"]
    # Opak karışım (8 haneli yarı saydam hex Qt stil sayfasında yanlış karışır)
    base["accent_soft"] = _mix(accent, base["surface2"] if is_dark else base["surface"], 0.24 if is_dark else 0.16)
    # vurgu METİN olarak: parlak ton koyuda okunur, açık gri zeminde yalnızca ~2:1 -> açıkta daha derin ton
    base["accent_text"] = accent if is_dark else spec["accent2"]
    base["border_focus"] = accent
    base["is_dark"] = is_dark
    base["accent_key"] = accent_key
    return base


def _build_qss(p: dict) -> str:
    """Temiz, modern ve rounded bileşenler için tam QSS"""
    chk_path = get_checkmark_icon_path()
    chev_path = get_chevron_down_icon_path(p["text_secondary"])
    return f"""
        /* ── Temel Ayarlar ── */
        * {{
            font-family: 'Segoe UI', 'Segoe UI Variable Text', -apple-system, BlinkMacSystemFont, Arial, sans-serif;
            font-size: 9.5pt;
        }}

        QWidget {{
            color: {p['text']};
            background: transparent;
        }}

        QMainWindow {{
            background: transparent;
        }}

        QDialog {{
            background-color: {p['surface']};
            color: {p['text']};
        }}

        /* ── Yuvarlatılmış Dış Çerçeve (Rounded Windows) ── */
        QFrame#app_chrome, QFrame#dialog_chrome {{
            background-color: {p['base']};
            border: 1px solid {p['border']};
            border-top: 2px solid {p['accent']};
            border-radius: 12px;
        }}

        /* ── Custom Title Bar ── */
        QFrame#title_bar {{
            background-color: {p['surface']};
            border: none;
            border-bottom: 1px solid {p['border']};
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
            min-height: 37px;     /* + 1 px alt çizgi = 38 px başlık çubuğu */
            max-height: 37px;
        }}

        QLabel#title_label {{
            color: {p['text']};
            font-size: 10.5pt;
            font-weight: 700;
            background: transparent;
            padding-left: 4px;
        }}

        QLabel#title_badge {{
            color: {p['accent_text']};
            background-color: {p['accent_soft']};
            font-size: 8pt;
            font-weight: 700;
            border-radius: 6px;
            padding: 2px 7px;
        }}

        /* ── Pencere Kontrol Butonları ── */
        QPushButton#window_control_btn {{
            background-color: transparent;
            border: none;
            border-radius: 7px;
            font-size: 12pt;
            font-weight: 400;
            color: {p['text_muted']};
            padding: 0px;
            margin: 3px 1px;
            min-width: 34px;
            min-height: 30px;
            max-width: 34px;
            max-height: 30px;
        }}
        QPushButton#window_control_btn:hover {{
            background-color: {p['surface2']};
            color: {p['text']};
        }}
        QPushButton#window_control_btn:pressed {{
            background-color: {p['surface_active']};
        }}

        QPushButton#window_close_btn {{
            background-color: transparent;
            border: none;
            border-radius: 7px;
            font-size: 14pt;
            font-weight: 400;
            color: {p['text_muted']};
            padding: 0px;
            margin: 3px 6px 3px 1px;
            min-width: 34px;
            min-height: 30px;
            max-width: 34px;
            max-height: 30px;
        }}
        QPushButton#window_close_btn:hover {{
            background-color: #ef4444;
            color: #ffffff;
        }}
        QPushButton#window_close_btn:pressed {{
            background-color: #dc2626;
            color: #ffffff;
        }}

        /* ── Title Bar Menü Butonları ── */
        QPushButton#title_menu_btn::menu-indicator {{
            subcontrol-origin: padding;
            subcontrol-position: right center;
            right: 6px;
            width: 8px;
        }}
        QPushButton#title_menu_btn {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 7px;
            padding: 4px 22px 4px 6px;
            font-size: 9pt;
            font-weight: 600;
            color: {p['text_secondary']};
            qproperty-iconSize: 16px;
            min-height: 20px;
            max-height: 20px;
        }}
        QPushButton#title_menu_btn:hover {{
            background-color: {p['surface2']};
            border-color: {p['border']};
            color: {p['text']};
        }}
        QPushButton#title_menu_btn:pressed, QPushButton#title_menu_btn[open="true"] {{
            background-color: {p['surface_active']};
            color: {p['accent_text']};
        }}

        /* ── Genel Buton Tasarımları ── */
        QPushButton {{
            background-color: {p['surface2']};
            color: {p['text']};
            border: 1px solid {p['lo']};
            border-top-color: {p['hi']};
            border-left-color: {p['hi']};
            border-radius: 10px;
            padding: 0px 12px;
            font-weight: 600;
            font-size: 9pt;
            outline: none;
            min-height: 32px;
            max-height: 32px;
        }}
        QPushButton:hover {{
            background-color: {p['surface2']};
            border-color: {p['border_strong']};
            color: {p['text']};
        }}
        QPushButton:pressed {{
            background-color: {p['surface_active']};
        }}
        QPushButton:disabled {{
            color: {p['text_muted']};
            background-color: {p['surface2']};
            border-color: {p['border']};
        }}

        /* Vurgulu Primary Buton */
        QPushButton[class="primary"] {{
            background-color: {p['accent2']};
            border: 1px solid {p['accent2']};
            border-top-color: {p['accent_hi']};
            border-left-color: {p['accent_hi']};
            color: #ffffff;
            font-weight: 600;
        }}
        QPushButton[class="primary"]:hover {{
            background-color: {p['accent']};
            border-color: {p['accent']};
        }}
        QPushButton[class="primary"]:pressed {{
            background-color: {p['accent2']};
        }}

        /* Soft / Tehlike Butonu */
        QPushButton[class="danger"] {{
            background-color: {p['danger_soft']};
            border: 1px solid {p['danger_soft']};
            color: {p['danger_text']};
            font-weight: 600;
        }}
        QPushButton[class="danger"]:hover {{
            background-color: {p['danger']};
            border-color: {p['danger']};
            color: #ffffff;
        }}
        QPushButton[class="danger"]:pressed {{
            background-color: {p['danger_hover']};
            border-color: {p['danger_hover']};
            color: #ffffff;
        }}

        /* a class rule outranks the generic :disabled one, so coloured buttons say "disabled" themselves */
        QPushButton[class="primary"]:disabled, QPushButton[class="danger"]:disabled {{
            background-color: {p['surface2']};
            border-color: {p['border']};
            color: {p['text_muted']};
        }}

        /* İkincil / Nötr Buton */
        QPushButton[class="secondary"] {{
            background-color: {p['surface']};
            border: 1px solid {p['border_strong']};
            border-radius: 8px;
            color: {p['text']};
            padding: 0px 12px;
            font-weight: 600;
            min-height: 32px;
            max-height: 32px;
        }}
        QPushButton[class="secondary"]:hover {{
            background-color: {p['surface2']};
            border-color: {p['accent']};
            color: {p['text']};
        }}
        QPushButton[class="secondary"]:pressed {{
            background-color: {p['surface_active']};
        }}

        /* ── Giriş Alanları (Inputs) ── */
        QLineEdit, QPlainTextEdit, QKeySequenceEdit {{
            background-color: {p['surface']};
            color: {p['text']};
            border: 1px solid {p['border']};
            border-radius: 9px;
            padding: 8px 12px;
            font-size: 9.5pt;
            selection-background-color: {p['accent']};
            selection-color: {p['selected_text']};
        }}
        QLineEdit:hover, QPlainTextEdit:hover, QKeySequenceEdit:hover {{
            border-color: {p['border_strong']};
        }}
        QLineEdit:focus, QPlainTextEdit:focus, QKeySequenceEdit:focus {{
            border: 2px solid {p['accent']};
            background-color: {p['surface']};
            padding: 7px 11px;
        }}

        QTextEdit {{
            background-color: {p['surface']};
            color: {p['text']};
            border: 1px solid {p['border']};
            border-radius: 9px;
            padding: 8px 12px;
            font-size: 9.5pt;
            selection-background-color: {p['accent']};
            selection-color: {p['selected_text']};
        }}
        QTextEdit:hover {{
            border-color: {p['border_strong']};
        }}
        QTextEdit:focus {{
            border: 2px solid {p['accent']};
            padding: 7px 11px;
        }}

        /* ── ComboBox ── */
        QComboBox {{
            background-color: {p['surface']};
            color: {p['text']};
            border: 2px solid {p['border_strong']};
            border-radius: 10px;
            padding: 6px 34px 6px 12px;
            font-size: 9.5pt;
            min-height: 36px;
            combobox-popup: 0;
        }}
        QComboBox:hover {{
            border-color: {p['accent']};
            background-color: {p['surface']};
        }}
        QComboBox:focus, QComboBox:on {{
            border-color: {p['accent']};
            background-color: {p['surface']};
        }}
        QComboBox QAbstractItemView {{
            background-color: {p['surface']};
            color: {p['text']};
            border: 1px solid {p['border_strong']};
            outline: none;
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: center right;
            width: 28px;
            border: none;
            background: transparent;
            margin-right: 4px;
        }}
        QComboBox::down-arrow {{
            image: url("{chev_path}");
            width: 12px;
            height: 12px;
        }}
        QListView, QComboBox QAbstractItemView {{
            background-color: {p['surface']};
            color: {p['text']};
            border: 1px solid {p['border_strong']};
            border-radius: 10px;
            padding: 6px;
            outline: none;
            selection-background-color: transparent;
            selection-color: {p['text']};
        }}
        QComboBox QAbstractItemView::item {{
            background-color: transparent;
            color: {p['text']};
            padding: 8px 12px;
            border-radius: 8px;
            min-height: 30px;
            margin: 1px 2px;
        }}
        QComboBox QAbstractItemView::item:hover {{
            background-color: {p['surface2']};
            color: {p['text']};
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {p['accent2']};
            color: #ffffff;
            font-weight: 600;
            border-radius: 8px;
        }}

        /* ── Modern Sekmeler (TabWidget & TabBar) ── */
        QTabWidget {{
            border: none;
            background: transparent;
        }}
        QTabWidget::tab-bar {{
            alignment: center;
        }}
        QTabWidget::pane {{
            border: 1px solid {p['lo']};
            border-top-color: {p['hi']};
            border-left-color: {p['hi']};
            border-radius: 16px;
            background-color: {p['surface']};
            margin-top: 6px;
            padding: 12px;
        }}
        QTabBar {{
            background-color: transparent;
            qproperty-drawBase: 0;
        }}
        QTabBar::tab {{
            background-color: {p['surface2']};
            color: {p['text_muted']};
            padding: 9px 26px;
            border: 1px solid {p['lo']};
            border-top-color: {p['hi']};
            border-left-color: {p['hi']};
            border-radius: 15px;
            margin: 2px 6px 4px 6px;
            font-weight: 600;
            font-size: 9.5pt;
        }}
        QTabBar::tab:selected {{
            background-color: {p['accent_soft']};
            color: {p['accent_text']};
            border: 1px solid {p['accent']};
            font-weight: 700;
        }}
        QTabBar::tab:hover:!selected {{
            background-color: {p['surface_active']};
            color: {p['text']};
        }}

        /* ── Tablo (QTableWidget) ── */
        QTableWidget {{
            background-color: {p['surface']};
            alternate-background-color: {p['surface2']};
            color: {p['text']};
            border: 1px solid {p['border']};
            border-radius: 12px;
            gridline-color: transparent;
            outline: none;
        }}
        QTableWidget::item {{
            color: {p['text']};
            padding: 11px 16px;
            border: none;
            border-bottom: 1px solid {p['border']};
            background-color: transparent;
            font-weight: 500;
        }}
        QTableWidget::item:selected {{
            background-color: {p['accent_soft']};
            color: {p['text']};
            border-bottom: 1px solid {p['border']};
        }}
        QTableWidget::item:hover:!selected {{
            background-color: {p['surface2']};
        }}

        QHeaderView {{
            background-color: {p['surface2']};
            border: none;
            border-bottom: 1px solid {p['border']};
        }}
        QHeaderView::section {{
            background-color: {p['surface2']};
            color: {p['text_muted']};
            padding: 10px 16px;
            border: none;
            border-right: 1px solid {p['border']};
            font-weight: 700;
            font-size: 8.5pt;
            text-transform: uppercase;
        }}
        QHeaderView::section:first {{
            border-top-left-radius: 11px;
        }}
        QHeaderView::section:last {{
            border-top-right-radius: 11px;
            border-right: none;
        }}

        /* ── Araç çubuğu: segment grubu, özet hapı, simge düğmesi ── */
        QFrame#btn_group {{
            background-color: {p['surface2']};
            border: 1px solid {p['lo']};
            border-top-color: {p['hi']};
            border-left-color: {p['hi']};
            border-radius: 12px;
        }}
        QFrame#btn_sep {{
            background-color: {p['border']};
            border: none;
            margin: 6px 2px;
            max-width: 1px;
        }}
        QPushButton[class="seg"], QPushButton[class="seg-danger"] {{
            background-color: transparent;
            border: none;
            border-radius: 9px;
            padding: 0px 14px;
            color: {p['text']};
            font-weight: 600;
            min-height: 30px;
            max-height: 30px;
        }}
        QPushButton[class="seg"]:hover {{
            background-color: {p['surface_active']};
        }}
        QPushButton[class="seg-danger"] {{
            color: {p['danger_text']};
        }}
        QPushButton[class="seg-danger"]:hover {{
            background-color: {p['danger_soft']};
        }}
        QPushButton[class="seg"]:pressed, QPushButton[class="seg-danger"]:pressed {{
            background-color: {p['surface']};
        }}
        /* seçim yokken (araç çubuğu): pasif düğmeler soluk, üzerine gelince tepki yok */
        QPushButton[class="seg"]:disabled, QPushButton[class="seg-danger"]:disabled {{
            background-color: transparent;
            color: {p['text_muted']};
        }}
        QPushButton[class="icon"] {{
            padding: 0px;
            min-width: 36px;
            max-width: 36px;
            border-radius: 18px;
        }}
        QLabel#summary_chip {{
            color: {p['text_secondary']};
            background-color: {p['surface']};
            border: 1px solid {p['border']};
            border-radius: 13px;
            padding: 5px 14px;
            font-size: 8.5pt;
            font-weight: 600;
        }}

        /* ── Gruplanmış liste: kart ızgarası ── */
        QScrollArea#card_grid {{
            background-color: transparent;
            border: none;
        }}
        QFrame#list_panel {{
            background-color: {p['surface']};
            border: 1px solid {p['border']};
            border-radius: 12px;
        }}
        QWidget#card_grid_inner {{
            background-color: transparent;
        }}
        QFrame#list_row {{
            background-color: {p['surface2']};
            border: 1px solid {p['lo']};
            border-top-color: {p['hi']};
            border-left-color: {p['hi']};
            border-radius: 12px;
        }}
        QFrame#list_row:hover {{
            background-color: {p['surface_active']};
            border-color: {p['border_strong']};
        }}
        QFrame#list_row[selected="true"] {{
            background-color: {p['accent_soft']};
            border: 1px solid {p['accent']};
        }}
        QFrame#row_accent {{
            background-color: transparent;
            border: none;
            border-radius: 2px;
        }}
        QFrame#row_accent[selected="true"] {{
            background-color: {p['accent']};
        }}
        QFrame#row_sep {{
            background-color: {p['border']};
            border: none;
            max-height: 1px;
        }}
        QFrame#status_dot {{
            background-color: {p['text_muted']};
            border-radius: 4px;
        }}
        QFrame#status_dot[active="true"] {{
            background-color: {p['success']};
        }}
        QFrame#status_dot[active="false"] {{
            background-color: {p['text_muted']};
        }}
        /* tuş başlığı: klavye tuşu gibi alt kenarı kalın */
        QLabel#card_kbd {{
            color: {p['text']};
            background-color: {p['surface']};
            border: 1px solid {p['border_strong']};
            border-bottom: 2px solid {p['border_strong']};
            border-radius: 7px;
            padding: 3px 9px;
            font-size: 9pt;
            font-weight: 700;
            min-width: 56px;
            max-width: 240px;
        }}
        QLabel#card_primary {{
            color: {p['accent_text']};
            font-weight: 700;
            font-size: 8.5pt;
        }}
        QLabel#card_secondary {{
            color: {p['text']};
            font-size: 10pt;
            font-weight: 600;
            min-width: 0;
        }}
        /* pasif kayıt: metinler soluk (kart yine tıklanabilir, seçilip yeniden açılabilir) */
        QFrame#list_row[cardEnabled="false"] QLabel#card_secondary,
        QFrame#list_row[cardEnabled="false"] QLabel#card_primary,
        QFrame#list_row[cardEnabled="false"] QLabel#card_kbd {{
            color: {p['text_muted']};
        }}
        QLabel#card_state {{
            border-radius: 9px;
            padding: 2px 10px;
            font-size: 8pt;
            font-weight: 700;
            min-width: 34px;
        }}
        QLabel#card_state[active="true"] {{
            color: {p['success_text']};
            background-color: {p['success_soft']};
        }}
        QLabel#card_state[active="false"] {{
            color: {p['text_muted']};
            background-color: {p['surface_active']};
        }}
        QLabel#card_badge {{
            color: {p['accent_text']};
            background-color: {p['accent_soft']};
            border: 1px solid {p['accent']};
            border-radius: 5px;
            padding: 2px 6px;
            font-size: 8pt;
            font-weight: 800;
        }}
        QLabel#card_chip {{
            color: {p['accent_text']};
            font-size: 8.5pt;
            font-weight: 600;
        }}
        QFrame#list_empty {{
            background-color: transparent;
            border: none;
        }}
        QLabel#empty_title {{
            color: {p['text']};
            font-size: 12pt;
            font-weight: 700;
        }}

        /* ── CheckBox ── */
        QCheckBox {{
            spacing: 10px;
            color: {p['text']};
            background: transparent;
            font-size: 9.5pt;
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 5px;
            background-color: {p['surface2']};
            border: 1px solid {p['border_strong']};
        }}
        QCheckBox::indicator:hover {{
            border-color: {p['accent']};
            background-color: {p['surface']};
        }}
        QCheckBox::indicator:checked {{
            background-color: {p['accent2']};
            border-color: {p['accent2']};
            image: url("{chk_path}");
        }}

        /* ── ScrollBar ── */
        QScrollBar:vertical {{
            background-color: transparent;
            width: 8px;
            margin: 2px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical {{
            background: {p['accent']};
            border-radius: 4px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {p['accent']};
        }}
        QScrollBar:horizontal {{
            background-color: transparent;
            height: 8px;
            margin: 2px;
            border-radius: 4px;
        }}
        QScrollBar::handle:horizontal {{
            background: {p['accent']};
            border-radius: 4px;
            min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {p['accent']};
        }}
        QScrollBar::add-line, QScrollBar::sub-line,
        QScrollBar::add-page, QScrollBar::sub-page {{
            background: none;
            border: none;
        }}

        /* ── Kart ve Çerçeveler ── */
        QFrame[frameShape="6"] {{
            background-color: {p['surface']};
            border: 1px solid {p['border']};
            border-radius: 12px;
            padding: 14px;
        }}
        QFrame[frameShape="4"] {{
            background-color: {p['border']};
            border: none;
            max-height: 1px;
        }}

        /* Modern Kart Widget */
        QFrame#card_frame {{
            background-color: {p['surface']};
            border: 1px solid {p['border']};
            border-radius: 12px;
        }}

        /* ── Menüler (QMenu) ── */
        QMenu {{
            background-color: {p['surface']};
            border: 1px solid {p['border']};
            border-radius: 12px;
            padding: 6px;
            icon-size: 18px;
        }}
        QMenu::item {{
            padding: 7px 32px 7px 8px;
            border-radius: 7px;
            color: {p['text']};
            background-color: transparent;
            font-size: 9.5pt;
            min-height: 22px;
        }}
        QMenu::icon {{
            padding-left: 6px;
            padding-right: 6px;
        }}
        QMenu::item:selected {{
            background-color: {p['accent2']};
            color: #ffffff;
        }}
        QMenu::item:checked {{
            background-color: {p['accent_soft']};
            color: {p['accent_text']};
            font-weight: 700;
        }}
        QMenu::item:checked:selected {{
            background-color: {p['accent2']};
            color: #ffffff;
            font-weight: 700;
        }}
        QMenu::indicator {{
            width: 0px;
            height: 0px;
        }}
        QMenu::separator {{
            height: 1px;
            background: {p['border']};
            margin: 4px 6px;
        }}
        QMenu::right-arrow {{
            width: 8px;
            height: 8px;
            margin-right: 8px;
        }}

        /* ── Başlık ve Bilgi Etiketleri ── */
        QLabel {{
            color: {p['text']};
            background: transparent;
        }}
        QLabel#hint_label {{
            color: {p['text_muted']};
            font-size: 8.5pt;
            padding-top: 2px;
            line-height: 1.35;
        }}
        QLabel#section_header {{
            color: {p['text']};
            font-size: 11pt;
            font-weight: 700;
        }}
        QLabel#dialog_header {{
            color: {p['text']};
            font-size: 13pt;
            font-weight: 700;
        }}
        QLabel#update_status {{
            color: {p['text_muted']};
            font-size: 8.5pt;
        }}
        QLabel#update_error {{
            color: {p['danger_text']};
            background-color: {p['danger_soft']};
            border: 1px solid {p['danger']};
            border-radius: 8px;
            padding: 8px 10px;
        }}

        /* ── Status Bar ── */
        QStatusBar {{
            background-color: {p['surface']};
            color: {p['text_muted']};
            border-top: 1px solid {p['border']};
            border-bottom-left-radius: 15px;
            border-bottom-right-radius: 15px;
            padding: 4px 12px;
            font-size: 8.5pt;
        }}

        /* ── Progress Bar ── */
        QProgressBar {{
            background-color: {p['surface2']};
            border: 1px solid {p['border']};
            border-radius: 8px;
            text-align: center;
            color: {p['text']};
            font-weight: 600;
            height: 16px;
        }}
        QProgressBar::chunk {{
            background-color: {p['accent']};
            border-radius: 7px;
        }}

        /* ── Tooltip ── */
        QToolTip {{
            background-color: {p['surface']};
            color: {p['text']};
            border: 1px solid {p['border']};
            border-radius: 7px;
            padding: 6px 10px;
            font-size: 8.5pt;
        }}
    """


class ThemeManager(QObject):
    """Modern tema ve vurgu rengi yöneticisi"""

    theme_changed = pyqtSignal(str, str)  # (theme_name, accent_key)

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.current_theme = "light"
        self.current_accent = DEFAULT_ACCENT

    def set_theme(self, theme_name: str, accent_key: str | None = None):
        """Temayı (light / dark / system) ve opsiyonel vurgu rengini uygula"""
        # Geriye dönük uyumluluk: 'neumorphic_dark' -> 'dark', 'neumorphic_light' -> 'light'
        if 'dark' in theme_name.lower():
            clean_theme = 'dark'
        elif 'light' in theme_name.lower():
            clean_theme = 'light'
        else:
            clean_theme = 'light'

        self.current_theme = clean_theme
        if accent_key and accent_key in ACCENTS:
            self.current_accent = accent_key

        palette = _build_palette(self.current_theme == "dark", self.current_accent)
        global _ACTIVE_ACCENT, _ACTIVE_ACCENT_BASE
        _ACTIVE_ACCENT = palette["accent_text"]
        _ACTIVE_ACCENT_BASE = palette["accent"]
        qss = _build_qss(palette)
        self.app.setStyleSheet(qss)
        self.theme_changed.emit(self.current_theme, self.current_accent)

    def set_accent(self, accent_key: str):
        """Sadece vurgu rengini değiştir"""
        if accent_key in ACCENTS:
            self.set_theme(self.current_theme, accent_key)

    def get_current_theme(self) -> str:
        return self.current_theme

    def get_current_accent(self) -> str:
        return self.current_accent

    def get_palette(self) -> dict:
        """Mevcut temanın ve vurgunun renk paletini döndür"""
        return _build_palette(self.current_theme == "dark", self.current_accent)

    def style_combo(self, combo) -> None:
        """Popup'ı ilk açılışta zıplatmadan hazırlar."""
        from PyQt6.QtCore import QSize, Qt

        p = self.get_palette()
        combo.setMinimumHeight(36)
        combo.setMaxVisibleItems(8)
        view = combo.view()
        view.setAutoFillBackground(True)
        view.setUniformItemSizes(True)
        for i in range(combo.count()):
            combo.setItemData(i, QSize(0, 32), Qt.ItemDataRole.SizeHintRole)
        view.setStyleSheet(f"""
            QAbstractItemView {{
                background-color: {p['surface']};
                color: {p['text']};
                outline: none;
                border: 1px solid {p['border_strong']};
                padding: 4px;
            }}
            QAbstractItemView::item {{
                min-height: 28px;
                padding: 6px 10px;
                color: {p['text']};
            }}
            QAbstractItemView::item:selected {{
                background-color: {p['accent2']};
                color: #ffffff;
            }}
        """)
        if not getattr(combo, "_fk_popup_patched", False):
            original = combo.showPopup

            def _show_popup():
                view.setMinimumWidth(max(combo.width(), 160))
                original()

            combo.showPopup = _show_popup
            combo._fk_popup_patched = True
