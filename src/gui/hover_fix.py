"""Açılır menüden sonra düğmede takılı kalan üzerine gelme (hover) görünümünü temizler.

QMenu açıkken fareyi kendisi yakalar; düğme "fare ayrıldı" olayını hiç almaz. Menü dışarıya tıklanarak kapatılınca
düğme hâlâ fare üstündeymiş gibi :hover ile çizilir ve fare bir daha üstüne gelip gidene dek öyle kalır.
(Lumina'daki app/ui/hover_fix.py ile aynı çözüm.)
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QMenu, QWidget


def settle_hover(widget: QWidget | None) -> None:
    """Fare artık `widget`in üstünde değilse ona bir "ayrıldı" olayı gönderir ve yeniden çizer."""
    if widget is None:
        return
    try:
        inside = widget.isVisible() and widget.rect().contains(widget.mapFromGlobal(QCursor.pos()))
    except RuntimeError:  # pencere kapanırken widget silinmiş olabilir
        return
    if inside or not widget.testAttribute(Qt.WidgetAttribute.WA_UnderMouse):
        return
    widget.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, False)
    QApplication.sendEvent(widget, QEvent(QEvent.Type.Leave))
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def settle_hover_after_menu(button: QWidget, menu: QMenu) -> None:
    """`button.setMenu(menu)` ile açılan menüler için: menü her kapandığında (exec dönünce) düğmenin hover'ı düzeltilir.

    QPushButton menüyü kendi içinde `exec()` ile açtığından çağrının ardına kod eklenemez; menü gizlenirken bir
    sonraki olay turuna (exec döndükten sonra) settle_hover sıraya konur."""
    menu.aboutToHide.connect(lambda b=button: QTimer.singleShot(0, lambda: settle_hover(b)))
