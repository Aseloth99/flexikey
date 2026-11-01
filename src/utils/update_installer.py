"""Güncelleme indirici ve kurucu.

İndirme: https + güvenilir ana makine doğrulaması, ilerleme/hız, SHA-256 doğrulaması; paket `%TEMP%\\FlexiKey_Update.pkg`
olarak saklanır (paket türü dosya adından değil İÇERİĞİNDEN anlaşılır: exe ya da içinde exe olan zip).
Kurulum: self_update modülü çalışan exe'yi yeniden adlandırıp yenisini yerine koyar ve yeni sürümü başlatır; betik,
taskkill, PowerShell ve ek pencere YOKTUR. Hata iletileri tr/en'dir (arayüz diline göre).
"""

import hashlib
import hmac
import os
import re
import ssl
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from src.utils import self_update
from src.utils.helpers import log_error, log_info, log_warning
from src.utils.locales import get_active_language, t
from src.utils.updater import as_size, trusted_update_host, validate_download_url

_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
PACKAGE_NAME = "FlexiKey_Update.pkg"
EXE_NAMES = ("FlexiKey.exe",)     # paketteki exe'nin adı (zip içinde; büyük/küçük harf önemsiz)
_USER_AGENT = 'AppUpp/1.0 FlexiKey-Updater'


def normalize_sha256(value) -> str:
    """Sunucunun gönderdiği sağlama toplamını 64 haneli küçük harf SHA-256'ya çevirir.

    Geçersiz biçim ValueError verir: sunucu bir sağlama toplamı gönderdiyse onu doğrulayamamak
    güncellemenin reddedilmesi demektir (sessizce atlanmaz).
    """
    text = str(value).strip().lower()
    if text.startswith('sha256:'):
        text = text[len('sha256:'):].strip()
    if not _SHA256_RE.match(text):
        raise ValueError("Sağlama toplamı geçerli bir SHA-256 değil")
    return text


def update_package_path(temp_dir: Optional[str] = None) -> str:
    """İndirilen paketin yolu: sunucu/URL'den gelen ad ya da uzantı ASLA kullanılmaz."""
    return os.path.join(temp_dir or tempfile.gettempdir(), PACKAGE_NAME)


def is_frozen() -> bool:
    return bool(getattr(sys, 'frozen', False))


def current_exe() -> str:
    return os.path.abspath(sys.executable)


class BackgroundJob:
    """Arayüzü dondurmayan iş (indirme/kurulum): daemon iş parçacığı, çıkışta süreci tutmaz.
    `isRunning()` adı Qt'nin QThread arayüzüyle aynıdır (çağıranlar ayırt etmesin)."""

    def __init__(self, target: Callable, *args, **kwargs):
        self._thread = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True, name="FlexiKey-update")

    def start(self) -> None:
        self._thread.start()

    def isRunning(self) -> bool:
        return self._thread.is_alive()


class _HttpsOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Yönlendirmeler yalnızca https'e (veya loopback'e) gidebilir; https -> http indirgemesi yok."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_download_url(newurl)  # ana makine kısıtı yok (CDN yönlendirmesi olabilir), şema kısıtı var
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_url(request, ssl_context):
    handlers = [_HttpsOnlyRedirectHandler()]
    if ssl_context is not None:
        handlers.append(urllib.request.HTTPSHandler(context=ssl_context))
    return urllib.request.build_opener(*handlers).open(request, timeout=30)


def _remove(path: Optional[str]) -> None:
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


class _Cancelled(Exception):
    """Kullanıcı indirmeyi iptal etti (hata değil; sessizce sonlanır)."""


class UpdateInstaller(QObject):
    """Güncelleme paketini indirir, doğrular ve kurar."""

    # Boyutlar `object`: pyqtSignal(int) 32 bitlik C int'tir, 2 GB üstü değerde taşma hatası verirdi
    download_progress = pyqtSignal(object, object, float)
    download_complete = pyqtSignal(str)
    download_failed = pyqtSignal(str)
    install_started = pyqtSignal()
    install_complete = pyqtSignal()
    install_failed = pyqtSignal(str)

    def __init__(self, parent=None, language: Optional[Callable[[], str]] = None):
        super().__init__(parent)
        self.temp_dir = tempfile.gettempdir()
        self.downloaded_file: Optional[str] = None
        self.expected_sha256: Optional[str] = None  # sunucu gönderdiyse zorunlu doğrulama
        # Arayüz dilini veren işlev (None: sistem dili); hata iletileri bu dilde üretilir
        self.language = language
        self._cancel = threading.Event()

        # Hız hesaplama için değişkenler
        self.speed_samples = deque()  # Sliding window: (timestamp, bytes)
        self.smoothed_speed = 0.0  # EMA ile yumuşatılmış hız (MB/s)
        self.last_update_time = 0.0
        self.last_downloaded = 0
        self.current_downloaded = 0
        self.current_total = 0
        self._last_progress_emit = 0.0

    # ------------------------------------------------------------------ iletiler (tr/en)
    def _lang(self) -> str:
        try:
            if callable(self.language):
                return self.language() or get_active_language()
        except Exception:
            pass
        return get_active_language()

    def _msg(self, key: str, **fields) -> str:
        template = t(key, self._lang())
        try:
            return template.format(**fields)
        except (KeyError, IndexError, ValueError):
            return template

    def describe_package_error(self, error: self_update.PackageError) -> str:
        """Paket/kurulum hatasını arayüz dilinde anlat (modülün Türkçe iletisi yalnızca günlüğe gider)."""
        code = getattr(error, 'code', '')
        key = f"update_err_{code}" if code else ''
        if key and t(key, self._lang()) != key:
            return self._msg(key, detail=getattr(error, 'detail', ''), folder=getattr(error, 'detail', ''))
        return str(error)

    # ------------------------------------------------------------------ ilerleme
    def _emit_progress(self, downloaded: int, total: int, force: bool = False):
        """İlerleme sinyalini gönder (UI thread'inde işlenir)"""
        now = time.time()
        if not force and (now - self._last_progress_emit) < 0.1:
            return

        self._last_progress_emit = now
        current_speed = self._calculate_speed()
        smoothed = self._smooth_speed(current_speed)
        self.download_progress.emit(downloaded, total, smoothed)

    def _add_speed_sample(self, bytes_downloaded: int):
        """Sliding window'a yeni örnek ekle"""
        current_time = time.time()
        self.speed_samples.append((current_time, bytes_downloaded))

        # 1.5 saniyeden eski örnekleri temizle
        cutoff_time = current_time - 1.5
        while self.speed_samples and self.speed_samples[0][0] < cutoff_time:
            self.speed_samples.popleft()

    def _calculate_speed(self) -> float:
        """Sliding window ile hız hesapla (MB/s)"""
        if len(self.speed_samples) < 2:
            return 0.0

        first_time, first_bytes = self.speed_samples[0]
        last_time, last_bytes = self.speed_samples[-1]

        time_diff = last_time - first_time
        if time_diff <= 0:
            return 0.0

        bytes_diff = last_bytes - first_bytes
        speed_mbps = (bytes_diff / time_diff) / (1024 * 1024)

        return speed_mbps

    def _smooth_speed(self, new_speed: float) -> float:
        """Exponential moving average ile hızı yumuşat"""
        alpha = 0.3  # Yeni değer %30, eski değer %70 ağırlıkta
        if self.smoothed_speed == 0.0:
            self.smoothed_speed = new_speed
        else:
            self.smoothed_speed = alpha * new_speed + (1 - alpha) * self.smoothed_speed

        return self.smoothed_speed

    def _sha256_file(self, path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    # ------------------------------------------------------------------ ön kontrol ve iptal
    def preflight_error(self, exe: Optional[str] = None) -> Optional[str]:
        """İndirmeden ÖNCE: bu çalıştırmada kurulum mümkün mü? Değilse kullanıcıya gösterilecek ileti (tr/en), yoksa None.
        Kaynaktan çalışırken (derlenmiş exe değil) kurulacak bir exe yoktur; klasör yazılamıyorsa indirme boşa gitmesin."""
        if exe is None:
            if not is_frozen():
                return self._msg("update_source_run")
            exe = current_exe()
        try:
            self_update.check_writable(exe)
        except self_update.PackageError as e:
            log_warning(f"Güncelleme klasörü yazılamıyor: {e}")
            return self.describe_package_error(e)
        return None

    def cancel(self) -> None:
        """Sürmekte olan indirmeyi iptal eder: iş parçacığı bir sonraki blokta durur, kısmi dosyayı siler ve HİÇBİR
        sinyal göndermez. Yeni bir indirme başlatmak güvenlidir (her indirmenin kendi bayrağı ve geçici dosyası vardır)."""
        self._cancel.set()

    def discard_package(self) -> None:
        _remove(self.downloaded_file)

    # ------------------------------------------------------------------ indirme
    def _fail_download(self, message: str) -> bool:
        self.download_failed.emit(message)
        return False

    def download_update(self, download_url: str, expected_size: Optional[int] = None,
                        expected_checksum: Optional[str] = None) -> bool:
        """Paketi indirir (ilerleme sinyalleriyle), doğrular ve `download_complete` yayınlar. İptalde sessizce False."""
        cancel = threading.Event()
        self._cancel = cancel          # her indirmenin KENDİ bayrağı: iptal edilmiş eski iş yeniye karışmaz
        final = update_package_path(self.temp_dir)
        part = f"{final}.{os.getpid()}.{int(time.time() * 1000)}.part"   # her indirmenin kendi kısmi dosyası
        try:
            # Ağa çıkmadan önce: adres (https + güvenilir ana makine) ve sağlama toplamı doğrulaması
            try:
                validate_download_url(download_url, trusted_update_host())
            except ValueError as url_error:
                log_error(f"Güncelleme indirme adresi reddedildi: {url_error}")
                return self._fail_download(self._msg("update_err_insecure_url", detail=url_error))

            self.expected_sha256 = None
            if expected_checksum and str(expected_checksum).strip():
                try:
                    self.expected_sha256 = normalize_sha256(expected_checksum)
                except ValueError as checksum_error:
                    log_error(f"Sunucunun sağlama toplamı geçersiz: {checksum_error}")
                    return self._fail_download(self._msg("update_err_server_checksum"))
            else:
                log_warning("Güncelleme için sunucu sağlama toplamı göndermedi: bütünlük doğrulanamayacak")

            # Hız hesaplama değişkenlerini sıfırla
            self.speed_samples.clear()
            self.smoothed_speed = 0.0
            self.current_downloaded = 0
            declared = as_size(expected_size)
            self.current_total = declared
            self._last_progress_emit = 0.0

            # Toplam boyut biliniyorsa hemen UI'ı bilgilendir
            if self.current_total > 0:
                self._emit_progress(0, self.current_total, force=True)

            self.downloaded_file = final
            _remove(final)

            parsed_url = urllib.parse.urlparse(download_url)
            is_localhost = parsed_url.hostname in ('localhost', '127.0.0.1', '::1')
            ssl_context = ssl._create_unverified_context() if is_localhost else None

            # Add cache-busting parameter to URL to prevent caching
            cache_buster = int(time.time() * 1000)  # milliseconds timestamp
            if parsed_url.query:
                download_url_with_cache = f"{download_url}&_t={cache_buster}"
            else:
                download_url_with_cache = f"{download_url}?_t={cache_buster}"

            req = urllib.request.Request(download_url_with_cache)
            req.add_header('User-Agent', _USER_AGENT)
            # Force no-cache headers to prevent HTTP caching
            req.add_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            req.add_header('Pragma', 'no-cache')
            req.add_header('Expires', '0')

            with _open_url(req, ssl_context) as response:
                # Önce sunucudan Content-Length almaya çalış
                try:
                    header_length = int(response.headers.get('Content-Length', 0) or 0)
                except (TypeError, ValueError):
                    header_length = 0
                total_size = header_length

                # Eğer Content-Length yoksa veya 0 ise API'den gelen beklenen boyutu kullan
                if total_size <= 0 and declared > 0:
                    total_size = declared

                self.current_total = total_size
                downloaded = 0
                block_size = 64 * 1024

                if total_size > 0:
                    self._emit_progress(0, total_size, force=True)

                with open(part, 'wb') as f:
                    while True:
                        chunk = response.read(block_size)
                        if cancel.is_set():
                            raise _Cancelled()
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded > self_update.MAX_EXE_BYTES:
                            raise self_update.PackageError("Paket izin verilen boyuttan büyük", "too_big")
                        self.current_downloaded = downloaded

                        # Her chunk'ta sliding window'a örnek ekle
                        self._add_speed_sample(downloaded)
                        self._emit_progress(downloaded, total_size)

            # Son güncelleme
            self._emit_progress(downloaded, total_size, force=True)

            if self.expected_sha256:
                actual = self._sha256_file(part)
                if not hmac.compare_digest(actual, self.expected_sha256):
                    _remove(part)
                    log_error("Güncelleme sağlama toplamı uyuşmadı, dosya silindi")
                    return self._fail_download(self._msg("update_err_checksum_download"))

            # İçerik bir exe ya da zip değilse (örn. sunucunun 200 döndürdüğü HTML hata sayfası) hemen söyle
            self_update.sniff_package(part)

            if cancel.is_set():
                raise _Cancelled()
            os.replace(part, final)
            self.download_complete.emit(final)
            return True

        except _Cancelled:
            _remove(part)
            log_info("Güncelleme indirmesi iptal edildi")
            return False
        except self_update.PackageError as e:
            _remove(part)
            log_error(f"Güncelleme paketi kullanılamaz: {e}")
            return self._fail_download(self.describe_package_error(e))
        except urllib.error.HTTPError as e:
            _remove(part)
            return self._fail_download(self._msg("update_err_http", code=e.code))
        except urllib.error.URLError as e:
            _remove(part)
            return self._fail_download(self._msg("update_err_network", detail=getattr(e, 'reason', e)))
        except TimeoutError:
            _remove(part)
            return self._fail_download(self._msg("update_err_timeout"))
        except OSError as e:
            _remove(part)
            return self._fail_download(self._msg("update_err_io", detail=e))
        except Exception as e:
            _remove(part)
            return self._fail_download(str(e))

    # ------------------------------------------------------------------ kurulum
    def _fail_install(self, message: str, package: Optional[str] = None) -> bool:
        _remove(package)       # tekrar denemek yeniden indirir; yarım kalan paket %TEMP%'te birikmesin
        self.install_failed.emit(message)
        return False

    def install_update(self, installer_path: Optional[str] = None, *, visible: bool = False,
                       old_version: Optional[str] = None, exe: Optional[str] = None) -> bool:
        """İndirilen paketi kurar ve yeni sürümü başlatır (`install_complete`); çağıran uygulama TEMİZ çıkış yapmalıdır.
        Hata `install_failed` olarak bildirilir ve çalışan uygulama olduğu gibi kalır. İş parçacığından çağrılabilir.
        visible: kurulum anında ana pencere ekranda mıydı (yeni sürüm pencereyi açık/gizli getirir)."""
        update_file = installer_path or self.downloaded_file
        try:
            if not update_file or not os.path.exists(update_file):
                return self._fail_install(self._msg("update_err_missing"))

            if exe is None:
                if not is_frozen():
                    return self._fail_install(self._msg("update_source_run"), package=update_file)
                exe = current_exe()

            # Dosya %TEMP%'te bekledi: sunucu sağlama toplamı verdiyse kurulumdan hemen önce yeniden doğrula
            if self.expected_sha256:
                actual = self._sha256_file(update_file)
                if not hmac.compare_digest(actual, self.expected_sha256):
                    log_error("Kurulum öncesi sağlama toplamı uyuşmadı, kurulum iptal edildi")
                    return self._fail_install(self._msg("update_err_checksum_install"), package=update_file)

            log_info("Güncelleme kurulumu başlatılıyor")
            self.install_started.emit()

            if old_version is None:
                from src.utils.updater import UpdateChecker
                old_version = UpdateChecker.CURRENT_VERSION
            try:
                self_update.install_and_relaunch(update_file, exe, EXE_NAMES, visible=visible, old_version=old_version)
            except self_update.PackageError as e:
                log_error(f"Güncelleme kurulamadı: {e}")
                return self._fail_install(self.describe_package_error(e), package=update_file)

            self.install_complete.emit()
            return True

        except Exception as e:
            log_error("Güncelleme kurulumunda beklenmeyen hata", e)
            return self._fail_install(self._msg("update_err_unexpected", detail=e), package=update_file)
