"""Güncelleme testleri için ortak yardımcılar: sahte PE/zip paketleri, Qt'siz FlexiKeyApp, eşzamanlı sahte iş parçacığı."""

from __future__ import annotations

import io
import time
import zipfile
from unittest import mock

import _support  # noqa: F401  (proje kökü sys.path'e eklenir, offscreen Qt)

from src import app as app_module
from src.app import FlexiKeyApp


def fake_pe(machine: int = 0x8664, payload: bytes = b"") -> bytes:
    """Geçerli PE başlığı olan sahte exe (başlık + mimari doğrulamasını geçer)."""
    head = bytearray(0x80)
    head[:2] = b"MZ"
    head[0x3C:0x40] = (0x80).to_bytes(4, "little")
    return bytes(head) + b"PE\0\0" + machine.to_bytes(2, "little") + payload


def make_zip(entries: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


class SyncJob:
    """BackgroundJob yerine: işi hemen (aynı iş parçacığında) çalıştırır; test sonucu beklemek zorunda kalmaz."""

    started: list = []

    def __init__(self, target, *args, **kwargs):
        self.target, self.args, self.kwargs = target, args, kwargs

    def start(self):
        SyncJob.started.append(self)
        self.target(*self.args, **self.kwargs)

    def isRunning(self):
        return False


class PendingJob(SyncJob):
    """Başlatılır ama bitmez (iş sürüyor görünür)."""

    def start(self):
        SyncJob.started.append(self)

    def isRunning(self):
        return True


def make_app(*, visible: bool = False, minimized: bool = False, lang: str = "tr", pending: dict | None = None) -> FlexiKeyApp:
    """__init__ (QApplication, tepsi, pencere...) çalıştırılmadan, güncelleme akışı için gereken durumla FlexiKeyApp."""
    app = object.__new__(FlexiKeyApp)
    app.update_dialog = None
    app.download_thread = None
    app.install_thread = None
    app._pending_update = pending
    app._ready_package = None
    app._update_cancelled = False
    app._last_progress = (0, 0, 0.0)
    app._auto_update_timer = None
    app._updating = False
    app._started_at = time.monotonic()
    app._updated_from = None
    app.settings_manager = mock.Mock()
    app.settings_manager.load_settings.return_value = {}
    app.tray_manager = mock.Mock()
    app.main_window = mock.Mock(lang=lang)
    app.main_window.isVisible.return_value = visible
    app.main_window.isMinimized.return_value = minimized
    app.update_installer = mock.Mock()
    app.update_installer.preflight_error.return_value = None
    app.update_checker = mock.Mock()
    return app


def pending_info(version: str = "1.1.0", checksum: str = "a" * 64, mandatory: bool = False, size: int = 123) -> dict:
    return {"version": version, "download_url": "https://macik.com.tr/Pages/AppDownload?slug=flexikey&file=FlexiKey.exe",
            "file_size": size, "checksum": checksum, "release_notes": "notlar", "is_mandatory": mandatory}


class TimerCapture:
    """app_module.QTimer yerine: singleShot çağrılarını sıraya alır, fire() ile çalıştırır."""

    def __init__(self, testcase):
        self.mock = mock.Mock(name="QTimer")
        patch = mock.patch.object(app_module, "QTimer", self.mock)
        patch.start()
        testcase.addCleanup(patch.stop)

    def fire(self):
        """Şimdiye dek planlanan tek atımlıkları çalıştırır (çalışırken yenileri planlanırsa onlar bekler)."""
        calls = list(self.mock.singleShot.call_args_list)
        self.mock.singleShot.reset_mock()
        for call in calls:
            _, fn = call.args
            fn()
        return len(calls)

    def delays(self):
        return [c.args[0] for c in self.mock.singleShot.call_args_list]
