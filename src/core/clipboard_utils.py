"""Pano yardimcilari: CF_HTML bicimi, guvenli pano acma, kaydet/geri yukle.

Windows pano modulleri (win32clipboard / win32con) disaridan verilir; bu sayede mantik
gercek panoya dokunmadan sahte (mock) bir modulle test edilebilir. CF_HTML yolu YALNIZCA
Windows'tadir; macOS/Linux'ta Qt QClipboard/QMimeData kullanilir (QtClipboard, dosyanin sonu).

Geri yuklenen bicimler: CF_UNICODETEXT, "HTML Format", "Rich Text Format".
Geri YUKLENMEYEN bicimler (resim/CF_DIB/CF_BITMAP, CF_HDROP dosya listesi, uygulamaya ozel
ve gecikmeli olusturulan (delayed rendering) bicimler): bunlar GDI/bellek tutamaclari ya da
sahibi uygulamanin renderlamasina bagli oldugundan guvenle kopyalanamaz. Panoda boyle bir
icerik varsa genisletme sonrasi pano bos birakilir ve durum loglanir (lossy=True).
"""

from __future__ import annotations

import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, Optional

from PyQt6.QtCore import QBuffer, QByteArray, QCoreApplication, QIODevice, QMimeData, QObject, QThread, pyqtSignal
from PyQt6.QtGui import QGuiApplication

from src.utils import platform_utils
from src.utils.helpers import log_error, log_info, log_warning

HTML_FORMAT_NAME = "HTML Format"
RTF_FORMAT_NAME = "Rich Text Format"
START_FRAGMENT = "<!--StartFragment-->"
END_FRAGMENT = "<!--EndFragment-->"

_HEADER_TEMPLATE = (
    "Version:0.9\r\n"
    "StartHTML:{:010d}\r\n"
    "EndHTML:{:010d}\r\n"
    "StartFragment:{:010d}\r\n"
    "EndFragment:{:010d}\r\n"
)
# Windows tarafindan baska bicimlerden otomatik uretilen (sentezlenen) bicimler: kayip sayilmaz
_SYNTHESIZED_FORMATS = {1, 7, 16}  # CF_TEXT, CF_OEMTEXT, CF_LOCALE
_CF_UNICODETEXT = 13


def build_cf_html(fragment: str) -> bytes:
    """CF_HTML ("HTML Format") verisini UTF-8 bayt dizisi olarak uretir.

    CF_HTML'deki StartHTML/EndHTML/StartFragment/EndFragment degerleri karakter degil BAYT
    ofsetleridir. Veri UTF-8 gonderildigi icin (c g i o s u = 2 bayt) ofsetler bayt
    uzunluklariyla hesaplanir; aksi halde parca sonu kayar ve yapistirilan icerik kesilir.
    """
    header_length = len(_HEADER_TEMPLATE.format(0, 0, 0, 0))  # ASCII: karakter == bayt
    prefix = ("<html><body>" + START_FRAGMENT).encode("utf-8")
    body = fragment.encode("utf-8", errors="replace")
    suffix = (END_FRAGMENT + "</body></html>").encode("utf-8")

    start_html = header_length
    start_fragment = start_html + len(prefix)
    end_fragment = start_fragment + len(body)
    end_html = end_fragment + len(suffix)

    header = _HEADER_TEMPLATE.format(start_html, end_html, start_fragment, end_fragment)
    return header.encode("ascii") + prefix + body + suffix


class ClipboardError(Exception):
    """Pano acilamadi (baska uygulama tutuyor)."""


@contextmanager
def open_clipboard(cb: Any, attempts: int = 10, delay: float = 0.02,
                   sleep: Callable[[float], None] = time.sleep) -> Iterator[None]:
    """OpenClipboard'u tekrar deneyerek acar; CloseClipboard HER ZAMAN (try/finally) cagrilir."""
    last_error: Optional[BaseException] = None
    for attempt in range(attempts):
        try:
            cb.OpenClipboard()
            break
        except Exception as exc:  # pywintypes.error: baska uygulama panoyu tutuyor
            last_error = exc
            if attempt < attempts - 1:
                sleep(delay)
    else:
        raise ClipboardError(f"Pano acilamadi: {last_error}") from last_error

    try:
        yield
    finally:
        try:
            cb.CloseClipboard()
        except Exception as exc:
            log_error("Pano kapatilamadi", exc)


@dataclass
class ClipboardSnapshot:
    data: Dict[Any, Any] = field(default_factory=dict)  # bicim kimligi -> veri
    lossy: bool = False  # geri yuklenemeyen bicimler vardi


def clipboard_sequence_number(cb: Any) -> Optional[int]:
    getter = getattr(cb, "GetClipboardSequenceNumber", None)
    if getter is None:
        return None
    try:
        return int(getter())
    except Exception:
        return None


def snapshot_clipboard(cb: Any, con: Any) -> ClipboardSnapshot:
    """Panonun geri yuklenebilir bicimlerini (metin/HTML/RTF) kaydeder."""
    snapshot = ClipboardSnapshot()
    with open_clipboard(cb):
        supported = {
            getattr(con, "CF_UNICODETEXT", _CF_UNICODETEXT),
            cb.RegisterClipboardFormat(HTML_FORMAT_NAME),
            cb.RegisterClipboardFormat(RTF_FORMAT_NAME),
        }
        for fmt in supported:
            try:
                if cb.IsClipboardFormatAvailable(fmt):
                    snapshot.data[fmt] = cb.GetClipboardData(fmt)
            except Exception as exc:
                log_warning(f"Pano bicimi okunamadi ({fmt}): {exc}")
                snapshot.lossy = True

        try:  # desteklenmeyen gercek bicimler var mi? (yalnizca bilgi/log icin)
            fmt = cb.EnumClipboardFormats(0)
            while fmt:
                if fmt not in supported and fmt not in _SYNTHESIZED_FORMATS:
                    snapshot.lossy = True
                fmt = cb.EnumClipboardFormats(fmt)
        except Exception:
            pass
    return snapshot


def set_clipboard_rich_text(cb: Any, con: Any, html_fragment: str, plain_text: str) -> None:
    """Panoya HTML (CF_HTML, UTF-8 bayt) + duz metin yazar; pano her durumda kapatilir."""
    html_bytes = build_cf_html(html_fragment)
    with open_clipboard(cb):
        cb.EmptyClipboard()
        cb.SetClipboardData(cb.RegisterClipboardFormat(HTML_FORMAT_NAME), html_bytes)
        cb.SetClipboardData(getattr(con, "CF_UNICODETEXT", _CF_UNICODETEXT), plain_text)


def restore_clipboard(cb: Any, snapshot: ClipboardSnapshot,
                      expected_sequence: Optional[int] = None) -> bool:
    """Kaydedilen icerigi geri yukler. Hata firlatmaz (finally icinde kullanilir).

    expected_sequence verilmis ve pano o sirada degismisse (kullanici arada baska bir sey
    kopyalamis) geri yukleme YAPILMAZ: kullanicinin yeni kopyasi ezilmesin.
    """
    try:
        if expected_sequence is not None:
            current = clipboard_sequence_number(cb)
            if current is not None and current != expected_sequence:
                log_warning("Pano genisletme sirasinda degisti; eski icerik geri yuklenmedi")
                return False
        if snapshot.lossy:
            log_info("Panoda geri yuklenemeyen bicimler (resim/dosya vb.) vardi; kaybolabilir")
        with open_clipboard(cb):
            cb.EmptyClipboard()
            for fmt, data in snapshot.data.items():
                try:
                    cb.SetClipboardData(fmt, data)
                except Exception as exc:
                    log_warning(f"Pano bicimi geri yuklenemedi ({fmt}): {exc}")
        return True
    except Exception as exc:
        log_error("Pano geri yuklenemedi", exc)
        return False


# ====================================================================================
# Pano arka uçları: HotkeyWorker._paste_rich_text bu arayüzü kullanır
#   snapshot() -> ClipboardSnapshot
#   set_rich_text(html, plain) -> token   (geri yüklemede "pano değişti mi" denetimi için)
#   restore(snapshot, token) -> bool      (asla hata fırlatmaz)
# Windows: CF_HTML (yukarıdaki işlevler). macOS/Linux: Qt QClipboard/QMimeData (text/html + text/plain).
# ====================================================================================
class Win32Clipboard:
    """Windows panosu (pywin32): CF_HTML + CF_UNICODETEXT. Modüller çağrı anında yüklenir."""

    @staticmethod
    def _modules():
        import win32clipboard
        import win32con
        return win32clipboard, win32con

    def snapshot(self) -> ClipboardSnapshot:
        cb, con = self._modules()
        return snapshot_clipboard(cb, con)

    def set_rich_text(self, html_fragment: str, plain_text: str) -> Optional[int]:
        cb, con = self._modules()
        set_clipboard_rich_text(cb, con, html_fragment, plain_text)
        return clipboard_sequence_number(cb)

    def restore(self, snapshot: ClipboardSnapshot, token: Optional[int] = None) -> bool:
        try:
            cb, _ = self._modules()
        except Exception as exc:
            log_error("Pano modulu yuklenemedi, geri yukleme yapilamadi", exc)
            return False
        return restore_clipboard(cb, snapshot, token)


class _GuiTask:
    def __init__(self, fn: Callable[[], Any]):
        self.fn = fn
        self.done = threading.Event()
        self.result: Any = None
        self.error: Optional[BaseException] = None

    def run(self) -> None:
        try:
            self.result = self.fn()
        except BaseException as exc:      # çağıran iş parçacığına iletilir
            self.error = exc
        finally:
            self.done.set()


class _GuiInvoker(QObject):
    """GUI iş parçacığında yaşar; başka iş parçacıklarından gelen işleri orada çalıştırır."""

    request = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.request.connect(self._execute)

    def _execute(self, task: "_GuiTask") -> None:
        task.run()


_INVOKER: Optional[_GuiInvoker] = None
_INVOKER_LOCK = threading.Lock()


def run_on_gui_thread(fn: Callable[[], Any], timeout: float = 5.0) -> Any:
    """fn()'i Qt GUI iş parçacığında çalıştırıp sonucunu döndürür (QClipboard yalnızca orada güvenlidir;
    X11'de panoya gelen istekleri de GUI olay döngüsü karşılar). GUI iş parçacığındaysak doğrudan çağrılır."""
    app = QCoreApplication.instance()
    if app is None:
        raise ClipboardError("Qt uygulamasi yok")
    if QThread.currentThread() is app.thread():
        return fn()
    global _INVOKER
    with _INVOKER_LOCK:
        if _INVOKER is None:
            invoker = _GuiInvoker()
            invoker.moveToThread(app.thread())
            _INVOKER = invoker
        invoker = _INVOKER
    task = _GuiTask(fn)
    invoker.request.emit(task)
    if not task.done.wait(timeout):
        raise ClipboardError("GUI is parcacigi yanit vermedi (pano islemi zaman asimi)")
    if task.error is not None:
        raise task.error
    return task.result


def _ensure_html_charset(html: str) -> str:
    """Bazı uygulamalar (LibreOffice, Firefox/Linux) charset yoksa UTF-8 HTML'i bozuk okur."""
    if "charset" in html[:2048].lower():
        return html
    return '<meta charset="utf-8">' + html


class QtClipboard:
    """Qt panosu (macOS/Linux): text/html + text/plain; önceki içeriğin (tüm MIME biçimleri) kaydet/geri yükle."""

    MARKER_FORMAT = "application/x-flexikey-paste"
    MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024

    def __init__(self, get_clipboard: Optional[Callable[[], Any]] = None,
                 run_on_gui: Callable[[Callable[[], Any]], Any] = run_on_gui_thread,
                 new_token: Optional[Callable[[], str]] = None):
        self._get_clipboard = get_clipboard or QGuiApplication.clipboard
        self._run = run_on_gui
        self._new_token = new_token or (lambda: uuid.uuid4().hex)

    def snapshot(self) -> ClipboardSnapshot:
        return self._run(self._snapshot)

    def _snapshot(self) -> ClipboardSnapshot:
        snapshot = ClipboardSnapshot()
        mime = self._get_clipboard().mimeData()
        if mime is None:
            return snapshot
        total = 0
        for fmt in mime.formats():
            if fmt == self.MARKER_FORMAT:
                continue
            data = bytes(mime.data(fmt))
            if not data:
                continue
            total += len(data)
            if total > self.MAX_SNAPSHOT_BYTES:
                snapshot.lossy = True
                break
            snapshot.data[fmt] = data
        try:
            if mime.hasImage() and "image/png" not in snapshot.data:
                image = mime.imageData()
                payload = QByteArray()
                buffer = QBuffer(payload)
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                if image.save(buffer, "PNG"):
                    snapshot.data["image/png"] = bytes(payload)
                else:
                    snapshot.lossy = True
        except Exception as exc:
            log_warning(f"Pano resmi okunamadi: {exc}")
            snapshot.lossy = True
        return snapshot

    def set_rich_text(self, html_fragment: str, plain_text: str) -> str:
        token = self._new_token()

        def apply() -> None:
            mime = QMimeData()
            mime.setHtml(_ensure_html_charset(html_fragment))
            mime.setText(plain_text)
            mime.setData(self.MARKER_FORMAT, token.encode("ascii"))
            self._get_clipboard().setMimeData(mime)

        self._run(apply)
        return token

    def restore(self, snapshot: ClipboardSnapshot, token: Optional[str] = None) -> bool:
        """Kaydedilen içeriği geri yükler; pano bu arada başka bir şeyle değiştiyse (kullanıcı yeni
        kopyaladı) DOKUNMAZ. Hata fırlatmaz (finally içinde kullanılır)."""
        try:
            return bool(self._run(lambda: self._restore(snapshot, token)))
        except Exception as exc:
            log_error("Pano geri yuklenemedi", exc)
            return False

    def _restore(self, snapshot: ClipboardSnapshot, token: Optional[str]) -> bool:
        clipboard = self._get_clipboard()
        if token is not None:
            current = clipboard.mimeData()
            marker = bytes(current.data(self.MARKER_FORMAT)) if current is not None else b""
            if marker != token.encode("ascii"):
                log_warning("Pano genisletme sirasinda degisti; eski icerik geri yuklenmedi")
                return False
        if snapshot.lossy:
            log_info("Panoda geri yuklenemeyen bicimler vardi; kaybolabilir")
        if not snapshot.data:
            clipboard.clear()
            return True
        mime = QMimeData()
        for fmt, data in snapshot.data.items():
            mime.setData(fmt, data)
        clipboard.setMimeData(mime)
        return True


def create_clipboard(platform: Optional[str] = None):
    """Platforma uygun pano arka ucu: Windows CF_HTML (pywin32), diğerleri Qt."""
    if platform_utils.is_windows(platform):
        return Win32Clipboard()
    return QtClipboard()
