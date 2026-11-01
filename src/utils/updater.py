"""Update checker for FlexiKey"""

import json
import math
import os
import ssl
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QThread
from src.utils import self_update
from src.utils.settings_manager import SettingsManager
from src.utils.helpers import log_error, log_info

LOOPBACK_HOSTS = ('localhost', '127.0.0.1', '::1')


def as_bool(value) -> bool:
    """Sunucu JSON'unda mantıksal alan bazen metin gelir ("false" bool olarak doğru sayılmasın)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1', 'yes', 'evet', 'on')
    return False


def as_size(value) -> int:
    """fileSize: sayı ya da sayı metni (ondalıklı/üstel olabilir). Geçersiz, sonsuz ya da <= 0 ise 0 (bilinmiyor)."""
    if isinstance(value, bool):
        return 0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(number) or number <= 0:
        return 0
    return int(number)


def as_text(value) -> str:
    """Metin alanı: dize değilse (null, sayı, liste) boş sayılır."""
    return value.strip() if isinstance(value, str) else ''


def validate_download_url(url: str, trusted_host: Optional[str] = None) -> str:
    """Sunucunun gönderdiği indirme adresini doğrular; geçerliyse adresi döndürür.

    Kurallar: yalnızca https (http yalnızca loopback/geliştirme), kullanıcı bilgisi (user:pass@)
    yok, ana makine dolu; trusted_host (güncelleme API'sinin ana makinesi) verilmişse indirme
    adresi o makine ya da alt alan adı olmalı (loopback hariç). Aksi halde ValueError.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("İndirme adresi boş")
    parsed = urllib.parse.urlparse(url.strip())
    host = (parsed.hostname or '').lower()
    if not host:
        raise ValueError("İndirme adresinde ana makine yok")
    if parsed.username or parsed.password:
        raise ValueError("İndirme adresi kimlik bilgisi içeremez")
    is_loopback = host in LOOPBACK_HOSTS
    if parsed.scheme == 'https':
        pass
    elif parsed.scheme == 'http' and is_loopback:
        pass  # yalnızca yerel geliştirme sunucusu
    else:
        raise ValueError(f"İndirme adresi https olmalı (gelen: {parsed.scheme or 'yok'})")
    if trusted_host and not is_loopback:
        trusted = trusted_host.lower()
        if host != trusted and not host.endswith('.' + trusted):
            raise ValueError(f"İndirme ana makinesi güvenilir değil: {host}")
    return url.strip()


def trusted_update_host() -> Optional[str]:
    return urllib.parse.urlparse(UpdateChecker.UPDATE_CHECK_URL).hostname


class _UpdateCheckWorker(QThread):
    """Güncelleme kontrolünü arka planda yapar (UI'ı bloklamaz)"""

    result_ready = pyqtSignal(dict)
    network_error = pyqtSignal(str)
    check_error = pyqtSignal(str)

    def __init__(self, url: str, ssl_context, parent=None):
        super().__init__(parent)
        self._url = url
        self._ssl_context = ssl_context

    def run(self):
        try:
            req = urllib.request.Request(self._url)
            req.add_header('User-Agent', 'AppUpp/1.0 FlexiKey-UpdateChecker')

            with urllib.request.urlopen(req, timeout=10, context=self._ssl_context) as response:
                raw = response.read()
            try:
                data = json.loads(raw.decode())
                if not isinstance(data, dict):
                    raise ValueError("yanıt bir nesne değil")
            except ValueError as parse_error:  # bozuk yanıt (internet yokluğu değil)
                self.check_error.emit(str(parse_error))
                return
            self.result_ready.emit(data)
        except urllib.error.HTTPError as e:
            self.network_error.emit(f"HTTP {e.code}: {e.reason if hasattr(e, 'reason') else ''}")
        except urllib.error.URLError as e:
            reason = e.reason if hasattr(e, 'reason') else e
            self.network_error.emit(str(reason))
        except TimeoutError as e:
            self.network_error.emit(str(e))
        except OSError as e:
            self.network_error.emit(str(e))
        except Exception as e:
            self.check_error.emit(str(e))


class UpdateChecker(QObject):
    """Check for application updates"""

    # file_size `object`: pyqtSignal(int) 32 bitlik C int'tir, 2 GB üstü bir fileSize taşma hatası verirdi
    update_available = pyqtSignal(str, str, str, bool, object, str)  # version, download_url, release_notes, is_mandatory, file_size, checksum
    # has_update. Arka plan denetimi başarısız olursa da False yayınlanır; ELLE denetimde
    # başarısızlık check_complete değil check_failed ile bildirilir (Ayarlar "Güncel" yerine "denetlenemedi" göstersin).
    check_complete = pyqtSignal(bool)
    check_failed = pyqtSignal()  # yalnızca manuel kontrol başarısız olursa
    notice_received = pyqtSignal(object)  # remote_notice.Notice (duyuru satırı)

    CURRENT_VERSION = "1.0.0"
    UPDATE_CHECK_URL = "https://macik.com.tr/api/updates/check"
    APP_NAME = "FlexiKey"
    CHECK_INTERVAL_HOURS = 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings_manager = SettingsManager()
        self.current_version = self.CURRENT_VERSION
        self.last_check_time: Optional[datetime] = None
        self.check_timer = QTimer(self)
        self.check_timer.timeout.connect(self._auto_check)

        self._worker: Optional[_UpdateCheckWorker] = None
        self._manual = False

    def start(self):
        """Otomatik güncelleme kontrolünü başlat (sessiz, arka plan)"""
        settings = self.settings_manager.load_settings()
        if not settings.get('auto_update_check', True):
            return

        self._check_if_needed()
        self.check_timer.start(self.CHECK_INTERVAL_HOURS * 3600 * 1000)

    def stop(self):
        """Otomatik güncelleme kontrolünü durdur"""
        self.check_timer.stop()

    def _auto_check(self):
        """Zamanlayıcıdan gelen sessiz kontrol"""
        self.check_for_updates(show_message=False)

    def _check_if_needed(self):
        """Son kontrolden bu yana yeterli süre geçtiyse sessizce kontrol et"""
        settings = self.settings_manager.load_settings()
        last_check_str = settings.get('last_update_check', None)

        if last_check_str:
            try:
                self.last_check_time = datetime.fromisoformat(last_check_str)
                if datetime.now() - self.last_check_time < timedelta(hours=self.CHECK_INTERVAL_HOURS):
                    return
            except Exception:
                pass

        self.check_for_updates(show_message=False)

    def check_for_updates(self, show_message: bool = False):
        """
        Güncelleme kontrolü başlat.

        Args:
            show_message: True ise manuel kontroldür; sonuç ve hatalar kullanıcıya gösterilir.
                          False ise otomatik/arka plan kontrolüdür; hata durumunda hiçbir uyarı çıkmaz.
        """
        settings = self.settings_manager.load_settings()
        auto_update_check = settings.get('auto_update_check', True)

        if not auto_update_check and not show_message:
            return

        # Zaten çalışan bir kontrol varsa: manuel talep bekleyen işi manuel'e yükselt
        if self._worker is not None and self._worker.isRunning():
            if show_message:
                self._manual = True
            return

        self._manual = bool(show_message)

        params = {
            'appName': self.APP_NAME,
            'currentVersion': self.current_version
        }
        url = f"{self.UPDATE_CHECK_URL}?{urllib.parse.urlencode(params)}"

        parsed_url = urllib.parse.urlparse(url)
        is_localhost = parsed_url.hostname in ('localhost', '127.0.0.1', '::1')
        ssl_context = ssl._create_unverified_context() if is_localhost else None

        self._worker = _UpdateCheckWorker(url, ssl_context, self)
        self._worker.result_ready.connect(self._on_worker_result)
        self._worker.network_error.connect(self._on_worker_network_error)
        self._worker.check_error.connect(self._on_worker_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_worker_finished(self):
        worker = self.sender()
        if worker is self._worker:
            self._worker = None

    def _skipped_version(self) -> Optional[str]:
        """Bu bilgisayarda geri alınmak zorunda kalan sürüm (bozuk çıktığı için bir daha önerilmez); yalnızca derlenmiş exe'de."""
        if not getattr(sys, 'frozen', False):
            return None
        return self_update.skipped_version(os.path.abspath(sys.executable))

    def _finish_up_to_date(self, lang: str, show_message: bool):
        from src.utils.locales import t
        self.check_complete.emit(False)
        if show_message:
            self._show_info(t("update_check_title", lang), t("update_current", lang).format(self.current_version))
        self.settings_manager.update(last_update_check=datetime.now().isoformat())

    def _fail_check(self):
        """Denetim sonuçlanamadı (ağ, bozuk yanıt, geçersiz adres). Elle denetimde Ayarlar'a "denetlenemedi" gider
        ("güncel" DEĞİL); arka plan denetiminde yalnızca check_complete(False) yayınlanır. Damga atılmaz: sonraki
        açılışta yeniden denenir."""
        if self._manual:
            self.check_failed.emit()
        else:
            self.check_complete.emit(False)

    def _on_worker_result(self, data: dict):
        settings = self.settings_manager.load_settings()
        show_message = self._manual
        from src.utils.locales import get_active_language, t
        lang = get_active_language(settings)

        try:
            from src.utils.remote_notice import parse_notice
            notice = parse_notice(data, lang)
            if notice is not None:
                self.notice_received.emit(notice)

            if not as_bool(data.get('updateAvailable', False)):
                self._finish_up_to_date(lang, show_message)
                return

            raw_version = data.get('version')
            latest_version = as_text(raw_version if isinstance(raw_version, str) else str(raw_version or '')).lstrip('vV')
            download_url = as_text(data.get('download_url'))
            release_notes = data.get('release_notes') if isinstance(data.get('release_notes'), str) else ''
            is_mandatory = as_bool(data.get('isMandatory', False))
            file_size = as_size(data.get('fileSize'))
            checksum = as_text(data.get('checksum'))

            if not latest_version or not download_url:
                self._fail_check()
                return

            try:
                validate_download_url(download_url, trusted_update_host())
            except ValueError as url_error:
                # Güvenilmeyen/biçimsiz indirme adresi: güncellemeyi sunma
                log_error(f"Güncelleme indirme adresi reddedildi: {url_error}")
                self._show_warning(t("update_check_title", lang), t("check_error_prefix", lang).format(str(url_error)))
                self._fail_check()
                return

            skipped = self._skipped_version()
            if skipped and skipped.lstrip('vV') == latest_version:
                # Bu sürüm bu bilgisayarda açılışta çöktü ve eskisi geri getirildi: aynı sürüm bir daha önerilmez
                log_info(f"Sunulan sürüm (v{latest_version}) bu bilgisayarda geri alındığı için önerilmiyor")
                self._finish_up_to_date(lang, show_message)
                return

            if self._compare_versions(latest_version, self.current_version) > 0:
                self.update_available.emit(latest_version, download_url, release_notes, is_mandatory, file_size, checksum)
                self.check_complete.emit(True)
                # Damga ATILMAZ: güncelleme bekliyorken uygulama kapanıp açılırsa (ya da kurulum yarıda kalırsa) bir
                # sonraki açılışta yeniden denetlenir; yoksa "Güncelle" düğmesi 24 saat boyunca kaybolurdu.
            else:
                self._finish_up_to_date(lang, show_message)

        except Exception as e:
            log_error("Guncelleme sonucu islenemedi", e)
            self._fail_check()

    def _on_worker_network_error(self, reason: str):
        log_info(f"Guncelleme kontrolu basarisiz (ag): {reason}")
        self._fail_check()

    def _on_worker_error(self, message: str):
        log_info(f"Guncelleme kontrolu basarisiz: {message}")
        self._fail_check()

    def _show_info(self, title: str, text: str):
        """Güncelleme sonuçları için pop-up açılmaz: ayarlardaki durum satırı / başlık çubuğundaki düğme gösterir."""
        log_info(f"{title}: {text}")

    def _show_warning(self, title: str, text: str):
        log_info(f"{title}: {text}")

    def _compare_versions(self, version1: str, version2: str) -> int:
        """
        Compare two version strings

        Returns:
            1 if version1 > version2
            -1 if version1 < version2
            0 if version1 == version2
        """
        try:
            v1_parts = [int(x) for x in version1.split('.')]
            v2_parts = [int(x) for x in version2.split('.')]

            max_len = max(len(v1_parts), len(v2_parts))
            v1_parts += [0] * (max_len - len(v1_parts))
            v2_parts += [0] * (max_len - len(v2_parts))

            for v1, v2 in zip(v1_parts, v2_parts):
                if v1 > v2:
                    return 1
                elif v1 < v2:
                    return -1

            return 0
        except Exception:
            return 0

    def get_current_version(self) -> str:
        """Get current application version"""
        return self.current_version
