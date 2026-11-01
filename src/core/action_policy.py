"""Eylem politikası: yıkıcı eylemler, kullanıcı tanımlı komut doğrulaması, içe aktarma önizlemesi.

Qt'ye bağımlı değildir; hotkey_manager (çalıştırma) ve main_window (içe aktarma önizlemesi)
tarafından kullanılır ve tek başına test edilebilir.
"""

from __future__ import annotations

import os
from typing import Any, Dict, FrozenSet, List, NamedTuple, Optional, Sequence, Tuple

from src.utils import platform_utils
from src.utils.locales import t

# Onaysız çalıştırılmaması gereken yıkıcı yerleşik komutlar -> etiket anahtarı
DESTRUCTIVE_COMMANDS: Dict[str, str] = {
    'bilgisayari_kapat': 'cmd_shutdown',
    'yeniden_basla': 'cmd_restart',
    'oturumu_kapat': 'cmd_logout',
    'cop_kutusunu_bosalt': 'cmd_empty_recycle_bin',
}

# HotkeyManager._build_command_table() anahtarlarıyla eşit olmalıdır (testle doğrulanır)
KNOWN_COMMANDS = frozenset({
    'bilgisayari_kapat', 'yeniden_basla', 'uyku_modu', 'hazirda_beklet', 'kilitle',
    'oturumu_kapat', 'ekrani_kapat', 'cop_kutusunu_bosalt', 'ekran_goruntusu',
    'ekran_alintisi', 'pano_gecmisi', 'emoji_paneli', 'buyutec', 'ekran_klavyesi',
    'gorev_yoneticisi', 'calistir', 'komut_istemi', 'powershell', 'dosya_gezgini',
    'not_defteri', 'hesap_makinesi', 'paint', 'ayarlar', 'denetim_masasi', 'aygit_yoneticisi',
    'ses_karistirici', 'hizmetler', 'chrome', 'firefox', 'edge', 'ses_ac', 'ses_kis',
    'sesi_kapat', 'ses_maksimum', 'ses_minimum', 'oynat_duraklat', 'sonraki_sarki',
    'onceki_sarki', 'durdur', 'masaustunu_goster', 'tum_pencereleri_kucult', 'gorev_gorunumu',
    'yeni_sanal_masaustu', 'sonraki_masaustu', 'onceki_masaustu', 'sanal_masaustu_kapat',
    'sola_yasla', 'saga_yasla', 'pencereyi_buyut', 'pencereyi_kapat', 'pencere_degistir',
    'geri', 'ileri', 'sayfayi_yenile', 'yeni_sekme', 'sekmeyi_kapat', 'kapatilan_sekmeyi_ac',
    'gizli_pencere', 'bu_bilgisayar', 'indirilenler', 'belgelerim', 'resimlerim', 'muziklerim',
    'videolarim', 'masaustu', 'geri_donusum_kutusu', 'kopyala', 'kes', 'yapistir',
    'tumunu_sec', 'geri_al', 'yeniden_yap', 'bul', 'kaydet', 'yazdir',
})

# Risk sınıfları
RISK_NORMAL = 'normal'
RISK_DESTRUCTIVE = 'destructive'      # güç/oturum/silme: çalıştırmadan önce onay ister
RISK_LAUNCH = 'launch'                # kullanıcı tanımlı program/dosya çalıştırır
RISK_CUSTOM_COMMAND = 'custom'        # bilinmeyen "sistem komutu" değeri: serbest komut satırı
RISK_INVALID = 'invalid'              # bilinmeyen eylem türü

# Kabuk (cmd.exe) yönlendirme/zincirleme karakterleri
SHELL_METACHARS = frozenset('&|<>^%`;()\r\n\x00')
# POSIX kabuğu (/bin/sh) yönlendirme/zincirleme/genişletme karakterleri
POSIX_SHELL_METACHARS = frozenset('&|<>;`$(){}\\\r\n\x00*?[]!#~')
# Doğrudan CreateProcess ile çalışmayan ama zararsız (zincirsiz) kullanılabilen cmd yerleşikleri
SHELL_FALLBACK_BUILTINS = frozenset({'start'})
MAX_COMMAND_LENGTH = 8192


class ShellPolicy(NamedTuple):
    """Platformun kabuk semantiği: hangi kabuk, hangi yerleşikler (varsa) ve hangi karakterler yasak."""
    argv_prefix: Tuple[str, ...]
    builtins: FrozenSet[str]
    metachars: FrozenSet[str]


# Kullanıcı tanımlı komutlar HİÇBİR platformda kabuğa verilmez; tek istisna kabuk yerleşiği olan
# ve zincirleme karakteri içermeyen komutlardır. Windows: ``cmd.exe /d /c`` + 'start'.
# macOS/Linux: ``/bin/sh -c`` tanımlıdır ama izinli yerleşik YOK (komutlar shlex ile doğrudan çalışır).
SHELL_POLICIES: Dict[str, ShellPolicy] = {
    platform_utils.WINDOWS: ShellPolicy(('cmd.exe', '/d', '/c'), SHELL_FALLBACK_BUILTINS, SHELL_METACHARS),
    platform_utils.MACOS: ShellPolicy(('/bin/sh', '-c'), frozenset(), POSIX_SHELL_METACHARS),
    platform_utils.LINUX: ShellPolicy(('/bin/sh', '-c'), frozenset(), POSIX_SHELL_METACHARS),
}


def shell_policy(platform: Optional[str] = None) -> ShellPolicy:
    return SHELL_POLICIES[platform_utils.current_platform(platform)]


def shell_argv(command_line: str, platform: Optional[str] = None) -> List[str]:
    """Platformun kabuk çağrısı argv'si (Windows: cmd.exe /d /c ..., POSIX: /bin/sh -c ...)."""
    return list(shell_policy(platform).argv_prefix) + [command_line]


def classify_action(action_type: Any, action_value: Any) -> str:
    """Bir eylemin risk sınıfını döndürür."""
    if action_type == 'command':
        if action_value in DESTRUCTIVE_COMMANDS:
            return RISK_DESTRUCTIVE
        if action_value in KNOWN_COMMANDS:
            return RISK_NORMAL
        return RISK_CUSTOM_COMMAND
    if action_type in ('open_file', 'run_program'):
        return RISK_LAUNCH
    if action_type in ('text', 'shortcut', 'open_url'):
        return RISK_NORMAL
    return RISK_INVALID


def validate_user_command(target: str) -> str:
    """Kullanıcı tanımlı komut satırını doğrular; geçerliyse ortam değişkenleri açılmış halini döndürür.

    Reddedilen: boş, aşırı uzun, NUL/satır sonu içeren değerler.
    """
    if not isinstance(target, str):
        raise ValueError("Komut metin olmalı")
    target = target.strip()
    if not target:
        raise ValueError("Komut boş")
    if len(target) > MAX_COMMAND_LENGTH:
        raise ValueError("Komut çok uzun")
    if any(ch in target for ch in ('\x00', '\r', '\n')):
        raise ValueError("Komut geçersiz karakter içeriyor")
    return os.path.expandvars(target)


def shell_fallback_allowed(command_line: str, platform: Optional[str] = None) -> bool:
    """Kabuk yedeği yalnızca platform politikasının izin verdiği, zincirleme karakteri içermeyen
    yerleşikler için (Windows: 'start ...'; macOS/Linux: hiçbiri)."""
    policy = shell_policy(platform)
    if any(ch in policy.metachars for ch in command_line):
        return False
    first = command_line.strip().split(None, 1)[0].lower() if command_line.strip() else ''
    return first in policy.builtins


def _shorten(text: str, limit: int) -> str:
    text = ' '.join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def describe_hotkey_action(record: Dict[str, Any], lang: Optional[str], max_value_len: int = 60) -> Tuple[str, str]:
    """(risk, tek satırlık açıklama) döndürür."""
    action_type = record.get('action_type')
    value = record.get('action_value', '')
    risk = classify_action(action_type, value)
    type_label = t(f"action_{action_type}", lang) if risk != RISK_INVALID else str(action_type)
    if action_type == 'command' and value in DESTRUCTIVE_COMMANDS:
        shown = t(DESTRUCTIVE_COMMANDS[value], lang)
    else:
        shown = _shorten(value, max_value_len)
    return risk, f"{record.get('shortcut', '?')}  →  {type_label}: {shown}"


_RISK_MARKS = {
    RISK_DESTRUCTIVE: '⚠ ',
    RISK_LAUNCH: '⚠ ',
    RISK_CUSTOM_COMMAND: '⚠ ',
    RISK_INVALID: '✖ ',
    RISK_NORMAL: '• ',
}


def build_import_preview(hotkeys: Sequence[Dict[str, Any]], lang: Optional[str] = None,
                         max_value_len: int = 60) -> Dict[str, Any]:
    """İçe aktarılacak kısayolların eylem listesini ve risk sayılarını üretir.

    Dönen sözlük: lines (tüm satırlar, riskliler başta işaretli), risky (⚠ sayısı),
    destructive, launch, custom (sayılar).
    """
    lines: List[str] = []
    counts = {RISK_DESTRUCTIVE: 0, RISK_LAUNCH: 0, RISK_CUSTOM_COMMAND: 0, RISK_INVALID: 0}
    for record in hotkeys:
        risk, text = describe_hotkey_action(record, lang, max_value_len)
        if risk in counts:
            counts[risk] += 1
        lines.append(_RISK_MARKS.get(risk, '• ') + text)
    return {
        'lines': lines,
        'risky': counts[RISK_DESTRUCTIVE] + counts[RISK_LAUNCH] + counts[RISK_CUSTOM_COMMAND],
        'destructive': counts[RISK_DESTRUCTIVE],
        'launch': counts[RISK_LAUNCH],
        'custom': counts[RISK_CUSTOM_COMMAND],
    }
