"""Program / dosya / URL başlatma planlaması (macOS ve Linux).

Hiçbir yolda kabuk (``shell=True``, ``/bin/sh -c``) KULLANILMAZ. Kullanıcı tanımlı değer şuna çevrilir:

  * 'exec'    : argüman listesiyle doğrudan çalıştırma (``shlex`` ile ayrıştırılmış, ``~`` açılmış);
  * 'open'    : varsayılan uygulamayla açma (macOS ``open``, Linux ``xdg-open``) — dosya, klasör, URL;
  * 'qt_open' : xdg-open yoksa ``QDesktopServices.openUrl``.

Plan saf bir fonksiyondur (süreç başlatmaz), bu yüzden sahte ``which``/``exists`` ile test edilir.
Windows'un kendi yolu (ShellExecute/CreateProcess) hotkey_manager'da değişmeden durur.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
from typing import Callable, NamedTuple, Optional, Sequence, Tuple

from src.utils import platform_utils

# "http://x", "file:///x", "ftp://x" ve çift eğik çizgisiz yaygın şemalar
_URI_RE = re.compile(r'^(?:[a-zA-Z][a-zA-Z0-9+.\-]*://|(?:mailto|tel|sms|callto|xmpp|magnet|'
                     r'x-apple\.systempreferences|trash):)')


class LaunchPlan(NamedTuple):
    kind: str                      # 'exec' | 'open' | 'qt_open'
    argv: Tuple[str, ...] = ()     # 'exec' ve 'open' için çalıştırılacak argüman listesi
    target: str = ""               # 'qt_open' için açılacak hedef


class CommandUnavailable(Exception):
    """Komut bu platformda yok ('unsupported') ya da gerekli program kurulu değil ('not_installed')."""

    def __init__(self, command: str, reason: str = "unsupported", platform: Optional[str] = None):
        super().__init__(f"{reason}: {command}")
        self.command = command
        self.reason = reason
        self.platform = platform_utils.current_platform(platform)


def looks_like_uri(text: str) -> bool:
    return bool(_URI_RE.match(text or ""))


def open_plan(target: str, platform: Optional[str] = None,
              which: Callable[[str], Optional[str]] = shutil.which) -> LaunchPlan:
    """Dosya/klasör/URL'yi varsayılan uygulamayla açma planı."""
    if platform_utils.is_macos(platform):
        return LaunchPlan('open', ('open', target))
    if which('xdg-open'):
        return LaunchPlan('open', ('xdg-open', target))
    return LaunchPlan('qt_open', (), target)


def _resolve_executable(program: str, which: Callable[[str], Optional[str]],
                        isfile: Callable[[str], bool], access: Callable[[str, int], bool]) -> Optional[str]:
    if os.sep in program or '/' in program:
        return program if isfile(program) and access(program, os.X_OK) else None
    return which(program)


def plan_launch(command_line: str, platform: Optional[str] = None, *,
                which: Callable[[str], Optional[str]] = shutil.which,
                isfile: Callable[[str], bool] = os.path.isfile,
                exists: Callable[[str], bool] = os.path.exists,
                access: Callable[[str, int], bool] = os.access,
                expanduser: Callable[[str], str] = os.path.expanduser) -> LaunchPlan:
    """Kullanıcı tanımlı değeri (program, dosya, klasör, URL veya komut satırı) kabuksuz plana çevirir.

    Öncelik: URL -> yol gibi görünen tam satır (çalıştırılabilir dosya: çalıştır, aksi halde aç) ->
    ilk sözcük çalıştırılabilir (PATH veya yol) -> yol olarak var olan satır -> macOS uygulama adı.
    Hiçbiri değilse FileNotFoundError.
    """
    plat = platform_utils.current_platform(platform)
    line = (command_line or '').strip()
    if not line:
        raise ValueError("Komut boş")
    if looks_like_uri(line):
        return open_plan(line, plat, which)

    expanded = expanduser(line)
    if ('/' in line or line.startswith('~')) and exists(expanded):
        if isfile(expanded) and access(expanded, os.X_OK):
            return LaunchPlan('exec', (expanded,))
        return open_plan(expanded, plat, which)

    try:
        parts = shlex.split(line)
    except ValueError:
        parts = [line]
    if not parts:
        raise ValueError("Komut boş")
    parts = [expanduser(part) for part in parts]
    program, rest = parts[0], parts[1:]

    if _resolve_executable(program, which, isfile, access):
        return LaunchPlan('exec', tuple(parts))
    if plat == platform_utils.MACOS:
        return LaunchPlan('exec', ('open', '-a', program, *rest))     # uygulama adı (ör. Safari)
    raise FileNotFoundError(f"Komut bulunamadı: {program}")


def first_available(candidates: Sequence[Sequence[str]],
                    which: Callable[[str], Optional[str]] = shutil.which,
                    platform: Optional[str] = None) -> list:
    """Aday argüman listelerinden ilk kurulu programa ait olanı döndürür.

    Hiçbiri kurulu değilse CommandUnavailable('prog1 / prog2', 'not_installed')."""
    for argv in candidates:
        if argv and which(argv[0]):
            return list(argv)
    names = " / ".join(dict.fromkeys(argv[0] for argv in candidates if argv))
    raise CommandUnavailable(names, "not_installed", platform)
