"""Araç çubuğu simgeleri: emoji yerine verilen renkte çizilen vektörler (tema renklerini izler)."""

from __future__ import annotations

import re

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

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
