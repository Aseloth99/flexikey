"""Pencere içi kısa geri bildirim ("toast"): alt ortada beliren küçük satır, isteğe bağlı tek eylem düğmesiyle.

Kaydet / sil / dışa aktar gibi uygulama içi işlemlerin sonucu burada söylenir (masaüstü bildirimleri varsayılan
kapalı olduğundan kullanıcı başka hiçbir geri bildirim görmüyordu). Eylem düğmesi örn. "Geri al" ya da "Klasörü aç".

- Renkleri tema stil sayfasından gelir (QFrame#toast, QLabel#toast_text, QPushButton#toast_action); tür (bilgi /
  başarı / hata) yalnızca sol şeridin rengini değiştirir ([kind="..."]).
- Görünme/kaybolma 180 ms'lik hafif bir saydamlık geçişidir; Windows'ta animasyonlar kapalıysa geçiş olmaz.
- Fare üstündeyken süre işlemez (okumaya / tıklamaya zaman kalır).
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, Qt, QTimer
from PyQt6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from src.gui.smooth_progress import _system_animations_enabled

FADE_MS = 180
DEFAULT_MS = 3000
ACTION_MS = 5000  # eylemli toast (Geri al): kullanıcının tıklamaya yetişeceği süre
MARGIN = 40  # pencerenin alt kenarından uzaklık (liste çerçevesinin içinde kalır)
MAX_WIDTH = 560


class Toast(QFrame):
    """`host` widget'ının üstünde süzülen tek satırlık bildirim. Aynı anda bir tane görünür; yenisi eskisinin yerini alır."""

    def __init__(self, host: QWidget):
        super().__init__(host)
        self.setObjectName("toast")
        self.setProperty("kind", "info")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._host = host
        self._action: Callable[[], None] | None = None
        self._duration = DEFAULT_MS
        self._text = ""

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 8, 8, 8)
        row.setSpacing(10)
        self.text_label = QLabel(self)
        self.text_label.setObjectName("toast_text")
        self.text_label.setTextFormat(Qt.TextFormat.PlainText)
        self.text_label.setWordWrap(False)
        row.addWidget(self.text_label, 1)
        self.action_button = QPushButton(self)
        self.action_button.setObjectName("toast_action")
        self.action_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # klavye odağı listede kalsın
        self.action_button.clicked.connect(self._on_action)
        self.action_button.hide()
        row.addWidget(self.action_button, 0)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(1.0)
        self._effect.setEnabled(False)  # yalnızca geçiş sırasında açık (açıkken metin yumuşak/bulanık çizilebilir)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(self._on_fade_finished)
        self._fading_out = False

        host.installEventFilter(self)
        self.hide()

    # ------------------------------------------------------------------ dış arayüz
    def show_message(self, text: str, kind: str = "info", action_text: str = "",
                     action: Callable[[], None] | None = None, duration_ms: int | None = None) -> None:
        self._action = action if action_text else None
        self._text = text
        self.text_label.setText(text)
        self.action_button.setText(action_text)
        self.action_button.setVisible(bool(action_text and action))
        if self.property("kind") != kind:
            self.setProperty("kind", kind)
            self.style().unpolish(self)
            self.style().polish(self)
        self._duration = duration_ms or (ACTION_MS if self._action else DEFAULT_MS)
        self._reposition()
        was_visible = self.isVisible() and not self._fading_out
        self._fade.stop()
        self._fading_out = False
        self.show()
        self.raise_()
        if not was_visible and self._animate():
            self._effect.setEnabled(True)
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
        else:
            self._effect.setEnabled(False)
            self._effect.setOpacity(1.0)
        self._timer.start(self._duration)

    def dismiss(self) -> None:
        """Toast'ı kapatır (eylemi unutur: süresi geçen "Geri al" artık çalışmaz)."""
        self._timer.stop()
        self._action = None
        if not self.isVisible():
            return
        if self._animate():
            self._fading_out = True
            self._effect.setEnabled(True)
            self._fade.stop()
            self._fade.setStartValue(self._effect.opacity() if self._effect.isEnabled() else 1.0)
            self._fade.setEndValue(0.0)
            self._fade.start()
        else:
            self.hide()

    def has_action(self) -> bool:
        return self._action is not None and self.isVisible()

    def trigger_action(self) -> bool:
        """Eylem düğmesine basılmış gibi (testler ve klavye kısayolu için). Eylem yoksa False."""
        if not self.has_action():
            return False
        self._on_action()
        return True

    # ------------------------------------------------------------------ iç işler
    def _animate(self) -> bool:
        return self._host.isVisible() and _system_animations_enabled()

    def _on_action(self) -> None:
        action, self._action = self._action, None
        self.dismiss()
        if action is not None:
            action()

    def _on_fade_finished(self) -> None:
        if self._fading_out:
            self._fading_out = False
            self.hide()
        self._effect.setEnabled(False)
        self._effect.setOpacity(1.0)

    def _reposition(self) -> None:
        host = self._host
        action_w = self.action_button.sizeHint().width() + 10 if self.action_button.isVisibleTo(self) else 0
        room = max(120, min(MAX_WIDTH, host.width() - 2 * MARGIN) - 32 - action_w)
        self.text_label.setMaximumWidth(room)
        metrics = self.text_label.fontMetrics()
        full = self._text
        if metrics.horizontalAdvance(full) > room:
            self.text_label.setToolTip(full)
            self.text_label.setText(metrics.elidedText(full, Qt.TextElideMode.ElideMiddle, room))
        else:
            self.text_label.setToolTip("")
            self.text_label.setText(full)
        self.adjustSize()
        width = min(self.sizeHint().width(), max(160, host.width() - 2 * MARGIN))
        height = self.sizeHint().height()
        self.resize(width, height)
        self.move((host.width() - width) // 2, host.height() - height - MARGIN)

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self._host and event.type() == QEvent.Type.Resize and self.isVisible():
            self._reposition()
        return super().eventFilter(watched, event)

    def enterEvent(self, event):  # noqa: N802
        self._timer.stop()  # fare üstündeyken kapanmasın
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        if self.isVisible() and not self._fading_out:
            self._timer.start(min(self._duration, 2000))
        super().leaveEvent(event)


def toast_for(host: QWidget) -> Toast:
    """`host` için tek Toast (ilk çağrıda oluşturulur)."""
    toast = getattr(host, "_flexikey_toast", None)
    if toast is None:
        toast = Toast(host)
        host._flexikey_toast = toast
    return toast
