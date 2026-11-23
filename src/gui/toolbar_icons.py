"""Araç çubuğu simgeleri: emoji yerine verilen renkte çizilen vektörler (tema renklerini izler)."""

from __future__ import annotations

import math
import re

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

KINDS = ("plus", "edit", "trash", "power", "refresh", "update", "download", "upload", "palette", "bolt", "archive",
         "keyboard", "textdoc", "gear")
_CACHE: dict[tuple[str, str, int], QIcon] = {}


def strip_symbols(text: str) -> str:
    """Metnin başındaki emoji/simge karakterlerini (ve boşluklarını) atar: "✏️ Düzenle" -> "Düzenle"."""
    return re.sub(r"^[^\w]+", "", text or "", flags=re.UNICODE).strip()


def toolbar_icon(kind: str, color: str, size: int = 16) -> QIcon:
    if kind not in KINDS:
        raise ValueError(f"unknown icon: {kind}")
    key = (kind, color.lower(), size)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    scale = 2
    pix = QPixmap(size * scale, size * scale)
    pix.setDevicePixelRatio(scale)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    c = QColor(color)
    s = float(size)
    pen = QPen(c, s * 0.115)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "plus":
        p.drawLine(QPointF(s * 0.5, s * 0.2), QPointF(s * 0.5, s * 0.8))
        p.drawLine(QPointF(s * 0.2, s * 0.5), QPointF(s * 0.8, s * 0.5))
    elif kind == "edit":
        path = QPainterPath()
        path.moveTo(QPointF(s * 0.2, s * 0.8))
        path.lineTo(QPointF(s * 0.26, s * 0.58))
        path.lineTo(QPointF(s * 0.62, s * 0.22))
        path.lineTo(QPointF(s * 0.78, s * 0.38))
        path.lineTo(QPointF(s * 0.42, s * 0.74))
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(s * 0.54, s * 0.3), QPointF(s * 0.7, s * 0.46))
    elif kind == "trash":
        p.drawLine(QPointF(s * 0.2, s * 0.28), QPointF(s * 0.8, s * 0.28))
        p.drawLine(QPointF(s * 0.4, s * 0.28), QPointF(s * 0.4, s * 0.18))
        p.drawLine(QPointF(s * 0.4, s * 0.18), QPointF(s * 0.6, s * 0.18))
        p.drawLine(QPointF(s * 0.6, s * 0.18), QPointF(s * 0.6, s * 0.28))
        body = QPainterPath()
        body.moveTo(QPointF(s * 0.28, s * 0.28))
        body.lineTo(QPointF(s * 0.32, s * 0.82))
        body.lineTo(QPointF(s * 0.68, s * 0.82))
        body.lineTo(QPointF(s * 0.72, s * 0.28))
        p.drawPath(body)
        p.drawLine(QPointF(s * 0.45, s * 0.42), QPointF(s * 0.45, s * 0.68))
        p.drawLine(QPointF(s * 0.55, s * 0.42), QPointF(s * 0.55, s * 0.68))
    elif kind == "power":
        p.drawArc(QRectF(s * 0.2, s * 0.22, s * 0.6, s * 0.6), 120 * 16, -300 * 16)
        p.drawLine(QPointF(s * 0.5, s * 0.14), QPointF(s * 0.5, s * 0.46))
    elif kind == "refresh":
        p.drawArc(QRectF(s * 0.2, s * 0.2, s * 0.6, s * 0.6), 40 * 16, 270 * 16)
        arrow = QPainterPath()
        arrow.moveTo(QPointF(s * 0.74, s * 0.14))
        arrow.lineTo(QPointF(s * 0.76, s * 0.36))
        arrow.lineTo(QPointF(s * 0.54, s * 0.34))
        p.drawPath(arrow)
    elif kind in ("update", "download"):
        p.drawLine(QPointF(s * 0.5, s * 0.2), QPointF(s * 0.5, s * 0.64))
        p.drawLine(QPointF(s * 0.5, s * 0.64), QPointF(s * 0.32, s * 0.46))
        p.drawLine(QPointF(s * 0.5, s * 0.64), QPointF(s * 0.68, s * 0.46))
        p.drawLine(QPointF(s * 0.22, s * 0.82), QPointF(s * 0.78, s * 0.82))
    elif kind == "upload":
        p.drawLine(QPointF(s * 0.5, s * 0.66), QPointF(s * 0.5, s * 0.22))
        p.drawLine(QPointF(s * 0.5, s * 0.22), QPointF(s * 0.32, s * 0.4))
        p.drawLine(QPointF(s * 0.5, s * 0.22), QPointF(s * 0.68, s * 0.4))
        p.drawLine(QPointF(s * 0.22, s * 0.82), QPointF(s * 0.78, s * 0.82))
    elif kind == "palette":
        p.drawEllipse(QRectF(s * 0.14, s * 0.14, s * 0.72, s * 0.72))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        for cx, cy in ((0.36, 0.38), (0.6, 0.34), (0.68, 0.56), (0.38, 0.62)):
            p.drawEllipse(QPointF(s * cx, s * cy), s * 0.055, s * 0.055)
    elif kind == "bolt":
        bolt = QPainterPath()
        bolt.moveTo(QPointF(s * 0.58, s * 0.1))
        bolt.lineTo(QPointF(s * 0.26, s * 0.54))
        bolt.lineTo(QPointF(s * 0.5, s * 0.54))
        bolt.lineTo(QPointF(s * 0.42, s * 0.9))
        bolt.lineTo(QPointF(s * 0.74, s * 0.44))
        bolt.lineTo(QPointF(s * 0.5, s * 0.44))
        bolt.closeSubpath()
        p.drawPath(bolt)
    elif kind == "archive":
        p.drawRoundedRect(QRectF(s * 0.14, s * 0.2, s * 0.72, s * 0.18), s * 0.04, s * 0.04)
        p.drawRoundedRect(QRectF(s * 0.2, s * 0.38, s * 0.6, s * 0.44), s * 0.04, s * 0.04)
        p.drawLine(QPointF(s * 0.42, s * 0.54), QPointF(s * 0.58, s * 0.54))
    elif kind == "keyboard":
        p.drawRoundedRect(QRectF(s * 0.1, s * 0.24, s * 0.8, s * 0.52), s * 0.1, s * 0.1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        for row, y in enumerate((0.36, 0.5)):
            for i in range(4):
                p.drawRoundedRect(QRectF(s * (0.22 + i * 0.16), s * y, s * 0.09, s * 0.06), s * 0.02, s * 0.02)
        p.drawRoundedRect(QRectF(s * 0.3, s * 0.63, s * 0.4, s * 0.06), s * 0.02, s * 0.02)
    elif kind == "textdoc":
        p.drawRoundedRect(QRectF(s * 0.22, s * 0.12, s * 0.56, s * 0.76), s * 0.1, s * 0.1)
        for y, end in ((0.34, 0.66), (0.5, 0.66), (0.66, 0.52)):
            p.drawLine(QPointF(s * 0.34, s * y), QPointF(s * end, s * y))
    elif kind == "gear":
        p.drawEllipse(QRectF(s * 0.34, s * 0.34, s * 0.32, s * 0.32))
        for ang in range(0, 360, 45):
            p.save()
            p.translate(s * 0.5, s * 0.5)
            p.rotate(ang)
            p.drawLine(QPointF(0, -s * 0.3), QPointF(0, -s * 0.4))
            p.restore()
        p.drawEllipse(QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56))
    p.end()
    icon = QIcon(pix)
    _CACHE[key] = icon
    return icon


def _menu_accent(kind: str = "accent") -> str:
    """Seçili vurgunun rengi (`accent`, `hi_light`): tema yöneticisinin en son uyguladığı vurgudan okunur."""
    from src.utils import theme_manager as tm

    base = str(getattr(tm, "_ACTIVE_ACCENT_BASE", "") or "").lower()
    spec = next((s for s in tm.ACCENTS.values() if s["accent"].lower() == base), tm.ACCENTS[tm.DEFAULT_ACCENT])
    return spec[kind]


# --- Renkli menü simgeleri ------------------------------------------------------------------------------------
# Lumina'daki (`app/ui/icons.py: menu_icon`) çizim ve renklerin aynısı: başlık menüleri, tepsi menüsü, sağ tık
# menüleri ve Ayarlar kenar çubuğu için iki tonlu, renkli simgeler. Her anlamın sabit bir rengi var (ayarlar mor
# dişli, bilgi mavi, güncelleme yeşil, çıkış/sil kırmızı, klasör amber...); "blue"/"sky" aileleri seçili vurguyu
# izler. Araç çubuğu simgeleri tek renk kalır. 32'lik ızgarada çizilir (32 ve 48 px kopya: %100/%150'de keskin);
# devre dışı satırlarda Qt simgeyi kendisi griler.

MENU_PALETTE = {
    "blue": "#2196F3", "blue_soft": "#90CAF9",  # "blue"/"sky" aileleri `_mi_color` içinde seçili vurguya yönlenir
    "amber": "#f59e0b", "amber_soft": "#fcd34d", "amber_deep": "#d97706",
    "green": "#22c55e", "emerald": "#10b981",
    "violet": "#8b5cf6", "purple": "#a855f7", "purple_soft": "#e9d5ff",
    "indigo": "#7c7ff5", "sky": "#2196F3", "sky_soft": "#90CAF9",
    "teal": "#14b8a6", "red": "#ef4444", "red_soft": "#fecaca",
    "orange": "#f97316", "cyan": "#06b6d4", "yellow": "#eab308",
}


def _mi_color(name: str) -> QColor:
    """Menü simgesi rengi. "blue"/"sky" aileleri seçili vurguyu izler; diğerleri anlam taşıyan sabit tonlardır."""
    if name in ("blue", "sky"):
        return QColor(_menu_accent("accent"))
    if name in ("blue_soft", "sky_soft"):
        return QColor(_menu_accent("hi_light"))
    return QColor(MENU_PALETTE[name])


def _mi_pen(color: QColor, width: float = 2.2) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _mi_icon(draw) -> QIcon:
    """`draw(painter)` 32×32'lik ızgarada çizer; 32 ve 48 px kopyalar."""
    icon = QIcon()
    for size in (32, 48):
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(size / 32.0, size / 32.0)
        draw(p)
        p.end()
        icon.addPixmap(pix)
    return icon


def _mi_gear(p: QPainter) -> None:
    gear = QPainterPath()
    gear.addEllipse(QPointF(16, 16), 8.6, 8.6)
    for i in range(8):
        tooth = QPainterPath()
        tooth.addRoundedRect(QRectF(-2.4, -12.4, 4.8, 6.0), 1.2, 1.2)
        p.save()
        p.translate(16, 16)
        p.rotate(i * 45)
        gear = gear.united(p.transform().map(tooth))
        p.restore()
    hole = QPainterPath()
    hole.addEllipse(QPointF(16, 16), 3.6, 3.6)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_mi_color("violet")))
    p.drawPath(gear.subtracted(hole))


def _mi_badge(p: QPainter, color: str) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_mi_color(color)))
    p.drawEllipse(QPointF(16, 16), 11, 11)


def _mi_info(p: QPainter) -> None:
    _mi_badge(p, "blue")
    p.setBrush(QBrush(QColor("#ffffff")))
    p.drawEllipse(QPointF(16, 10.6), 1.7, 1.7)
    p.drawRoundedRect(QRectF(14.5, 14, 3, 9.5), 1.3, 1.3)


def _mi_add(p: QPainter) -> None:
    """Yeşil rozet + beyaz artı: "Yeni …" satırları."""
    _mi_badge(p, "green")
    p.setPen(_mi_pen(QColor("#ffffff"), 2.4))
    p.drawLine(QPointF(16, 10.5), QPointF(16, 21.5))
    p.drawLine(QPointF(10.5, 16), QPointF(21.5, 16))


def _mi_update(p: QPainter) -> None:
    color = _mi_color("emerald")
    p.setPen(_mi_pen(color, 2.2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(6.5, 6.5, 19, 19), 30 * 16, 150 * 16)
    p.drawArc(QRectF(6.5, 6.5, 19, 19), 210 * 16, 150 * 16)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    p.drawPolygon(QPolygonF([QPointF(24.6, 5.8), QPointF(25.4, 12.6), QPointF(18.8, 10.6)]))
    p.drawPolygon(QPolygonF([QPointF(7.4, 26.2), QPointF(6.6, 19.4), QPointF(13.2, 21.4)]))


def _mi_exit(p: QPainter) -> None:
    """Kapı + dışarı ok: "Çıkış" satırları."""
    color = _mi_color("red")
    p.setPen(_mi_pen(color, 2.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolyline(QPolygonF([QPointF(14.5, 6.5), QPointF(6.5, 6.5), QPointF(6.5, 25.5), QPointF(14.5, 25.5)]))
    p.drawLine(QPointF(12.0, 16.0), QPointF(26.0, 16.0))
    p.drawPolyline(QPolygonF([QPointF(21.0, 11.0), QPointF(26.0, 16.0), QPointF(21.0, 21.0)]))


def _mi_view(p: QPainter) -> None:
    eye = QPainterPath()
    eye.moveTo(4, 16)
    eye.quadTo(16, 4.5, 28, 16)
    eye.quadTo(16, 27.5, 4, 16)
    p.setPen(_mi_pen(_mi_color("indigo"), 1.8))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(eye)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_mi_color("indigo")))
    p.drawEllipse(QPointF(16, 16), 4.6, 4.6)


def _mi_globe(p: QPainter) -> None:
    fill = _mi_color("sky")
    fill.setAlpha(55)
    p.setPen(_mi_pen(_mi_color("sky"), 1.7))
    p.setBrush(QBrush(fill))
    p.drawEllipse(QPointF(16, 16), 10, 10)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(16, 16), 4.6, 10)
    p.drawLine(QPointF(6, 16), QPointF(26, 16))
    p.drawLine(QPointF(7.6, 11), QPointF(24.4, 11))
    p.drawLine(QPointF(7.6, 21), QPointF(24.4, 21))


def _mi_document(p: QPainter) -> None:
    body = QPainterPath()
    body.moveTo(9, 5.5)
    body.lineTo(18.5, 5.5)
    body.lineTo(24, 11)
    body.lineTo(24, 25)
    body.quadTo(24, 26.5, 22.5, 26.5)
    body.lineTo(9.5, 26.5)
    body.quadTo(8, 26.5, 8, 25)
    body.lineTo(8, 7)
    body.quadTo(8, 5.5, 9, 5.5)
    p.setPen(_mi_pen(_mi_color("blue"), 1.6))
    p.setBrush(QBrush(_mi_color("blue_soft")))
    p.drawPath(body)
    p.setBrush(QBrush(_mi_color("blue")))
    p.drawPolygon(QPolygonF([QPointF(18.5, 5.5), QPointF(24, 11), QPointF(18.5, 11)]))
    p.setPen(_mi_pen(_mi_color("blue"), 1.5))
    for y, x2 in ((15.5, 20.5), (19, 20.5), (22.5, 17)):
        p.drawLine(QPointF(11.5, y), QPointF(x2, y))


def _mi_folder(p: QPainter) -> None:
    back = QPainterPath()
    back.moveTo(5, 9.5)
    back.quadTo(5, 7.5, 7, 7.5)
    back.lineTo(12.5, 7.5)
    back.lineTo(15, 10)
    back.lineTo(25, 10)
    back.quadTo(27, 10, 27, 12)
    back.lineTo(27, 23)
    back.quadTo(27, 25, 25, 25)
    back.lineTo(7, 25)
    back.quadTo(5, 25, 5, 23)
    back.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_mi_color("amber_deep")))
    p.drawPath(back)
    p.setBrush(QBrush(_mi_color("amber_soft")))
    p.drawRoundedRect(QRectF(5, 12.5, 22, 12.5), 2.0, 2.0)


def _mi_plus_badge(p: QPainter) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_mi_color("green")))
    p.drawEllipse(QPointF(23, 22), 7, 7)
    p.setPen(_mi_pen(QColor("#ffffff"), 1.9))
    p.drawLine(QPointF(23, 18.6), QPointF(23, 25.4))
    p.drawLine(QPointF(19.6, 22), QPointF(26.4, 22))


def _mi_folder_add(p: QPainter) -> None:
    """Klasör + yeşil artı rozeti (Lumina "Kopyala…" ile aynı çizim): "Klasör Ekle"."""
    _mi_folder(p)
    _mi_plus_badge(p)


def _mi_file_add(p: QPainter) -> None:
    """Belge + yeşil artı rozeti: "Dosya Ekle"."""
    _mi_document(p)
    _mi_plus_badge(p)


def _mi_copy(p: QPainter) -> None:
    p.setPen(_mi_pen(_mi_color("sky"), 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(12, 5.5, 13, 15.5), 2, 2)
    p.setBrush(QBrush(_mi_color("sky_soft")))
    p.drawRoundedRect(QRectF(7, 10.5, 13, 15.5), 2, 2)


def _mi_trash(p: QPainter) -> None:
    p.setPen(_mi_pen(_mi_color("red"), 1.8))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(7.5, 10), QPointF(24.5, 10))
    p.drawLine(QPointF(13, 10), QPointF(13.8, 6.8))
    p.drawLine(QPointF(19, 10), QPointF(18.2, 6.8))
    p.drawLine(QPointF(13.8, 6.8), QPointF(18.2, 6.8))
    p.setBrush(QBrush(_mi_color("red_soft")))
    p.drawRoundedRect(QRectF(9.5, 10, 13, 15.5), 2, 2)
    p.drawLine(QPointF(14, 14), QPointF(14, 21.5))
    p.drawLine(QPointF(18, 14), QPointF(18, 21.5))


def _mi_open_with(p: QPainter) -> None:
    p.setPen(_mi_pen(_mi_color("purple"), 1.8))
    p.setBrush(QBrush(_mi_color("purple_soft")))
    p.drawRoundedRect(QRectF(5.5, 9.5, 17, 17), 2.5, 2.5)
    p.setPen(_mi_pen(_mi_color("purple"), 2.1))
    p.drawLine(QPointF(14, 18), QPointF(26, 6))
    p.drawLine(QPointF(19, 6), QPointF(26, 6))
    p.drawLine(QPointF(26, 6), QPointF(26, 13))


def _mi_rename(p: QPainter) -> None:
    p.save()
    p.translate(16, 16)
    p.rotate(45)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_mi_color("amber")))
    p.drawRoundedRect(QRectF(-3.2, -11.5, 6.4, 17), 1.2, 1.2)
    p.setBrush(QBrush(_mi_color("amber_deep")))
    p.drawRect(QRectF(-3.2, -11.5, 6.4, 3.4))
    p.setBrush(QBrush(QColor("#fde68a")))
    p.drawPolygon(QPolygonF([QPointF(-3.2, 5.5), QPointF(3.2, 5.5), QPointF(0, 11)]))
    p.restore()
    p.setPen(_mi_pen(_mi_color("amber_deep"), 1.6))
    p.drawLine(QPointF(17, 26), QPointF(26, 26))


def _mi_guide(p: QPainter) -> None:
    """Açık kitap: "Kullanım Kılavuzu"."""
    color = _mi_color("indigo")
    soft = QColor(color)
    soft.setAlpha(60)
    p.setPen(_mi_pen(color, 1.7))
    p.setBrush(QBrush(soft))
    for x_out in (5.0, 27.0):
        page = QPainterPath()
        page.moveTo(16, 9)
        page.cubicTo(16 + (x_out - 16) * 0.27, 7, 16 + (x_out - 16) * 0.68, 6.8, x_out, 7.5)
        page.lineTo(x_out, 24)
        page.cubicTo(16 + (x_out - 16) * 0.68, 23.3, 16 + (x_out - 16) * 0.27, 23.5, 16, 25.5)
        page.closeSubpath()
        p.drawPath(page)
    p.drawLine(QPointF(16, 9), QPointF(16, 25.5))


def _mi_bolt(p: QPainter) -> None:
    """Şimşek: "Hızlı İşlemler"."""
    p.setPen(_mi_pen(_mi_color("amber_deep"), 1.2))
    p.setBrush(QBrush(_mi_color("yellow")))
    p.drawPolygon(QPolygonF([QPointF(18.4, 4), QPointF(8.8, 16.8), QPointF(15.6, 16.8), QPointF(13.6, 28),
                             QPointF(23.2, 15.2), QPointF(16.4, 15.2)]))


def _mi_backup(p: QPainter) -> None:
    """Arşiv kutusu: "Yedekleme ve Aktarım"."""
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_mi_color("amber_deep")))
    p.drawRoundedRect(QRectF(5, 7, 22, 6.5), 1.8, 1.8)
    p.setBrush(QBrush(_mi_color("amber_soft")))
    p.drawRoundedRect(QRectF(7, 13.5, 18, 12.5), 1.8, 1.8)
    p.setPen(_mi_pen(_mi_color("amber_deep"), 2.0))
    p.drawLine(QPointF(13, 17.5), QPointF(19, 17.5))


def _mi_trim(p: QPainter) -> None:
    """Makas: "Kırp…" (Lumina'daki kırpma gibi yeşil)."""
    color = _mi_color("green")
    p.setPen(_mi_pen(color, 2.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(9.5, 22.5), 3.6, 3.6)
    p.drawEllipse(QPointF(22.5, 22.5), 3.6, 3.6)
    p.drawLine(QPointF(11.8, 19.6), QPointF(23, 6))
    p.drawLine(QPointF(20.2, 19.6), QPointF(9, 6))


def _mi_adjust(p: QPainter) -> None:
    """Kaydırıcılar: dosyaya özel ayarlar."""
    color = _mi_color("orange")
    p.setPen(_mi_pen(color, 2.0))
    for y in (9, 16, 23):
        p.drawLine(QPointF(5.5, y), QPointF(26.5, y))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    for x, y in ((11, 9), (21, 16), (14, 23)):
        p.drawEllipse(QPointF(x, y), 3.3, 3.3)


def _mi_send(p: QPainter) -> None:
    """Kâğıt uçak: "Dosya Gönder" / aktarım."""
    color = _mi_color("teal")
    soft = QColor(color)
    soft.setAlpha(70)
    p.setPen(_mi_pen(color, 1.8))
    p.setBrush(QBrush(soft))
    p.drawPolygon(QPolygonF([QPointF(4.5, 15), QPointF(27.5, 5.5), QPointF(20.5, 27), QPointF(15, 18.5)]))
    p.drawLine(QPointF(15, 18.5), QPointF(27.5, 5.5))


def _mi_star(p: QPainter) -> None:
    """Yıldız: sık kullanılanlar."""
    points = []
    for i in range(10):
        radius = 11.0 if i % 2 == 0 else 4.8
        angle = math.radians(-90 + i * 36)
        points.append(QPointF(16 + radius * math.cos(angle), 16.8 + radius * math.sin(angle)))
    p.setPen(_mi_pen(_mi_color("amber_deep"), 1.2))
    p.setBrush(QBrush(_mi_color("yellow")))
    p.drawPolygon(QPolygonF(points))


def _mi_network(p: QPainter) -> None:
    """Bağlı üç düğüm: ağ ayarları."""
    color = _mi_color("cyan")
    p.setPen(_mi_pen(color, 2.0))
    p.drawLine(QPointF(16, 8.5), QPointF(8.5, 22.5))
    p.drawLine(QPointF(16, 8.5), QPointF(23.5, 22.5))
    p.drawLine(QPointF(8.5, 22.5), QPointF(23.5, 22.5))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    for x, y in ((16, 8.5), (8.5, 22.5), (23.5, 22.5)):
        p.drawEllipse(QPointF(x, y), 4.2, 4.2)


def _mi_pause(p: QPainter) -> None:
    """İki çubuk: "Duraklat"."""
    p.setPen(_mi_pen(_mi_color("amber_deep"), 1.2))
    p.setBrush(QBrush(_mi_color("amber")))
    p.drawRoundedRect(QRectF(8.2, 6.5, 5.8, 19), 1.8, 1.8)
    p.drawRoundedRect(QRectF(18, 6.5, 5.8, 19), 1.8, 1.8)


def _mi_play(p: QPainter) -> None:
    """Üçgen: "Sürdür" / oynat."""
    p.setPen(_mi_pen(_mi_color("emerald"), 1.4))
    p.setBrush(QBrush(_mi_color("green")))
    p.drawPolygon(QPolygonF([QPointF(10, 6.5), QPointF(26, 16), QPointF(10, 25.5)]))

# Anlam -> simge (renk anlamla birlikte gelir; dört uygulamada aynı tablo)
_MENU_DRAWERS = {
    "settings": _mi_gear,       # mor dişli
    "info": _mi_info,           # mavi (vurgu) rozet
    "update": _mi_update,       # zümrüt yeşili oklar
    "exit": _mi_exit,           # kırmızı kapı
    "view": _mi_view,           # çivit göz (Göster/Gizle, önizleme)
    "globe": _mi_globe,         # vurgu küre (dil)
    "file": _mi_document,       # mavi (vurgu) belge
    "folder": _mi_folder,       # amber klasör (klasörde göster / klasörü aç)
    "folder_add": _mi_folder_add,
    "file_add": _mi_file_add,
    "add": _mi_add,             # yeşil artı (yeni …)
    "copy": _mi_copy,           # vurgu kopya
    "trash": _mi_trash,         # kırmızı çöp
    "open_with": _mi_open_with,  # mor dışarı aç
    "rename": _mi_rename,       # amber kalem (yaz/düzenle)
    "guide": _mi_guide,         # çivit kitap
    "bolt": _mi_bolt,           # sarı şimşek
    "backup": _mi_backup,       # amber arşiv
    "trim": _mi_trim,           # yeşil makas
    "adjust": _mi_adjust,       # turuncu kaydırıcılar
    "send": _mi_send,           # camgöbeği-yeşil uçak (aktarım)
    "star": _mi_star,           # sarı yıldız
    "network": _mi_network,     # camgöbeği düğümler
    "pause": _mi_pause,         # amber çubuklar (duraklat)
    "play": _mi_play,           # yeşil üçgen (sürdür / oynat)
}
MENU_ICON_NAMES = frozenset(_MENU_DRAWERS)
_MENU_ICON_CACHE: dict[str, QIcon] = {}


def menu_icon(name: str) -> QIcon:
    """Menü satırı / ayarlar sekmesi için renkli simge (önbellekli; QApplication kurulduktan sonra çağrılmalı)."""
    key = f"{name}|{_menu_accent('accent')}"  # vurgu değişince "blue"/"sky" ailesi yeniden çizilir
    icon = _MENU_ICON_CACHE.get(key)
    if icon is None:
        icon = _mi_icon(_MENU_DRAWERS[name])
        _MENU_ICON_CACHE[key] = icon
    return icon
