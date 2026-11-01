"""Güncelleme penceresi: sürüm, indirme boyutu ve sürüm notları; "Şimdi Güncelle" ile ilerleme -> kuruluyor.

Hata olursa pencere AÇIK kalır: satır içi hata etiketi + "Tekrar dene" (açılır kutu yok). İndirme sürerken Esc/X
indirmeyi iptal edip pencereyi kapatır; kurulum geri alınamaz, o sırada kapatma yok sayılır.

Pencere çerçevesi: uygulamanın öbür pencereleri gibi özel üst çubuklu (`ChromeDialog`); içerik `self.body_host` içine kurulur.
Güncelleme mantığı, sinyaller, durumlar ve metinler çerçeveden bağımsızdır.
"""

from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton, QProgressBar, QTextEdit)
from PyQt6.QtCore import Qt, pyqtSignal
from src.gui.chrome_dialog import ChromeDialog
from src.utils.helpers import format_bytes, format_speed
from src.utils.locales import get_active_language, t


def _set_notes(box, notes: str, default: str) -> None:
    """Sürüm notları HTML ise HTML olarak, düz metinse satır sonları korunarak gösterilir (setHtml satırları birleştirirdi)."""
    from PyQt6.QtCore import Qt as _Qt
    text = notes or ""
    if not text.strip():
        box.setHtml(default)
    elif _Qt.mightBeRichText(text):
        box.setHtml(text)
    else:
        box.setPlainText(text)


class UpdateDialog(ChromeDialog):
    """Güncelleme bilgisi ve ilerleme penceresi"""

    # Durumlar
    IDLE = "idle"                # sürüm bilgisi gösteriliyor
    DOWNLOADING = "downloading"  # indiriliyor (iptal edilebilir)
    INSTALLING = "installing"    # kuruluyor (iptal edilemez)
    ERROR = "error"              # satır içi hata; "Tekrar dene" var

    # Signals
    update_accepted = pyqtSignal()  # "Şimdi Güncelle" / "Tekrar dene"
    update_deferred = pyqtSignal()  # hiç başlatmadan kapatıldı ("Daha Sonra", Esc, X)
    update_cancelled = pyqtSignal()  # indirme sürerken iptal edildi (pencere de kapanır)

    def __init__(self, version: str, release_notes: str, is_mandatory: bool = False, parent=None,
                 lang: str | None = None, *, file_size=None, current_version: str | None = None):
        super().__init__(parent)
        self.version = version
        self.release_notes = release_notes
        self.is_mandatory = is_mandatory
        self.file_size = file_size
        self._state = self.IDLE
        if lang is None and parent is not None and hasattr(parent, 'lang'):
            lang = parent.lang
        elif lang is None and parent is not None and hasattr(parent, 'settings_manager'):
            lang = get_active_language(parent.settings_manager.load_settings())
        self.lang = lang or get_active_language()
        if current_version is None:
            from src.utils.updater import UpdateChecker
            current_version = UpdateChecker.CURRENT_VERSION   # sınıf sabiti: denetleyici (ve ayar dosyası) açılmaz
        self.current_version = current_version

        self._placed = False
        self.setWindowTitle(t("update_available_title", self.lang))
        self.setModal(True)
        self.setMinimumWidth(520)

        self._setup_ui()
        self.resize(560, 460)

    def showEvent(self, event):
        """`show()` ile açıldığında da (uygulama bunu kullanır) ilk gösterimde ana pencerenin / ekranın ortasına yerleşir."""
        if not self._placed:
            self._placed = True
            self._prepare_geometry()
        super().showEvent(event)

    # ------------------------------------------------------------------ arayüz
    def _setup_ui(self):
        layout = QVBoxLayout(self.body_host)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Başlık
        title_label = QLabel(t("update_version_heading", self.lang).format(self.version))
        title_label.setObjectName("dialog_header")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        # Mevcut -> yeni sürüm
        version_label = QLabel(t("update_version_line", self.lang).format(self.current_version, self.version))
        version_label.setObjectName("hint_label")
        version_label.setWordWrap(True)
        layout.addWidget(version_label)

        # İndirme boyutu (sunucu fileSize verdiyse)
        self.size_label = QLabel()
        self.size_label.setObjectName("hint_label")
        self.size_label.setWordWrap(True)
        size = self._known_size()
        if size:
            self.size_label.setText(t("update_size_line", self.lang).format(size=format_bytes(size)))
        self.size_label.setVisible(bool(size))
        layout.addWidget(self.size_label)

        # Sürüm notları (kaydırılabilir)
        notes_label = QLabel(t("update_notes", self.lang))
        notes_label.setObjectName("section_header")
        layout.addWidget(notes_label)

        self.notes_text = QTextEdit()
        self.notes_text.setReadOnly(True)
        self.notes_text.setMinimumHeight(110)
        default_notes = f"<p>{t('update_available_plain', self.lang)}</p>"
        _set_notes(self.notes_text, self.release_notes, default_notes)
        layout.addWidget(self.notes_text, 1)

        # Progress bar (initially hidden)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumHeight(18)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Progress label (initially hidden)
        self.progress_label = QLabel()
        self.progress_label.setVisible(False)
        self.progress_label.setWordWrap(True)
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_label.setObjectName("hint_label")
        layout.addWidget(self.progress_label)

        # Status label (for installation)
        self.status_label = QLabel()
        self.status_label.setVisible(False)
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Satır içi hata (kırmızımsı; açılır kutu yok)
        self.error_label = QLabel()
        self.error_label.setObjectName("update_error")
        self.error_label.setTextFormat(Qt.TextFormat.PlainText)   # hata iletisindeki "<...>" biçim sanılmasın
        self.error_label.setWordWrap(True)
        self.error_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        # Daha sonra (yalnızca isteğe bağlı güncellemelerde)
        self.later_btn = QPushButton(t("update_later", self.lang))
        self.later_btn.clicked.connect(self.reject)
        self.later_btn.setVisible(not self.is_mandatory)
        button_layout.addWidget(self.later_btn)

        # İptal (yalnızca indirme sürerken)
        self.cancel_btn = QPushButton(t("cancel", self.lang))
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setVisible(False)
        button_layout.addWidget(self.cancel_btn)

        # Güncelle (hata olunca "Tekrar dene" olur)
        self.update_btn = QPushButton(t("update_now", self.lang))
        self.update_btn.setProperty("class", "primary")
        self.update_btn.clicked.connect(self._on_update)
        self.update_btn.setDefault(True)
        button_layout.addWidget(self.update_btn)
        self.retry_btn = self.update_btn   # aynı düğme: hata durumunda "Tekrar dene"

        layout.addLayout(button_layout)

    def _known_size(self) -> int:
        try:
            size = int(self.file_size or 0)
        except (TypeError, ValueError, OverflowError):
            return 0
        return size if size > 0 else 0

    # ------------------------------------------------------------------ durum
    @property
    def state(self) -> str:
        return self._state

    @property
    def is_busy(self) -> bool:
        return self._state in (self.DOWNLOADING, self.INSTALLING)

    def _on_update(self):
        """"Şimdi Güncelle" / "Tekrar dene": uygulama indirmeyi başlatır (ikinci tıklama yok sayılır)."""
        if self.is_busy:
            return
        self.show_downloading()
        self.update_accepted.emit()

    def reject(self):
        """Esc / X / İptal / Daha Sonra. İndirme sürerken iptal eder ve kapatır; kurulumda kapatmayı yok sayar."""
        if self._state == self.INSTALLING:
            return
        if self._state == self.DOWNLOADING:
            self._state = self.IDLE
            self.update_cancelled.emit()
        elif self._state == self.IDLE and not self.is_mandatory:
            self.update_deferred.emit()
        super().reject()

    def _hide_progress(self):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.status_label.setVisible(False)

    def show_downloading(self):
        """İndirme başladı: ilerleme çubuğu + hız, "İptal" düğmesi."""
        self._state = self.DOWNLOADING
        self.error_label.setVisible(False)
        self.update_btn.setVisible(False)
        self.later_btn.setVisible(False)
        self.cancel_btn.setVisible(True)

        self.status_label.setVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress_label.setText(t("update_downloading", self.lang))

    def update_download_progress(self, downloaded: int, total: int, speed_mbps: float):
        """
        Update download progress

        Args:
            downloaded: Bytes downloaded
            total: Total bytes to download
            speed_mbps: Download speed in MB/s
        """
        downloaded_str = format_bytes(downloaded)
        speed_str = format_speed(speed_mbps) if speed_mbps > 0 else ""

        if total > 0:
            if self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 100)

            percent = min(int((downloaded / total) * 100), 100)
            self.progress_bar.setValue(percent)

            total_str = format_bytes(total)
            progress_text = f"{downloaded_str} / {total_str} ({percent}%)"
        else:
            # Toplam boyut bilinmiyorsa belirsiz mod
            self.progress_bar.setRange(0, 0)
            progress_text = t("update_downloaded_bytes", self.lang).format(downloaded_str)

        if speed_str:
            progress_text += f" - {speed_str}"

        self.progress_label.setText(progress_text)

    def show_download_complete(self):
        """İndirme bitti (kurulum hemen başlayacak)."""
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_label.setText(t("update_download_done", self.lang))

    def show_installing(self):
        """Kuruluyor: geri alınamaz, düğme yok; uygulama kısa süre sonra kendiliğinden yeniden başlar."""
        self._state = self.INSTALLING
        self.error_label.setVisible(False)
        self.progress_label.setVisible(False)
        self.progress_bar.setRange(0, 0)       # belirsiz ilerleme
        self.progress_bar.setVisible(True)

        self.status_label.setVisible(True)
        self.status_label.setText(t("update_installing", self.lang))

        self.update_btn.setVisible(False)
        self.later_btn.setVisible(False)
        self.cancel_btn.setVisible(False)

    def show_restarting(self):
        """Kurulum bitti, uygulama yeniden başlıyor."""
        self.status_label.setText(t("update_restarting", self.lang))

    def show_error(self, detail: str):
        """Satır içi hata: pencere açık kalır; "Tekrar dene" ve "Daha Sonra" görünür."""
        self._state = self.ERROR
        self._hide_progress()
        self.error_label.setText(t("update_failed_inline", self.lang).format(error=detail))
        self.error_label.setVisible(True)

        self.cancel_btn.setVisible(False)
        self.later_btn.setVisible(not self.is_mandatory)
        self.update_btn.setText(t("update_retry", self.lang))
        self.update_btn.setVisible(True)
        self.update_btn.setEnabled(True)
        self.update_btn.setFocus()
