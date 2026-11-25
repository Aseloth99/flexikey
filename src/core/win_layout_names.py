"""Windows: ``keyboard`` kütüphanesinin tuş adlarını öndeki pencerenin klavye düzenine göre üretir.

Sorun: ``keyboard`` bir tuşun adını (yazılan harfi) kendi iş parçacığının o anki klavye düzeniyle (``ToUnicode``)
bulur ve önbellekte tutar; tabloyu da bir kez kurar. FlexiKey oturum açılışında, kullanıcının düzeni (ör. Türkçe Q)
yerleşmeden başlarsa tablo ABD düzeniyle kurulur: Türkçe Q'daki "i" tuşu "'", "ı" tuşu "i" diye görünür ve içinde
"i" geçen hiçbir kısaltma tetiklenmez; program yeniden açılınca düzelir. Kancanın kendini yeniden kurması tabloyu
yenilemez. Kısayollar etkilenmez (RegisterHotKey, tuş adı kullanmaz).

Çözüm: ad önbelleği düzen başına tutulur. Her tuş olayında öndeki pencerenin düzeni (``GetKeyboardLayout``) alınır
ve ad ``ToUnicodeEx`` / ``MapVirtualKeyExW`` ile o düzene göre çıkarılır. Kullanıcı düzen değiştirirse (Türkçe Q /
ABD) de doğru ad gelir. ``ToUnicodeEx``'e 0x4 bayrağı verilir: klavyenin ölü tuş durumu değişmez (^ ´ ¨ bozulmaz).

Yalnızca ``keyboard._winkeyboard``'ın şu (alt çizgisiz ama belgelenmemiş) adlarına dayanır: ``to_name``,
``from_name``, ``get_event_names``, ``_setup_name_tables``, ``tables_lock``, ``keypad_keys``, ``official_virtual_keys``,
``keyboard_state_type``, ``GetKeyNameText``. Biri yoksa hiçbir şey değiştirilmez (eski davranış sürer).
"""

from __future__ import annotations

import ctypes
from typing import Any, Callable, Iterator, Optional

DONT_CHANGE_KEYBOARD_STATE = 0x4      # ToUnicodeEx: ölü tuş durumuna dokunma (Windows 10 1607+; eskilerde yok sayılır)
MAPVK_VK_TO_CHAR = 2

REQUIRED_NAMES = ('to_name', 'from_name', 'get_event_names', '_setup_name_tables', 'tables_lock', 'keypad_keys',
                  'official_virtual_keys', 'keyboard_state_type', 'GetKeyNameText')


class LayoutNameTable(dict):
    """``_winkeyboard.to_name`` yerine geçen tablo: içte anahtar (düzen, giriş).

    Kütüphanenin kanca kodu her olayda şu sırayla sorar: ``entry in to_name`` -> yoksa
    ``to_name[entry] = list(get_event_names(*entry))`` -> ``to_name[entry]``. Düzen ilk soruda (``in``) okunur ve aynı
    olayın ad üretiminde, yazımında ve okumasında kullanılır. Kanca tek iş parçacığında çalışır.
    """

    MAX_CHANGE_REPORTS = 20            # düzen değişimi günlüğe en çok bu kadar yazılır (pencereler arası gidip gelme)

    def __init__(self, layout_fn: Callable[[], Any], on_change: Optional[Callable[[int, int], None]] = None):
        super().__init__()
        self._layout_fn = layout_fn
        self._on_change = None
        self._reports = 0
        self.layout = 0
        self.refresh_layout()
        self._on_change = on_change

    def refresh_layout(self) -> int:
        try:
            layout = int(self._layout_fn() or 0)
        except Exception:
            return self.layout         # okunamadıysa bir önceki düzende kal
        if layout != self.layout:
            old, self.layout = self.layout, layout
            if self._on_change is not None and self._reports < self.MAX_CHANGE_REPORTS:
                self._reports += 1
                try:
                    self._on_change(old, layout)
                except Exception:
                    pass
        return self.layout

    def __bool__(self) -> bool:
        # _setup_name_tables "tablo kurulu" saysın: kanca yeniden kurulunca tabloyu eski düzenle doldurmasın
        return True

    def __contains__(self, entry) -> bool:
        return dict.__contains__(self, (self.refresh_layout(), entry))

    def __getitem__(self, entry):
        return dict.get(self, (self.layout, entry), [])      # defaultdict(list) gibi: yoksa boş liste

    def __setitem__(self, entry, names) -> None:
        dict.__setitem__(self, (self.layout, entry), names)

    def get(self, entry, default=None):
        return dict.get(self, (self.layout, entry), default)


class User32Api:
    """Gerçek Windows çağrıları (kütüphanenin ``user32`` nesnesinden ayrı: onun argtypes'ına dokunulmaz)."""

    def __init__(self, keyboard_state_type: Any):
        from ctypes import wintypes
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        self._foreground = user32.GetForegroundWindow
        self._foreground.argtypes = []
        self._foreground.restype = wintypes.HWND
        self._thread_of = user32.GetWindowThreadProcessId
        self._thread_of.argtypes = [wintypes.HWND, ctypes.c_void_p]
        self._thread_of.restype = wintypes.DWORD
        self._layout_of = user32.GetKeyboardLayout
        self._layout_of.argtypes = [wintypes.DWORD]
        self._layout_of.restype = ctypes.c_void_p
        self._to_unicode_ex = user32.ToUnicodeEx
        self._to_unicode_ex.argtypes = [ctypes.c_uint, ctypes.c_uint, keyboard_state_type, ctypes.c_wchar_p,
                                        ctypes.c_int, ctypes.c_uint, ctypes.c_void_p]
        self._to_unicode_ex.restype = ctypes.c_int
        self._map_vk = user32.MapVirtualKeyExW
        self._map_vk.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
        self._map_vk.restype = ctypes.c_uint

    def foreground_layout(self) -> int:
        """Öndeki pencerenin klavye düzeni; ön pencere yoksa bu iş parçacığınınki (GetKeyboardLayout(0))."""
        hwnd = self._foreground()
        thread_id = self._thread_of(hwnd, None) if hwnd else 0
        return self._layout_of(thread_id) or 0

    def to_unicode_ex(self, vk, scan_code, state, buffer, size, flags, layout) -> int:
        return self._to_unicode_ex(vk, scan_code, state, buffer, size, flags, layout or None)

    def map_vk_to_char(self, vk, layout) -> int:
        return self._map_vk(vk, MAPVK_VK_TO_CHAR, layout or None)


def make_event_names(wk: Any, api: Any, table: LayoutNameTable) -> Callable[..., Iterator[str]]:
    """``_winkeyboard.get_event_names``'in düzene duyarlı karşılığı: aynı adlar, aynı sıra, ``table.layout`` düzeniyle."""
    keypad_keys = wk.keypad_keys
    official = wk.official_virtual_keys
    state = wk.keyboard_state_type()
    unicode_buffer = ctypes.create_unicode_buffer(32)
    name_buffer = ctypes.create_unicode_buffer(32)

    def get_event_names(scan_code, vk, is_extended, modifiers):
        layout = table.layout
        is_keypad = (scan_code, vk, is_extended) in keypad_keys
        is_official = vk in official
        if is_keypad and is_official:
            yield official[vk][0]

        state[0x10] = 0x80 * ('shift' in modifiers)
        state[0x11] = 0x80 * ('alt gr' in modifiers)
        state[0x12] = 0x80 * ('alt gr' in modifiers)
        state[0x14] = 0x01 * ('caps lock' in modifiers)
        state[0x90] = 0x01 * ('num lock' in modifiers)
        state[0x91] = 0x01 * ('scroll lock' in modifiers)
        ret = api.to_unicode_ex(vk, scan_code, state, unicode_buffer, len(unicode_buffer),
                                DONT_CHANGE_KEYBOARD_STATE, layout)
        if ret and unicode_buffer.value:
            yield unicode_buffer.value
            if ret < 0:
                # ölü tuş: 0x4 bayrağını tanımayan eski Windows'ta durum değişmiş olabilir; ikinci çağrı temizler
                api.to_unicode_ex(vk, scan_code, state, unicode_buffer, len(unicode_buffer),
                                  DONT_CHANGE_KEYBOARD_STATE, layout)

        if wk.GetKeyNameText(scan_code << 16 | is_extended << 24, name_buffer, len(name_buffer)) and name_buffer.value:
            yield name_buffer.value

        char = api.map_vk_to_char(vk, layout) & 0xFF
        if char:
            yield chr(char)

        if not is_keypad and is_official:
            yield official[vk][0]

    return get_event_names


def layout_text(layout: int) -> str:
    """Günlük için: 0x41F041F -> '041F041F' (alt 16 bit dil, üst 16 bit düzen; Türkçe Q = 041F041F, ABD = 04090409)."""
    return f"{layout & 0xFFFFFFFF:08X}"


def install(keyboard_module: Any, api: Optional[Any] = None,
            on_change: Optional[Callable[[int, int], None]] = None) -> bool:
    """``keyboard``'ın Windows ad tablosunu düzene duyarlı yapar. Kuruluysa ya da kurulursa True; kütüphane
    beklenen biçimde değilse False (hiçbir şey değiştirilmez). ``on_change(eski, yeni)``: öndeki pencerenin
    düzeni değişince (teşhis günlüğü için, en çok ``MAX_CHANGE_REPORTS`` kez; kanca iş parçacığında çağrılır)."""
    wk = getattr(keyboard_module, '_os_keyboard', None)
    if wk is None or any(not hasattr(wk, name) for name in REQUIRED_NAMES):
        return False
    if isinstance(wk.to_name, LayoutNameTable):
        return True
    api = api if api is not None else User32Api(wk.keyboard_state_type)
    table = LayoutNameTable(api.foreground_layout, on_change)
    wk.get_event_names = make_event_names(wk, api, table)
    # Ad -> tuş tablosu (send('ctrl+v'), kısayol çözümleme) boşsa şimdi, öndeki pencerenin düzeniyle kurulur. Bundan
    # sonra to_name hep "dolu" görüneceğinden kütüphane onu bir daha kurmaz.
    wk._setup_name_tables()
    with wk.tables_lock:
        wk.to_name = table
    return True


def missing_names(keyboard_module: Any) -> list:
    """Teşhis için: kütüphanede bulunmayan adlar (boşsa kurulabilir)."""
    wk = getattr(keyboard_module, '_os_keyboard', None)
    if wk is None:
        return ['_os_keyboard']
    return [name for name in REQUIRED_NAMES if not hasattr(wk, name)]
