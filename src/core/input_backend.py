"""Girdi arka ucu: küresel kısayol, tuş enjeksiyonu ve yazılan tuş akışı soyutlaması.

HotkeyWorker/HotkeyManager (hotkey_manager.py) yalnızca bu arayüzü tanır; platforma özgü kod burada:

  * WindowsKeyboardBackend  - Windows: ``keyboard`` kütüphanesi (düşük seviye kanca) + yazılan tuşlar
    için pynput. Önceki davranış AYNEN korunur (kanca sağlığı, özel API kurtarma, kısaltmalar).
  * PynputBackend           - macOS / Linux (X11): tek bir pynput dinleyicisi; kısayol eşleştirme,
    yazılan tuş akışı ve ``Controller`` ile enjeksiyon.
  * UnavailableBackend      - desteklenmeyen ortam (Wayland, X11 yok, macOS izni yok, bağımlılık yok):
    çökmek yerine "yumuşak" başarısızlık; kayıtlar sessizce atlanır, enjeksiyon açıklayıcı hata verir.

Hiçbir yerde import anında platforma özgü modül (keyboard, pynput, winreg...) yüklenmez; hepsi
``create_backend`` / yapıcılar içinde, platform denetiminden sonra yüklenir.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable, Dict, List, Mapping, NamedTuple, Optional, Tuple

from src.utils import keynames
from src.utils import platform_utils
from src.utils.helpers import log_error, log_warning

# ------------------------------------------------------------------ durum / ortam denetimi
STATUS_OK = "ok"
STATUS_WAYLAND = "wayland"
STATUS_NO_DISPLAY = "no_display"
STATUS_MAC_PERMISSION = "macos_permission"
STATUS_MISSING_DEPENDENCY = "missing_dependency"

ALLOW_WAYLAND_ENV = "FLEXIKEY_ALLOW_WAYLAND"   # XWayland'de denemek isteyen ileri düzey kullanıcılar için


class BackendStatus(NamedTuple):
    ok: bool
    code: str
    detail: str = ""


OK_STATUS = BackendStatus(True, STATUS_OK)


class BackendUnavailable(RuntimeError):
    """Girdi arka ucu bu ortamda kullanılamıyor (ayrıntı: ``status``)."""

    def __init__(self, status: BackendStatus, message: str = ""):
        super().__init__(message or f"{status.code}: {status.detail}".strip(": "))
        self.status = status


def describe_status(status: BackendStatus, lang: Optional[str] = None) -> str:
    """Durumu kullanıcıya gösterilecek yerelleştirilmiş, nasıl düzeltileceğini anlatan metne çevirir."""
    from src.utils.locales import t
    if status.ok:
        return ""
    detail = status.detail
    if status.code == STATUS_MAC_PERMISSION:
        names = [t(f"input_perm_{part}", lang) for part in status.detail.split(",") if part]
        detail = ", ".join(names)
    key = f"input_status_{status.code}"
    template = t(key, lang)
    if template == key:
        return status.detail or status.code
    return template.format(detail)


def macos_permission_state(ax_probe: Optional[Callable[[], Optional[bool]]] = None,
                           listen_probe: Optional[Callable[[], Optional[bool]]] = None
                           ) -> Tuple[Optional[bool], Optional[bool]]:
    """(Erişilebilirlik, Girdi İzleme) izni: True/False, belirlenemezse None.

    Erişilebilirlik = ``AXIsProcessTrusted`` (tuş enjeksiyonu); Girdi İzleme =
    ``CGPreflightListenEventAccess`` (macOS 10.15+, küresel dinleme). Yalnızca macOS'ta, ctypes ile
    çağrılır; fonksiyon bulunamazsa None (bilinmiyor) döner ve engellenmez.
    """
    return (_call_probe(ax_probe or _default_ax_probe), _call_probe(listen_probe or _default_listen_probe))


def _call_probe(probe: Callable[[], Optional[bool]]) -> Optional[bool]:
    try:
        value = probe()
    except Exception:
        return None
    return None if value is None else bool(value)


def _load_mac_function(library: str, name: str):
    import ctypes
    import ctypes.util
    path = ctypes.util.find_library(library)
    if not path:
        return None
    function = getattr(ctypes.cdll.LoadLibrary(path), name, None)
    if function is not None:
        function.restype = ctypes.c_bool
        function.argtypes = []
    return function


def _default_ax_probe() -> Optional[bool]:
    function = _load_mac_function("ApplicationServices", "AXIsProcessTrusted")
    return None if function is None else function()


def _default_listen_probe() -> Optional[bool]:
    function = _load_mac_function("CoreGraphics", "CGPreflightListenEventAccess")
    return None if function is None else function()


def import_pynput_keyboard():
    """pynput.keyboard modülü. Linux'ta X sunucusuna bağlanamazsa ImportError verir."""
    from pynput import keyboard
    return keyboard


def check_environment(platform: Optional[str] = None, env: Optional[Mapping[str, str]] = None, *,
                      pynput_importer: Optional[Callable[[], Any]] = None,
                      mac_probe: Optional[Callable[[], Tuple[Optional[bool], Optional[bool]]]] = None
                      ) -> BackendStatus:
    """Küresel kısayol/enjeksiyon bu ortamda çalışabilir mi? Hiçbir şey kaydetmez/başlatmaz.

    Windows: her zaman uygun (``keyboard`` varlığı ``create_backend``'de denenir).
    Linux: Wayland oturumu (küresel kanca/enjeksiyon genelde çalışmaz) ve DISPLAY'sız oturum reddedilir.
    macOS: pynput yüklü mü ve Erişilebilirlik / Girdi İzleme izinleri verilmiş mi.
    """
    plat = platform_utils.current_platform(platform)
    if plat == platform_utils.WINDOWS:
        return OK_STATUS
    env = os.environ if env is None else env
    if plat == platform_utils.LINUX:
        session = platform_utils.linux_session_type(env)
        if session == platform_utils.SESSION_WAYLAND and not (env.get(ALLOW_WAYLAND_ENV) or "").strip():
            return BackendStatus(False, STATUS_WAYLAND, session)
        if not platform_utils.has_x11_display(env):
            return BackendStatus(False, STATUS_NO_DISPLAY, session)
    importer = pynput_importer or import_pynput_keyboard
    try:
        importer()
    except Exception as exc:     # ImportError (X yok / paket yok) ve pynput'un başlatma hataları
        return BackendStatus(False, STATUS_MISSING_DEPENDENCY, f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}".strip())
    if plat == platform_utils.MACOS:
        accessibility, input_monitoring = (mac_probe or macos_permission_state)()
        missing = []
        if accessibility is False:
            missing.append("accessibility")
        if input_monitoring is False:
            missing.append("input_monitoring")
        if missing:
            return BackendStatus(False, STATUS_MAC_PERMISSION, ",".join(missing))
    return OK_STATUS


# ------------------------------------------------------------------ arayüz
def _noop() -> None:
    return None


class InputBackend:
    """Girdi arka ucu arayüzü. Yöntem adları ``keyboard`` kütüphanesininkilerle uyumludur."""

    name = "base"
    available = True
    status = OK_STATUS
    native_abbreviations = False   # düz metin kısaltmalarını arka uç kendisi eşleştirir mi?
    needs_watchdog = False         # düşük seviye kanca sağlık denetimi (yalnızca Windows)
    paste_keys = "ctrl+v"          # Yapıştırma kısayolu (macOS'ta win = Cmd)

    # küresel kısayollar --------------------------------------------------------------
    def add_hotkey(self, normalized: str, callback: Callable[[], None], suppress: bool = False,
                   timeout: float = 0.1) -> Callable[[], None]:
        raise NotImplementedError

    def remove_hotkey(self, handle_or_name: Any) -> None:
        raise NotImplementedError

    def unhook_all(self) -> None:
        raise NotImplementedError

    def hook(self, callback: Callable[[Any], Any]) -> Any:
        """Tüm tuş olaylarını izleyen dinleyici (kanca sağlık sınaması). Desteklenmiyorsa None."""
        return None

    # metin kısaltmaları (yalnızca native_abbreviations=True) -----------------------------
    def add_abbreviation(self, trigger: str, replacement: str) -> None:
        raise NotImplementedError

    def remove_abbreviation(self, trigger: str) -> None:
        raise NotImplementedError

    # enjeksiyon --------------------------------------------------------------------------
    def write(self, text: str) -> None:
        raise NotImplementedError

    def send(self, keys: str) -> None:
        raise NotImplementedError

    def press_and_release(self, key: str) -> None:
        self.send(key)

    def send_media(self, name: str) -> None:
        raise NotImplementedError

    # yazılan tuş akışı (zengin / yazılan metin genişletmeleri) ------------------------------
    def create_key_listener(self, on_key: Callable[[str, Optional[str]], None]) -> Any:
        """``on_key(kind, char)`` çağıran dinleyici (start/stop/is_alive). kind: char|space|enter|other.
        Desteklenmiyorsa None."""
        return None

    # sağlık ----------------------------------------------------------------------------------
    def revive_if_dead(self) -> bool:
        """Dinleyici iş parçacığı ölmüşse sıfırlanmaya hazırlar; yeniden kayıt gerekiyorsa True."""
        return False

    def prepare_hard_reinstall(self) -> None:
        """Kancayı sıfırdan kurmak için dahili durumu sıfırlar (kayıtları worker yeniden ekler)."""

    def stop(self) -> None:
        """Tüm dinleyicileri durdurur."""


class UnavailableBackend(InputBackend):
    """Desteklenmeyen ortamda yumuşak başarısızlık: kayıtlar atlanır, enjeksiyon açıklayıcı hata verir."""

    name = "unavailable"
    available = False

    def __init__(self, status: BackendStatus):
        self.status = status
        self._warned = False

    def _error(self) -> BackendUnavailable:
        from src.utils.locales import t
        return BackendUnavailable(self.status, describe_status(self.status, None) or t("input_status_title"))

    def add_hotkey(self, normalized, callback, suppress=False, timeout=0.1):
        if not self._warned:
            self._warned = True
            log_warning(f"Girdi arka ucu kullanılamıyor ({self.status.code}: {self.status.detail}); "
                        "kısayollar kaydedilmeyecek")
        return _noop

    def remove_hotkey(self, handle_or_name):
        return None

    def unhook_all(self):
        return None

    def add_abbreviation(self, trigger, replacement):
        return None

    def remove_abbreviation(self, trigger):
        return None

    def write(self, text):
        raise self._error()

    def send(self, keys):
        raise self._error()

    def send_media(self, name):
        raise self._error()


# ------------------------------------------------------------------ yazılan tuş sınıflandırması
def classify_pynput_key(key: Any, keyboard_module: Any) -> Tuple[str, Optional[str]]:
    """pynput tuşu -> ('char', c) | ('space', None) | ('enter', None) | ('other', None).

    Eski HotkeyWorker davranışı: önce ``key.char``; yoksa Space/Enter; gerisi yok sayılır."""
    char = getattr(key, "char", None)
    if char:
        return "char", char
    try:
        if key == keyboard_module.Key.space:
            return "space", None
        if key == keyboard_module.Key.enter:
            return "enter", None
    except Exception:
        pass
    return "other", None


# ------------------------------------------------------------------ Windows: keyboard kütüphanesi
_PRIVATE_API_WARNED: set = set()


def _warn_private_api_once(name: str, detail: str = "") -> None:
    """keyboard kütüphanesinin özel (alt çizgili) API'leri sürümler arasında değişebilir.

    Bulunamazsa kanca kurtarma/yenileme sessizce işlevsiz kalırdı; artık ilk seferde loglanır
    (her yenilemede tekrar logu şişirmesin diye ad başına bir kez).
    """
    if name in _PRIVATE_API_WARNED:
        return
    _PRIVATE_API_WARNED.add(name)
    log_warning(f"keyboard özel API'si kullanılamıyor: {name} {detail}".strip())


class WindowsKeyboardBackend(InputBackend):
    """Windows: ``keyboard`` kütüphanesi (WH_KEYBOARD_LL kancası) — önceki davranışın aynısı."""

    name = "windows-keyboard"
    native_abbreviations = True
    needs_watchdog = True
    paste_keys = "ctrl+v"

    def __init__(self, keyboard_module: Any = None, pynput_module: Any = None):
        if keyboard_module is None:
            import keyboard as keyboard_module      # yalnızca Windows'ta çağrılır (create_backend)
        self.kb = keyboard_module
        self._pynput = pynput_module
        self._pynput_tried = pynput_module is not None

    # küresel kısayollar
    def add_hotkey(self, normalized, callback, suppress=False, timeout=0.1):
        return self.kb.add_hotkey(normalized, callback, suppress=suppress, timeout=timeout)

    def remove_hotkey(self, handle_or_name):
        if callable(handle_or_name):
            handle_or_name()
        else:
            self.kb.remove_hotkey(handle_or_name)

    def unhook_all(self):
        """keyboard kütüphanesinin tüm hotkey durumunu güvenli temizler."""
        try:
            self.kb.unhook_all()
        except Exception as exc:
            log_error("keyboard.unhook_all basarisiz", exc)
        # unhook_all _hotkeys sozlugunu temizlemiyor; biz temizleyelim (ozel API: try/except + log)
        hotkeys = getattr(self.kb, '_hotkeys', None)
        if hotkeys is None:
            _warn_private_api_once('_hotkeys')
            return
        try:
            hotkeys.clear()
        except Exception as exc:
            _warn_private_api_once('_hotkeys.clear', repr(exc))

    def hook(self, callback):
        return self.kb.hook(callback, suppress=False)

    # kısaltmalar
    def add_abbreviation(self, trigger, replacement):
        return self.kb.add_abbreviation(trigger, replacement)

    def remove_abbreviation(self, trigger):
        self.kb.remove_abbreviation(trigger)

    # enjeksiyon
    def write(self, text):
        self.kb.write(text)

    def send(self, keys):
        self.kb.send(keys)

    def press_and_release(self, key):
        self.kb.press_and_release(key)

    # yazılan tuş akışı: pynput (kanca keyboard'da, yazılanları izlemek pynput'ta — eskisi gibi)
    def _pynput_keyboard(self):
        if not self._pynput_tried:
            self._pynput_tried = True
            try:
                self._pynput = import_pynput_keyboard()
            except ImportError:
                self._pynput = None
        return self._pynput

    def create_key_listener(self, on_key):
        pynput_kb = self._pynput_keyboard()
        if pynput_kb is None:
            return None

        def on_press(key):
            on_key(*classify_pynput_key(key, pynput_kb))

        def on_release(key):
            pass

        return pynput_kb.Listener(on_press=on_press, on_release=on_release, suppress=False)

    # sağlık
    def revive_if_dead(self):
        """Dinleyici thread olduysa yeni OS hook kurmaya zorla."""
        try:
            listener = getattr(self.kb, '_listener', None)
            if listener is None:
                _warn_private_api_once('_listener')
                return False
            if not hasattr(listener, 'listening_thread'):
                _warn_private_api_once('_listener.listening_thread')
                return False
            thread = listener.listening_thread
            if thread is not None and not thread.is_alive():
                listener.listening = False
                return True
        except Exception as exc:
            _warn_private_api_once('_listener(erisim hatasi)', repr(exc))
        return False

    def prepare_hard_reinstall(self):
        """keyboard kutuphanesi hook'u yalnizca listening=False iken kurdugu icin bayragi dusurur."""
        listener = getattr(self.kb, '_listener', None)
        if listener is not None:
            listener.listening = False
        else:
            _warn_private_api_once('_listener')


# ------------------------------------------------------------------ macOS / Linux: pynput
# ABD düzenine göre Shift ile üretilen simgelerin değiştirilmemiş karşılıkları ('ctrl+shift+1' için)
_UNSHIFT = {
    '!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
    '_': '-', '+': '=', '{': '[', '}': ']', '|': '\\', ':': ';', '"': "'", '<': ',', '>': '.', '?': '/', '~': '`',
}

# kanonik tuş adı -> pynput.keyboard.Key üyesi
_NAMED_KEYS = {
    'enter': 'enter', 'esc': 'esc', 'tab': 'tab', 'space': 'space', 'backspace': 'backspace',
    'delete': 'delete', 'insert': 'insert', 'home': 'home', 'end': 'end',
    'page up': 'page_up', 'page down': 'page_down',
    'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right',
    'caps lock': 'caps_lock', 'num lock': 'num_lock', 'scroll lock': 'scroll_lock',
    'print screen': 'print_screen', 'pause': 'pause', 'menu': 'menu',
}
_NAMED_KEYS.update({f'f{n}': f'f{n}' for n in range(1, 25)})

_MODIFIER_KEY_MEMBERS = {
    'ctrl': ('ctrl', 'ctrl_l', 'ctrl_r'),
    'alt': ('alt', 'alt_l', 'alt_r'),            # alt_gr bilerek yok: karakter üretir (AltGr+Q = @)
    'shift': ('shift', 'shift_l', 'shift_r'),
    'win': ('cmd', 'cmd_l', 'cmd_r'),            # Win / Super / Command
}
_SEND_MODIFIER_MEMBER = {'ctrl': 'ctrl', 'alt': 'alt', 'shift': 'shift', 'win': 'cmd'}

_MEDIA_MEMBERS = {
    'play_pause': 'media_play_pause', 'next': 'media_next', 'previous': 'media_previous',
    'volume_up': 'media_volume_up', 'volume_down': 'media_volume_down', 'mute': 'media_volume_mute',
}

_MAC_KEYPAD_KEYCODES = {82: '0', 83: '1', 84: '2', 85: '3', 86: '4', 87: '5', 88: '6', 89: '7', 91: '8', 92: '9'}
_X11_KP_0, _X11_KP_9 = 0xFFB0, 0xFFB9

_REPEAT_WINDOW = 1.0            # bu süre içinde yinelenen basış = tuş otomatik tekrarı


class _Hotkey(NamedTuple):
    modifiers: frozenset
    key: str
    callback: Callable[[], None]
    normalized: str


class _TypedSubscription:
    """create_key_listener dönüşü: paylaşılan pynput dinleyicisine abone; start/stop/is_alive."""

    def __init__(self, backend: "PynputBackend", on_key: Callable[[str, Optional[str]], None]):
        self._backend = backend
        self.on_key = on_key

    def start(self):
        self._backend._subscribe(self)

    def stop(self):
        self._backend._unsubscribe(self)

    def is_alive(self) -> bool:
        return self._backend._subscription_alive(self)


class PynputBackend(InputBackend):
    """macOS ve Linux (X11): tek pynput dinleyicisi ile kısayol eşleştirme + yazılan tuş akışı."""

    name = "pynput"
    native_abbreviations = False
    needs_watchdog = False

    def __init__(self, platform: Optional[str] = None, keyboard_module: Any = None,
                 sleep: Callable[[float], None] = time.sleep, monotonic: Callable[[], float] = time.monotonic):
        self.platform = platform_utils.current_platform(platform)
        self._pk = keyboard_module if keyboard_module is not None else import_pynput_keyboard()
        self._sleep = sleep
        self._monotonic = monotonic
        self.paste_keys = "win+v" if self.platform == platform_utils.MACOS else "ctrl+v"
        self._lock = threading.RLock()
        self._listener = None
        self._controller = None
        self._hotkeys: Dict[int, _Hotkey] = {}
        self._next_id = 1
        self._subs: List[_TypedSubscription] = []
        self._held: set = set()
        self._down: Dict[Any, float] = {}
        key_cls = self._pk.Key
        self._mod_of_key: Dict[Any, str] = {}
        for modifier, members in _MODIFIER_KEY_MEMBERS.items():
            for member in members:
                key_obj = getattr(key_cls, member, None)
                if key_obj is not None:
                    self._mod_of_key[key_obj] = modifier
        self._name_of_key: Dict[Any, str] = {}
        for name, member in _NAMED_KEYS.items():
            key_obj = getattr(key_cls, member, None)
            if key_obj is not None:
                self._name_of_key[key_obj] = name

    # ---------------------------------------------------------------- dinleyici yaşam döngüsü
    def _ensure_listener(self):
        with self._lock:
            if self._listener is not None and self._listener.is_alive():
                return
            self._held.clear()
            self._down.clear()
            listener = self._pk.Listener(on_press=self._on_press, on_release=self._on_release)
            listener.start()
            self._listener = listener

    def _stop_listener(self):
        with self._lock:
            listener, self._listener = self._listener, None
        if listener is not None:
            try:
                listener.stop()
            except Exception as exc:
                log_error("pynput dinleyicisi durdurulamadı", exc)

    def _subscribe(self, sub: "_TypedSubscription"):
        with self._lock:
            if sub not in self._subs:
                self._subs.append(sub)
        self._ensure_listener()

    def _unsubscribe(self, sub: "_TypedSubscription"):
        with self._lock:
            if sub in self._subs:
                self._subs.remove(sub)
            idle = not self._subs and not self._hotkeys
        if idle:
            self._stop_listener()

    def _subscription_alive(self, sub: "_TypedSubscription") -> bool:
        with self._lock:
            listener = self._listener
            return sub in self._subs and listener is not None and listener.is_alive()

    def stop(self):
        with self._lock:
            self._hotkeys.clear()
            self._subs.clear()
        self._stop_listener()

    def revive_if_dead(self) -> bool:
        with self._lock:
            listener = self._listener
            if listener is None or listener.is_alive():
                return False
            self._listener = None
            return bool(self._hotkeys or self._subs)

    def prepare_hard_reinstall(self):
        self._stop_listener()

    # ---------------------------------------------------------------- küresel kısayollar
    def add_hotkey(self, normalized, callback, suppress=False, timeout=0.1):
        parsed = keynames.parse_shortcut(normalized)
        if parsed.key is None:
            raise ValueError(f"Yalnızca değiştirici içeren kısayol desteklenmiyor: {normalized!r}")
        self._to_pynput_key(parsed.key)     # bu platformda basılamayan/algılanamayan tuşu erken reddet
        self._ensure_listener()
        with self._lock:
            hotkey_id = self._next_id
            self._next_id += 1
            self._hotkeys[hotkey_id] = _Hotkey(frozenset(parsed.modifiers), parsed.key, callback, normalized)
        return lambda: self.remove_hotkey(hotkey_id)

    def remove_hotkey(self, handle_or_name):
        with self._lock:
            if isinstance(handle_or_name, int):
                self._hotkeys.pop(handle_or_name, None)
            elif callable(handle_or_name):
                handle_or_name()
            else:
                for hotkey_id in [i for i, h in self._hotkeys.items() if h.normalized == handle_or_name]:
                    del self._hotkeys[hotkey_id]

    def unhook_all(self):
        with self._lock:
            self._hotkeys.clear()
            self._held.clear()
            self._down.clear()
            idle = not self._subs
        if idle:
            self._stop_listener()

    # ---------------------------------------------------------------- olay işleme (dinleyici iş parçacığı)
    def _key_ident(self, key) -> Any:
        name = self._name_of_key.get(key)
        if name:
            return name
        vk = getattr(key, "vk", None)
        if vk is not None:
            return ("vk", vk)
        char = getattr(key, "char", None)
        return ("char", char.lower() if char else None)

    def _numpad_name(self, key) -> Optional[str]:
        vk = getattr(key, "vk", None)
        if not isinstance(vk, int):
            return None
        if self.platform == platform_utils.LINUX and _X11_KP_0 <= vk <= _X11_KP_9:
            return f"numpad {vk - _X11_KP_0}"
        if self.platform == platform_utils.MACOS and vk in _MAC_KEYPAD_KEYCODES:
            return f"numpad {_MAC_KEYPAD_KEYCODES[vk]}"
        return None

    def _event_key_name(self, key, shift_held: bool) -> Optional[str]:
        """pynput olay tuşu -> kanonik ad ('a', '5', 'f5', 'space', 'numpad 3'...); tanınmıyorsa None."""
        name = self._name_of_key.get(key)
        if name:
            return name
        numpad = self._numpad_name(key)
        if numpad:
            return numpad
        char = getattr(key, "char", None)
        if not char:
            return None
        if len(char) == 1 and 1 <= ord(char) <= 26:
            char = chr(ord(char) + 96)          # Ctrl+harf kontrol karakteri -> harf
        if shift_held and char in _UNSHIFT:
            return _UNSHIFT[char]
        return char.lower()

    def _on_press(self, key):
        try:
            modifier = self._mod_of_key.get(key)
            if modifier:
                self._held.add(modifier)
                return
            now = self._monotonic()
            ident = self._key_ident(key)
            last = self._down.get(ident)
            self._down[ident] = now
            held = frozenset(self._held)
            # Tuş otomatik tekrarı kısayolu yeniden tetiklemez (ama yazılan karakter olarak sayılır)
            is_repeat = last is not None and now - last < _REPEAT_WINDOW
            name = None if is_repeat else self._event_key_name(key, "shift" in held)
            if name:
                with self._lock:
                    matches = [h for h in self._hotkeys.values() if h.key == name and h.modifiers == held]
                for hotkey in matches:
                    try:
                        hotkey.callback()
                    except Exception as exc:
                        log_error(f"Kısayol geri çağrısı hatası: {hotkey.normalized}", exc)
            self._notify_typed(key, held)
        except Exception as exc:
            log_error("pynput basış olayı işlenemedi", exc)

    def _on_release(self, key):
        try:
            modifier = self._mod_of_key.get(key)
            if modifier:
                self._held.discard(modifier)
                return
            self._down.pop(self._key_ident(key), None)
        except Exception as exc:
            log_error("pynput bırakış olayı işlenemedi", exc)

    def _notify_typed(self, key, held: frozenset):
        with self._lock:
            subs = list(self._subs)
        if not subs:
            return
        # Ctrl/Cmd/Super ile basılan tuşlar kısayoldur, yazılan metin değil (AltGr = Ctrl+Alt değil, ayrı)
        shortcut_like = ("win" in held) or ("ctrl" in held and "alt" not in held)
        kind, char = classify_pynput_key(key, self._pk)
        if shortcut_like:
            kind, char = "other", None
        for sub in subs:
            try:
                sub.on_key(kind, char)
            except Exception as exc:
                log_error("Yazılan tuş geri çağrısı hatası", exc)

    def create_key_listener(self, on_key):
        return _TypedSubscription(self, on_key)

    # ---------------------------------------------------------------- enjeksiyon
    def _get_controller(self):
        with self._lock:
            if self._controller is None:
                self._controller = self._pk.Controller()
            return self._controller

    def _to_pynput_key(self, name: str):
        key_cls = self._pk.Key
        if name in _SEND_MODIFIER_MEMBER:
            member = getattr(key_cls, _SEND_MODIFIER_MEMBER[name], None)
            if member is not None:
                return member
        elif name in _NAMED_KEYS:
            member = getattr(key_cls, _NAMED_KEYS[name], None)
            if member is not None:
                return member
        elif name.startswith("numpad ") and name[7:].isdigit():
            return self._pk.KeyCode.from_char(name[7:])
        elif len(name) == 1:
            return self._pk.KeyCode.from_char(name)
        raise ValueError(f"Bu platformda desteklenmeyen tuş: {name!r}")

    def write(self, text):
        self._get_controller().type(text.replace("\r\n", "\n").replace("\r", "\n"))

    def send(self, keys):
        parsed = keynames.parse_shortcut(keys)
        controller = self._get_controller()
        modifiers = [self._to_pynput_key(m) for m in parsed.modifiers]
        main_key = self._to_pynput_key(parsed.key) if parsed.key is not None else None
        pressed = []
        try:
            for modifier in modifiers:
                controller.press(modifier)
                pressed.append(modifier)
                self._sleep(0.005)
            if main_key is not None:
                controller.press(main_key)
                self._sleep(0.01)
                controller.release(main_key)
                self._sleep(0.005)
        finally:
            for modifier in reversed(pressed):
                controller.release(modifier)

    def send_media(self, name):
        member = getattr(self._pk.Key, _MEDIA_MEMBERS.get(name, ""), None)
        if member is None:
            raise ValueError(f"Bu platformda desteklenmeyen medya tuşu: {name!r}")
        controller = self._get_controller()
        controller.press(member)
        controller.release(member)


# ------------------------------------------------------------------ fabrika
def create_backend(platform: Optional[str] = None, env: Optional[Mapping[str, str]] = None, *,
                   pynput_importer: Optional[Callable[[], Any]] = None,
                   mac_probe: Optional[Callable[[], Tuple[Optional[bool], Optional[bool]]]] = None,
                   keyboard_module: Any = None) -> InputBackend:
    """Platforma uygun girdi arka ucunu kurar; desteklenmiyorsa UnavailableBackend (çökmez)."""
    plat = platform_utils.current_platform(platform)
    if plat == platform_utils.WINDOWS:
        try:
            return WindowsKeyboardBackend(keyboard_module=keyboard_module)
        except ImportError as exc:
            return UnavailableBackend(BackendStatus(False, STATUS_MISSING_DEPENDENCY, f"keyboard: {exc}"))
    status = check_environment(plat, env, pynput_importer=pynput_importer, mac_probe=mac_probe)
    if not status.ok:
        log_warning(f"Girdi arka ucu kullanılamıyor: {status.code} {status.detail}")
        return UnavailableBackend(status)
    try:
        module = (pynput_importer or import_pynput_keyboard)()
        return PynputBackend(plat, keyboard_module=module)
    except Exception as exc:
        return UnavailableBackend(BackendStatus(False, STATUS_MISSING_DEPENDENCY, f"{type(exc).__name__}: {exc}"))
