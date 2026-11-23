"""Responsive gruplanmış liste — website tarzı çok sütunlu ızgara."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QPalette, QPen, QPixmap, QTransform
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QPushButton,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from src.gui.command_icons import GlyphLabel
from src.utils.helpers import format_shortcut_for_display

CARD_MAX_WIDTH = 620
CARD_MIN_WIDTH = 300  # en dar kart: iki sütun bununla sığıyorsa liste tek sütuna düşmez
CARD_COMFORT_WIDTH = 340  # sütun sayısı buna göre belirlenir: üçüncü sütun ancak kartlar rahat sığarsa
CARD_MIN_TEXT = 110  # kısayol çipi uzasa bile metin sütununa kalması gereken en az genişlik
KBD_MIN = 76  # kısayol / tetikleyici çipinin en dar hâli (kenarlık + iç boşluk dahil)
KBD_PAD = 24  # çipin yazı dışındaki payı: 9 px iç boşluk + 1 px kenarlık her yanda, 4 px pay
CARD_GLYPH = 14  # tür / komut simgesi (emoji yerine çizim; rengi yanındaki yazıdan gelir)
CARD_GLYPH_GAP = 5
GRID_GAP = 8
DRAG_TILT = 2.5  # sürüklenen kart Trello'daki gibi hafif eğik durur (derece)
DRAG_SCROLL_EDGE = 40  # imleç listenin üst/alt kenarına bu kadar yaklaşınca liste kendiliğinden kayar
FLASH_MS = 650  # yeni eklenen kartın kısa süre vurgulu kalması
LAND_MS = 180  # bırakılan kartın kopyası yerine kayarak iner


def _animations_enabled() -> bool:
    from src.gui.smooth_progress import _system_animations_enabled
    return _system_animations_enabled()


def _elide_metrics(label: QLabel, text: str) -> str:
    text = (text or "").replace("\r", "").replace("\n", " ").strip()
    if not text:
        return ""
    metrics = QFontMetrics(label.font())
    # İçerik alanı: stil sayfasının iç boşluğu / kenarlığı düşülmüş genişlik (çipte 9 px + 1 px her yanda).
    width = max(40, label.contentsRect().width())
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, width)


def _transparent(widget: QWidget):
    widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)


def _empty_pixmap(kind: str, color: QColor, size: int = 52) -> QPixmap:
    """Bos liste simgesi: klavye (kisayollar) ya da metin belgesi (genisletmeler); verilen renkte cizilir."""
    scale = 2
    pix = QPixmap(size * scale, size * scale)
    pix.setDevicePixelRatio(scale)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = float(size)
    pen = QPen(color, 2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "text":
        painter.drawRoundedRect(QRectF(s * 0.2, s * 0.12, s * 0.6, s * 0.76), 6, 6)
        for y, end in ((0.34, 0.68), (0.5, 0.68), (0.66, 0.54)):
            painter.drawLine(QPointF(s * 0.32, s * y), QPointF(s * end, s * y))
    else:
        painter.drawRoundedRect(QRectF(s * 0.08, s * 0.24, s * 0.84, s * 0.52), 7, 7)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        key_w, key_h, gap = s * 0.1, s * 0.07, s * 0.035
        for row, y in enumerate((0.35, 0.47)):
            for i in range(5):
                painter.drawRoundedRect(QRectF(s * 0.17 + i * (key_w + gap), s * y, key_w, key_h), 1.5, 1.5)
        painter.drawRoundedRect(QRectF(s * 0.27, s * 0.59, s * 0.46, key_h), 1.5, 1.5)
    painter.end()
    return pix


class _BaseCard(QFrame):
    clicked = pyqtSignal()
    double_clicked = pyqtSignal()
    KBD_CAP = 220  # çipin en geniş hâli; "Ctrl + Alt + Shift + Backspace" gibi kısayollar sığar

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("list_row")
        self.setProperty("selected", False)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.item_index = -1
        self.setMinimumHeight(60)
        self.setMaximumWidth(CARD_MAX_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._primary_full = ""
        self._secondary_full = ""
        self._kbd_full = ""
        self._kbd_column = 0  # listenin verdiği ortak çip genişliği (0: henüz verilmedi)

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 12, 8)  # yan cubuk kartin kenarina yapismasin: ustten/alttan pay
        root.setSpacing(10)

        self.accent_bar = QFrame()
        self.accent_bar.setObjectName("row_accent")
        self.accent_bar.setFixedWidth(4)
        root.addWidget(self.accent_bar)
        _transparent(self.accent_bar)

        self.status_dot = QFrame()
        self.status_dot.setObjectName("status_dot")
        self.status_dot.setFixedSize(8, 8)
        root.addWidget(self.status_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        _transparent(self.status_dot)

        self.kbd_label = QLabel()
        self.kbd_label.setObjectName("card_kbd")
        self.kbd_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Listedeki bütün çipler aynı genişlikte (liste belirler, set_kbd_column): metin sütunları hizalı başlar.
        # Uzun çip "…" ile kısalır, tam hâli kartın ipucunda.
        self.kbd_label.setMinimumWidth(KBD_MIN)
        self.kbd_label.setMaximumWidth(self.KBD_CAP)
        self.kbd_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        root.addWidget(self.kbd_label, 0, Qt.AlignmentFlag.AlignVCenter)
        _transparent(self.kbd_label)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self.primary_label = QLabel()
        self.primary_label.setObjectName("card_primary")
        self.primary_label.setWordWrap(False)
        self.primary_label.setMinimumWidth(CARD_MIN_TEXT)
        self.primary_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.primary_icon = GlyphLabel("", CARD_GLYPH)
        self.primary_icon.setObjectName("card_primary_icon")
        self.primary_icon.setVisible(False)
        text_col.addLayout(self._icon_row(self.primary_icon, self.primary_label))
        _transparent(self.primary_label)

        self.secondary_label = QLabel()
        self.secondary_label.setObjectName("card_secondary")
        self.secondary_label.setWordWrap(False)
        self.secondary_label.setMinimumWidth(0)
        self.secondary_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.secondary_icon = GlyphLabel("", CARD_GLYPH)
        self.secondary_icon.setObjectName("card_secondary_icon")
        self.secondary_icon.setVisible(False)
        text_col.addLayout(self._icon_row(self.secondary_icon, self.secondary_label))
        _transparent(self.secondary_label)

        root.addLayout(text_col, 1)

        self.badge_label = QLabel("HTML")
        self.badge_label.setObjectName("card_badge")
        self.badge_label.setVisible(False)
        root.addWidget(self.badge_label, 0, Qt.AlignmentFlag.AlignVCenter)
        _transparent(self.badge_label)

        # Durum hapi (Aktif / Pasif): renk noktasina ek olarak yaziyla da soylenir
        self.state_label = QLabel("")
        self.state_label.setObjectName("card_state")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setVisible(False)
        root.addWidget(self.state_label, 0, Qt.AlignmentFlag.AlignVCenter)
        _transparent(self.state_label)
        self._has_state = False
        self._pill_allowed = True  # liste karar verir: hap ya bütün kartlarda görünür ya hiçbirinde

    @staticmethod
    def _icon_row(icon: GlyphLabel, label: QLabel) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(CARD_GLYPH_GAP)
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(label, 1)
        return row

    def _set_glyphs(self, primary: str, secondary: str):
        self.primary_icon.set_glyph(primary)
        self.secondary_icon.set_glyph(secondary if self._secondary_full else "")

    def natural_kbd_width(self) -> int:
        """Çipin tam yazısı için gereken genişlik (KBD_MIN..KBD_CAP)."""
        text = " ".join((self._kbd_full or self.kbd_label.text()).split())
        hint = QFontMetrics(self.kbd_label.font()).horizontalAdvance(text) + KBD_PAD
        return min(self.KBD_CAP, max(KBD_MIN, hint))

    def set_kbd_column(self, width: int):
        """Listenin ortak çip genişliği: kısa çip de bu genişlikte durur, uzun olan kısalır."""
        width = max(KBD_MIN, int(width))
        self._kbd_column = width
        if self.kbd_label.minimumWidth() == width == self.kbd_label.maximumWidth():
            return
        self.kbd_label.setFixedWidth(width)
        self._apply_elide()

    def base_width(self) -> int:
        """Çip dışındaki her şeyin (yan çubuk, nokta, en dar metin sütunu, rozet, boşluklar) kapladığı genişlik."""
        margins = self.layout().contentsMargins()
        text_w = CARD_MIN_TEXT
        if self.primary_icon.glyph() or self.secondary_icon.glyph():
            text_w += CARD_GLYPH + CARD_GLYPH_GAP
        widths = [4, 8, text_w]
        if self.badge_label.isVisibleTo(self):
            widths.append(self.badge_label.sizeHint().width())
        spacing = self.layout().spacing() * len(widths)  # + çipin kendi aralığı
        return margins.left() + margins.right() + sum(widths) + spacing

    def required_width(self) -> int:
        """Kısayol çipi tam, metin sütunu en az CARD_MIN_TEXT görünsün diye gereken genişlik.

        "Aktif / Pasif" hapı sayılmaz: yer yoksa gizlenir (durumu renkli nokta zaten gösterir)."""
        return self.base_width() + self.natural_kbd_width()

    def pill_fits(self, width: int) -> bool:
        """Bu genişlikte kısayol çipi (listenin ortak genişliğinde) ve metin sığdıktan sonra durum hapına yer kalır mı?"""
        kbd_w = self._kbd_column or self.natural_kbd_width()
        used = self.base_width() + kbd_w
        return width - used >= self.state_label.sizeHint().width() + self.layout().spacing()

    def search_text(self) -> str:
        """Süzgeç yalnızca kartta GÖRÜNEN yazıya bakar: gizli (parola) öğelerin değeri kartta zaten noktalarla
        durur, bu yüzden aranarak bulunamaz / tahmin edilemez."""
        return " ".join(p for p in (self._kbd_full, self._primary_full, self._secondary_full) if p).casefold()

    def set_flash(self, on: bool):
        """Yeni eklenen kartı kısa süre vurgular (QSS: QFrame#list_row[flash="true"])."""
        if bool(self.property("flash")) == on:
            return
        self.setProperty("flash", on)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _fit_state_pill(self):
        """Durum hapı yalnızca yer kalırsa görünür (durumu renkli nokta zaten gösterir)."""
        self.state_label.setVisible(self._has_state and self._pill_allowed and self.pill_fits(self.width()))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_state_pill()
        self._apply_elide()

    def _apply_elide(self):
        # Önce tam kısayolla yerleştir (genişleyen kartta çip yeniden uzayabilsin), sonra her etiketi kendi
        # GÜNCEL genişliğine göre kısalt; yoksa yerleşimden önceki eski genişlikle kısalırdı.
        if self._kbd_full:
            self.kbd_label.setText(self._kbd_full)
        if self.layout() is not None:
            self.layout().activate()
        if self._kbd_full:
            shown = _elide_metrics(self.kbd_label, self._kbd_full)
            self.kbd_label.setText(shown)
            self.setToolTip(self._kbd_full if shown != self._kbd_full else "")
        if self._primary_full:
            self.primary_label.setText(_elide_metrics(self.primary_label, self._primary_full))
        if self._secondary_full:
            self.secondary_label.setText(_elide_metrics(self.secondary_label, self._secondary_full))

    def set_selected(self, selected: bool):
        self.setProperty("selected", selected)
        self.accent_bar.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.accent_bar.style().unpolish(self.accent_bar)
        self.accent_bar.style().polish(self.accent_bar)
        self.update()

    def set_enabled_state(self, enabled: bool, state_text: str = ""):
        # Dikkat: "enabled" adli ozellik QWidget.enabled'i gercekten kapatir (pasif kartlar tiklanamaz olurdu)
        self.setProperty("cardEnabled", bool(enabled))
        self.style().unpolish(self)
        self.style().polish(self)
        for widget in (self.status_dot, self.state_label):
            widget.setProperty("active", bool(enabled))
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.state_label.setText(state_text)
        self._has_state = bool(state_text)
        self._fit_state_pill()


class HotkeyCard(_BaseCard):
    def set_data(self, shortcut: str, chip: str, detail: str, enabled: bool, is_rich: bool = False, state_text: str = "",
                 chip_glyph: str = "", detail_glyph: str = ""):
        self.set_enabled_state(enabled, state_text)
        self._kbd_full = format_shortcut_for_display(shortcut)
        self._primary_full = chip or self._kbd_full
        self._secondary_full = (detail or "").replace("\r", "").replace("\n", " ").strip()
        self._set_glyphs(chip_glyph, detail_glyph)
        kbd_font = QFont("Segoe UI")
        kbd_font.setPointSize(9)
        kbd_font.setWeight(QFont.Weight.DemiBold)
        self.kbd_label.setFont(kbd_font)
        self.kbd_label.setText(self._kbd_full)
        self.primary_label.setText(self._primary_full)
        self.secondary_label.setText(self._secondary_full)
        self.secondary_label.setVisible(bool(self._secondary_full))
        self.badge_label.setVisible(bool(is_rich))
        self._apply_elide()


class ExpansionCard(_BaseCard):
    KBD_CAP = 130  # tetikleyici serbest metin: çok uzun olan bütün sütunu genişletmesin, "…" ile kısalır
    def set_data(self, trigger: str, chip: str, detail: str, enabled: bool, is_rich: bool = False, state_text: str = "",
                 chip_glyph: str = "", detail_glyph: str = ""):
        self.set_enabled_state(enabled, state_text)
        self._kbd_full = trigger or ""
        self._primary_full = chip or trigger or ""
        self._secondary_full = (detail or "").replace("\r", "").replace("\n", " ").strip()
        self._set_glyphs(chip_glyph, detail_glyph)
        kbd_font = QFont("Segoe UI")
        kbd_font.setPointSize(9)
        kbd_font.setWeight(QFont.Weight.DemiBold)
        self.kbd_label.setFont(kbd_font)
        self.kbd_label.setText(self._kbd_full)
        self.primary_label.setText(self._primary_full)
        self.secondary_label.setText(self._secondary_full)
        self.secondary_label.setVisible(bool(self._secondary_full))
        self.badge_label.setVisible(bool(is_rich))
        self._apply_elide()


class EmptyListPlaceholder(QFrame):
    """Bos liste: simge + baslik + aciklama + (varsa) eylem dugmesi. Mesajin ilk cumlesi baslik olur."""

    def __init__(self, message: str, parent=None, action_text: str = "", action=None, kind: str = "keyboard"):
        super().__init__(parent)
        self.setObjectName("list_empty")
        self.setMinimumWidth(420)  # dar kalirsa baslik satirlara bolunuyordu
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 28, 24, 20)
        layout.setSpacing(10)
        # NOT: layout.setAlignment(...) kullanma — sarmalı etiketlerin heightForWidth'ini bozar, başlığın ikinci satırı kırpılır.
        # Etiketler tam genişlikte kalır (metin kendi içinde ortalanır); yalnızca simge ve düğme ortalanır.

        title_text, _sep, hint_text = (message or "").partition(". ")
        if not hint_text:
            title_text, hint_text = message or "", ""

        icon = QLabel()
        icon.setObjectName("hint_label")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.ensurePolished()  # QSS rengi palete islensin
        icon.setPixmap(_empty_pixmap(kind, icon.palette().color(QPalette.ColorRole.WindowText)))
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)

        title = QLabel(title_text.strip().rstrip("."))
        title.setObjectName("empty_title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        layout.addWidget(title)

        if hint_text:
            hint = QLabel(hint_text.strip())
            hint.setObjectName("hint_label")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setWordWrap(True)
            layout.addWidget(hint)

        if action_text and action is not None:
            button = QPushButton(action_text)
            button.setProperty("class", "primary")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumWidth(170)
            button.clicked.connect(lambda *_: action())
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            self.action_button = button


class NoResultsPlaceholder(QFrame):
    """Süzgeçle hiçbir kart eşleşmediğinde: başlık + nasıl temizleneceği."""

    def __init__(self, title: str, hint: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("list_empty")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 28, 24, 20)
        layout.setSpacing(6)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("empty_title")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("hint_label")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setWordWrap(True)
        self.hint_label.setVisible(bool(hint))
        layout.addWidget(self.hint_label)


class CardListWidget(QScrollArea):
    """Pencere genişliğine göre kartları yan yana dizer (max genişlik sınırlı).

    Kartlar sürüklenerek sıralanır (Trello gibi): tutulan kart imleçle birlikte süzülür, bırakılacağı yerde boş bir
    yuva açılır ve öteki kartlar canlı kayar. Bırakınca `reordered(eski, yeni)`; Esc sürüklemeyi geri alır."""

    activated = pyqtSignal(int)
    selection_changed = pyqtSignal(int)
    reordered = pyqtSignal(int, int)
    delete_requested = pyqtSignal(int)  # Delete tuşu (seçili kart)
    context_menu_requested = pyqtSignal(int, QPoint)  # sağ tık / Menü tuşu / Shift+F10: kart sırası, menünün global yeri

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card_grid")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self._panel = QFrame()
        self._panel.setObjectName("list_panel")
        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        self._container = QWidget()
        self._container.setObjectName("card_grid_inner")
        self._grid = QGridLayout(self._container)
        self._grid.setContentsMargins(8, 8, 8, 8)
        self._grid.setHorizontalSpacing(GRID_GAP)
        self._grid.setVerticalSpacing(GRID_GAP)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        panel_layout.addWidget(self._container)
        panel_layout.addStretch(1)
        self.setWidget(self._panel)

        self._cards: list[_BaseCard] = []
        self._selected_index = -1
        self._columns = 1
        self._empty_widget: QWidget | None = None
        self._filter = ""  # casefold edilmiş süzgeç metni ("" = süzgeç yok)
        self._no_results_texts = ("", "")
        self._no_results: NoResultsPlaceholder | None = None
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._end_flash)
        self._flashing: _BaseCard | None = None

        self._press: tuple[_BaseCard, QPoint] | None = None  # sol tuşla basılan kart ve basılan yer (global)
        self._drag: dict | None = None
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(30)
        self._scroll_timer.timeout.connect(self._drag_auto_scroll)

    def _inner_width(self) -> int:
        width = self.viewport().width() if self.viewport() else self.width()
        return max(180, width - 20)

    def _preferred_card_width(self) -> int:
        """Rahat kart genişliği: en uzun kısayolun tam göründüğü genişlik (en az CARD_COMFORT_WIDTH)."""
        need = max((card.required_width() for card in self._cards), default=0)
        return max(CARD_COMFORT_WIDTH, min(CARD_MAX_WIDTH, need))

    def _column_count(self) -> int:
        inner = self._inner_width()
        cols = (inner + GRID_GAP) // (self._preferred_card_width() + GRID_GAP)
        # Dar pencere ya da tek bir uzun kısayol listeyi tek sütuna düşürmesin: iki dar kart sığıyorsa iki sütun
        # (uzun kısayolun çipi o zaman "…" ile kısalır, tam hâli kartın ipucunda).
        if cols < 2 and inner >= 2 * CARD_MIN_WIDTH + GRID_GAP:
            cols = 2
        return max(1, min(8, cols))

    def _card_width(self) -> int:
        inner = self._inner_width()
        cols = self._column_count()
        available = (inner - GRID_GAP * (cols - 1)) // cols
        return max(CARD_MIN_WIDTH, min(CARD_MAX_WIDTH, available))

    def kbd_column_width(self, card_width: int) -> int:
        """Bütün çiplerin ortak genişliği: en uzun çipin tam hâli (kart türünün sınırına kadar), metin sütununa
        CARD_MIN_TEXT kalacak kadar. Böylece "Ctrl + M" ile "Ctrl + Shift + 1" kartlarının yazıları aynı yerden başlar."""
        if not self._cards:
            return KBD_MIN
        natural = max(card.natural_kbd_width() for card in self._cards)
        room = card_width - max(card.base_width() for card in self._cards)
        return max(KBD_MIN, min(natural, room))

    def _apply_card_sizes(self):
        width = self._card_width()
        column = self.kbd_column_width(width)
        for card in self._cards:
            card.set_kbd_column(column)
        # Hap bazı kartlarda görünüp bazılarında görünmesin: ya hepsine sığar ya hiçbirinde gösterilmez.
        allowed = all(card.pill_fits(width) for card in self._cards if card._has_state)
        for card in self._cards:
            card._pill_allowed = allowed
            card.setFixedWidth(width)
            card._fit_state_pill()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cols = self._column_count()
        if cols != self._columns and self._cards:
            self._columns = cols
            self._relayout()
        else:
            self._apply_card_sizes()

    def currentRow(self) -> int:
        return self.selected_index()

    def selected_index(self) -> int:
        if 0 <= self._selected_index < len(self._cards):
            # Süzgeçle gizlenmiş kart "seçili" sayılmaz: görünmeyen öge düzenlenemez / silinemez.
            if self._filter and self._filter not in self._cards[self._selected_index].search_text():
                return -1
            return self._selected_index
        return -1

    def setCurrentRow(self, row: int):
        if 0 <= row < len(self._cards):
            self._select_index(row)

    def count(self) -> int:
        return len(self._cards)

    def card_at(self, index: int):
        return self._cards[index] if 0 <= index < len(self._cards) else None

    # ------------------------------------------------------------------ süzgeç
    def _visible_cards(self) -> list[_BaseCard]:
        if not self._filter:
            return list(self._cards)
        return [c for c in self._cards if self._filter in c.search_text()]

    def visible_indices(self) -> list[int]:
        """Süzgeçten geçen kartların (ayarlardaki) sıra numaraları."""
        visible = set(map(id, self._visible_cards()))
        return [i for i, c in enumerate(self._cards) if id(c) in visible]

    def filter_text(self) -> str:
        return self._filter

    def set_filter(self, text: str, no_results_title: str = "", no_results_hint: str = ""):
        """Kartları görünen yazılarına göre süzer (büyük/küçük harf duyarsız). Boş metin süzgeci kaldırır.

        Eşleşen yoksa "sonuç yok" yer tutucusu gösterilir; seçili kart elendiyse seçim ilk eşleşene geçer."""
        self._no_results_texts = (no_results_title, no_results_hint)
        text = (text or "").strip().casefold()
        if text == self._filter:
            self._update_no_results()
            return
        self._filter = text
        if not self._cards:
            return  # boş liste: "henüz öğe yok" yazısı kalır
        self._relayout()
        visible = self.visible_indices()
        if visible and self._selected_index not in visible:
            self._select_index(visible[0])

    def _update_no_results(self):
        """Süzgeç bütün kartları eliyorsa "sonuç yok" yazısı ızgarada durur."""
        show = bool(self._filter) and bool(self._cards) and not self.visible_indices()
        if not show:
            if self._no_results is not None:
                self._grid.removeWidget(self._no_results)
                self._no_results.hide()
                self._no_results.setParent(None)
                self._no_results.deleteLater()
                self._no_results = None
                self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            return
        title, hint = self._no_results_texts
        if self._no_results is None:
            self._no_results = NoResultsPlaceholder(title, hint)
            self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)
            self._grid.addWidget(self._no_results, 0, 0, 1, 8)
        else:
            self._no_results.title_label.setText(title)
            self._no_results.hint_label.setText(hint)
            self._no_results.hint_label.setVisible(bool(hint))

    def is_showing_no_results(self) -> bool:
        return self._no_results is not None

    # ------------------------------------------------------------------ klavye
    def keyPressEvent(self, event):  # noqa: N802
        """Oklar seçimi taşır (ızgarada sağ/sol bir kart, yukarı/aşağı bir satır), Home/End uçlara gider,
        Enter düzenler (activated), Delete siler (delete_requested). Boşluk ana pencereye kalır (aktif/pasif)."""
        key = event.key()
        visible = self.visible_indices()
        if key == Qt.Key.Key_F10 and event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            self._keyboard_context_menu()  # Shift+F10: Menü tuşunun klavye karşılığı
            event.accept()
            return
        if not visible or event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            super().keyPressEvent(event)
            return
        current = self._selected_index if self._selected_index in visible else -1
        pos = visible.index(current) if current >= 0 else -1
        cols = max(1, self._columns)
        steps = {
            Qt.Key.Key_Right: 1, Qt.Key.Key_Left: -1,
            Qt.Key.Key_Down: cols, Qt.Key.Key_Up: -cols,
        }
        if key in steps:
            if pos < 0:
                target = 0
            else:
                target = pos + steps[key]
                if not 0 <= target < len(visible):
                    target = pos  # kenarda: yerinde kal
            self._keyboard_select(visible[target])
        elif key == Qt.Key.Key_Home:
            self._keyboard_select(visible[0])
        elif key == Qt.Key.Key_End:
            self._keyboard_select(visible[-1])
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if current >= 0:
                self.activated.emit(current)
        elif key == Qt.Key.Key_Delete:
            if current >= 0:
                self.delete_requested.emit(current)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def _keyboard_select(self, index: int):
        if index != self._selected_index:
            self._select_index(index)
        self.scroll_to(index)

    # ------------------------------------------------------------------ sağ tık menüsü
    def contextMenuEvent(self, event):  # noqa: N802
        """Menü tuşu seçili kartın menüsünü açar; kartların dışındaki boşlukta sağ tık bir şey açmaz."""
        if event.reason() == event.Reason.Keyboard:
            self._keyboard_context_menu()
            event.accept()
            return
        event.ignore()

    def _keyboard_context_menu(self) -> bool:
        index = self.selected_index()
        if index < 0 or self._drag:
            return False
        card = self._cards[index]
        self.scroll_to(index)
        # menü kartın sol üstüne yakın açılır (fare yerine): klavyeyle de neyin menüsü olduğu belli olsun
        self.context_menu_requested.emit(index, card.mapToGlobal(QPoint(12, min(card.height(), 24))))
        return True

    def _card_context_menu(self, card: _BaseCard, global_pos: QPoint):
        """Sağ tık: liste alışkanlığı gibi altta kalan kart seçilir (zaten seçiliyse seçim değişmez), sonra menü."""
        if self._drag:
            return
        index = self._cards.index(card)
        self._press = None
        if index != self._selected_index:
            self._select_index(index)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.context_menu_requested.emit(index, global_pos)

    def scroll_to(self, index: int):
        """Kartı görünür alana kaydırır (yerleşim bitmemişse bir olay turu sonra yine)."""
        if not 0 <= index < len(self._cards):
            return
        card = self._cards[index]
        self._grid.activate()
        self.ensureWidgetVisible(card, 0, GRID_GAP)
        QTimer.singleShot(0, lambda c=card: self._ensure_visible_later(c))

    def _ensure_visible_later(self, card: _BaseCard):
        try:
            if card in self._cards and card.isVisibleTo(self):
                self.ensureWidgetVisible(card, 0, GRID_GAP)
        except RuntimeError:
            pass

    # ------------------------------------------------------------------ yeni kart vurgusu
    def flash_row(self, index: int):
        """Kartı seçer, görünür alana kaydırır ve kısa süre vurgular (yeni eklenen / geri alınan öğe)."""
        if not 0 <= index < len(self._cards):
            return
        self._select_index(index)
        self.scroll_to(index)
        self._end_flash()
        card = self._cards[index]
        card.set_flash(True)
        self._flashing = card
        self._flash_timer.start(FLASH_MS)

    def flashing_card(self):
        return self._flashing

    def _end_flash(self):
        card, self._flashing = self._flashing, None
        self._flash_timer.stop()
        if card is not None:
            try:
                card.set_flash(False)
            except RuntimeError:
                pass

    def clear_cards(self):
        self._drag_finish(cancel=True, notify=False)  # liste yenilenirken sürükleme yarıda kalmasın
        self._press = None
        self._end_flash()
        if self._no_results is not None:
            self._no_results.hide()
            self._no_results.setParent(None)
            self._no_results.deleteLater()
            self._no_results = None
        self._cards.clear()
        self._selected_index = -1
        self._empty_widget = None
        # cards sit top-left at their own size; show_empty() widens the grid again for its message
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # önce gizle: ızgara bekleyen bir "göster" sıraya koymuş olabilir, ebeveynsiz kart ayrı pencere açılırdı
                widget.hide()
                widget.setParent(None)

    def _select_index(self, index: int):
        if index < 0 or index >= len(self._cards):
            return
        self._selected_index = index
        for i, card in enumerate(self._cards):
            card.set_selected(i == index)
        self.selection_changed.emit(index)

    def _on_card_clicked(self, index: int):
        self._select_index(index)
        self.setFocus(Qt.FocusReason.MouseFocusReason)

    def _on_card_double_clicked(self, index: int):
        self._select_index(index)
        self.activated.emit(index)

    def _relayout(self):
        for i in reversed(range(self._grid.count())):
            item = self._grid.takeAt(i)
            widget = item.widget()
            if widget is not None and widget not in self._cards and not (self._drag and widget is self._drag["slot"]) \
                    and widget is not self._no_results:
                widget.hide()
                widget.setParent(None)
        cols = max(1, self._columns)
        for c in range(8):
            self._grid.setColumnStretch(c, 0)
            self._grid.setColumnMinimumWidth(c, 0)
        self._apply_card_sizes()
        if self._drag:
            self._drag_layout()
            return
        visible = self._visible_cards()
        shown = set(map(id, visible))
        for card in self._cards:
            if id(card) not in shown:
                card.hide()  # süzgeçte elendi: ızgaradan çıktı, gizli bekler
        for i, card in enumerate(visible):
            row, col = divmod(i, cols)
            self._grid.addWidget(card, row, col)
            card.show()
        self._update_no_results()

    def add_card(self, card: _BaseCard) -> int:
        index = len(self._cards)
        card.item_index = index
        # sıra sürükleyerek değişebilir: kartın yeri tıklandığı an bulunur
        card.clicked.connect(lambda c=card: self._on_card_clicked(self._cards.index(c)))
        card.double_clicked.connect(lambda c=card: self._on_card_double_clicked(self._cards.index(c)))
        card.installEventFilter(self)
        self._cards.append(card)
        self._columns = self._column_count()
        self._apply_card_sizes()
        row, col = divmod(index, max(1, self._columns))
        self._grid.addWidget(card, row, col)
        return index

    def set_cards(self, cards: list[_BaseCard], select_row: int = 0):
        self.clear_cards()
        self._columns = self._column_count()
        for c in range(8):
            self._grid.setColumnStretch(c, 0)
        for card in cards:
            self.add_card(card)
        if self._filter and cards:
            self._relayout()  # süzgeç açıkken yenilenen liste de süzülmüş gelsin
        if cards:
            row = min(max(select_row, 0), len(cards) - 1)
            visible = self.visible_indices()
            if visible and row not in visible:
                row = visible[0]
            self._select_index(row)
        else:
            self._selected_index = -1

    def show_empty(self, message: str, action_text: str = "", action=None, kind: str = "keyboard"):
        self.clear_cards()
        # a left-aligned grid gave the word-wrapped message only its narrowest width, so it was cut off
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._empty_widget = EmptyListPlaceholder(message, action_text=action_text, action=action, kind=kind)
        self._grid.addWidget(self._empty_widget, 0, 0, 1, 8)
        self._grid.setColumnStretch(0, 1)

    # ------------------------------------------------------------------ sürükleyerek sıralama
    def eventFilter(self, watched, event):
        et = event.type()
        drag = getattr(self, "_drag", None)  # QScrollArea, __init__ bitmeden de buraya uğrar
        if drag and watched is drag["float"]:
            # sürükleme süresince fare ve klavye süzülen kartta (grab): bırakma ve Esc buraya gelir
            if et == QEvent.Type.MouseMove:
                if event.buttons() & Qt.MouseButton.LeftButton:
                    self._drag_move(event.globalPosition().toPoint())
                else:
                    self._drag_finish()  # bırakma kaçırıldıysa (ör. pencere değişti) kart takılı kalmasın
                return True
            if et == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self._drag_finish()
                return True
            if et == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                self._drag_finish(cancel=True)
                return True
            if et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick, QEvent.Type.KeyPress):
                return True
        elif isinstance(watched, _BaseCard) and watched in getattr(self, "_cards", ()):
            if et == QEvent.Type.ContextMenu:
                if event.reason() == event.Reason.Keyboard:
                    self._keyboard_context_menu()
                else:
                    self._card_context_menu(watched, event.globalPos())
                event.accept()
                return True
            if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._press = (watched, event.globalPosition().toPoint())
            elif et == QEvent.Type.MouseButtonRelease:
                self._press = None
            elif et == QEvent.Type.MouseMove and self._press and event.buttons() & Qt.MouseButton.LeftButton:
                pos = event.globalPosition().toPoint()
                card, start = self._press
                # süzgeç açıkken sıralama kapalı: görünen sıra ayarlardaki sıranın tamamı değildir
                if (pos - start).manhattanLength() >= QApplication.startDragDistance() and len(self._cards) > 1 \
                        and not self._filter:
                    self._press = None
                    self._drag_begin(card, start, pos)
                    return True
        return super().eventFilter(watched, event)

    def is_dragging(self) -> bool:
        return self._drag is not None

    def _drag_begin(self, card: _BaseCard, start: QPoint, pos: QPoint):
        index = self._cards.index(card)
        slot = QFrame()
        slot.setObjectName("card_drop_slot")
        slot.setFixedSize(card.size())

        # Süzülen kopya: kartın görüntüsü, hafif eğik ve gölgeli; tutulan nokta imlecin altında kalır.
        shot = card.grab()
        ratio = shot.devicePixelRatio() or 1.0
        tilted = shot.transformed(QTransform().rotate(DRAG_TILT), Qt.TransformationMode.SmoothTransformation)
        tilted.setDevicePixelRatio(ratio)
        size = tilted.deviceIndependentSize().toSize()
        floating = QLabel(self.window())  # listenin kenarında kesilmesin: pencerenin her yerinde üstte süzülür
        floating.setObjectName("card_drag_float")
        floating.setMouseTracking(True)  # düğmesiz hareket de gelsin: bırakma kaçırıldıysa anlaşılır
        floating.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        floating.setStyleSheet("background: transparent; border: none;")
        floating.setPixmap(tilted)
        floating.resize(size)
        shadow = QGraphicsDropShadowEffect(floating)
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 90))
        floating.setGraphicsEffect(shadow)
        grab_point = card.mapFromGlobal(start)
        pad = QPoint((size.width() - card.width()) // 2, (size.height() - card.height()) // 2)

        self._drag = {
            "card": card, "from": index, "to": index, "slot": slot, "float": floating,
            "grab": grab_point + pad, "center": QPoint(card.width() // 2, card.height() // 2) - grab_point,
        }
        card.hide()
        self._drag_layout()
        floating.show()
        floating.raise_()
        floating.installEventFilter(self)
        floating.grabMouse(QCursor(Qt.CursorShape.ClosedHandCursor))
        floating.grabKeyboard()
        self._scroll_timer.start()
        self._drag_move(pos)

    def _drag_layout(self):
        """Sürükleme sırasında ızgara: sürüklenen kartın yerinde boş yuva, öteki kartlar sırayla."""
        drag = self._drag
        items: list[QWidget] = [c for c in self._cards if c is not drag["card"]]
        items.insert(drag["to"], drag["slot"])
        while self._grid.count():
            self._grid.takeAt(0)
        cols = max(1, self._columns)
        drag["slot"].setFixedSize(drag["card"].width(), drag["card"].height())
        for i, widget in enumerate(items):
            row, col = divmod(i, cols)
            self._grid.addWidget(widget, row, col)
        drag["slot"].show()
        self._grid.activate()

    def _drop_index(self, center: QPoint) -> int:
        """Süzülen kartın ortasına en yakın yuva (yuvalar sıra numarasıyla sabit hücrelerdir)."""
        cols = max(1, self._columns)
        best, best_dist = self._drag["to"], None
        for i in range(len(self._cards)):
            rect = self._grid.cellRect(*divmod(i, cols))
            if not rect.isValid():
                continue
            dist = (rect.center() - center).manhattanLength()
            if best_dist is None or dist < best_dist:
                best, best_dist = i, dist
        return best

    def _drag_move(self, pos: QPoint):
        drag = self._drag
        if drag is None:
            return
        floating = drag["float"]
        floating.move(floating.parentWidget().mapFromGlobal(pos) - drag["grab"])
        target = self._drop_index(self._container.mapFromGlobal(pos) + drag["center"])
        if target != drag["to"]:
            drag["to"] = target
            self._drag_layout()

    def _drag_auto_scroll(self):
        if self._drag is None:
            self._scroll_timer.stop()
            return
        pos = QCursor.pos()
        y = self.viewport().mapFromGlobal(pos).y()
        height = self.viewport().height()
        if y < DRAG_SCROLL_EDGE:
            step = -max(2, (DRAG_SCROLL_EDGE - y) // 3)
        elif y > height - DRAG_SCROLL_EDGE:
            step = max(2, (y - height + DRAG_SCROLL_EDGE) // 3)
        else:
            return
        bar = self.verticalScrollBar()
        before = bar.value()
        bar.setValue(before + step)
        if bar.value() != before:
            self._drag_move(pos)

    def _drag_finish(self, cancel: bool = False, notify: bool = True):
        drag, self._drag = self._drag, None
        if drag is None:
            return
        self._scroll_timer.stop()
        floating = drag["float"]
        floating.removeEventFilter(self)
        floating.releaseMouse()
        floating.releaseKeyboard()
        land_from = floating.pos() if (notify and not cancel and floating.isVisible()) else None
        floating.hide()
        slot = drag["slot"]
        self._grid.removeWidget(slot)
        slot.hide()
        slot.setParent(None)
        slot.deleteLater()
        card = drag["card"]
        if not notify:
            floating.deleteLater()
            return  # liste zaten yeniden kuruluyor
        card.show()
        src, dst = drag["from"], (drag["from"] if cancel else drag["to"])
        if dst != src:
            self._cards.insert(dst, self._cards.pop(src))
            for i, c in enumerate(self._cards):
                c.item_index = i
        self._relayout()
        self._select_index(dst)
        self._land(floating, land_from, card)
        if dst != src:
            self.reordered.emit(src, dst)

    def _land(self, floating: QLabel, start: QPoint | None, card: _BaseCard):
        """Bırakılan kartın süzülen kopyası kartın yeni yerine kısa (LAND_MS) bir kaymayla iner, sonra silinir.
        Animasyonlar kapalıysa / pencere görünmüyorsa hemen silinir."""
        parent = floating.parentWidget()
        if start is None or parent is None or not parent.isVisible() or not _animations_enabled():
            floating.deleteLater()
            return
        self._grid.activate()
        size = floating.size()
        pad = QPoint((size.width() - card.width()) // 2, (size.height() - card.height()) // 2)
        target = card.mapTo(parent, QPoint(0, 0)) - pad
        floating.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        floating.move(start)
        floating.show()
        floating.raise_()
        anim = QPropertyAnimation(floating, b"pos", floating)
        anim.setDuration(LAND_MS)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.finished.connect(floating.deleteLater)
        anim.start()
