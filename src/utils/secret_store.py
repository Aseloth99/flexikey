"""Gizli metinlerin (parola vb.) diskte şifreli tutulması.

Windows'ta DPAPI (CryptProtectData): anahtar Windows hesabına bağlıdır, uygulama bir parola ya da anahtar saklamaz.
Dosyayı başka biri ya da başka bir hesap açarsa değerler çözülemez (kayıt korunur, değer boş görünür).
Diğer sistemlerde bu kullanılamaz: `protect` None döner ve çağıran değeri olduğu gibi saklar
(değer yine de listede ve bildirimlerde gizli kalır).
"""

from __future__ import annotations

import base64
import sys
from typing import Optional

PREFIX = "dpapi1:"
_ENTROPY = b"FlexiKey.secret.v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


def available() -> bool:
    return sys.platform == "win32"


def is_blob(value: object) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.POINTER(_DataBlob), ctypes.c_void_p,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(_DataBlob), ctypes.c_void_p,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p

    def _blob_of(data: bytes) -> "_DataBlob":
        buf = ctypes.create_string_buffer(data, len(data))
        return _DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    def _take(out: "_DataBlob") -> bytes:
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            _kernel32.LocalFree(out.pbData)

    def _protect_bytes(data: bytes) -> Optional[bytes]:
        src, keep = _blob_of(data)
        entropy, keep2 = _blob_of(_ENTROPY)
        out = _DataBlob()
        if not _crypt32.CryptProtectData(ctypes.byref(src), "FlexiKey", ctypes.byref(entropy), None, None,
                                         _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
            return None
        del keep, keep2
        return _take(out)

    def _unprotect_bytes(data: bytes) -> Optional[bytes]:
        src, keep = _blob_of(data)
        entropy, keep2 = _blob_of(_ENTROPY)
        out = _DataBlob()
        if not _crypt32.CryptUnprotectData(ctypes.byref(src), None, ctypes.byref(entropy), None, None,
                                           _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
            return None
        del keep, keep2
        return _take(out)
else:  # pragma: no cover - Windows dışı
    def _protect_bytes(data: bytes) -> Optional[bytes]:
        return None

    def _unprotect_bytes(data: bytes) -> Optional[bytes]:
        return None


def protect(text: str) -> Optional[str]:
    """Metni şifreler: "dpapi1:<base64>". Bu sistemde şifrelenemezse None."""
    if not text:
        return None
    try:
        sealed = _protect_bytes(text.encode("utf-8"))
    except Exception:
        return None
    if sealed is None:
        return None
    return PREFIX + base64.b64encode(sealed).decode("ascii")


def unprotect(blob: str) -> Optional[str]:
    """`protect` çıktısını çözer; başka hesaba/makineye ait ya da bozuksa None."""
    if not is_blob(blob):
        return None
    try:
        raw = base64.b64decode(blob[len(PREFIX):], validate=True)
        plain = _unprotect_bytes(raw)
        return plain.decode("utf-8") if plain is not None else None
    except Exception:
        return None
