"""Testler icin sahte ortamla kurulmus HotkeyManager (gercek surec/klavye/pano/ctypes yok).

Varsayilan ortam Windows'tur (eski testlerin dayandigi); platform_name="darwin"/"linux" ile
macOS/Linux davranisi ayni duzenekle sinanir. Arka uc FakeBackend'dir: kb.write / kb.send ... mock'tur.
"""

from __future__ import annotations

import sys
import unittest
from unittest import mock

import _support
from _support import capture_logs
from _fakes import FakeBackend

from PyQt6.QtWidgets import QApplication

from src.core import hotkey_manager
from src.core import win_input

_APP = QApplication.instance() or QApplication([])


class ManagerTestCase(unittest.TestCase):
    """HotkeyManager'i sahte bir platformda (varsayilan Windows) kurar."""

    startfile_fails = False
    platform_name = "win32"        # "darwin" / "linux" icin alt siniflarda degistirilir
    backend_kwargs: dict = {}

    def make_backend(self):
        if self.platform_name == "win32":
            return FakeBackend(**self.backend_kwargs)
        return FakeBackend(native_abbreviations=False, needs_watchdog=False,
                           paste_keys="win+v" if self.platform_name == "darwin" else "ctrl+v",
                           **self.backend_kwargs)

    def setUp(self):
        patcher, self.log_lines = capture_logs()
        patcher.start()
        self.addCleanup(patcher.stop)

        self.popen = mock.Mock(name="Popen")
        self.startfile = mock.Mock(name="startfile")
        if self.startfile_fails:
            self.startfile.side_effect = OSError("dosya degil")
        self.fake_ctypes = mock.MagicMock(name="ctypes")
        self.kb = self.make_backend()

        for p in (
            mock.patch.object(sys, "platform", self.platform_name),
            mock.patch.object(hotkey_manager.subprocess, "Popen", self.popen),
            mock.patch.object(hotkey_manager.os, "startfile", self.startfile, create=True),
            mock.patch.object(win_input, "ctypes", self.fake_ctypes),
            mock.patch.object(hotkey_manager.time, "sleep"),
        ):
            p.start()
            self.addCleanup(p.stop)

        # Arka plan girdi isi (INPUT_INJECTOR) bitmeden yamalar KALDIRILMASIN: aksi halde gercek
        # ctypes/keyboard cagrilirdi. Temizleme LIFO oldugu icin bu, yamalardan once calisir.
        self.addCleanup(hotkey_manager.INPUT_INJECTOR.wait_idle)

        self.manager = hotkey_manager.HotkeyManager(backend=self.kb)
        self.events: list[tuple[str, str]] = []
        self.manager.action_executed.connect(lambda kind, text: self.events.append((kind, text)))
        self.confirm_calls: list[str] = []

    def confirm_with(self, answer):
        def confirm(command):
            self.confirm_calls.append(command)
            return answer
        self.manager.confirm_destructive = confirm

    def run_command(self, command):
        self.manager.execute_action("command", command, "Ctrl+Alt+K", False)

    def pump(self):
        """Arka plan is parcacigindan gelen (kuyruklu) sinyalleri ana is parcacigina teslim et."""
        _APP.processEvents()

    def popen_commands(self):
        return [call.args[0] for call in self.popen.call_args_list]
