"""Yerleşik sistem komutları tablosu (Windows, macOS, Linux).

``build_command_table(host, platform)`` komut adı -> çağrılabilir sözlüğü üretir. ``host`` (HotkeyManager)
şunları sağlar:

  host.launch(target)      liste (argv) ya da metin; kabuksuz süreç başlatır
  host.send_keys(keys)     tuş kombinasyonunu arka planda (INPUT_INJECTOR) gönderir; 'win' = Win/Super/Cmd
  host.send_media(name)    medya tuşu (play_pause, next, previous, ...)
  host.which(name)         PATH araması (shutil.which)

Windows tablosu önceki davranışın aynısıdır (VK kodlu doğrudan SendInput, shutdown.exe ...). macOS/Linux
tabloları kendi yerel araçlarını kullanır (osascript/pmset/open, systemctl/loginctl/xdg-open/pactl ...);
bir komutun karşılığı yoksa ``CommandUnavailable('unsupported')``, gerekli program kurulu değilse
``CommandUnavailable('not_installed')`` fırlatılır (kullanıcıya yerelleştirilmiş hata gösterilir).
Tüm tablolar ``action_policy.KNOWN_COMMANDS`` ile aynı anahtar kümesine sahiptir (testle doğrulanır).
"""

from __future__ import annotations

import getpass
import glob
import os
import shutil
from typing import Callable, Dict, Optional

from src.utils import platform_utils
from src.core import win_input
from src.utils.helpers import log_error
from src.core.launcher import CommandUnavailable, first_available


def _expand(path: str) -> str:
    return os.path.expanduser(path)


# ------------------------------------------------------------------ yardımcılar
def empty_linux_trash(data_home: Optional[str] = None) -> None:
    """Linux çöp kutusunu kabuk (rm -rf ...) kullanmadan boşaltır (XDG_DATA_HOME/Trash)."""
    base = os.path.join(data_home or os.environ.get('XDG_DATA_HOME') or _expand('~/.local/share'), 'Trash')
    for sub in ('files', 'info'):
        for path in glob.glob(os.path.join(glob.escape(base), sub, '*')):
            try:
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except OSError as exc:
                log_error(f"Çöp kutusu öğesi silinemedi: {path}", exc)


def xdg_user_dir(key: str, fallback: str, home: Optional[str] = None,
                 config_home: Optional[str] = None) -> str:
    """~/.config/user-dirs.dirs içinden XDG_<KEY>_DIR (ör. DOWNLOAD) yolu; yoksa ~/<fallback>."""
    home = home or _expand('~')
    config_home = config_home or os.environ.get('XDG_CONFIG_HOME') or os.path.join(home, '.config')
    wanted = f"XDG_{key}_DIR="
    try:
        with open(os.path.join(config_home, 'user-dirs.dirs'), encoding='utf-8') as handle:
            for line in handle:
                line = line.strip()
                if line.startswith(wanted):
                    value = line[len(wanted):].strip().strip('"')
                    value = value.replace('$HOME', home).replace('${HOME}', home)
                    if value and os.path.isabs(value):
                        return value
    except OSError:
        pass
    return os.path.join(home, fallback)


# Bu platformda karşılığı olmayan komutlar (tablo bunlar için CommandUnavailable fırlatır)
UNSUPPORTED: Dict[str, frozenset] = {
    platform_utils.WINDOWS: frozenset(),
    platform_utils.MACOS: frozenset({
        'pano_gecmisi', 'ekran_klavyesi', 'paint', 'denetim_masasi', 'aygit_yoneticisi',
        'ses_karistirici', 'hizmetler', 'durdur', 'yeni_sanal_masaustu', 'sanal_masaustu_kapat',
        'sola_yasla', 'saga_yasla',
    }),
    platform_utils.LINUX: frozenset({
        'denetim_masasi', 'aygit_yoneticisi', 'hizmetler', 'yeni_sanal_masaustu', 'sanal_masaustu_kapat',
    }),
}


def command_supported(command: str, platform: Optional[str] = None) -> bool:
    """Yerleşik komutun bu platformda (kurulu program gerektirebilir) bir karşılığı var mı?"""
    return command not in UNSUPPORTED[platform_utils.current_platform(platform)]


def _unsupported(command: str, platform: str) -> Callable[[], None]:
    def action():
        raise CommandUnavailable(command, 'unsupported', platform)
    return action


# ------------------------------------------------------------------ Windows (önceki davranış)
def _windows_table(host) -> Dict[str, Callable[[], None]]:
    launch = host.launch
    combo = win_input.send_keys_combo
    vk = win_input.send_vk
    burst = win_input.send_vk_burst
    win, ctrl, shift, alt = 0x5B, 0x11, 0x10, 0x12
    return {
        # Sistem
        'bilgisayari_kapat': lambda: launch(['shutdown', '/s', '/t', '0']),
        'yeniden_basla': lambda: launch(['shutdown', '/r', '/t', '0']),
        'uyku_modu': lambda: launch(['rundll32.exe', 'powrprof.dll,SetSuspendState', '0,1,0']),
        'hazirda_beklet': lambda: launch(['shutdown', '/h']),
        'kilitle': lambda: win_input.lock_workstation(),
        'oturumu_kapat': lambda: launch(['shutdown', '/l']),
        'ekrani_kapat': lambda: win_input.turn_off_screen(),
        'cop_kutusunu_bosalt': lambda: win_input.empty_recycle_bin(),

        # Ekran & Araçlar
        'ekran_goruntusu': lambda: vk(0x2C),
        'ekran_alintisi': lambda: combo(0x53, [win, shift]),
        'pano_gecmisi': lambda: combo(0x56, [win]),
        'emoji_paneli': lambda: combo(0xBE, [win]),
        'buyutec': lambda: launch('magnify.exe'),
        'ekran_klavyesi': lambda: launch('osk.exe'),

        # Uygulamalar & Sistem Araçları
        'gorev_yoneticisi': lambda: launch('taskmgr'),
        'calistir': lambda: combo(0x52, [win]),
        'komut_istemi': lambda: launch('cmd.exe'),
        'powershell': lambda: launch('powershell.exe'),
        'dosya_gezgini': lambda: launch('explorer'),
        'not_defteri': lambda: launch('notepad'),
        'hesap_makinesi': lambda: launch('calc'),
        'paint': lambda: launch('mspaint'),
        'ayarlar': lambda: launch('ms-settings:'),
        'denetim_masasi': lambda: launch('control'),
        'aygit_yoneticisi': lambda: launch('devmgmt.msc'),
        'ses_karistirici': lambda: launch('sndvol.exe'),
        'hizmetler': lambda: launch('services.msc'),

        # Tarayıcılar
        'chrome': lambda: launch('chrome'),
        'firefox': lambda: launch('firefox'),
        'edge': lambda: launch('msedge'),

        # Ses (Sıfır gecikmeli Windows VK kodları: AF=Up, AE=Down, AD=Mute)
        'ses_ac': lambda: vk(0xAF),
        'ses_kis': lambda: vk(0xAE),
        'sesi_kapat': lambda: vk(0xAD),
        'ses_maksimum': lambda: burst(0xAF, 50),
        'ses_minimum': lambda: burst(0xAE, 50),

        # Medya (B3=PlayPause, B0=Next, B1=Prev, B2=Stop)
        'oynat_duraklat': lambda: vk(0xB3),
        'sonraki_sarki': lambda: vk(0xB0),
        'onceki_sarki': lambda: vk(0xB1),
        'durdur': lambda: vk(0xB2),

        # Pencere & Masaüstü
        'masaustunu_goster': lambda: combo(0x44, [win]),
        'tum_pencereleri_kucult': lambda: combo(0x4D, [win]),
        'gorev_gorunumu': lambda: combo(0x09, [win]),
        'yeni_sanal_masaustu': lambda: combo(0x44, [win, ctrl]),
        'sonraki_masaustu': lambda: combo(0x27, [win, ctrl]),
        'onceki_masaustu': lambda: combo(0x25, [win, ctrl]),
        'sanal_masaustu_kapat': lambda: combo(0x73, [win, ctrl]),
        'sola_yasla': lambda: combo(0x25, [win]),
        'saga_yasla': lambda: combo(0x27, [win]),
        'pencereyi_buyut': lambda: combo(0x26, [win]),
        'pencereyi_kapat': lambda: combo(0x73, [alt]),
        'pencere_degistir': lambda: combo(0x09, [alt]),

        # Tarayıcı Gezintisi
        'geri': lambda: combo(0x25, [alt]),
        'ileri': lambda: combo(0x27, [alt]),
        'sayfayi_yenile': lambda: vk(0x74),
        'yeni_sekme': lambda: combo(0x54, [ctrl]),
        'sekmeyi_kapat': lambda: combo(0x57, [ctrl]),
        'kapatilan_sekmeyi_ac': lambda: combo(0x54, [ctrl, shift]),
        'gizli_pencere': lambda: combo(0x4E, [ctrl, shift]),

        # Hızlı Erişim
        'bu_bilgisayar': lambda: launch(['explorer', '::{20D04FE0-3AEA-1069-A2D8-08002B30309D}']),
        'indirilenler': lambda: launch('shell:downloads'),
        'belgelerim': lambda: launch('shell:documents'),
        'resimlerim': lambda: launch('shell:pictures'),
        'muziklerim': lambda: launch('shell:music'),
        'videolarim': lambda: launch('shell:videos'),
        'masaustu': lambda: launch('shell:desktop'),
        'geri_donusum_kutusu': lambda: launch('shell:RecycleBinFolder'),

        # Metin & Düzenleme
        'kopyala': lambda: combo(0x43, [ctrl]),
        'kes': lambda: combo(0x58, [ctrl]),
        'yapistir': lambda: combo(0x56, [ctrl]),
        'tumunu_sec': lambda: combo(0x41, [ctrl]),
        'geri_al': lambda: combo(0x5A, [ctrl]),
        'yeniden_yap': lambda: combo(0x59, [ctrl]),
        'bul': lambda: combo(0x46, [ctrl]),
        'kaydet': lambda: combo(0x53, [ctrl]),
        'yazdir': lambda: combo(0x50, [ctrl]),
    }


# ------------------------------------------------------------------ macOS
def _osascript(script: str):
    return ['osascript', '-e', script]


def _macos_table(host) -> Dict[str, Callable[[], None]]:
    plat = platform_utils.MACOS
    launch, keys = host.launch, host.send_keys

    def folder(path: str):
        return lambda: launch(['open', _expand(path)])

    def app(name: str):
        return lambda: launch(['open', '-a', name])

    def media(name: str):
        return lambda: host.send_media(name)

    volume_get = 'output volume of (get volume settings)'
    table: Dict[str, Callable[[], None]] = {
        # Sistem
        'bilgisayari_kapat': lambda: launch(_osascript('tell application "System Events" to shut down')),
        'yeniden_basla': lambda: launch(_osascript('tell application "System Events" to restart')),
        'uyku_modu': lambda: launch(['pmset', 'sleepnow']),
        'hazirda_beklet': lambda: launch(['pmset', 'sleepnow']),
        'kilitle': lambda: keys('ctrl+win+q'),                       # Ctrl+Cmd+Q: ekranı kilitle
        'oturumu_kapat': lambda: launch(_osascript('tell application "System Events" to log out')),
        'ekrani_kapat': lambda: launch(['pmset', 'displaysleepnow']),
        'cop_kutusunu_bosalt': lambda: launch(_osascript('tell application "Finder" to empty trash')),

        # Ekran & Araçlar
        'ekran_goruntusu': lambda: launch(['screencapture', '-c']),
        'ekran_alintisi': lambda: launch(['screencapture', '-i', '-c']),
        'emoji_paneli': lambda: keys('ctrl+win+space'),
        'buyutec': lambda: keys('alt+win+8'),                        # Yakınlaştırma (Erişilebilirlik'te açıksa)

        # Uygulamalar & Sistem Araçları
        'gorev_yoneticisi': app('Activity Monitor'),
        'calistir': lambda: keys('win+space'),                       # Spotlight
        'komut_istemi': app('Terminal'),
        'powershell': lambda: launch(first_available([['pwsh']], host.which, plat)),
        'dosya_gezgini': folder('~'),
        'not_defteri': app('TextEdit'),
        'hesap_makinesi': app('Calculator'),
        'ayarlar': lambda: launch(['open', 'x-apple.systempreferences:']),

        # Tarayıcılar
        'chrome': app('Google Chrome'),
        'firefox': app('Firefox'),
        'edge': app('Microsoft Edge'),

        # Ses (osascript: ek izin gerektirmez)
        'ses_ac': lambda: launch(_osascript(f'set volume output volume ({volume_get} + 6)')),
        'ses_kis': lambda: launch(_osascript(f'set volume output volume ({volume_get} - 6)')),
        'sesi_kapat': lambda: launch(_osascript('set volume output muted (not (output muted of (get volume settings)))')),
        'ses_maksimum': lambda: launch(_osascript('set volume output volume 100')),
        'ses_minimum': lambda: launch(_osascript('set volume output volume 0')),

        # Medya
        'oynat_duraklat': media('play_pause'),
        'sonraki_sarki': media('next'),
        'onceki_sarki': media('previous'),

        # Pencere & Masaüstü
        'masaustunu_goster': lambda: keys('f11'),
        'tum_pencereleri_kucult': lambda: keys('alt+win+m'),
        'gorev_gorunumu': lambda: keys('ctrl+up'),                   # Mission Control
        'sonraki_masaustu': lambda: keys('ctrl+right'),
        'onceki_masaustu': lambda: keys('ctrl+left'),
        'pencereyi_buyut': lambda: keys('ctrl+win+f'),
        'pencereyi_kapat': lambda: keys('win+w'),
        'pencere_degistir': lambda: keys('win+tab'),

        # Tarayıcı Gezintisi
        'geri': lambda: keys('win+['),
        'ileri': lambda: keys('win+]'),
        'sayfayi_yenile': lambda: keys('win+r'),
        'yeni_sekme': lambda: keys('win+t'),
        'sekmeyi_kapat': lambda: keys('win+w'),
        'kapatilan_sekmeyi_ac': lambda: keys('win+shift+t'),
        'gizli_pencere': lambda: keys('win+shift+n'),

        # Hızlı Erişim
        'bu_bilgisayar': lambda: launch(['open', '/']),
        'indirilenler': folder('~/Downloads'),
        'belgelerim': folder('~/Documents'),
        'resimlerim': folder('~/Pictures'),
        'muziklerim': folder('~/Music'),
        'videolarim': folder('~/Movies'),
        'masaustu': folder('~/Desktop'),
        'geri_donusum_kutusu': folder('~/.Trash'),

        # Metin & Düzenleme (macOS'ta Cmd)
        'kopyala': lambda: keys('win+c'),
        'kes': lambda: keys('win+x'),
        'yapistir': lambda: keys('win+v'),
        'tumunu_sec': lambda: keys('win+a'),
        'geri_al': lambda: keys('win+z'),
        'yeniden_yap': lambda: keys('win+shift+z'),
        'bul': lambda: keys('win+f'),
        'kaydet': lambda: keys('win+s'),
        'yazdir': lambda: keys('win+p'),
    }
    for name in UNSUPPORTED[plat]:
        table[name] = _unsupported(name, plat)
    return table


# ------------------------------------------------------------------ Linux
_TERMINALS = [['x-terminal-emulator'], ['gnome-terminal'], ['konsole'], ['xfce4-terminal'],
              ['mate-terminal'], ['kitty'], ['alacritty'], ['xterm']]
_VOLUME = {
    'up': [['pactl', 'set-sink-volume', '@DEFAULT_SINK@', '+5%'],
           ['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', '5%+'],
           ['amixer', '-q', 'sset', 'Master', '5%+']],
    'down': [['pactl', 'set-sink-volume', '@DEFAULT_SINK@', '-5%'],
             ['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', '5%-'],
             ['amixer', '-q', 'sset', 'Master', '5%-']],
    'mute': [['pactl', 'set-sink-mute', '@DEFAULT_SINK@', 'toggle'],
             ['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', 'toggle'],
             ['amixer', '-q', 'sset', 'Master', 'toggle']],
    'max': [['pactl', 'set-sink-volume', '@DEFAULT_SINK@', '100%'],
            ['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', '1.0'],
            ['amixer', '-q', 'sset', 'Master', '100%']],
    'min': [['pactl', 'set-sink-volume', '@DEFAULT_SINK@', '0%'],
            ['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', '0'],
            ['amixer', '-q', 'sset', 'Master', '0%']],
}


def _linux_table(host) -> Dict[str, Callable[[], None]]:
    plat = platform_utils.LINUX
    launch, keys, which = host.launch, host.send_keys, host.which

    def one_of(*candidates):
        return lambda: launch(first_available(list(candidates), which, plat))

    def fixed(*argv):
        return lambda: launch(list(argv))

    def folder(xdg_key: str, fallback: str):
        return lambda: launch(['xdg-open', xdg_user_dir(xdg_key, fallback)])

    def player(playerctl_cmd: Optional[str], key_name: Optional[str], command: str):
        """MPRIS (playerctl) varsa onu, yoksa medya tuşu enjeksiyonunu kullanır (Wayland'de de çalışır)."""
        def action():
            if which('playerctl') and playerctl_cmd:
                launch(['playerctl', playerctl_cmd])
            elif key_name:
                host.send_media(key_name)
            else:
                raise CommandUnavailable('playerctl', 'not_installed', plat)
        return action

    def logout():
        session = os.environ.get('XDG_SESSION_ID')
        if session:
            launch(['loginctl', 'terminate-session', session])
        else:
            launch(['loginctl', 'terminate-user', getpass.getuser()])

    table: Dict[str, Callable[[], None]] = {
        # Sistem
        'bilgisayari_kapat': fixed('systemctl', 'poweroff'),
        'yeniden_basla': fixed('systemctl', 'reboot'),
        'uyku_modu': fixed('systemctl', 'suspend'),
        'hazirda_beklet': fixed('systemctl', 'hibernate'),
        'kilitle': fixed('loginctl', 'lock-session'),
        'oturumu_kapat': logout,
        'ekrani_kapat': fixed('xset', 'dpms', 'force', 'off'),
        'cop_kutusunu_bosalt': lambda: empty_linux_trash(),

        # Ekran & Araçlar
        'ekran_goruntusu': one_of(['gnome-screenshot', '-c'], ['spectacle', '-b', '-f', '-c'],
                                  ['flameshot', 'full', '-c'], ['xfce4-screenshooter', '-f', '-c']),
        'ekran_alintisi': one_of(['gnome-screenshot', '-a', '-c'], ['spectacle', '-b', '-r', '-c'],
                                 ['flameshot', 'gui'], ['xfce4-screenshooter', '-r', '-c']),
        'pano_gecmisi': one_of(['copyq', 'toggle']),
        'emoji_paneli': one_of(['gnome-characters'], ['emote'], ['kcharselect'], ['gucharmap']),
        'buyutec': one_of(['kmag']),
        'ekran_klavyesi': one_of(['onboard'], ['florence'], ['matchbox-keyboard'], ['kvkbd']),

        # Uygulamalar & Sistem Araçları
        'gorev_yoneticisi': one_of(['gnome-system-monitor'], ['plasma-systemmonitor'], ['ksysguard'],
                                   ['xfce4-taskmanager'], ['mate-system-monitor'], ['lxtask']),
        'calistir': lambda: keys('alt+f2'),
        'komut_istemi': one_of(*_TERMINALS),
        'powershell': one_of(['pwsh']),
        'dosya_gezgini': lambda: launch(['xdg-open', _expand('~')]),
        'not_defteri': one_of(['gnome-text-editor'], ['gedit'], ['kate'], ['mousepad'], ['xed'], ['pluma'], ['leafpad']),
        'hesap_makinesi': one_of(['gnome-calculator'], ['kcalc'], ['mate-calc'], ['galculator'], ['xcalc']),
        'paint': one_of(['pinta'], ['kolourpaint'], ['gimp']),
        'ayarlar': one_of(['gnome-control-center'], ['systemsettings'], ['xfce4-settings-manager'],
                          ['cinnamon-settings'], ['mate-control-center'], ['unity-control-center']),
        'ses_karistirici': one_of(['pavucontrol']),

        # Tarayıcılar
        'chrome': one_of(['google-chrome'], ['google-chrome-stable'], ['chromium'], ['chromium-browser']),
        'firefox': one_of(['firefox']),
        'edge': one_of(['microsoft-edge'], ['microsoft-edge-stable']),

        # Ses (PulseAudio/PipeWire/ALSA komut satırı araçları: Wayland'de de çalışır)
        'ses_ac': one_of(*_VOLUME['up']),
        'ses_kis': one_of(*_VOLUME['down']),
        'sesi_kapat': one_of(*_VOLUME['mute']),
        'ses_maksimum': one_of(*_VOLUME['max']),
        'ses_minimum': one_of(*_VOLUME['min']),

        # Medya
        'oynat_duraklat': player('play-pause', 'play_pause', 'oynat_duraklat'),
        'sonraki_sarki': player('next', 'next', 'sonraki_sarki'),
        'onceki_sarki': player('previous', 'previous', 'onceki_sarki'),
        'durdur': player('stop', None, 'durdur'),

        # Pencere & Masaüstü (GNOME/KDE varsayılan kısayolları)
        'masaustunu_goster': lambda: keys('win+d'),
        'tum_pencereleri_kucult': lambda: keys('win+d'),
        'gorev_gorunumu': lambda: keys('win'),
        'sonraki_masaustu': lambda: keys('ctrl+alt+right'),
        'onceki_masaustu': lambda: keys('ctrl+alt+left'),
        'sola_yasla': lambda: keys('win+left'),
        'saga_yasla': lambda: keys('win+right'),
        'pencereyi_buyut': lambda: keys('win+up'),
        'pencereyi_kapat': lambda: keys('alt+f4'),
        'pencere_degistir': lambda: keys('alt+tab'),

        # Tarayıcı Gezintisi
        'geri': lambda: keys('alt+left'),
        'ileri': lambda: keys('alt+right'),
        'sayfayi_yenile': lambda: keys('f5'),
        'yeni_sekme': lambda: keys('ctrl+t'),
        'sekmeyi_kapat': lambda: keys('ctrl+w'),
        'kapatilan_sekmeyi_ac': lambda: keys('ctrl+shift+t'),
        'gizli_pencere': lambda: keys('ctrl+shift+n'),

        # Hızlı Erişim
        'bu_bilgisayar': fixed('xdg-open', '/'),
        'indirilenler': folder('DOWNLOAD', 'Downloads'),
        'belgelerim': folder('DOCUMENTS', 'Documents'),
        'resimlerim': folder('PICTURES', 'Pictures'),
        'muziklerim': folder('MUSIC', 'Music'),
        'videolarim': folder('VIDEOS', 'Videos'),
        'masaustu': folder('DESKTOP', 'Desktop'),
        'geri_donusum_kutusu': fixed('xdg-open', 'trash:///'),

        # Metin & Düzenleme
        'kopyala': lambda: keys('ctrl+c'),
        'kes': lambda: keys('ctrl+x'),
        'yapistir': lambda: keys('ctrl+v'),
        'tumunu_sec': lambda: keys('ctrl+a'),
        'geri_al': lambda: keys('ctrl+z'),
        'yeniden_yap': lambda: keys('ctrl+y'),
        'bul': lambda: keys('ctrl+f'),
        'kaydet': lambda: keys('ctrl+s'),
        'yazdir': lambda: keys('ctrl+p'),
    }
    for name in UNSUPPORTED[plat]:
        table[name] = _unsupported(name, plat)
    return table


def build_command_table(host, platform: Optional[str] = None) -> Dict[str, Callable[[], None]]:
    """Platforma uygun komut tablosu (anahtarlar her platformda KNOWN_COMMANDS ile aynıdır)."""
    plat = platform_utils.current_platform(platform)
    if plat == platform_utils.WINDOWS:
        return _windows_table(host)
    if plat == platform_utils.MACOS:
        return _macos_table(host)
    return _linux_table(host)
