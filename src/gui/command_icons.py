"""Sistem komutu, eylem türü ve komut kategorisi simgeleri: emoji yerine tek tarzda çizilen çizgi simgeler.

Emoji Windows sürümüne göre değişiyordu: bir kısmı renkli, bir kısmı (🗕 🗔 🗖 ⬅ ✖) tek renk glif olarak çıkıyor,
🪟 gibi yenileri Windows 10'da hiç bulunmadığı için boş kutu görünüyordu. Buradaki simgeler 24'lük ızgarada çizilir,
verilen renge boyanır (tema ve vurgu rengini izler) ve her ölçekte keskin kalır.

Komut adı -> simge eşlemesi yalnızca buradadır (`COMMAND_GLYPHS`); kartlar ve komut seçme ızgarası aynı tabloyu kullanır.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import QLabel

GRID = 24.0
STROKE = 1.9

# Yerleşik komut -> simge. Anahtarlar `action_policy.KNOWN_COMMANDS` ile aynıdır (testle doğrulanır).
COMMAND_GLYPHS: dict[str, str] = {
    # Sistem Gücü
    "bilgisayari_kapat": "power", "yeniden_basla": "restart", "uyku_modu": "moon", "hazirda_beklet": "hibernate",
    "kilitle": "lock", "oturumu_kapat": "logout", "ekrani_kapat": "screen_off", "cop_kutusunu_bosalt": "trash_empty",
    # Ekran & Araçlar
    "ekran_goruntusu": "camera", "ekran_alintisi": "snip", "pano_gecmisi": "clipboard_history",
    "emoji_paneli": "smile", "buyutec": "zoom_in", "ekran_klavyesi": "keyboard",
    # Uygulamalar & Araçlar
    "gorev_yoneticisi": "activity", "calistir": "run", "komut_istemi": "terminal", "powershell": "powershell",
    "dosya_gezgini": "folder", "not_defteri": "notepad", "hesap_makinesi": "calculator", "paint": "palette",
    "ayarlar": "gear", "denetim_masasi": "sliders", "aygit_yoneticisi": "chip", "ses_karistirici": "mixer",
    "hizmetler": "services",
    # Tarayıcılar
    "chrome": "chrome", "firefox": "firefox", "edge": "edge",
    # Ses
    "ses_ac": "volume_up", "ses_kis": "volume_down", "sesi_kapat": "volume_mute", "ses_maksimum": "volume_max",
    "ses_minimum": "volume_min",
    # Medya
    "oynat_duraklat": "play_pause", "sonraki_sarki": "next_track", "onceki_sarki": "prev_track", "durdur": "stop",
    # Pencere & Masaüstü
    "masaustunu_goster": "show_desktop", "tum_pencereleri_kucult": "window_minimize", "gorev_gorunumu": "task_view",
    "yeni_sanal_masaustu": "desktop_add", "sonraki_masaustu": "desktop_next", "onceki_masaustu": "desktop_prev",
    "sanal_masaustu_kapat": "desktop_close", "sola_yasla": "snap_left", "saga_yasla": "snap_right",
    "pencereyi_buyut": "window_maximize", "pencereyi_kapat": "window_close", "pencere_degistir": "window_switch",
    # Tarayıcı Gezintisi
    "geri": "arrow_left", "ileri": "arrow_right", "sayfayi_yenile": "refresh", "yeni_sekme": "tab_add",
    "sekmeyi_kapat": "tab_close", "kapatilan_sekmeyi_ac": "tab_reopen", "gizli_pencere": "incognito",
    # Hızlı Erişim
    "bu_bilgisayar": "computer", "indirilenler": "download", "belgelerim": "document", "resimlerim": "picture",
    "muziklerim": "music", "videolarim": "film", "masaustu": "desktop", "geri_donusum_kutusu": "trash",
    # Metin & Düzenleme
    "kopyala": "copy", "kes": "scissors", "yapistir": "paste", "tumunu_sec": "select_all", "geri_al": "undo",
    "yeniden_yap": "redo", "bul": "search", "kaydet": "save", "yazdir": "printer",
}

# Eylem türü (kart çipi, "İşlem Türü" listesi) -> simge
ACTION_GLYPHS: dict[str, str] = {
    "text": "type", "command": "gear", "open_url": "globe", "open_file": "folder", "run_program": "app",
    "shortcut": "keyboard", "secret": "lock", "expansion": "type", "rich": "notepad",
}

# Komut kategorisi başlığı (yerelleştirme anahtarı) -> simge
GROUP_GLYPHS: dict[str, str] = {
    "cmd_grp_power": "power", "cmd_grp_screen": "camera", "cmd_grp_apps": "apps", "cmd_grp_media": "music",
    "cmd_grp_volume": "volume_max", "cmd_grp_windows": "window", "cmd_grp_browsers": "globe",
    "cmd_grp_browser_nav": "compass", "cmd_grp_quick_access": "folder", "cmd_grp_text": "pencil",
}


def command_glyph(command: str) -> str:
    """Komutun simgesi; tabloda olmayan (elle yazılmış) komut için dişli."""
    return COMMAND_GLYPHS.get(command, "gear")


class _G:
    """24'lük ızgarada çizim yardımcıları (ressam önceden ölçeklenmiştir)."""

    def __init__(self, painter: QPainter, color: QColor):
        self.p = painter
        self.color = color
        pen = QPen(color, STROKE)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.pen = pen
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _brush(self, fill: bool):
        self.p.setBrush(self.color if fill else Qt.BrushStyle.NoBrush)

    def line(self, x1, y1, x2, y2):
        self.p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def poly(self, *pts, close=False, fill=False):
        path = QPainterPath(QPointF(*pts[0]))
        for pt in pts[1:]:
            path.lineTo(QPointF(*pt))
        if close or fill:
            path.closeSubpath()
        self.path(path, fill)

    def path(self, path: QPainterPath, fill=False):
        self._brush(fill)
        self.p.drawPath(path)
        self._brush(False)

    def rect(self, x, y, w, h, r=0.0, fill=False):
        self._brush(fill)
        self.p.drawRoundedRect(QRectF(x, y, w, h), r, r)
        self._brush(False)

    def circle(self, cx, cy, r, fill=False):
        self._brush(fill)
        self.p.drawEllipse(QPointF(cx, cy), r, r)
        self._brush(False)

    def ellipse(self, cx, cy, rx, ry):
        self.p.drawEllipse(QPointF(cx, cy), rx, ry)

    def dot(self, cx, cy, r=1.15):
        self.p.setPen(Qt.PenStyle.NoPen)
        self.p.setBrush(self.color)
        self.p.drawEllipse(QPointF(cx, cy), r, r)
        self.p.setPen(self.pen)
        self.p.setBrush(Qt.BrushStyle.NoBrush)

    def arc(self, cx, cy, r, start, span):
        """Yay: açılar derece, saat 3'ten saat yönünün tersine (Qt gibi)."""
        self.p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), int(round(start * 16)), int(round(span * 16)))

    def head(self, x, y, dx, dy, size=3.6):
        """Ucu (x, y)'de olan, (dx, dy) yönüne bakan ok başı."""
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        for sign in (1, -1):
            ang = math.radians(140 * sign)
            bx = ux * math.cos(ang) - uy * math.sin(ang)
            by = ux * math.sin(ang) + uy * math.cos(ang)
            self.line(x, y, x + bx * size, y + by * size)

    def arc_arrow(self, cx, cy, r, start, span, size=3.6):
        """Yay + bitiş ucunda hareket yönüne bakan dolu üçgen uç (çizgi uç yayın üstüne binip kanca gibi görünüyordu)."""
        self.arc(cx, cy, r, start, span)
        end = math.radians(start + span)
        x, y = cx + r * math.cos(end), cy - r * math.sin(end)
        sign = 1 if span > 0 else -1
        fx, fy = -math.sin(end) * sign, -math.cos(end) * sign  # hareket yönü
        nx, ny = -fy, fx
        tip = (x + fx * size * 0.75, y + fy * size * 0.75)
        back = (x - fx * size * 0.45, y - fy * size * 0.45)
        half = size * 0.62
        self.poly(tip, (back[0] + nx * half, back[1] + ny * half), (back[0] - nx * half, back[1] - ny * half),
                  fill=True)

    def arrow(self, x1, y1, x2, y2, size=3.6):
        self.line(x1, y1, x2, y2)
        self.head(x2, y2, x2 - x1, y2 - y1, size)


_GLYPHS: dict = {}


def _glyph(name: str):
    def register(func):
        _GLYPHS[name] = func
        return func
    return register


# ------------------------------------------------------------------ ortak parçalar
def _monitor(g: _G):
    g.rect(3, 4, 18, 12.5, 2.2)
    g.line(12, 16.5, 12, 19.6)
    g.line(8, 19.8, 16, 19.8)


def _frame(g: _G):
    g.rect(3.5, 3.5, 17, 17, 2.8)


def _browser(g: _G):
    g.rect(3, 4.5, 18, 15, 2.4)
    g.line(3.4, 9, 20.6, 9)


def _speaker(g: _G):
    g.poly((3.5, 9.5), (7, 9.5), (11.5, 5.5), (11.5, 18.5), (7, 14.5), (3.5, 14.5), close=True)


def _clipboard(g: _G):
    g.rect(5, 5, 14, 15.5, 2.2)
    g.rect(9.2, 3.2, 5.6, 3.4, 1.2, fill=True)


def _bin(g: _G):
    g.line(4, 6.5, 20, 6.5)
    g.poly((9, 6.5), (9, 4), (15, 4), (15, 6.5))
    g.poly((6, 6.5), (7, 20), (17, 20), (18, 6.5))


def _crescent(cx, cy, r, bite_dx, bite_dy, bite_r) -> QPainterPath:
    moon = QPainterPath()
    moon.addEllipse(QPointF(cx, cy), r, r)
    bite = QPainterPath()
    bite.addEllipse(QPointF(cx + bite_dx, cy + bite_dy), bite_r, bite_r)
    return moon.subtracted(bite)


# ------------------------------------------------------------------ sistem gücü
@_glyph("power")
def _power(g):
    g.arc(12, 13, 7.5, 60, -300)
    g.line(12, 3.5, 12, 12)


@_glyph("restart")
def _restart(g):
    g.arc_arrow(12, 12.5, 7.5, 0, -280, 4.4)


@_glyph("moon")
def _moon(g):
    g.path(_crescent(11, 13, 8, 5.2, -5.2, 7.2))


@_glyph("hibernate")
def _hibernate(g):
    g.path(_crescent(9.5, 14.5, 6.5, 4.4, -4.4, 5.8))
    g.poly((14.5, 4), (20.5, 4), (14.5, 10.5), (20.5, 10.5))


@_glyph("lock")
def _lock(g):
    g.rect(5, 10.5, 14, 10, 2.4)
    path = QPainterPath(QPointF(8, 10.5))
    path.lineTo(8, 7.5)
    path.arcTo(QRectF(8, 3.5, 8, 8), 180, -180)
    path.lineTo(16, 10.5)
    g.path(path)
    g.dot(12, 15.5, 1.5)


@_glyph("logout")
def _logout(g):
    g.poly((10, 4), (5, 4), (5, 20), (10, 20))
    g.arrow(10, 12, 20, 12, 4.4)


@_glyph("screen_off")
def _screen_off(g):
    _monitor(g)
    g.line(8.5, 7.3, 15.5, 13.2)


@_glyph("trash")
def _trash(g):
    _bin(g)
    g.line(10, 10.5, 10, 16)
    g.line(14, 10.5, 14, 16)


@_glyph("trash_empty")
def _trash_empty(g):
    _bin(g)
    g.line(9.8, 10.8, 14.2, 15.6)
    g.line(14.2, 10.8, 9.8, 15.6)


# ------------------------------------------------------------------ ekran & araçlar
@_glyph("camera")
def _camera(g):
    g.rect(3, 7, 18, 12.5, 2.6)
    g.poly((8.5, 7), (10, 4.5), (14, 4.5), (15.5, 7))
    g.circle(12, 13.2, 3.4)


@_glyph("snip")
def _snip(g):
    g.poly((4, 9), (4, 5), (8, 5))
    g.poly((16, 5), (20, 5), (20, 9))
    g.poly((20, 15), (20, 19), (16, 19))
    g.poly((8, 19), (4, 19), (4, 15))
    g.line(12, 9.2, 12, 14.8)
    g.line(9.2, 12, 14.8, 12)


@_glyph("clipboard_history")
def _clipboard_history(g):
    _clipboard(g)
    g.circle(12, 13.5, 3.7)
    g.poly((12, 11.6), (12, 13.6), (13.5, 14.5))


@_glyph("paste")
def _paste(g):
    _clipboard(g)
    g.arrow(12, 9.5, 12, 16.5, 3.4)


@_glyph("smile")
def _smile(g):
    g.circle(12, 12, 8.5)
    g.dot(9, 10)
    g.dot(15, 10)
    g.arc(12, 12, 4.6, 205, 130)


@_glyph("search")
def _search(g):
    g.circle(10.5, 10.5, 6.5)
    g.line(15.3, 15.3, 20.5, 20.5)


@_glyph("zoom_in")
def _zoom_in(g):
    _search(g)
    g.line(10.5, 7.8, 10.5, 13.2)
    g.line(7.8, 10.5, 13.2, 10.5)


@_glyph("keyboard")
def _keyboard(g):
    g.rect(2.5, 6, 19, 12, 2.6)
    for x in (6.5, 10.2, 13.8, 17.5):
        g.dot(x, 10.2, 0.95)
    g.line(8, 14.2, 16, 14.2)


# ------------------------------------------------------------------ uygulamalar & araçlar
@_glyph("activity")
def _activity(g):
    g.rect(3, 4, 18, 16, 2.6)
    g.poly((6, 13), (9, 13), (10.7, 8.8), (13.2, 16), (14.8, 12), (18, 12))


@_glyph("run")
def _run(g):
    _frame(g)
    g.poly((10, 8.3), (16, 12), (10, 15.7), close=True)


@_glyph("terminal")
def _terminal(g):
    g.rect(2.5, 4.5, 19, 15, 2.6)
    g.poly((6.5, 9.3), (9.6, 12), (6.5, 14.7))
    g.line(11.8, 14.7, 16, 14.7)


@_glyph("powershell")
def _powershell(g):
    g.poly((6.8, 4.5), (21.5, 4.5), (17.2, 19.5), (2.5, 19.5), close=True)
    g.poly((8.8, 8.8), (12.3, 12), (7.6, 15.2))
    g.line(12.4, 15.4, 15.6, 15.4)


@_glyph("folder")
def _folder(g):
    g.poly((3, 6), (9.5, 6), (12, 8.8), (21, 8.8), (21, 18.8), (3, 18.8), close=True)


@_glyph("notepad")
def _notepad(g):
    g.rect(5, 3.5, 14, 17, 2.2)
    g.line(8.5, 8.5, 15.5, 8.5)
    g.line(8.5, 12, 15.5, 12)
    g.line(8.5, 15.5, 13, 15.5)


@_glyph("calculator")
def _calculator(g):
    g.rect(5, 3, 14, 18, 2.6)
    g.rect(8.2, 6, 7.6, 3.2, 0.8)
    for y in (13.2, 16.8):
        for x in (8.8, 12, 15.2):
            g.dot(x, y, 0.95)


@_glyph("palette")
def _palette(g):
    g.circle(12, 12, 8.5)
    g.dot(8.4, 10)
    g.dot(12, 7.6)
    g.dot(15.8, 10)
    g.circle(14.6, 15.4, 1.9)


@_glyph("gear")
def _gear(g):
    g.circle(12, 12, 3)
    g.circle(12, 12, 6.4)
    for ang in range(0, 360, 45):
        rad = math.radians(ang)
        g.line(12 + 6.4 * math.cos(rad), 12 + 6.4 * math.sin(rad), 12 + 9 * math.cos(rad), 12 + 9 * math.sin(rad))


@_glyph("sliders")
def _sliders(g):
    for y, knob in ((6.5, 15), (12, 8.5), (17.5, 13)):
        g.line(3.5, y, knob - 2.6, y)
        g.line(knob + 2.6, y, 20.5, y)
        g.circle(knob, y, 2.2)


@_glyph("chip")
def _chip(g):
    g.rect(6.5, 6.5, 11, 11, 2)
    g.rect(10, 10, 4, 4, 0.8)
    for v in (9.5, 14.5):
        g.line(v, 3.5, v, 6.5)
        g.line(v, 17.5, v, 20.5)
        g.line(3.5, v, 6.5, v)
        g.line(17.5, v, 20.5, v)


@_glyph("mixer")
def _mixer(g):
    for x, knob in ((6, 15), (12, 8.5), (18, 13)):
        g.line(x, 3.5, x, knob - 2.4)
        g.line(x, knob + 2.4, x, 20.5)
        g.rect(x - 2.3, knob - 1.7, 4.6, 3.4, 1.1)


@_glyph("services")
def _services(g):
    for y in (4.5, 13):
        g.rect(3.5, y, 17, 6.5, 2)
        g.dot(7.2, y + 3.25, 1.0)
        g.line(11, y + 3.25, 17, y + 3.25)


# ------------------------------------------------------------------ tarayıcılar
@_glyph("globe")
def _globe(g):
    g.circle(12, 12, 8.5)
    g.ellipse(12, 12, 3.7, 8.5)
    g.line(3.5, 12, 20.5, 12)


@_glyph("chrome")
def _chrome(g):
    g.circle(12, 12, 8.5)
    g.circle(12, 12, 3.4)
    reach = math.sqrt(8.5 ** 2 - 3.4 ** 2)
    for turn in (0, 120, 240):
        rad = math.radians(turn)
        cos, sin = math.cos(rad), math.sin(rad)
        x1, y1 = 0.0, -3.4
        x2, y2 = reach, -3.4
        g.line(12 + x1 * cos - y1 * sin, 12 + x1 * sin + y1 * cos, 12 + x2 * cos - y2 * sin, 12 + x2 * sin + y2 * cos)


@_glyph("firefox")
def _firefox(g):
    path = QPainterPath(QPointF(12.2, 3.2))
    path.cubicTo(12.6, 5.6, 16.4, 6.2, 18.6, 9.2)
    path.cubicTo(21.6, 13.4, 19.2, 20.6, 12, 20.6)
    path.cubicTo(6.6, 20.6, 3.4, 16.6, 3.4, 12.6)
    path.cubicTo(3.4, 9.8, 4.6, 7.6, 6.2, 6.2)
    path.cubicTo(6.2, 7.8, 7, 8.8, 8.2, 9)
    path.cubicTo(8.4, 6.4, 10, 4.4, 12.2, 3.2)
    g.path(path)
    g.circle(12.4, 14, 3.3)


@_glyph("edge")
def _edge(g):
    g.arc(12, 12, 8.3, 0, 300)
    g.line(4.4, 12, 20.3, 12)


# ------------------------------------------------------------------ ses
@_glyph("volume_up")
def _volume_up(g):
    _speaker(g)
    g.line(17.5, 9, 17.5, 15)
    g.line(14.5, 12, 20.5, 12)


@_glyph("volume_down")
def _volume_down(g):
    _speaker(g)
    g.line(14.5, 12, 20.5, 12)


@_glyph("volume_mute")
def _volume_mute(g):
    _speaker(g)
    g.line(15, 9.5, 20, 14.5)
    g.line(20, 9.5, 15, 14.5)


@_glyph("volume_max")
def _volume_max(g):
    _speaker(g)
    g.arc(12, 12, 3.9, -48, 96)
    g.arc(12, 12, 7.7, -48, 96)


@_glyph("volume_min")
def _volume_min(g):
    _speaker(g)
    g.arc(12, 12, 3.9, -48, 96)


# ------------------------------------------------------------------ medya
@_glyph("play_pause")
def _play_pause(g):
    g.poly((3.5, 6), (3.5, 18), (11.5, 12), fill=True)
    g.line(15.2, 6.3, 15.2, 17.7)
    g.line(19.8, 6.3, 19.8, 17.7)


@_glyph("next_track")
def _next_track(g):
    g.poly((5, 6), (5, 18), (14.5, 12), fill=True)
    g.line(18.5, 6.3, 18.5, 17.7)


@_glyph("prev_track")
def _prev_track(g):
    g.poly((19, 6), (19, 18), (9.5, 12), fill=True)
    g.line(5.5, 6.3, 5.5, 17.7)


@_glyph("stop")
def _stop(g):
    g.rect(6, 6, 12, 12, 2, fill=True)


# ------------------------------------------------------------------ pencere & masaüstü
@_glyph("computer")
def _computer(g):
    _monitor(g)


@_glyph("desktop")
def _desktop(g):
    _monitor(g)
    g.dot(6.8, 7.6, 0.95)
    g.dot(6.8, 10.6, 0.95)
    g.line(5.6, 13.6, 18.4, 13.6)


@_glyph("show_desktop")
def _show_desktop(g):
    _monitor(g)
    g.arrow(12, 6.6, 12, 13.2, 3.0)


@_glyph("desktop_add")
def _desktop_add(g):
    _monitor(g)
    g.line(12, 7.2, 12, 13.3)
    g.line(9, 10.25, 15, 10.25)


@_glyph("desktop_close")
def _desktop_close(g):
    _monitor(g)
    g.line(9.7, 7.9, 14.3, 12.6)
    g.line(14.3, 7.9, 9.7, 12.6)


@_glyph("desktop_next")
def _desktop_next(g):
    _monitor(g)
    g.arrow(8, 10.25, 16, 10.25, 3.2)


@_glyph("desktop_prev")
def _desktop_prev(g):
    _monitor(g)
    g.arrow(16, 10.25, 8, 10.25, 3.2)


@_glyph("window")
def _window(g):
    _browser(g)


@_glyph("window_minimize")
def _window_minimize(g):
    _frame(g)
    g.line(8.2, 15.6, 15.8, 15.6)


@_glyph("window_maximize")
def _window_maximize(g):
    _frame(g)
    g.poly((13, 7.4), (16.6, 7.4), (16.6, 11))
    g.line(16.6, 7.4, 13.2, 10.8)
    g.poly((11, 16.6), (7.4, 16.6), (7.4, 13))
    g.line(7.4, 16.6, 10.8, 13.2)


@_glyph("window_close")
def _window_close(g):
    _frame(g)
    g.line(8.8, 8.8, 15.2, 15.2)
    g.line(15.2, 8.8, 8.8, 15.2)


@_glyph("window_switch")
def _window_switch(g):
    g.rect(3, 9, 12.5, 10.5, 2.2)
    g.poly((8.5, 9), (8.5, 4.5), (21, 4.5), (21, 15), (15.5, 15))


@_glyph("task_view")
def _task_view(g):
    g.rect(7, 5.5, 10, 11, 2)
    g.poly((4.2, 7.6), (3, 7.6), (3, 14.4), (4.2, 14.4))
    g.poly((19.8, 7.6), (21, 7.6), (21, 14.4), (19.8, 14.4))
    g.line(9, 20, 15, 20)


@_glyph("snap_left")
def _snap_left(g):
    g.rect(3, 4.5, 18, 15, 2.4)
    g.rect(5.6, 7.1, 5.2, 9.8, 0.9, fill=True)


@_glyph("snap_right")
def _snap_right(g):
    g.rect(3, 4.5, 18, 15, 2.4)
    g.rect(13.2, 7.1, 5.2, 9.8, 0.9, fill=True)


# ------------------------------------------------------------------ tarayıcı gezintisi
@_glyph("arrow_left")
def _arrow_left(g):
    g.arrow(19.5, 12, 4.5, 12, 6.2)


@_glyph("arrow_right")
def _arrow_right(g):
    g.arrow(4.5, 12, 19.5, 12, 6.2)


@_glyph("refresh")
def _refresh(g):
    g.arc_arrow(12, 12, 7.5, 195, -125, 4.2)
    g.arc_arrow(12, 12, 7.5, 15, -125, 4.2)


@_glyph("tab_add")
def _tab_add(g):
    _browser(g)
    g.line(12, 11.6, 12, 17)
    g.line(9.3, 14.3, 14.7, 14.3)


@_glyph("tab_close")
def _tab_close(g):
    _browser(g)
    g.line(9.9, 12.2, 14.1, 16.4)
    g.line(14.1, 12.2, 9.9, 16.4)


@_glyph("tab_reopen")
def _tab_reopen(g):
    _browser(g)
    path = QPainterPath(QPointF(8, 12.3))
    path.lineTo(13.4, 12.3)
    path.arcTo(QRectF(10.9, 12.3, 5, 5), 90, -180)
    path.lineTo(10.6, 17.3)
    g.path(path)
    g.head(8, 12.3, -1, 0, 2.8)


@_glyph("incognito")
def _incognito(g):
    g.line(3.5, 10.5, 20.5, 10.5)
    g.poly((7, 10.5), (8.6, 4.5), (15.4, 4.5), (17, 10.5))
    g.circle(8, 16.2, 2.8)
    g.circle(16, 16.2, 2.8)
    g.line(10.8, 16.2, 13.2, 16.2)


@_glyph("compass")
def _compass(g):
    g.circle(12, 12, 8.5)
    g.poly((15.6, 8.4), (13.4, 13.4), (8.4, 15.6), (10.6, 10.6), close=True)


# ------------------------------------------------------------------ hızlı erişim
@_glyph("download")
def _download(g):
    g.arrow(12, 3.5, 12, 15, 5.2)
    g.poly((4, 16.5), (4, 20), (20, 20), (20, 16.5))


@_glyph("document")
def _document(g):
    g.poly((6, 3.5), (13.5, 3.5), (18.5, 8.5), (18.5, 20.5), (6, 20.5), close=True)
    g.poly((13.5, 3.5), (13.5, 8.5), (18.5, 8.5))
    g.line(9, 13, 15.5, 13)
    g.line(9, 16.5, 15.5, 16.5)


@_glyph("picture")
def _picture(g):
    g.rect(3, 4.5, 18, 15, 2.4)
    g.circle(8.3, 9.4, 1.6)
    g.poly((4, 17.6), (9.2, 12.8), (12.4, 15.6), (15.4, 12.8), (20, 17.2))


@_glyph("music")
def _music(g):
    g.poly((9.6, 17), (9.6, 5.6), (18.6, 4), (18.6, 15.4))
    g.circle(7, 17.2, 2.6, fill=True)
    g.circle(16, 15.6, 2.6, fill=True)


@_glyph("film")
def _film(g):
    g.rect(3, 5, 18, 14, 2.4)
    g.line(7.2, 5.2, 7.2, 18.8)
    g.line(16.8, 5.2, 16.8, 18.8)
    for y in (9.7, 14.3):
        g.line(3.2, y, 7.2, y)
        g.line(16.8, y, 20.8, y)


# ------------------------------------------------------------------ metin & düzenleme
@_glyph("copy")
def _copy(g):
    g.rect(4.5, 8, 11, 12.5, 2.2)
    g.poly((9, 8), (9, 3.8), (19.5, 3.8), (19.5, 16), (15.5, 16))


@_glyph("scissors")
def _scissors(g):
    g.circle(6.3, 6.8, 2.7)
    g.circle(6.3, 17.2, 2.7)
    g.line(8.5, 8.4, 20.5, 18)
    g.line(8.5, 15.6, 20.5, 6)


@_glyph("select_all")
def _select_all(g):
    dashed = QPen(g.pen)
    dashed.setDashPattern([1.6, 1.9])
    g.p.setPen(dashed)
    g.rect(3.5, 3.5, 17, 17, 2.4)
    g.p.setPen(g.pen)
    g.rect(8.2, 8.2, 7.6, 7.6, 1.4, fill=True)


@_glyph("undo")
def _undo(g):
    path = QPainterPath(QPointF(4.5, 9))
    path.lineTo(14.5, 9)
    path.arcTo(QRectF(9.5, 9, 10, 10), 90, -180)
    path.lineTo(10, 19)
    g.path(path)
    g.head(4.5, 9, -1, 0, 4.4)


@_glyph("redo")
def _redo(g):
    path = QPainterPath(QPointF(19.5, 9))
    path.lineTo(9.5, 9)
    path.arcTo(QRectF(4.5, 9, 10, 10), 90, 180)
    path.lineTo(14, 19)
    g.path(path)
    g.head(19.5, 9, 1, 0, 4.4)


@_glyph("save")
def _save(g):
    g.poly((4, 4), (16.2, 4), (20, 7.8), (20, 20), (4, 20), close=True)
    g.poly((8, 4), (8, 8.8), (14.8, 8.8), (14.8, 4))
    g.poly((7.6, 20), (7.6, 13.8), (16.4, 13.8), (16.4, 20))


@_glyph("printer")
def _printer(g):
    g.poly((7, 8.5), (7, 3.5), (17, 3.5), (17, 8.5))
    g.poly((7, 17), (3.5, 17), (3.5, 8.5), (20.5, 8.5), (20.5, 17), (17, 17))
    g.rect(7, 13.5, 10, 7, 0.8)


# ------------------------------------------------------------------ eylem türleri & kategoriler
@_glyph("type")
def _type(g):
    g.poly((5.5, 8), (5.5, 5), (18.5, 5), (18.5, 8))
    g.line(12, 5, 12, 19)
    g.line(9.2, 19, 14.8, 19)


@_glyph("app")
def _app(g):
    _browser(g)
    g.poly((10.4, 11.4), (14.6, 14.2), (10.4, 17), fill=True)


@_glyph("apps")
def _apps(g):
    for x in (4, 13.5):
        for y in (4, 13.5):
            g.rect(x, y, 6.5, 6.5, 1.6)


@_glyph("pencil")
def _pencil(g):
    g.poly((4.5, 19.5), (5.6, 14.6), (15.6, 4.6), (19.4, 8.4), (9.4, 18.4), close=True)
    g.line(13.4, 6.8, 17.2, 10.6)


GLYPH_NAMES = tuple(sorted(_GLYPHS))


def draw_glyph(painter: QPainter, name: str, rect: QRectF, color) -> None:
    """`name` simgesini `rect` içine (kare kabul edilir) `color` renginde çizer."""
    draw = _GLYPHS.get(name)
    if draw is None:
        raise ValueError(f"unknown glyph: {name}")
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    side = min(rect.width(), rect.height())
    painter.translate(rect.x() + (rect.width() - side) / 2, rect.y() + (rect.height() - side) / 2)
    painter.scale(side / GRID, side / GRID)
    draw(_G(painter, QColor(color)))
    painter.restore()


_PIXMAPS: dict[tuple[str, str, int], QPixmap] = {}


def glyph_pixmap(name: str, color, size: int = 16) -> QPixmap:
    key = (name, QColor(color).name(QColor.NameFormat.HexArgb), size)
    cached = _PIXMAPS.get(key)
    if cached is not None:
        return cached
    if name not in _GLYPHS:  # ressam açılmadan: yarım kalan QPainter Qt'yi düşürür
        raise ValueError(f"unknown glyph: {name}")
    scale = 3  # %150 ekranda da keskin
    pix = QPixmap(size * scale, size * scale)
    pix.setDevicePixelRatio(scale)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    draw_glyph(painter, name, QRectF(0, 0, size, size), color)
    painter.end()
    _PIXMAPS[key] = pix
    return pix


def glyph_icon(name: str, color, size: int = 16, on_color=None) -> QIcon:
    """Düğme / liste simgesi; `on_color` verilirse işaretli (seçili) durumda o renkte görünür."""
    icon = QIcon()
    icon.addPixmap(glyph_pixmap(name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    if on_color is not None:
        icon.addPixmap(glyph_pixmap(name, on_color, size), QIcon.Mode.Normal, QIcon.State.On)
    return icon


class GlyphLabel(QLabel):
    """Simgeyi kendi yazı renginde çizen etiket: rengi stil sayfası verir, tema değişince kendiliğinden boyanır."""

    def __init__(self, name: str = "", size: int = 16, parent=None):
        super().__init__(parent)
        self._name = name
        self._size = size
        self.setFixedSize(QSize(size, size))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def glyph(self) -> str:
        return self._name

    def set_glyph(self, name: str):
        if name and name not in _GLYPHS:
            raise ValueError(f"unknown glyph: {name}")
        self._name = name or ""
        self.setVisible(bool(self._name))
        self.update()

    def paintEvent(self, _event):
        if not self._name:
            return
        painter = QPainter(self)
        draw_glyph(painter, self._name, QRectF(0, 0, self._size, self._size),
                   self.palette().color(QPalette.ColorRole.WindowText))
        painter.end()
