"""Ana pencerenin boyutu / konumu / tam ekran (büyütülmüş) durumu: açılışlar arasında hatırlanır.

Ayarlarda `window_geometry` = {"x", "y", "w", "h", "maximized"} olarak durur (dışa aktarmaya girmez). Geri
yüklerken pencere görünür bir ekrana sığdırılır: ekran sökülmüş / çözünürlük küçülmüşse pencere ekran dışında
ya da ekrandan büyük açılmaz.
"""

from __future__ import annotations

from typing import Any, Iterable

from PyQt6.QtCore import QRect

SETTINGS_KEY = "window_geometry"
MIN_VISIBLE = 120  # pencerenin (başlık çubuğuyla) en az bu kadarı bir ekranda kalmalı


def geometry_to_dict(rect: QRect, maximized: bool) -> dict:
    return {"x": int(rect.x()), "y": int(rect.y()), "w": int(rect.width()), "h": int(rect.height()),
            "maximized": bool(maximized)}


def geometry_from_dict(raw: Any) -> tuple[QRect, bool] | None:
    """Kayıtlı değer geçerliyse (dikdörtgen, büyütülmüş mü); bozuk / eksikse None."""
    if not isinstance(raw, dict):
        return None
    try:
        x, y, w, h = (int(raw[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return None
    if w <= 0 or h <= 0 or w > 100_000 or h > 100_000:
        return None
    return QRect(x, y, w, h), bool(raw.get("maximized", False))


def clamp_to_screens(rect: QRect, screens: Iterable[QRect], minimum: tuple[int, int] = (0, 0)) -> QRect:
    """`rect`i görünür bir ekrana sığdırır.

    screens: ekranların kullanılabilir alanları (görev çubuğu hariç); ilki birincil ekran sayılır.
    - Pencere en çok kesiştiği ekrana alınır; hiçbiriyle (yeterince) kesişmiyorsa birincil ekranın ortasına.
    - Ekrandan büyükse ekran kadar küçültülür (ama `minimum`un altına inmez).
    - Sol üst köşe (başlık çubuğu) daima ekranın içinde kalır.
    """
    areas = [QRect(s) for s in screens if s is not None and s.isValid()]
    if not areas:
        return QRect(rect)
    best, best_area = None, 0
    for area in areas:
        overlap = area.intersected(rect)
        size = overlap.width() * overlap.height() if overlap.isValid() else 0
        if size > best_area:
            best, best_area = area, size
    centered = False
    if best is None or best_area < MIN_VISIBLE * MIN_VISIBLE // 2:
        best, centered = areas[0], True
    min_w, min_h = minimum
    w = max(min(rect.width(), best.width()), min(min_w, best.width()))
    h = max(min(rect.height(), best.height()), min(min_h, best.height()))
    if centered:
        x = best.x() + (best.width() - w) // 2
        y = best.y() + (best.height() - h) // 2
    else:
        x = max(best.left(), min(rect.x(), best.right() - w + 1))
        y = max(best.top(), min(rect.y(), best.bottom() - h + 1))
    return QRect(x, y, w, h)
