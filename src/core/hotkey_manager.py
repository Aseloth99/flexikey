"""
Hotkey Manager - Rich text desteği ile

Platformdan bağımsız mantık burada (kısayol kaydı, metin genişletme eşleştirme, gizlilik tamponu,
yıkıcı eylem onayı, eylem çalıştırma). Platforma özgü her şey arka uçlarda:

  input_backend.py    küresel kısayol / tuş enjeksiyonu / yazılan tuş akışı (Windows: keyboard,
                      macOS+Linux: pynput; desteklenmeyen ortamda UnavailableBackend)
  clipboard_utils.py  pano (Windows CF_HTML, diğerleri Qt)
  system_commands.py  yerleşik komut tabloları (Windows / macOS / Linux)
  launcher.py         macOS/Linux program-dosya-URL başlatma planı (kabuksuz)
  win_input.py, win_hotkey.py  Windows'a özgü ctypes / RegisterHotKey
"""

import os
import shutil
import subprocess
import threading
import time
import webbrowser

from PyQt6.QtCore import QObject, QThread, pyqtSignal, QTimer, Qt, QUrl
from PyQt6.QtWidgets import QApplication

from src.core import clipboard_utils
from src.core import input_backend
from src.utils import platform_utils
from src.core import system_commands
from src.core import win_input
from src.core.action_policy import (
    DESTRUCTIVE_COMMANDS, shell_argv, shell_fallback_allowed, validate_user_command,
)
from src.utils.helpers import log_error, log_info, log_warning
from src.core.input_injector import INPUT_INJECTOR, _InputInjector  # noqa: F401  (INPUT_INJECTOR: geriye uyumluluk)
from src.core.launcher import CommandUnavailable, plan_launch
from src.utils.locales import t
from src.core.win_hotkey import WinHotkeyFilter, WinHotkeyTable, parse_win_hotkey

# Gizlilik: zengin metin genişletme tamponu en çok bu kadar saniye hareketsiz kalabilir
RICH_BUFFER_IDLE_SECONDS = 5.0

# Eski ad (geriye uyumluluk): parola alanı denetimi artık win_input'ta
focused_control_is_password = win_input.focused_control_is_password

# Windows konsol kodlaması
win_input.ensure_utf8_console()


class HotkeyWorker(QObject):
    """Klavye worker"""

    action_triggered = pyqtSignal(str, str, str, bool)  # type, value, shortcut, is_rich

    def __init__(self, backend=None, clipboard=None, platform=None):
        super().__init__()
        self.backend = backend if backend is not None else input_backend.create_backend(platform)
        self.clipboard = clipboard   # None: ilk yapıştırmada platforma göre kurulur
        self._platform = platform
        # shortcut -> (normalized, action_type, action_value, is_rich, remove_handle)
        self.hotkeys = {}
        self.expansions = {}
        self.running = True
        self.rich_expansions = {}  # Rich text genişletmeleri için: {trigger: html_content}
        # Arka uç kısaltmaları kendisi eşleştirmiyorsa (macOS/Linux) düz metin genişletmeleri de
        # yazılan tuş akışıyla (aşağıdaki tampon) eşleştirilir: {trigger: replacement}
        self.typed_expansions = {}
        self.last_typed = ""  # Son yazılan karakterleri takip et
        self.hook_handle = None  # Keyboard hook handle
        self.pending_rich_expansion = None  # Bekleyen rich text genişletme
        self.pynput_listener = None  # Yazılan tuş dinleyicisi (start/stop/is_alive)
        self.buffer = ""  # Yazılan karakterleri buffer'da tut
        self.buffer_lock = threading.Lock()  # Buffer için lock
        self._buffer_last_time = 0.0  # Tampona son karakter eklenme zamanı (time.monotonic)
        self._word_overflow = False   # Tampon taştı: kelime en uzun tetikleyiciden uzun
        self._taken_word_overflow = False
        self.rich_text_marker = ""  # Özel Unicode karakter (Private Use Area)
        self.is_pasting = False  # Rich text yapıştırma işlemi devam ediyor mu?
        self.pasting_lock = threading.Lock()  # Pasting flag için lock
        self._refresh_lock = threading.Lock()  # Hook yenileme kilidi
        self._last_trigger = {}  # shortcut -> timestamp (cift tetiklemeyi engelle)
        self._trigger_lock = threading.Lock()
        # Hook saglik kontrolu icin
        self._last_event_time = 0.0  # Hook'un gordugu son klavye olayi
        self._probe_time = 0.0       # Son saglik testinin zamani
        self._probe_hook_handle = None
        self._probe_misses = 0

    def _make_hotkey_callback(self, action_type: str, action_value: str, shortcut: str, is_rich: bool):
        """Hotkey callback oluştur — ayni kisayol 400ms icinde tekrar tetiklenmez"""
        def callback():
            now = time.time()
            with self._trigger_lock:
                last = self._last_trigger.get(shortcut, 0)
                if now - last < 0.4:
                    return
                self._last_trigger[shortcut] = now
            self.action_triggered.emit(action_type, action_value, shortcut, is_rich)
        return callback

    def _clear_keyboard_hotkeys(self):
        """Arka ucun tüm hotkey durumunu güvenli temizle (Windows: keyboard.unhook_all + _hotkeys)"""
        self.backend.unhook_all()

    def _on_any_key(self, event):
        """Her klavye olayinda zaman damgasi tut (hook canli mi anlamak icin)"""
        self._last_event_time = time.time()
        return None

    def _install_probe_hook(self):
        """Hook sagligini olcen dinleyiciyi kur"""
        try:
            self._probe_hook_handle = self.backend.hook(self._on_any_key)
        except Exception:
            self._probe_hook_handle = None

    def _reregister_all(self):
        """Kisayollari, genisletmeleri ve saglik dinleyicisini yeniden ekle"""
        for shortcut, data in list(self.hotkeys.items()):
            normalized, action_type, action_value, is_rich = data[:4]
            handle = data[4] if len(data) > 4 else None
            if handle is None:
                continue
            try:
                new_handle = self._register_hotkey(
                    shortcut, normalized, action_type, action_value, is_rich, silent=True
                )
                self.hotkeys[shortcut] = (
                    normalized, action_type, action_value, is_rich, new_handle
                )
            except Exception as e:
                log_error(f"Kisayol yenileme hatasi {shortcut}", e)

        if self.backend.native_abbreviations:
            for trigger, (replacement, is_rich) in list(self.expansions.items()):
                if is_rich:
                    continue
                try:
                    self._add_native_abbreviation(trigger, replacement)
                except Exception:
                    pass

        self._install_probe_hook()

    def _system_idle_seconds(self) -> float:
        """Kullanicinin bilgisayara en son dokunmasindan bu yana gecen sure"""
        return win_input.system_idle_seconds()

    def probe_hook_health(self):
        """
        Hook'un gercekten calisip calismadigini test et.
        Zararsiz bir tus olayi (VK_NONAME) enjekte eder; hook canliysa
        bu olayi gorur ve _last_event_time guncellenir. (Yalnizca Windows dusuk seviye kancasi.)
        """
        self._probe_time = 0.0

        if not self.backend.needs_watchdog:
            return

        if not self.running or not self.hotkeys:
            return

        # Hook yakin zamanda gercek bir tus gorduyse zaten calisiyor
        if time.time() - self._last_event_time < 300:
            self._probe_misses = 0
            return

        # Kullanici bilgisayari kullanmiyorsa test etme:
        # enjekte edilen tus uyku/ekran koruyucuyu engellerdi
        if self._system_idle_seconds() > 30:
            return

        try:
            self._probe_time = time.time()
            # VK_NONAME (0xFC): hicbir uygulamada etkisi olmayan rezerve tus
            win_input.send_probe_key()
        except Exception:
            self._probe_time = 0.0

    def verify_hook_health(self):
        """
        Test sonucunu degerlendir. Hook olayi gormediyse Windows hook'u
        dusurmus demektir; OS seviyesinde yeniden kurulur.
        """
        if not self.running or not self._probe_time:
            return

        if self._last_event_time >= self._probe_time:
            self._probe_misses = 0
            return

        # VK_NONAME bazi sistemlerde hook'a ulasmiyor; tek kacirma yetmez
        self._probe_misses += 1
        if self._probe_misses < 3:
            return

        self._probe_misses = 0
        log_info("Klavye hook'u yanit vermiyor - yeniden kuruluyor")
        self._hard_reinstall_hook()

    def _hard_reinstall_hook(self):
        """
        Windows low-level hook'unu sifirdan kurar.
        keyboard kutuphanesi hook'u yalnizca listening=False iken kurdugu icin
        bayragi dusurup tum kayitlari yeniden ekleriz.
        """
        with self._refresh_lock:
            try:
                self.backend.prepare_hard_reinstall()

                # unhook_all -> start_if_necessary -> yeni thread + yeni OS hook
                self._clear_keyboard_hotkeys()
                self._reregister_all()
                self._last_event_time = time.time()
                self._probe_misses = 0
                log_info("Klavye hook'u yeniden kuruldu")
            except Exception as e:
                log_error("Hook yeniden kurma hatasi", e)

    def _should_suppress_hotkey(self, normalized: str) -> bool:
        """Kendi durumunu değiştiren tuşları (Scroll/Caps/Num Lock) yut"""
        key = (normalized or "").strip().lower()
        if '+' in key:
            return False
        return key in ('scroll lock', 'scrolllock', 'caps lock', 'capslock', 'num lock', 'numlock')

    def _register_hotkey(self, shortcut: str, normalized: str, action_type: str,
                         action_value: str, is_rich: bool, silent: bool = False):
        """Tek bir kısayolu arka uca kaydet; remove handle döndür"""
        callback = self._make_hotkey_callback(action_type, action_value, shortcut, is_rich)
        suppress = self._should_suppress_hotkey(normalized)
        remove_handle = self.backend.add_hotkey(
            normalized, callback, suppress=suppress, timeout=0.1
        )
        if not silent:
            log_info(f"Kisayol kaydedildi: {shortcut} -> {normalized} ({action_type})")
        return remove_handle

    def _revive_listener_if_dead(self) -> bool:
        """Dinleyici thread olduysa yeni OS hook kurmaya zorla."""
        return self.backend.revive_if_dead()

    def refresh_registrations(self, force: bool = False):
        """
        Kısayolları yeniden kaydet (sessiz).
        force=True: her seferinde temizle + yeniden ekle (ust uste binmeyi onler).
        """
        if not self.running:
            return

        with self._refresh_lock:
            try:
                revived = self._revive_listener_if_dead()

                if force or revived:
                    self._clear_keyboard_hotkeys()
                    self._reregister_all()

                if self._has_buffered_expansions():
                    if self.pynput_listener is None or not self.pynput_listener.is_alive():
                        try:
                            if self.pynput_listener is not None:
                                self.pynput_listener.stop()
                        except Exception:
                            pass
                        self.pynput_listener = None
                        self._start_pynput_hook()
            except Exception as e:
                log_error("Kayit yenileme hatasi", e)

    def set_backend(self, backend):
        """Girdi arka ucunu değiştir (ör. macOS izni verildikten sonra): tüm kayıtlar yeni arka uca taşınır."""
        with self._refresh_lock:
            old, self.backend = self.backend, backend
            if old is not backend:
                try:
                    old.stop()
                except Exception as exc:
                    log_error("Eski girdi arka ucu durdurulamadi", exc)
            if self.pynput_listener is not None:
                try:
                    self.pynput_listener.stop()
                except Exception:
                    pass
                self.pynput_listener = None
            self._reregister_all()
            if self._has_buffered_expansions():
                self._start_pynput_hook()

    def add_hotkey(self, shortcut: str, action_type: str, action_value: str, is_rich: bool = False):
        """Kısayol ekle"""
        try:
            if shortcut in self.hotkeys:
                self.remove_hotkey(shortcut)

            normalized = self._normalize_shortcut(shortcut)
            handle = self._register_hotkey(shortcut, normalized, action_type, action_value, is_rich)
            self.hotkeys[shortcut] = (normalized, action_type, action_value, is_rich, handle)

        except Exception as e:
            log_error(f"Kisayol ekleme hatasi {shortcut}", e)

    def remove_hotkey(self, shortcut: str):
        """Kısayol sil"""
        try:
            if shortcut not in self.hotkeys:
                return
            data = self.hotkeys[shortcut]
            remove_handle = data[4] if len(data) > 4 else None
            normalized = data[0]
            try:
                if callable(remove_handle):
                    remove_handle()
                elif remove_handle is not None:
                    self.backend.remove_hotkey(normalized)
            except Exception:
                # Fallback: normalize ile silmeyi dene
                try:
                    self.backend.remove_hotkey(normalized)
                except Exception:
                    pass
            del self.hotkeys[shortcut]
        except Exception as e:
            log_error(f"Kisayol silme hatasi {shortcut}", e)

    @staticmethod
    def _html_to_plain_text(html_content: str) -> str:
        from PyQt6.QtGui import QTextDocument
        doc = QTextDocument()
        doc.setHtml(html_content)
        return doc.toPlainText()

    def _add_native_abbreviation(self, trigger: str, replacement: str):
        """Arka ucun kendi düz metin kısaltması."""
        self.backend.add_abbreviation(trigger, replacement)

    def _get_clipboard(self):
        if self.clipboard is None:
            self.clipboard = clipboard_utils.create_clipboard(self._platform)
        return self.clipboard

    def _paste_rich_text(self, html_content: str):
        """Rich text'i clipboard'a kopyalayıp yapıştır; önceki pano içeriğini geri yükler"""
        snapshot = None
        clipboard = None
        clipboard_changed = False
        token = None
        try:
            clipboard = self._get_clipboard()

            # Yapıştırma işlemi başladığını işaretle
            with self.pasting_lock:
                self.is_pasting = True

            plain_text = self._html_to_plain_text(html_content)

            # Önceki pano içeriğini (metin/HTML/RTF) kaydet; kaydedilemezse yine de yapıştır
            try:
                snapshot = clipboard.snapshot()
            except Exception as snap_error:
                log_error("Pano içeriği kaydedilemedi (geri yüklenmeyecek)", snap_error)

            # HTML (Windows: CF_HTML bayt ofsetleri UTF-8'e göre; diğerleri: text/html) + düz metin
            clipboard_changed = True
            token = clipboard.set_rich_text(html_content, plain_text)

            # Clipboard'ın hazır olması için bekle
            time.sleep(0.15)

            # Ctrl+V (macOS'ta Cmd+V) yapıştır
            self.backend.send(self.backend.paste_keys)

            # Yapıştırma işleminin tamamlanması için bekle
            # (yapıştırılan içerik buffer'a eklenmesin diye)
            # HTML içeriğinin uzunluğuna göre bekleme süresini ayarla
            content_length = len(html_content)
            wait_time = min(0.15 + (content_length / 10000), 0.5)  # Maksimum 0.5 saniye
            time.sleep(wait_time)
        except Exception as e:
            log_error("Zengin metin yapıştırılamadı, düz metin yazılıyor", e)
            # Hata durumunda düz metin olarak yaz (is_pasting açık kalır: yazılan karakterler
            # tampona girip genişletmeyi yeniden tetiklemesin)
            try:
                self.backend.write(self._html_to_plain_text(html_content))
            except Exception:
                self.backend.write(html_content)
        finally:
            # Kullanıcının önceki panosunu geri yükle (arada kullanıcı başka bir şey kopyaladıysa dokunma)
            if clipboard_changed and snapshot is not None:
                clipboard.restore(snapshot, token)
            # Yapıştırma işlemi bittiğini işaretle ve buffer'ı temizle
            with self.pasting_lock:
                self.is_pasting = False
            with self.buffer_lock:
                self.buffer = ""

    def add_expansion(self, trigger: str, replacement: str, is_rich: bool = False):
        """Metin genişletme ekle"""
        try:
            if trigger in self.expansions:
                self.remove_expansion(trigger)

            if is_rich:
                # Rich text için: HTML'i clipboard'a kopyalayıp yapıştırma stratejisi
                # Arka ucun kısaltma özelliği geri çağrı desteklemediği için
                # yazılan tuş akışını izleyip space'te HTML yapıştıracağız

                # Rich text genişletmelerini ayrı bir dict'te sakla
                self.rich_expansions[trigger] = replacement
                self.expansions[trigger] = (replacement, is_rich)
                self._ensure_typed_listener()
            elif self.backend.native_abbreviations:
                # Düz metin için arka ucun kendi kısaltması (Windows: keyboard.add_abbreviation)
                self._add_native_abbreviation(trigger, replacement)
                self.expansions[trigger] = (replacement, is_rich)
            else:
                # macOS/Linux: düz metin de yazılan tuş akışıyla eşleştirilir
                self.typed_expansions[trigger] = replacement
                self.expansions[trigger] = (replacement, is_rich)
                self._ensure_typed_listener()

        except Exception as e:
            log_error(f"Genisletme hatasi {trigger}", e)

    def _ensure_typed_listener(self):
        if self.pynput_listener is None:
            self._start_pynput_hook()

    def _focus_is_password_field(self) -> bool:
        return win_input.focused_control_is_password()

    def _has_buffered_expansions(self) -> bool:
        return bool(self.rich_expansions or self.typed_expansions)

    def _max_rich_trigger_length(self) -> int:
        """Tamponda tutulacak en çok karakter: en uzun (zengin veya yazılan-düz) tetikleyici."""
        return max((len(trigger) for trigger in (*self.rich_expansions, *self.typed_expansions)), default=0)

    def _buffer_clear(self):
        with self.buffer_lock:
            self.buffer = ""
            self._word_overflow = False

    def _buffer_append(self, char: str, now: float = None) -> bool:
        """Yazılan karakteri tampona ekler. Gizlilik kuralları:
          * zengin genişletme yoksa hiçbir şey tutulmaz,
          * odaktaki denetim parola kutusuysa (en iyi çaba) tampon silinir ve karakter alınmaz,
          * RICH_BUFFER_IDLE_SECONDS hareketsizlikten sonra eski içerik atılır,
          * tampon yalnızca en uzun tetikleyici kadar karakter tutar (eskiden 100).
        Karakter eklendiyse True döner."""
        now = time.monotonic() if now is None else now
        max_length = self._max_rich_trigger_length()
        if max_length == 0 or self._focus_is_password_field():
            self._buffer_clear()
            return False
        with self.buffer_lock:
            if self.buffer and now - self._buffer_last_time > RICH_BUFFER_IDLE_SECONDS:
                self.buffer = ""
                self._word_overflow = False
            combined = self.buffer + char
            if len(combined) > max_length:
                self._word_overflow = True      # kelimenin başı tampondan düştü
            self.buffer = combined[-max_length:]
            self._buffer_last_time = now
        return True

    def _buffer_take_word(self, now: float = None) -> str:
        """Tampondaki kelimeyi alıp tamponu sıfırlar; hareketsizlikle bayatlamışsa boş döner."""
        now = time.monotonic() if now is None else now
        with self.buffer_lock:
            stale = bool(self.buffer) and now - self._buffer_last_time > RICH_BUFFER_IDLE_SECONDS
            word = "" if stale else self.buffer.strip()
            self._taken_word_overflow = self._word_overflow and not stale
            self.buffer = ""
            self._word_overflow = False
        return word

    def expire_buffer(self, now: float = None) -> bool:
        """Hareketsizlik süresi dolduysa tamponu siler (periyodik çağrılır). Silindiyse True."""
        now = time.monotonic() if now is None else now
        with self.buffer_lock:
            if self.buffer and now - self._buffer_last_time > RICH_BUFFER_IDLE_SECONDS:
                self.buffer = ""
                self._word_overflow = False
                return True
        return False

    def _find_buffered_expansion(self, word: str):
        """Tamponlanan kelimeye uyan genişletme: (trigger, replacement, is_rich) ya da None.

        Zengin: kelimenin tamamı ya da SONU tetikleyiciyle biter (en uzun tetikleyici seçilir; örn.
        "test" ve "st" varsa "test"). Düz (yazılan-metin): kelimenin TAMAMI tetikleyici olmalı
        (keyboard.add_abbreviation ile aynı anlam; kelimenin başı tampondan düştüyse eşleşmez)."""
        best = None
        if word in self.rich_expansions:
            best = (word, self.rich_expansions[word], True)
        else:
            for trigger, html in self.rich_expansions.items():
                if word.endswith(trigger) and (best is None or len(trigger) > len(best[0])):
                    best = (trigger, html, True)
        if word in self.typed_expansions and not self._taken_word_overflow:
            if best is None or len(word) > len(best[0]):
                best = (word, self.typed_expansions[word], False)
        return best

    def _type_plain_replacement(self, text: str):
        """Düz metni yazar; yazılan karakterler tampona girip genişletmeyi yeniden tetiklemesin."""
        with self.pasting_lock:
            self.is_pasting = True
        try:
            self.backend.write(text)
            time.sleep(min(0.15 + (len(text) / 10000), 0.5))
        finally:
            with self.pasting_lock:
                self.is_pasting = False
            with self.buffer_lock:
                self.buffer = ""
                self._word_overflow = False

    def _perform_expansion(self, trigger_length: int, is_space_key: bool, replacement: str, is_rich: bool):
        """Tetikleyiciyi (ve space tuşunu) geri silip yerine genişletmeyi yazar/yapıştırır (arka plan)."""
        try:
            # Kısa bir bekleme (tuşun tamamen işlenmesi için)
            time.sleep(0.1)

            # Önce space tuşunu geri al (eğer space ise)
            if is_space_key:
                self.backend.press_and_release('backspace')
                time.sleep(0.03)

            # Sadece trigger kısmını backspace ile sil
            # Örneğin "asdmt" -> sadece "mt" silinir, "asd" kalır
            for i in range(trigger_length):
                self.backend.press_and_release('backspace')
                time.sleep(0.02)  # Her backspace arasında kısa bekleme

            # Clipboard'ın hazır olması için bekle
            time.sleep(0.15)

            if is_rich:
                # HTML'i yapıştır
                self._paste_rich_text(replacement)
            else:
                self._type_plain_replacement(replacement)
        except Exception:
            # Hata durumunda flag'i temizle
            with self.pasting_lock:
                self.is_pasting = False

    def _on_typed_key(self, kind: str, char):
        """Yazılan tuş akışı geri çağrısı (kind: char | space | enter | other). Sessizce devam eder."""
        if not self.running:
            return

        try:
            # Yapıştırma işlemi devam ediyorsa karakterleri ignore et
            with self.pasting_lock:
                if self.is_pasting:
                    return

            # Karakter tuşları için buffer'a ekle
            if kind == 'char' and char:
                self._buffer_append(char)

            # Enter genişletmez (çok satırlı alanda satır sonu ekler; geri silme tetikleyici yerine onu silerdi):
            # yalnızca kelimeyi bitirir
            elif kind == 'enter':
                self._buffer_clear()

            # Space tuşuna basıldığında kontrol et
            elif kind == 'space':
                if not self._has_buffered_expansions():
                    # Buffer'ı temizle (yeni kelime için)
                    self._buffer_clear()
                    return

                # Buffer'daki kelimeyi al (space'ten önceki kısım) ve buffer'ı temizle;
                # hareketsizlikle bayatlamış tampon kullanılmaz
                current_word = self._buffer_take_word()

                # Kelime boşsa işlem yapma
                if not current_word:
                    return

                found = self._find_buffered_expansion(current_word)
                if found:
                    trigger, replacement, is_rich = found
                    # Thread'de çalıştır (UI'ı bloklamamak için)
                    threading.Thread(
                        target=self._perform_expansion,
                        args=(len(trigger), kind == 'space', replacement, is_rich),
                        daemon=True,
                    ).start()
        except Exception:
            pass  # Sessizce devam et

    def _start_pynput_hook(self):
        """Yazılan tuş akışını dinleyen kancayı başlat (zengin / yazılan-düz genişletmeler için)"""
        if self.pynput_listener is not None:
            return

        try:
            listener = self.backend.create_key_listener(self._on_typed_key)
            if listener is None:
                return
            listener.start()
            self.pynput_listener = listener
        except Exception:
            self.pynput_listener = None

    def remove_expansion(self, trigger: str):
        """Metin genişletme sil"""
        try:
            if trigger in self.expansions:
                # Rich text değilse arka ucun kısaltmasını kaldır
                expansion_data = self.expansions[trigger]
                if not expansion_data[1]:  # is_rich değilse
                    if self.backend.native_abbreviations:
                        self.backend.remove_abbreviation(trigger)
                    self.typed_expansions.pop(trigger, None)
                del self.expansions[trigger]
            if trigger in self.rich_expansions:
                del self.rich_expansions[trigger]
        except Exception as e:
            log_error(f"Genisletme silme hatasi {trigger}", e)

    def clear_all(self):
        """Tüm kısayolları temizle (genişletmeleri KORUR)"""
        # Sadece kısayolları temizle
        for shortcut in list(self.hotkeys.keys()):
            self.remove_hotkey(shortcut)

    def clear_expansions(self):
        """Sadece genişletmeleri temizle"""
        for trigger in list(self.expansions.keys()):
            self.remove_expansion(trigger)

    def uses_keyboard_hook(self) -> bool:
        """Düz metin genişletme veya kanca yedekli kısayol varsa LL hook gerekir (yalnızca Windows kancası)"""
        if not self.backend.needs_watchdog:
            return False
        if any(callable(data[4]) if len(data) > 4 else False for data in self.hotkeys.values()):
            return True
        return any(not is_rich for _, is_rich in self.expansions.values())

    def _normalize_shortcut(self, shortcut: str) -> str:
        """Kısayolu normalize et - keyboard kütüphanesi formatına çevir"""
        shortcut = shortcut.lower().strip()

        # Modifier tuşları normalize et
        replacements = {
            'control+': 'ctrl+',
            'win+': 'windows+',
            'cmd+': 'windows+',
            'meta+': 'windows+',
            'super+': 'windows+',
        }

        for old, new in replacements.items():
            shortcut = shortcut.replace(old, new)

        # Tek tuşlar için özel işlem (scroll lock, pause, vb.)
        # keyboard kütüphanesi "scroll lock" formatını bekliyor
        single_keys = {
            'scrolllock': 'scroll lock',
            'scroll_lock': 'scroll lock',
            'scroll lock': 'scroll lock',
            'printscreen': 'print screen',
            'print_screen': 'print screen',
            'print screen': 'print screen',
            'pageup': 'page up',
            'page_up': 'page up',
            'page up': 'page up',
            'pagedown': 'page down',
            'page_down': 'page down',
            'page down': 'page down',
            'capslock': 'caps lock',
            'caps_lock': 'caps lock',
            'caps lock': 'caps lock',
            'numlock': 'num lock',
            'num_lock': 'num lock',
            'num lock': 'num lock',
        }

        # Eğer modifier yoksa ve tek tuş varsa normalize et
        if '+' not in shortcut:
            if shortcut in single_keys:
                shortcut = single_keys[shortcut]

        return shortcut


class HotkeyManager(QObject):
    """Kısayol yöneticisi"""

    action_executed = pyqtSignal(str, str)
    # Girdi arka ucunun durumu değişti (BackendStatus): arayüz uyarı bandını günceller
    input_status_changed = pyqtSignal(object)

    def __init__(self, backend=None, platform=None, clipboard=None):
        super().__init__()
        self.lang = "tr"
        self._platform = platform
        self.which = shutil.which   # PATH araması (testlerde değiştirilebilir)
        self.backend = backend if backend is not None else input_backend.create_backend(platform)
        self.worker = HotkeyWorker(backend=self.backend, clipboard=clipboard, platform=platform)
        self.worker.action_triggered.connect(
            self.execute_action,
            Qt.ConnectionType.QueuedConnection
        )

        self._win_hotkeys = WinHotkeyTable()
        self._win_filter = WinHotkeyFilter(self._on_os_hotkey)
        self._filter_installed = False

        # Modifier durumunu tazelemek icin periyodik yenileme (10 dakika, sessiz)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._periodic_refresh)
        self._refresh_timer.setInterval(10 * 60 * 1000)

        # Hook saglik kontrolu (60 saniye) - yalnizca LL kanca kullaniliyorsa;
        # macOS/Linux'ta dinleyici canliligi ve ortamin (izin/oturum) sonradan duzelip duzelmedigi
        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.timeout.connect(self._run_watchdog)
        self._watchdog_timer.setInterval(60 * 1000)

        # Gizlilik: yazılan karakter tamponu hareketsizlikte silinsin (2 sn'de bir kontrol)
        self._buffer_timer = QTimer(self)
        self._buffer_timer.timeout.connect(lambda: self.worker.expire_buffer())
        self._buffer_timer.setInterval(2000)

        self._last_app_state = Qt.ApplicationState.ApplicationInactive

        # Yıkıcı komutlar (kapat/yeniden başlat/oturumu kapat/çöp kutusunu boşalt) için onay.
        # confirm_destructive(command) -> bool; varsayılan özel MessageBox (src/gui/message_box.py; testlerde değiştirilebilir).
        self.confirm_destructive = self._ask_user_to_confirm
        self._confirm_open = False

        # URL'leri açma (Windows dışı: QDesktopServices); testlerde değiştirilebilir
        self._qt_open_url = self._default_qt_open_url

    @property
    def platform(self) -> str:
        return platform_utils.current_platform(self._platform)

    @property
    def input_status(self):
        return self.backend.status

    def set_language(self, lang: str) -> None:
        self.lang = lang

    # ---------------------------------------------------------------- ortam / arka uç durumu
    def recheck_environment(self) -> bool:
        """Arka uç kullanılamıyorsa ortamı yeniden dener (ör. macOS izni verildi). Düzelirse True."""
        if self.backend.available:
            return False
        new_backend = input_backend.create_backend(self._platform)
        if new_backend.available:
            self.backend = new_backend
            self.worker.set_backend(new_backend)
            log_info("Girdi arka ucu artık kullanılabilir; kısayollar yeniden kaydedildi")
            self.input_status_changed.emit(new_backend.status)
            return True
        if new_backend.status != self.backend.status:
            self.backend = new_backend
            self.worker.backend = new_backend
            self.input_status_changed.emit(new_backend.status)
        return False

    def attach_window(self, window) -> None:
        """RegisterHotKey icin HWND bagla (yalnizca Windows)"""
        if window is None or not platform_utils.is_windows(self._platform):
            return
        try:
            wid = window.winId()
            hwnd = int(wid) if wid else 0
        except Exception:
            return
        if not hwnd:
            return
        self._win_hotkeys.set_hwnd(hwnd)
        app = QApplication.instance()
        if app is not None and not self._filter_installed:
            app.installNativeEventFilter(self._win_filter)
            self._filter_installed = True

    def _on_os_hotkey(self, hotkey_id: int) -> None:
        shortcut = self._win_hotkeys.shortcut_for_id(hotkey_id)
        if not shortcut or shortcut not in self.worker.hotkeys:
            return
        data = self.worker.hotkeys[shortcut]
        normalized, action_type, action_value, is_rich = data[:4]
        callback = self.worker._make_hotkey_callback(
            action_type, action_value, shortcut, is_rich
        )
        callback()

    def _run_watchdog(self):
        """Windows: hook'a test sinyali gonder, 800ms sonra sonucu degerlendir.
        macOS/Linux: olu dinleyiciyi yeniden baslat; arka uc kullanilamiyorsa ortami yeniden dene."""
        if not self.backend.available:
            self.recheck_environment()
            return
        if not self.backend.needs_watchdog:
            self.worker.refresh_registrations(False)
            return
        if not self.worker.uses_keyboard_hook():
            return
        self.worker.probe_hook_health()
        QTimer.singleShot(800, self.worker.verify_hook_health)

    def start(self):
        """Kısayol dinleyicisini başlat (zaten yüklenmiş kısayolları tekrar ekleme)"""
        if self.worker.uses_keyboard_hook():
            self.worker._install_probe_hook()
            self._refresh_timer.start()
            self._watchdog_timer.start()
        elif not self.backend.needs_watchdog:
            self._watchdog_timer.start()
        self._buffer_timer.start()
        log_info("HotkeyManager baslatildi")

        app = QApplication.instance()
        if app is not None:
            self._last_app_state = app.applicationState()
            try:
                app.applicationStateChanged.disconnect(self._on_app_state_changed)
            except (TypeError, RuntimeError):
                pass
            app.applicationStateChanged.connect(self._on_app_state_changed)
        self.input_status_changed.emit(self.backend.status)

    def _periodic_refresh(self):
        """Periyodik bakım: yalnizca LL kancayi sessizce taze kur"""
        if self.worker.uses_keyboard_hook():
            self.worker.refresh_registrations(force=True)

    def _on_app_state_changed(self, state):
        """PC uyandığında veya oturum açıldığında hook'ları yenile"""
        resume_states = (
            Qt.ApplicationState.ApplicationSuspended,
            Qt.ApplicationState.ApplicationHidden,
        )
        if (state == Qt.ApplicationState.ApplicationActive and
                self._last_app_state in resume_states):
            if self.worker.uses_keyboard_hook():
                QTimer.singleShot(1000, lambda: self.worker.refresh_registrations(force=True))
        if (state == Qt.ApplicationState.ApplicationActive and not self.backend.available
                and self._last_app_state != state):
            # Kullanıcı sistem ayarlarından (macOS izinleri) dönmüş olabilir: ortamı yeniden dene
            QTimer.singleShot(500, self.recheck_environment)
        self._last_app_state = state

    def refresh_registrations(self):
        """Dışarıdan çağrılabilir hook yenileme"""
        if not self.backend.available:
            self.recheck_environment()
        elif self.worker.uses_keyboard_hook():
            self.worker.refresh_registrations(force=True)

    def stop(self):
        """Yöneticiyi tamamen durdur"""
        try:
            self._refresh_timer.stop()
            self._watchdog_timer.stop()
            self._buffer_timer.stop()
            self.worker.running = False
            self.worker._buffer_clear()

            if self.worker.pynput_listener is not None:
                try:
                    self.worker.pynput_listener.stop()
                    self.worker.pynput_listener = None
                except Exception as e:
                    log_error("Pynput listener durdurma hatasi", e)

            for shortcut in list(self.worker.hotkeys.keys()):
                self.remove_hotkey(shortcut)

            self._win_hotkeys.clear()
            app = QApplication.instance()
            if app is not None and self._filter_installed:
                app.removeNativeEventFilter(self._win_filter)
                self._filter_installed = False

            self.backend.stop()
            log_info("HotkeyManager durduruldu")
        except Exception as e:
            log_error("HotkeyManager durdurma hatasi", e)

    def add_hotkey(self, shortcut: str, action_type: str, action_value: str, is_rich: bool = False):
        if shortcut in self.worker.hotkeys:
            self.remove_hotkey(shortcut)

        normalized = self.worker._normalize_shortcut(shortcut)
        parsed = parse_win_hotkey(normalized) if platform_utils.is_windows(self._platform) else None
        os_id = None
        if parsed is not None:
            mods, vk = parsed
            os_id = self._win_hotkeys.register(shortcut, mods, vk)

        if os_id is not None:
            self.worker.hotkeys[shortcut] = (
                normalized, action_type, action_value, is_rich, None
            )
            log_info(f"Kisayol kaydedildi: {shortcut} -> {normalized} ({action_type})")
            return

        self.worker.add_hotkey(shortcut, action_type, action_value, is_rich)

    def remove_hotkey(self, shortcut: str):
        if self._win_hotkeys.has(shortcut):
            self._win_hotkeys.unregister(shortcut)
        self.worker.remove_hotkey(shortcut)

    def add_expansion(self, trigger: str, replacement: str, is_rich: bool = False):
        self.worker.add_expansion(trigger, replacement, is_rich)

    def remove_expansion(self, trigger: str):
        self.worker.remove_expansion(trigger)

    def clear_all(self):
        for shortcut in list(self.worker.hotkeys.keys()):
            self.remove_hotkey(shortcut)

    # ---------------------------------------------------------------- komut tablosu için "ev sahibi" arayüzü
    def launch(self, target):
        self._launch_process(target)

    def send_keys(self, keys: str) -> None:
        """Tuş kombinasyonunu GUI'yi bekletmeden, arka planda (tetikleyici tuşlar bırakıldıktan sonra) gönderir."""
        def send(keys=keys):
            time.sleep(0.06)  # tetikleyici tuşların bırakılması için
            self.backend.send(keys)

        INPUT_INJECTOR.submit(send, on_error=self._injection_error)

    def send_media(self, name: str) -> None:
        INPUT_INJECTOR.submit(lambda: self.backend.send_media(name), on_error=self._injection_error)

    def _injection_error(self, exc):
        self.action_executed.emit('error', t('notif_error_prefix', self.lang).format(str(exc)))

    def _unavailable_message(self, exc: CommandUnavailable) -> str:
        if exc.reason == 'not_installed':
            return t('cmd_not_installed', self.lang).format(exc.command)
        return t('cmd_unsupported_platform', self.lang).format(
            platform_utils.platform_label(exc.platform), exc.command)

    def execute_action(self, action_type: str, action_value: str, shortcut: str, is_rich: bool):
        """Aksiyonu çalıştır"""
        try:
            log_info(f"Kisayol tetiklendi: {shortcut} ({action_type})")
            if action_type == 'text':
                # Rich text desteği
                if is_rich:
                    # HTML'i düz metne çevir ve yaz
                    from PyQt6.QtGui import QTextDocument
                    doc = QTextDocument()
                    doc.setHtml(action_value)
                    plain_text = doc.toPlainText()
                else:
                    plain_text = action_value
                # Uzun metinde yazma GUI iş parçacığını dondurur: arka planda, sıralı yaz
                INPUT_INJECTOR.submit(
                    lambda text=plain_text: self.backend.write(text),
                    on_error=self._injection_error,
                )
                self.action_executed.emit('text', t('notif_written', self.lang).format(action_value[:50]))

            elif action_type == 'command':
                if not self._execute_system_command(action_value):
                    label = t(DESTRUCTIVE_COMMANDS.get(action_value, action_value), self.lang)
                    self.action_executed.emit(
                        'command', t('confirm_destructive_cancelled', self.lang).format(label)
                    )
                    return
                silent_commands = {
                    'emoji_paneli', 'pano_gecmisi', 'ekran_alintisi', 'ekran_goruntusu',
                    'ses_ac', 'ses_kis', 'sesi_kapat', 'ses_maksimum', 'ses_minimum',
                    'oynat_duraklat', 'sonraki_sarki', 'onceki_sarki', 'durdur',
                    'masaustunu_goster', 'tum_pencereleri_kucult', 'gorev_gorunumu',
                    'yeni_sanal_masaustu', 'sonraki_masaustu', 'onceki_masaustu', 'sanal_masaustu_kapat',
                    'sola_yasla', 'saga_yasla', 'pencereyi_buyut', 'pencereyi_kapat', 'pencere_degistir',
                    'geri', 'ileri', 'sayfayi_yenile', 'yeni_sekme', 'sekmeyi_kapat', 'kapatilan_sekmeyi_ac', 'gizli_pencere',
                    'kopyala', 'kes', 'yapistir', 'tumunu_sec', 'geri_al', 'yeniden_yap', 'bul', 'kaydet', 'yazdir',
                    'calistir',
                }
                if action_value not in silent_commands:
                    self.action_executed.emit('command', t('notif_executed', self.lang).format(action_value))

            elif action_type == 'shortcut':
                norm_val = self.worker._normalize_shortcut(action_value)
                self.send_keys(norm_val)

            elif action_type == 'open_url':
                # URL formatını kontrol et ve düzelt
                url = action_value.strip()
                if not url:
                    self.action_executed.emit('error', t('notif_url_empty', self.lang))
                    return

                # Eğer http:// veya https:// yoksa ekle
                if not url.startswith(('http://', 'https://', 'file://', 'ftp://')):
                    url = 'https://' + url

                try:
                    self._open_url(url)
                    self.action_executed.emit('open_url', t('notif_opened', self.lang).format(url))
                except Exception as url_error:
                    self.action_executed.emit('error', t('notif_url_failed', self.lang).format(str(url_error)))

            elif action_type == 'open_file':
                self._launch_process(action_value)
                self.action_executed.emit('open_file', t('notif_opened', self.lang).format(action_value))

            elif action_type == 'run_program':
                self._launch_process(action_value)
                self.action_executed.emit('run_program', t('notif_executed', self.lang).format(action_value))

        except CommandUnavailable as e:
            log_warning(f"Komut kullanilamiyor ({shortcut}, {action_type}): {e}")
            self.action_executed.emit('error', self._unavailable_message(e))
        except Exception as e:
            log_error(f"Aksiyon hatasi ({shortcut}, {action_type})", e)
            self.action_executed.emit('error', t('notif_error_prefix', self.lang).format(str(e)))

    # ---------------------------------------------------------------- süreç / URL başlatma
    def _default_qt_open_url(self, url: str) -> bool:
        from PyQt6.QtGui import QDesktopServices
        return bool(QDesktopServices.openUrl(QUrl(url)))

    def _open_url(self, url: str) -> None:
        """URL'yi varsayılan tarayıcıda açar. Windows: webbrowser (eskisi gibi); macOS/Linux:
        QDesktopServices (open / xdg-open), olmazsa webbrowser."""
        if platform_utils.is_windows(self._platform):
            webbrowser.open(url)
            return
        if self._qt_open_url(url):
            return
        if not webbrowser.open(url):
            raise RuntimeError(t('notif_url_no_browser', self.lang))

    def _popen(self, args):
        """Konsol penceresi açmadan, kabuk (shell) KULLANMADAN süreç başlatır."""
        if platform_utils.is_windows(self._platform):
            creation_flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
            return subprocess.Popen(args, shell=False, creationflags=creation_flags)
        # POSIX: FlexiKey'den bağımsız oturumda, terminale bağlı olmadan çalışsın; zombi kalmasın
        try:
            process = subprocess.Popen(
                args, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True,
            )
        except FileNotFoundError:
            program = args[0] if isinstance(args, (list, tuple)) and args else str(args)
            raise CommandUnavailable(str(program), 'not_installed', self._platform)
        threading.Thread(target=process.wait, name='FlexiKey-reap', daemon=True).start()
        return process

    def _launch_process(self, target):
        """Uygulama veya komutu arka planda konsol penceresi açmadan başlatır.

        Hiçbir yolda ``shell=True`` kullanılmaz:
          * liste/tuple: yerleşik komut; doğrudan argüman listesi olarak çalıştırılır.
          * metin: kullanıcı tanımlı değer (program, dosya, URI, serbest komut satırı).
            Doğrulanır (boş/NUL/satır sonu/aşırı uzun reddedilir).
            Windows: ShellExecute ile denenir, olmazsa kabuksuz süreç olarak başlatılır. cmd.exe yedeği
            yalnızca zincirleme karakteri içermeyen ``start ...`` gibi yerleşikler için vardır;
            ``&``, ``|``, ``>`` vb. içeren değerler ASLA kabuğa verilmez.
            macOS/Linux: launcher.plan_launch (URL/dosya -> open/xdg-open; komut -> shlex ile
            doğrudan çalıştırma; kabuk yok).
        """
        if isinstance(target, (list, tuple)):
            if target:
                self._popen(list(target))
            return

        target = (target or '').strip()
        if not target:
            return
        command_line = validate_user_command(target)

        if not platform_utils.is_windows(self._platform):
            self._launch_posix(command_line)
            return

        # 1. ShellExecute ile doğrudan başlatmayı dene (GUI uygulamaları, dosyalar, shell URI'leri)
        if hasattr(os, 'startfile'):
            try:
                os.startfile(command_line)
                return
            except Exception:
                pass  # dosya/URI değil: komut satırı olarak dene

        # 2. Parametreli komutlar: kabuksuz süreç
        try:
            self._popen(command_line)  # CreateProcess komut satırını kendisi ayrıştırır
            return
        except FileNotFoundError:
            if shell_fallback_allowed(command_line, self._platform):
                log_warning(f"cmd.exe yedeği ile çalıştırılıyor (yerleşik komut): {command_line[:80]}")
                self._popen(shell_argv(command_line, self._platform))
                return
            raise

    def _launch_posix(self, command_line: str):
        try:
            plan = plan_launch(command_line, self._platform, which=self.which)
        except FileNotFoundError:
            program = command_line.split(None, 1)[0] if command_line.split() else command_line
            raise CommandUnavailable(program, 'not_installed', self._platform)
        if plan.kind == 'qt_open':
            if not self._qt_open_url(plan.target):
                raise CommandUnavailable('xdg-open', 'not_installed', self._platform)
            return
        self._popen(list(plan.argv))

    # ---------------------------------------------------------------- yıkıcı eylem onayı
    def _confirm_destructive_command(self, command: str) -> bool:
        """Yıkıcı komut için onay al. Onay yoksa/alınamıyorsa False (güvenli varsayılan)."""
        if self._confirm_open:
            log_info(f"Onay penceresi zaten açık; tekrar tetikleme yoksayıldı ({command})")
            return False
        self._confirm_open = True
        try:
            return bool(self.confirm_destructive(command))
        except Exception as exc:
            log_error(f"Yıkıcı komut onayı alınamadı ({command})", exc)
            return False
        finally:
            self._confirm_open = False

    def _ask_user_to_confirm(self, command: str) -> bool:
        """Varsayılan onay: özel MessageBox (yalnızca ana/GUI iş parçacığında), varsayılan düğme Hayır."""
        app = QApplication.instance()
        if app is None or QThread.currentThread() is not app.thread():
            log_error(f"Yıkıcı komut GUI iş parçacığı dışında istendi, reddedildi: {command}")
            return False
        from src.gui.message_box import MessageBox
        label = t(DESTRUCTIVE_COMMANDS.get(command, command), self.lang)
        detail_key = 'confirm_destructive_recycle' if command == 'cop_kutusunu_bosalt' else 'confirm_destructive_power'
        box = MessageBox()
        box.setIcon(MessageBox.Icon.Warning)
        box.setWindowTitle(t('confirm_destructive_title', self.lang))
        box.setText(t('confirm_destructive_text', self.lang).format(label))
        box.setInformativeText(t(detail_key, self.lang))
        box.setStandardButtons(MessageBox.StandardButton.Yes | MessageBox.StandardButton.No)
        box.setDefaultButton(MessageBox.StandardButton.No)
        box.setEscapeButton(MessageBox.StandardButton.No)
        # Tepsiden çalışırken pencere arkada kalmasın
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        box.activateWindow()
        box.raise_()
        return box.exec() == MessageBox.StandardButton.Yes

    def _execute_system_command(self, command: str) -> bool:
        """Sistem komutunu çalıştırır. Yıkıcı komutlar onaysız çalışmaz; onay verilmezse False döner."""
        if command in DESTRUCTIVE_COMMANDS and not self._confirm_destructive_command(command):
            log_info(f"Yıkıcı komut onaylanmadı, çalıştırılmadı: {command}")
            return False

        commands = self._build_command_table()
        if command in commands:
            action = commands[command]
            if callable(action):
                action()
            else:
                self._launch_process(action)
        else:
            # Yerleşik olmayan değer: kullanıcı tanımlı komut satırı (kabuksuz, doğrulanır)
            log_warning(f"Bilinmeyen sistem komutu kullanıcı tanımlı komut olarak çalıştırılıyor: {command[:80]}")
            self._launch_process(command)
        return True

    def _build_command_table(self) -> dict:
        """Yerleşik komut adı -> çalıştırıcı tablosu (Windows, macOS, Linux; bkz. system_commands.py)"""
        return system_commands.build_command_table(self, self._platform)
