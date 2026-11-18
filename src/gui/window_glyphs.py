"""Başlık çubuğu pencere düğmesi glifleri: büyüt (tek kare), geri yükle (iki kare) ve güncelleme oku (↑).

Metin glifleri ("□", "❐") yazı tipine göre farklı boyut ve kalınlıkta çıkıyordu; burada 32'lik ızgarada vektör olarak
çizilir (Lumina'daki `maximize_icon`/`restore_icon` ile aynı ölçüler) ve doğrudan paintEvent içinde boyandığından %100,
%125 ve %150 ölçekte keskin kalır. Ana pencerenin başlığı (`TitleGlyphButton`) ve içerik pencereleri
(`chrome_dialog._MaxButton`) aynı çizimi kullanır.
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QPushButton, QWidget

GRID = 32.0
# Glifin düğme içinde kapladığı kare (mantıksal piksel). 19.2 = 32 × 0.6: büyüt karesi 9 px olur (✕ ile aynı genişlik)
# ve tam sayı bir merkezde kenarları piksel ortasına düşer (%100 ölçekte bulanıklaşmaz).
GLYPH_BOX = 19.2

MAXIMIZE = "maximize"
RESTORE = "restore"
UPDATE = "update"

_MAX_RECT = QRectF(8.5, 8.5, 15, 15)
_FRONT_RECT = QRectF(8, 11.5, 12.5, 12.5)
_BACK_RECT = QRectF(11.5, 7.5, 12.5, 12.5)


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def draw_maximize(painter: QPainter, color: QColor) -> None:
    """Tek yuvarlatılmış kare (32 ızgarası; ressam önceden ölçeklenmiş olmalı)."""
    painter.setPen(_pen(color, 1.85))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(_MAX_RECT, 2.2, 2.2)


def draw_restore(painter: QPainter, color: QColor) -> None:
    """Üst üste iki kare: arkadaki yalnızca öndekinin örtmediği yerde çizilir (çizgiler kesişmez)."""
    pen = _pen(color, 1.7)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    front = QPainterPath()
    front.addRoundedRect(_FRONT_RECT, 1.8, 1.8)
    whole = QPainterPath()
    whole.addRect(QRectF(0, 0, GRID, GRID))
    painter.save()
    painter.setClipPath(whole.subtracted(front), Qt.ClipOperation.IntersectClip)
    painter.drawRoundedRect(_BACK_RECT, 1.8, 1.8)
    painter.restore()
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(_FRONT_RECT, 1.8, 1.8)


def draw_update_arrow(painter: QPainter, color: QColor) -> None:
    """Yukarı ok: gövde (16, 24)→(16, 9), uç (10.5, 14.5)→(16, 9)→(21.5, 14.5)."""
    painter.setPen(_pen(color, 2.1))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPointF(16, 24), QPointF(16, 9))
    head = QPainterPath(QPointF(10.5, 14.5))
    head.lineTo(QPointF(16, 9))
    head.lineTo(QPointF(21.5, 14.5))
    painter.drawPath(head)


_DRAW = {MAXIMIZE: draw_maximize, RESTORE: draw_restore, UPDATE: draw_update_arrow}


def _luminance(color: QColor) -> float:
    def channel(value: int) -> float:
        c = value / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(color.red()) + 0.7152 * channel(color.green()) + 0.0722 * channel(color.blue())


def contrast_ratio(a: str | QColor, b: str | QColor) -> float:
    """WCAG karşıtlık oranı (1..21)."""
    high, low = sorted((_luminance(QColor(a)), _luminance(QColor(b))), reverse=True)
    return (high + 0.05) / (low + 0.05)


def readable_accent(pal: dict, minimum: float = 3.0) -> QColor:
    """Başlık zemininde (`surface`) okunan vurgu rengi: önce vurgunun metin tonu (`accent_text`); koyu çivit, açık
    sarı/turuncu gibi zeminle yetersiz karşıtlıktaki vurgularda koyuda parlak ton (`accent_hi`), açıkta koyulaştırılmış
    ton kullanılır (simge karşıtlığı en az 3:1)."""
    background = QColor(pal["surface"])
    color = QColor(pal["accent_text"])
    if contrast_ratio(color, background) >= minimum:
        return color
    dark = bool(pal.get("is_dark"))
    if dark and pal.get("accent_hi") and contrast_ratio(pal["accent_hi"], background) >= minimum:
        return QColor(pal["accent_hi"])
    for _ in range(16):
        color = color.lighter(112) if dark else color.darker(112)
        if contrast_ratio(color, background) >= minimum:
            break
    return color


def paint_glyph(painter: QPainter, area: QRectF, glyph: str, color: QColor, box: float = GLYPH_BOX) -> None:
    """`glyph`i `area`nın ortasına `box` boyutlu kare olarak çizer (32 ızgarası ölçeklenir)."""
    draw = _DRAW.get(glyph)
    if draw is None:
        return
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(area.center().x() - box / 2.0, area.center().y() - box / 2.0)
    painter.scale(box / GRID, box / GRID)
    draw(painter, QColor(color))
    painter.restore()


class TitleGlyphButton(QPushButton):
    """Ana pencere başlığındaki metinsiz pencere düğmesi: zemin/üzerine gelme görünümü temanın QSS'inden
    (`window_control_btn`), glif vektör olarak çizilir. `ink(hot)` o anki rengi verir (hot: üzerinde/basılı)."""

    # Komşu "−" ve "×" metin glifleri yazı tipi ölçüsü yüzünden düğme zemininin ~2 px altında durur; vektör glif 1 px
    # aşağı alınarak satırda onlarla (ve 38 px başlığın ortasıyla) hizalanır, merkez tam sayı kalır (keskinlik).
    OPTICAL_DY = 1.0

    def __init__(self, glyph: str, ink: Callable[[bool], str | QColor], parent: QWidget | None = None):
        super().__init__("", parent)
        self._glyph = glyph
        self._ink = ink
        self.setObjectName("window_control_btn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def glyph(self) -> str:
        return self._glyph

    def set_glyph(self, glyph: str) -> None:
        if glyph != self._glyph:
            self._glyph = glyph
            self.update()

    def ink(self) -> QColor:
        return QColor(self._ink(self.underMouse() or self.isDown()))

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)  # QSS zemini (üzerine gelme / basılı)
        painter = QPainter(self)
        paint_glyph(painter, QRectF(self.rect()).translated(0, self.OPTICAL_DY), self._glyph, self.ink())
        painter.end()


__all__ = [
    "GLYPH_BOX", "GRID", "MAXIMIZE", "RESTORE", "UPDATE", "TitleGlyphButton", "contrast_ratio", "draw_maximize",
    "draw_restore", "draw_update_arrow", "paint_glyph", "readable_accent",
]
