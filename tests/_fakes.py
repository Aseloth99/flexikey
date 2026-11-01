"""Testler icin sahte girdi arka ucu ve yardimcilar (gercek klavye/pano/surec YOK)."""

from __future__ import annotations

from unittest import mock

import _support  # noqa: F401  (proje kokunu sys.path'e ekler)

from src.core.input_backend import OK_STATUS, InputBackend


class FakeTypedListener:
    """create_key_listener donusu: on_key'i yakalar, start/stop/is_alive taklidi."""

    def __init__(self, on_key):
        self.on_key = on_key
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def is_alive(self):
        return self.started and not self.stopped


class FakeBackend(InputBackend):
    """Tum cagrilari mock.Mock olarak kaydeden arka uc. Varsayilan: Windows `keyboard` arka ucu gibi."""

    name = "fake"

    def __init__(self, *, native_abbreviations=True, needs_watchdog=True, paste_keys="ctrl+v",
                 available=True, status=OK_STATUS, typed_listener=True):
        self.native_abbreviations = native_abbreviations
        self.needs_watchdog = needs_watchdog
        self.paste_keys = paste_keys
        self.available = available
        self.status = status
        self.listeners = []
        self._typed_listener = typed_listener
        self.write = mock.Mock(name="write")
        self.send = mock.Mock(name="send")
        self.press_and_release = mock.Mock(name="press_and_release")
        self.send_media = mock.Mock(name="send_media")
        self.add_hotkey = mock.Mock(name="add_hotkey", side_effect=self._add_hotkey)
        self.remove_hotkey = mock.Mock(name="remove_hotkey")
        self.unhook_all = mock.Mock(name="unhook_all")
        self.hook = mock.Mock(name="hook", return_value=object())
        self.add_abbreviation = mock.Mock(name="add_abbreviation")
        self.remove_abbreviation = mock.Mock(name="remove_abbreviation")
        self.revive_if_dead = mock.Mock(name="revive_if_dead", return_value=False)
        self.prepare_hard_reinstall = mock.Mock(name="prepare_hard_reinstall")
        self.stop = mock.Mock(name="stop")

    def _add_hotkey(self, normalized, callback, suppress=False, timeout=0.1):
        return mock.Mock(name=f"remove[{normalized}]")      # cagrilabilir: "kanca yedekli" kisayol

    def create_key_listener(self, on_key):
        if not self._typed_listener:
            return None
        listener = FakeTypedListener(on_key)
        self.listeners.append(listener)
        return listener

    @property
    def listener(self):
        return self.listeners[-1] if self.listeners else None
