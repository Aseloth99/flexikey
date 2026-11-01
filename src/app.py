"""FlexiKey uygulama sinifi: QApplication, yoneticiler, ana pencere, tepsi ve guncelleme akisi."""

import os
import sys
import time

from PyQt6.QtCore import QCoreApplication, QDir, QLockFile, Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from src.core.hotkey_manager import HotkeyManager
from src.gui.main_window import MainWindow
from src.gui.message_box import configure as configure_message_box
from src.gui.notification_manager import NotificationManager
from src.gui.tray_manager import TrayManager
from src.utils import self_update, startup
from src.utils.helpers import log_info
from src.utils.locales import get_active_language
from src.utils.settings_manager import SettingsManager, format_settings_warning, register_saved_items
from src.utils.theme_manager import ThemeManager
from src.utils.update_installer import BackgroundJob, UpdateInstaller
from src.utils.updater import UpdateChecker


def _try_raise_existing(socket_name: str = 'FlexiKey.SingleInstanceServer') -> bool:
    from PyQt6.QtNetwork import QLocalSocket
    sock = QLocalSocket()
    sock.connectToServer(socket_name)
    if sock.waitForConnected(300):
        sock.write(b"raise")
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def update_has_checksum(value) -> bool:
    """Sunucu geçerli bir SHA-256 verdi mi? Otomatik (sessiz) kurulum yalnızca doğrulanabilir paketle yapılır."""
    from src.utils.update_installer import normalize_sha256
    try:
        normalize_sha256(value or '')
        return True
    except ValueError:
        return False


def _is_frozen() -> bool:
    """Derlenmiş exe mi? Kaynaktan çalışırken değiştirilecek bir exe yoktur (otomatik kurulum desteklenmez)."""
    return bool(getattr(sys, 'frozen', False))


def _own_exe() -> str:
    return os.path.abspath(sys.executable)


class FlexiKeyApp:
    def __init__(self):
        self._started_at = time.monotonic()
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName("FlexiKey")
        self.app.setOrganizationName("FlexiKey")
        for effect in (
            Qt.UIEffect.UI_AnimateCombo,
            Qt.UIEffect.UI_AnimateMenu,
            Qt.UIEffect.UI_FadeMenu,
            Qt.UIEffect.UI_AnimateTooltip,
        ):
            self.app.setEffectEnabled(effect, False)

        self._instance_lock = QLockFile(os.path.join(QDir.tempPath(), 'FlexiKey.single.lock'))
        self._instance_lock.setStaleLockTime(10000)
        if not self._instance_lock.tryLock(100):
            if _try_raise_existing():
                sys.exit(0)
            self._instance_lock.removeStaleLockFile()
            if not self._instance_lock.tryLock(100):
                log_info("FlexiKey zaten calisiyor, ikinci ornek kapatildi")
                sys.exit(0)

        # Güncelleme sonrası ilk açılışlar "deneme"dir (yeni sürüm açılışta ölürse eskisi geri gelir)
        self._updating = False   # bu süreç kendini güncelledi ve çıkıyor: sağlıklı sayma/yan dosya temizliği yapılmaz
        self._updated_from = self_update.updated_from(sys.argv)
        self._self_update_startup()

        # Single instance local server
        from PyQt6.QtNetwork import QLocalServer
        QLocalServer.removeServer('FlexiKey.SingleInstanceServer')
        self._local_server = QLocalServer()
        self._local_server.listen('FlexiKey.SingleInstanceServer')
        self._local_server.newConnection.connect(self._on_single_instance_connection)

        # Set application icon
        icon_path = self.get_resource_path(os.path.join('assets', 'icons', 'keyboard.png'))
        if os.path.exists(icon_path):
            self.app.setWindowIcon(QIcon(icon_path))

        # Initialize managers
        self.settings_manager = SettingsManager()
        # "İlk kurulum" = ayar dosyası HİÇ yok. Dosya oluşmadan ÖNCE (ilk yükleme/kayıttan önce) sorulur.
        first_run = self.settings_manager.is_first_run()
        self.theme_manager = ThemeManager(self.app)
        # Özel hata/bilgi/soru kutuları (Qt'nin yerleşik kutusu yok): paleti her açılışta temadan/vurgudan okur
        configure_message_box(
            palette_provider=self.theme_manager.get_palette,
            app_icon_provider=lambda: QApplication.windowIcon(),
            lang_provider=lambda: get_active_language(),
        )
        self.hotkey_manager = HotkeyManager()

        # Initialize notification manager
        self.notification_manager = NotificationManager()

        # Initialize update checker
        self.update_checker = UpdateChecker()
        self.update_checker.update_available.connect(self._on_update_available)

        # Initialize update installer (hata iletileri arayüz dilinde)
        self.update_installer = UpdateInstaller(language=self._lang)
        self.update_installer.download_progress.connect(self._on_download_progress)
        self.update_installer.download_complete.connect(self._on_download_complete)
        self.update_installer.download_failed.connect(self._on_download_failed)
        self.update_installer.install_started.connect(self._on_install_started)
        self.update_installer.install_complete.connect(self._on_install_complete)
        self.update_installer.install_failed.connect(self._on_install_failed)

        # Update dialog reference
        self.update_dialog = None
        self.download_thread = None            # BackgroundJob: sürmekte olan indirme (iptal/bitişte None)
        self.install_thread = None             # BackgroundJob: sürmekte olan kurulum
        self._pending_update = None
        self._ready_package = None             # {'version', 'path'}: indirilmiş ama henüz kurulmamış paket
        self._update_cancelled = False
        self._last_progress = (0, 0, 0.0)      # pencere sonradan açılırsa ilerlemeyi hemen gösterir
        self._auto_update_timer = None

        # Create main window
        self.main_window = MainWindow(
            self.settings_manager,
            self.theme_manager,
            self.hotkey_manager,
            self.notification_manager,
            self.update_checker
        )
        self.main_window.update_requested.connect(self.show_pending_update)
        QTimer.singleShot(0, lambda: self.hotkey_manager.attach_window(self.main_window))

        # Initialize system tray
        self.tray_manager = TrayManager(
            self.main_window,
            self.theme_manager,
            self.hotkey_manager
        )
        self.main_window.tray_manager = self.tray_manager

        # Tray icon'u notification manager'a bağla
        self.notification_manager.set_tray_icon(self.tray_manager.tray_icon)

        # Load settings and apply
        self.load_settings()

        # İlk kurulumda "Açılışta Başlat" AÇIK (mevcut kullanıcıların ayarı değişmez)
        self._apply_first_run_defaults(first_run)

        # Windows başlangıcında registry yolunu güncelle (EXE taşınmışsa)
        self._update_startup_registry()

        # Start hotkey manager with delay
        QTimer.singleShot(1500, self._start_hotkeys)

        # Start update checker (if enabled) - non-blocking
        QTimer.singleShot(2000, self.update_checker.start)

        # Güncellemeden gelen yeniden başlatma: kullanıcıya "vX sürümüne güncellendi" de
        if self._updated_from:
            QTimer.singleShot(2500, self._announce_updated)

    def _apply_first_run_defaults(self, first_run: bool):
        """İlk kurulumda (ayar dosyası hiç yokken) "Açılışta Başlat" AÇILIR; yalnızca derlenmiş uygulamada (kaynaktan çalışan
        geliştirici kopyası kendini otomatik başlatmaya kaydetmez). Ayar dosyası hemen yazılır: sonraki açılış "ilk kurulum"
        sayılmaz, kullanıcı ayarı kapatırsa geri açılmaz."""
        if not (first_run and _is_frozen()):
            return
        settings = self.settings_manager.load_settings()
        if startup.apply_first_run_default(True, True, minimized=bool(settings.get('start_minimized', True))):
            log_info("Ilk kurulum: Acilista Baslat acildi")
        self.settings_manager.save_settings(settings)

    def _lang(self) -> str:
        from src.utils.locales import get_active_language
        return getattr(getattr(self, 'main_window', None), "lang", None) or get_active_language()

    # ------------------------------------------------------------------ kendini güncelleme: açılış ve kapanış
    def _self_update_startup(self):
        """Güncellemeden sonraki ilk açılışlar "deneme"dir: yeni sürüm iki kez açılışta ölürse eski exe geri gelir ve bu
        sürüm bir daha önerilmez. Tek kopya kilidi alındıktan SONRA çalışır: kilide takılıp çıkan ikinci başlatmalar
        "açılış" sayılıp ÇALIŞAN yeni sürümü geri aldırmasın."""
        if not _is_frozen():
            return
        exe = _own_exe()
        guard = self_update.startup_guard(exe, UpdateChecker.CURRENT_VERSION)
        if guard == self_update.Guard.ROLLED_BACK:
            log_info("Yeni sürüm açılışta çalışmadı: önceki sürüm geri getirildi ve yeniden başlatılıyor")
            try:
                self._instance_lock.unlock()
            except Exception:
                pass
            try:
                self_update.spawn(exe, ["--minimized"])
            except self_update.PackageError as e:
                log_info(f"Önceki sürüm başlatılamadı: {e}")
            sys.exit(0)
        QTimer.singleShot(int(self_update.HEALTHY_AFTER_SECONDS * 1000), self._confirm_healthy)
        self.app.aboutToQuit.connect(self._on_about_to_quit)

    def _confirm_healthy(self):
        """Yeni sürüm yeterince çalıştı: güncellemenin bıraktığı `.old` ve yan dosyalar silinir."""
        if _is_frozen() and not self._updating:
            self_update.confirm_healthy(_own_exe())

    def _on_about_to_quit(self):
        """Temiz çıkış: açılıştan en az 10 sn sonra çıkılıyorsa yeni sürüm sağlıklı sayılır. Kendini güncelleyip çıkan
        süreç bunu YAPMAZ (yan dosyalar yeni sürümün denemesine aittir). Sürmekte olan indirme de bırakılır."""
        try:
            self.update_installer.cancel()
        except Exception:
            pass
        if _is_frozen() and not self._updating and time.monotonic() - self._started_at >= 10:
            self_update.confirm_healthy(_own_exe())

    def _announce_updated(self):
        """`--updated <eski sürüm>` ile açıldık: tepsi balonuyla "vX sürümüne güncellendi" de."""
        from src.utils.locales import t
        from PyQt6.QtWidgets import QSystemTrayIcon
        version = UpdateChecker.CURRENT_VERSION
        if not self._updated_from or self._updated_from == version:
            return
        lang = self._lang()
        message = t("update_installed_toast", lang).format(app=t("app_title", lang), version=version)
        log_info(f"Guncelleme tamamlandi: v{self._updated_from} -> v{version}")
        try:
            self.tray_manager.tray_icon.showMessage(t("app_title", lang), message, QSystemTrayIcon.MessageIcon.Information, 8000)
        except Exception:
            pass

    def load_settings(self):
        """Kaydedilmiş ayarları yükle ve uygula"""
        settings = self.settings_manager.load_settings()

        # Apply theme & accent
        theme = settings.get('theme', 'system')
        accent = settings.get('accent', 'blue')

        # If theme is 'system', detect system theme
        if theme == 'system':
            from src.gui.main_window import is_system_dark_mode
            is_dark = is_system_dark_mode()
            actual_theme = 'dark' if is_dark else 'light'
            self.theme_manager.set_theme(actual_theme, accent)
        else:
            actual_theme = 'dark' if 'dark' in theme else 'light'
            self.theme_manager.set_theme(actual_theme, accent)

        # Show in tray on startup
        # Ayarlara VEYA komut satırı argümanına bak
        should_min = settings.get('start_minimized', False)
        if "--minimized" in sys.argv:
            should_min = True
        if self_update.wants_window(sys.argv):
            should_min = False   # güncellemeden önce pencere açıktı: yeni sürüm de açık gelir ("simge durumunda başlat"ı geçersiz kılar)

        if should_min:
            self.main_window.hide()
        else:
            self.main_window.show()

    def _start_hotkeys(self):
        """Kısayol ve genişletmeleri yükle, dinleyiciyi başlat"""
        settings = self.settings_manager.load_settings()

        # Kayıt başına hata yalıtımı: tek bozuk kayıt diğer kısayolları öldürmez.
        counts = register_saved_items(settings, self.hotkey_manager)

        self.hotkey_manager.start()
        log_info(
            f"Kisayollar yuklendi: {counts['hotkeys']} adet"
            f" (atlanan: {counts['hotkeys_failed']}), genisletme: {counts['expansions']}"
            f" (atlanan: {counts['expansions_failed']})"
        )
        self._show_settings_warnings()

    def _show_settings_warnings(self):
        """Ayar dosyası kurtarma/atlama uyarılarını (varsa) tepsi balonuyla göster.

        Bildirimler kapalı olsa bile gösterilir: bu, veri kaybı riski olan bir durumdur.
        """
        warnings = SettingsManager.pop_warnings()
        if not warnings:
            return
        from src.utils.locales import get_active_language, t
        from PyQt6.QtWidgets import QSystemTrayIcon
        lang = getattr(self.main_window, "lang", None) or get_active_language()
        for kind, detail in warnings:
            message = format_settings_warning(kind, detail, lang)
            log_info(f"Ayar uyarisi: {message}")
            try:
                self.tray_manager.tray_icon.showMessage(
                    t("settings_warn_title", lang), message,
                    QSystemTrayIcon.MessageIcon.Warning, 15000,
                )
            except Exception:
                pass

    def get_resource_path(self, relative_path):
        """Resource path için - EXE ve normal çalışma için"""
        try:
            base_path = sys._MEIPASS
        except Exception:
            from src.utils.helpers import get_application_path
            base_path = get_application_path()
        return os.path.join(base_path, relative_path)

    # ------------------------------------------------------------------ güncelleme akışı
    def _on_update_available(self, version: str, download_url: str, release_notes: str,
                            is_mandatory: bool, file_size, checksum: str):
        """Sessiz denetim yeni sürüm buldu: pop-up AÇILMAZ. Sürüm başlık çubuğundaki "Güncelle" düğmesinde ve
        tepsinin en üstündeki "Güncelle · vX" satırında görünür; ikisi de güncelleme penceresini açar. "Otomatik kur"
        açıksa uygulama kullanılmıyorken kendiliğinden kurulur."""
        previous = (self._pending_update or {}).get('version')
        self._pending_update = {
            'version': version,
            'download_url': download_url,
            'file_size': file_size,
            'checksum': checksum,
            'release_notes': release_notes,
            'is_mandatory': is_mandatory,
        }
        if previous and previous != version:
            self._discard_ready_package()   # eski sürümün hazır paketi yeni sürüme kurulmasın
        self.main_window.set_update_available(version)
        self.tray_manager.set_update_available(version)

        # Zorunlu güncellemeler kullanıcı arayüzünü kesmeden arka planda kurulur.
        if is_mandatory:
            self._start_silent_update()
            return

        self._schedule_auto_update()

    def _discard_ready_package(self):
        self._ready_package = None
        try:
            self.update_installer.discard_package()
        except Exception:
            pass

    def _download_running(self) -> bool:
        return self.download_thread is not None and self.download_thread.isRunning()

    def _install_running(self) -> bool:
        return self.install_thread is not None and self.install_thread.isRunning()

    def _update_busy(self) -> bool:
        """İndirme ya da kurulum sürüyor mu (aynı anda ikinci iş başlamasın)."""
        return self._download_running() or self._install_running()

    def _window_visible(self) -> bool:
        """Ana pencere ekranda mı (gizli/tepside ya da simge durumunda değil)? Kurulumdan sonra yeni sürüm bunu korur."""
        window = self.main_window
        return bool(window.isVisible() and not window.isMinimized())

    # ------------------------------------------------------------------ otomatik kurulum (kullanılmıyorken)
    AUTO_UPDATE_POLL_MS = 30_000
    IDLE_SECONDS = 120
    INSTALL_DELAY_MS = 800   # pencere açıkken "İndirme tamamlandı" yazısı kısa süre görünsün

    @staticmethod
    def update_is_idle(window_shown: bool, modal_open: bool,
                       seconds_since_activity: float, idle_seconds: float = 120.0) -> bool:
        """Uygulama "kullanılmıyor" mu: pencere ekrandaysa (gizli/simge durumunda değilse), bir diyalog açıksa ya da
        son kısayol kullanımı yeniyse değil (kurulum kısa süre uygulamayı yeniden başlatır)."""
        if modal_open or window_shown:
            return False
        return seconds_since_activity >= idle_seconds

    def _is_idle_for_update(self) -> bool:
        if self.update_dialog is not None:
            return False   # kullanıcı güncelleme penceresine bakıyor
        window = self.main_window
        last = getattr(window, 'last_activity', 0.0)
        since = (time.monotonic() - last) if last else float('inf')
        # Genişletmeler, sessiz komutlar ve medya tuşları last_activity'yi güncellemez: sistemdeki son girdi de sayılır
        since = min(since, self._system_idle_seconds())
        return self.update_is_idle(
            window.isVisible() and not window.isMinimized(),
            QApplication.activeModalWidget() is not None, since, self.IDLE_SECONDS,
        )

    @staticmethod
    def _system_idle_seconds() -> float:
        """Kullanıcının bilgisayara son dokunmasından bu yana geçen süre (yalnızca Windows; okunamazsa 0 = meşgul)."""
        if sys.platform != "win32":
            return float('inf')
        from src.core import win_input
        return win_input.system_idle_seconds()

    def _auto_update_enabled(self) -> bool:
        settings = self.settings_manager.load_settings()
        return bool(settings.get('auto_update_check', True) and settings.get('auto_update_install', True))

    def _schedule_auto_update(self):
        """"Otomatik kur" açıksa uygun ana kadar yoklar (kapalıysa hiçbir şey yapmaz)."""
        if not self._auto_update_enabled():
            return
        if self._auto_update_timer is None:
            self._auto_update_timer = QTimer()
            self._auto_update_timer.timeout.connect(self._try_auto_update)
        if not self._auto_update_timer.isActive():
            self._auto_update_timer.start(self.AUTO_UPDATE_POLL_MS)
        QTimer.singleShot(3000, self._try_auto_update)

    def _stop_auto_update_timer(self):
        if self._auto_update_timer is not None:
            self._auto_update_timer.stop()

    def _try_auto_update(self):
        if not self._pending_update:
            return
        if not self._auto_update_enabled():
            self._stop_auto_update_timer()
            return
        if not _is_frozen():
            # Kaynaktan çalışırken değiştirilecek exe yok: otomatik kurulum desteklenmez (düğme satır içi ileti verir)
            self._stop_auto_update_timer()
            return
        if self._update_busy() or self.update_dialog is not None:
            return
        if not self._pending_update.get('is_mandatory') and self._declined_version() == str(self._pending_update.get('version')):
            # Kullanıcı bu sürüme "Daha Sonra" dedi (ya da indirmeyi iptal etti): kendiliğinden kurulmaz.
            # Tepsi/düğme kalır, elle kurulabilir; daha yeni bir sürüm yine otomatik kurulur.
            log_info("Kullanıcı bu güncellemeyi erteledi: otomatik kurulmayacak (düğmeyle elle kurulabilir)")
            self._stop_auto_update_timer()
            return
        ready = self._has_ready_package()
        if not ready and not update_has_checksum(self._pending_update.get('checksum')):
            # Onaysız kurulumu kimse görmeden yapma: sunucu sağlama toplamı vermediyse yalnızca düğmeyle kurulur.
            log_info("Güncelleme sağlama toplamı içermiyor: otomatik kurulmayacak (düğmeyle elle kurulabilir)")
            self._stop_auto_update_timer()
            return
        if not self._is_idle_for_update():
            return
        self._stop_auto_update_timer()
        if ready:
            log_info("Uygulama kullanılmıyor: indirilmiş güncelleme kuruluyor")
            self._start_installation()
            return
        log_info("Uygulama kullanılmıyor: güncelleme sessizce kuruluyor")
        self._start_silent_update()

    def _declined_version(self) -> str:
        """Kullanıcının "Daha Sonra" dediği (ya da indirmeyi iptal ettiği) sürüm: otomatik kurulum onu kurmaz."""
        try:
            return str(self.settings_manager.load_settings().get('declined_update_version') or '')
        except Exception:
            return ''

    def _start_silent_update(self):
        """Kullanıcı onayı beklemeden (otomatik/zorunlu) indirme: pencere yok; hata olursa tepsi balonu."""
        info = self._pending_update
        if not info:
            return
        self._start_update_download(info['version'], info['download_url'], info['file_size'], info['checksum'])

    # ------------------------------------------------------------------ güncelleme penceresi
    def show_pending_update(self):
        """Başlık çubuğundaki düğmeden / tepsiden seçilen güncelleme ayrıntı penceresini aç (zaten açıksa öne getir)."""
        if not self._pending_update:
            return
        if self.update_dialog is not None:
            self._present_dialog(self.update_dialog)
            return
        self._open_update_dialog()

    def _present_dialog(self, dialog):
        """Pencereyi öne getir: ana pencere gizliyken de (tepsiden açıldıysa) görünür ve etkin olsun."""
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _open_update_dialog(self):
        """Kullanıcı düğmeye/tepsiye tıkladı: sürüm, boyut, sürüm notları ve "Şimdi Güncelle" ile ayrıntı penceresi."""
        from src.gui.update_dialog import UpdateDialog
        info = self._pending_update
        if not info:
            return
        # Ana pencere gizliyken sahipsiz açılır: görev çubuğunda kendi düğmesi olur (tepsiden açılınca kaybolmaz)
        dialog = UpdateDialog(
            version=info['version'],
            release_notes=info.get('release_notes', ''),
            is_mandatory=False,
            parent=self.main_window if self._window_visible() else None,
            lang=self._lang(),
            file_size=info.get('file_size'),
            current_version=UpdateChecker.CURRENT_VERSION,
        )
        self.update_dialog = dialog
        dialog.update_accepted.connect(self._on_dialog_update_accepted)
        dialog.update_deferred.connect(self._defer_update)
        dialog.update_cancelled.connect(self._cancel_update_download)
        dialog.finished.connect(lambda *_: self._on_dialog_finished(dialog))
        if self._download_running():
            # Sessiz (otomatik/zorunlu) indirme sürüyor: pencere ilerlemeyi gösterir
            dialog.show_downloading()
            dialog.update_download_progress(*self._last_progress)
        elif self._install_running():
            dialog.show_installing()
        self._present_dialog(dialog)

    def _on_dialog_finished(self, dialog):
        if self.update_dialog is dialog:
            self.update_dialog = None
        dialog.deleteLater()

    def _has_ready_package(self) -> bool:
        ready, info = self._ready_package, self._pending_update
        return bool(ready and info and ready.get('version') == info.get('version')
                    and ready.get('path') and os.path.exists(ready['path']))

    def _on_dialog_update_accepted(self):
        """"Şimdi Güncelle" / "Tekrar dene"."""
        info = self._pending_update
        if not info:
            return
        self._update_cancelled = False
        if self._has_ready_package():
            # Paket zaten indirilmişti (kurulum, kullanıcı geri döndüğü için bekletilmişti): yeniden indirme
            self.update_dialog.show_download_complete()
            QTimer.singleShot(self.INSTALL_DELAY_MS, self._start_installation)
            return
        self._start_update_download(info['version'], info['download_url'], info['file_size'], info['checksum'])

    # ------------------------------------------------------------------ indirme
    def _start_update_download(self, version: str, download_url: str, file_size, checksum: str):
        """İndirmeyi arka planda başlat (önce kurulum bu çalıştırmada mümkün mü diye bakılır)."""
        # Kullanıcının en son isteği güncellemeyi istemek: önceki iptal bayrağı geçersiz
        self._update_cancelled = False
        # Zaten çalışan bir indirme/kurulum varsa ikincisini başlatma (aynı dosyaya yazarlardı)
        if self._update_busy():
            log_info("Güncelleme indirmesi zaten sürüyor; ikinci indirme başlatılmadı")
            return

        # Kaynaktan çalışıyorsak ya da klasör yazılamıyorsa indirme boşa gitmesin: satır içi ileti
        problem = self.update_installer.preflight_error()
        if problem:
            self._show_update_failure(problem)
            return

        self._last_progress = (0, 0, 0.0)
        if self.update_dialog:
            self.update_dialog.show_downloading()

        # İndirme ayrı iş parçacığında: arayüz donmaz
        self.download_thread = BackgroundJob(
            self.update_installer.download_update,
            download_url,
            file_size if file_size and file_size > 0 else None,
            checksum if checksum else None,
        )
        self.download_thread.start()

    def _on_download_progress(self, downloaded, total, speed_mbps: float):
        """Handle download progress update"""
        self._last_progress = (downloaded, total, speed_mbps)
        if self.update_dialog:
            self.update_dialog.update_download_progress(downloaded, total, speed_mbps)

    def _on_download_complete(self, file_path: str):
        """İndirme bitti (sağlama toplamı ve paket biçimi doğrulandı): kurulumu başlat."""
        if self._update_cancelled:
            log_info("Güncelleme kullanıcı tarafından iptal edilmişti; kurulum başlatılmadı")
            try:
                os.remove(file_path)
            except OSError:
                pass
            return
        self.download_thread = None
        version = (self._pending_update or {}).get('version', '')
        self._ready_package = {'version': version, 'path': file_path}
        if self.update_dialog:
            self.update_dialog.show_download_complete()
        # Kurulum kısa gecikmeyle başlar (diyaloglu ve diyaloksuz akış); meşguliyet kurulumdan hemen önce yeniden bakılır
        QTimer.singleShot(self.INSTALL_DELAY_MS if self.update_dialog else 0, self._start_installation)

    def _notify_mandatory_install(self):
        """Arka planda kurulan güncellemede kullanıcıyı bilgilendir (uygulama yeniden başlayacak).
        "Zorunlu" yalnızca sunucu öyle işaretlediyse yazılır; otomatik (isteğe bağlı) kurulumda nötr metin."""
        from src.utils.locales import t
        from PyQt6.QtWidgets import QSystemTrayIcon
        lang = self._lang()
        mandatory = bool((getattr(self, '_pending_update', None) or {}).get('is_mandatory'))
        message = t("update_mandatory_installing" if mandatory else "update_auto_installing", lang)
        log_info("Zorunlu guncelleme indirildi, kuruluyor" if mandatory else "Guncelleme indirildi, kuruluyor")
        try:
            self.tray_manager.tray_icon.showMessage(
                t("app_title", lang), message, QSystemTrayIcon.MessageIcon.Information, 8000
            )
        except Exception:
            pass

    def _on_download_failed(self, error_message: str):
        """İndirme başarısız: pencere açıksa satır içi hata + "Tekrar dene"; değilse tepsi balonu."""
        self.download_thread = None
        self._show_update_failure(error_message)

    def _show_update_failure(self, message: str):
        """Güncelleme hatası: açılır kutu YOK. Pencere açıksa satır içi (pencere açık kalır), değilse günlük + tepsi balonu."""
        if self.update_dialog is not None:
            self.update_dialog.show_error(message)
        else:
            self._notify_silent_failure(message)

    # ------------------------------------------------------------------ kurulum
    def _start_installation(self):
        """Paketi kur (arka plan iş parçacığı) ve yeni sürümü başlat; başarıda `install_complete` ile temiz çıkış."""
        ready = self._ready_package
        if not ready or self._update_cancelled or self._install_running():
            return
        info = self._pending_update or {}
        if self.update_dialog is None and not info.get('is_mandatory') and not self._is_idle_for_update():
            # Sessiz kurulumun indirmesi sürerken kullanıcı geri döndü (pencere açıldı / kısayol kullandı): şimdi
            # kurma, paket hazır bekler; yeniden boşta olunca (ya da "Güncelle" ile) kurulur
            log_info("Güncelleme indirildi ama uygulama kullanılıyor: kurulum boşta olunca yapılacak")
            self._schedule_auto_update()
            return

        if self.update_dialog:
            self.update_dialog.show_installing()
        else:
            self._notify_mandatory_install()

        self.install_thread = BackgroundJob(
            self.update_installer.install_update,
            ready['path'],
            visible=self._window_visible(),
            old_version=UpdateChecker.CURRENT_VERSION,
        )
        self.install_thread.start()

    def _on_install_started(self):
        """Handle installation started"""
        pass

    def _on_install_complete(self):
        """Yeni sürüm başlatıldı (eski exe `.old` oldu): TEMİZ çıkış yap, yeni süreç bizi bekliyor."""
        self.install_thread = None
        self._ready_package = None
        self._updating = True
        if self.update_dialog:
            self.update_dialog.show_restarting()
        self._quit_for_update()

    def _quit_for_update(self):
        """Çıkış menüsüyle aynı yol: kısayol dinleyicisi durur, QApplication.quit() ile döngü biter (zorla öldürme yok)."""
        self.update_checker.stop()
        # Görünür pencereyle çıkış, E2E'de bazı koşularda Qt kapanışında yerel `access violation` (crash.log) verdi. Yalnızca `hide()` yetmedi
        # (gerçek exe, 100'er koşu: düzeltmesiz 16, yalnız hide() 5, hide()+deleteLater() 0 çökme): `hide()` `finished` sinyalini vermez, yani
        # `_on_dialog_finished`in `deleteLater()`ı çalışmaz; HWND'li saydam pencere Python sonlandırmasına dek yaşar ve yıkım sırası rastgele
        # kalırdı. Pencere önce gizlenir (`hide()` closeEvent'i çağırmaz: "Kuruluyor" penceresi reddedemez), sonra QApplication yaşarken yok
        # edilir (Qt `exec()` sonunda bekleyen DeferredDelete olaylarını işler).
        dialog = self.update_dialog
        if dialog is not None:
            self.update_dialog = None
            dialog.hide()
            dialog.deleteLater()
        close = getattr(self.main_window, 'close_app', None)
        if callable(close):
            close()
        else:
            QApplication.quit()
        # Kurulum sırasında açık "Güncelleme" penceresi kapanmayı reddeder; Qt 6'da `quit()` görünür pencereleri kapatmayı dener ve
        # reddeden olursa çıkış İPTAL olur (E2E'de eski süreç sonsuza dek yaşadı). `exit(0)` pencerelerden bağımsızdır (aboutToQuit yine çalışır).
        QCoreApplication.exit(0)
        if _is_frozen():
            self_update.arm_exit_watchdog()  # çıkış yine de takılırsa sert çıkış: yeni sürüm bizi bekliyor

    def _on_install_failed(self, error_message: str):
        """Kurulum başarısız: uygulama olduğu gibi çalışmaya devam eder; pencere açıksa satır içi hata + "Tekrar dene"."""
        self.install_thread = None
        self._ready_package = None
        self._show_update_failure(error_message)

    def _notify_silent_failure(self, error_message: str):
        """Arka plan güncellemesi başarısız: pop-up yok; günlük + tepsi balonu (düğme yeniden denemek için durur)."""
        from src.utils.locales import t
        from PyQt6.QtWidgets import QSystemTrayIcon
        log_info(f"Sessiz güncelleme başarısız: {error_message}")
        lang = self._lang()
        try:
            self.tray_manager.tray_icon.showMessage(
                t("app_title", lang), t("update_auto_failed", lang), QSystemTrayIcon.MessageIcon.Warning, 8000
            )
        except Exception:
            pass

    def _defer_update(self):
        """Pencere hiç başlatılmadan kapandı ("Daha Sonra", Esc, X): sürüm tepsi ve başlıkta beklemeye devam eder."""
        if self._pending_update:
            self.settings_manager.update(declined_update_version=self._pending_update['version'])
            self.tray_manager.set_update_available(self._pending_update['version'])

    def _cancel_update_download(self):
        """İndirme sürerken pencere kapatıldı/iptal edildi: indirme durur, kurulum YAPILMAZ (uygulama habersiz
        yeniden başlamaz); hemen yeniden indirme başlatılabilir."""
        self._update_cancelled = True
        if self._pending_update:
            # İptal de "şimdi değil" demektir: arkadan yeniden indirmeye kalkmasın
            self.settings_manager.update(declined_update_version=self._pending_update['version'])
        self.update_installer.cancel()
        self.download_thread = None
        self._ready_package = None
        self.update_installer.discard_package()

    def _parse_run_value_path(self, registry_value: str) -> str:
        """Run anahtarındaki EXE yolunu ayıkla (tırnak ve --minimized dahil)"""
        value = (registry_value or '').strip()
        if value.startswith('"'):
            end = value.find('"', 1)
            if end > 0:
                return value[1:end]
        return value.split(' --')[0].strip().strip('"')

    def _update_startup_registry(self):
        """Windows başlangıcında registry yolunu güncelle (EXE taşınmışsa)"""
        if sys.platform != "win32":
            return
        try:
            import winreg

            # Registry'de FlexiKey var mı kontrol et
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                   r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                                   winreg.KEY_READ | winreg.KEY_SET_VALUE)

                try:
                    registry_value, _ = winreg.QueryValueEx(key, "FlexiKey")
                    winreg.CloseKey(key)

                    # Registry'deki yol ile mevcut EXE yolu eşleşiyor mu kontrol et
                    if getattr(sys, 'frozen', False):
                        current_exe_path = os.path.abspath(sys.executable)
                        registry_path = self._parse_run_value_path(registry_value)

                        # Yollar eşleşmiyorsa güncelle
                        if os.path.normpath(registry_path).lower() != os.path.normpath(current_exe_path).lower():
                            # Ayarları yükle (--minimized durumunu kontrol etmek için)
                            settings = self.settings_manager.load_settings()
                            start_minimized = settings.get('start_minimized', False)
                            args = " --minimized" if start_minimized else ""

                            # Registry'yi güncelle
                            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                               r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                                               winreg.KEY_SET_VALUE)
                            new_value = f'"{current_exe_path}"{args}'
                            winreg.SetValueEx(key, "FlexiKey", 0, winreg.REG_SZ, new_value)
                            winreg.CloseKey(key)

                            log_info(f"Registry yolu güncellendi: {current_exe_path}")

                except FileNotFoundError:
                    # Registry'de FlexiKey yok, sorun yok
                    winreg.CloseKey(key)

            except Exception:
                # Registry okuma/yazma hatası - sessizce devam et
                pass

        except Exception:
            # Genel hata - sessizce devam et
            pass

    def _on_single_instance_connection(self):
        conn = self._local_server.nextPendingConnection()
        if conn:
            conn.disconnected.connect(conn.deleteLater)
            conn.readyRead.connect(lambda: self._raise_window())
            self._raise_window()

    def _raise_window(self):
        if hasattr(self, 'main_window') and self.main_window:
            self.main_window.showNormal()
            self.main_window.show()
            self.main_window.activateWindow()
            self.main_window.raise_()

    def _teardown_qt_objects(self):
        """Çıkışta (her çıkış yolunda) GUI nesnelerini `exec()` sonrası, Python kapanışından ÖNCE, BİLİNEN sırayla yok eder: güncelleme penceresi ->
        tepsi menüleri -> tepsi yöneticisi -> ana pencere (tepsi simgesi ana pencerenin çocuğudur; birlikte gider).

        Neden: Python kapanırken PyQt6'nın QtCore temizliği sahipsiz (Python'a ait) QObject'leri (ana pencere, tepsi, 6 menü, pencere...) harita
        sırasıyla siler; bu sıra koşudan koşuya değişir ve gerçek exe'de nadiren `access violation` (crash.log) ile çıkılıyordu (E2E, gerçek exe:
        güncelleyen eski süreç düzeltmesiz %12-16, yalnız hide()+deleteLater() %0,6; bu yıkım düzeltmesiz pencereyle bile 0/80; ana pencere
        AÇIKKEN sıradan çıkışta da bir kez görüldü). Silinmiş nesneler atlanır; QObject olmayanlar (test sahteleri) dokunulmaz."""
        from PyQt6 import sip
        from PyQt6.QtCore import QObject
        tray = getattr(self, 'tray_manager', None)
        victims = [
            getattr(self, 'update_dialog', None),
            getattr(tray, 'quick_menu', None), getattr(tray, 'lang_menu', None), getattr(tray, 'theme_menu', None), getattr(tray, 'menu', None),
            tray, getattr(self, 'main_window', None),
        ]
        for obj in victims:
            try:
                if isinstance(obj, QObject) and not sip.isdeleted(obj):
                    sip.delete(obj)
            except Exception:
                pass

    def run(self):
        """Uygulamayı çalıştır"""
        code = self.app.exec()
        try:
            self._instance_lock.unlock()
            self._local_server.close()
        except Exception:
            pass
        self._teardown_qt_objects()
        return code
