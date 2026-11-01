"""Uzaktan duyuru satiri: guncelleme istegi bicimi ve duyuru gosterimi."""

from __future__ import annotations

import io
import json
import types
import unittest
import urllib.parse
from unittest import mock

import _support  # noqa: F401

from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from src.utils import remote_notice as rn
from src.utils import updater


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeSettings:
    def __init__(self, **values):
        self.values = {"language": "tr", **values}

    def load_settings(self):
        return dict(self.values)

    def update(self, **kwargs):
        self.values.update(kwargs)


class UpdaterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _run(self, reply, **settings):
        fake = FakeSettings(**settings)
        with mock.patch.object(updater, "SettingsManager", lambda: fake):
            checker = updater.UpdateChecker()
        notices, seen, captured = [], {}, {}
        checker.notice_received.connect(notices.append)

        def fake_open(req, timeout=0, context=None):
            seen["url"] = req.full_url
            return _Resp(json.dumps(reply).encode())

        with mock.patch("urllib.request.urlopen", fake_open), \
                mock.patch.object(updater._UpdateCheckWorker, "start", lambda w: captured.setdefault("w", w)):
            checker.check_for_updates(False)
            captured["w"].run()
        self.app.processEvents()
        return seen.get("url", ""), notices

    def test_check_request_carries_only_app_name_and_version(self):
        url, _ = self._run({"updateAvailable": False})
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(query, {"appName": ["FlexiKey"], "currentVersion": [updater.UpdateChecker.CURRENT_VERSION]})

    def test_notice_arrives_without_an_update(self):
        _, notices = self._run({"updateAvailable": False, "notice": {"id": "n1", "text": "Bakım var"}})
        self.assertEqual([n.id for n in notices], ["n1"])
        _, notices = self._run({"updateAvailable": False})
        self.assertEqual(notices, [])


class WindowNoticeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_show_dismiss_and_remember(self):
        from src.gui.main_window import MainWindow
        from src.gui.notice_bar import NoticeBar

        host = QWidget()
        bar = NoticeBar()
        QVBoxLayout(host).addWidget(bar)
        host.show()
        fake = types.SimpleNamespace(settings_manager=FakeSettings(), notice_bar=bar)
        fake._on_notice_dismissed = lambda nid: MainWindow._on_notice_dismissed(fake, nid)
        bar.dismissed.connect(fake._on_notice_dismissed)
        self.assertFalse(bar.isVisible())
        MainWindow.show_notice(fake, rn.Notice("n1", "Duyuru", ""))
        self.assertTrue(bar.isVisible())
        bar.dismiss()
        self.assertEqual(fake.settings_manager.values["dismissed_notice"], "n1")
        MainWindow.show_notice(fake, rn.Notice("n1", "Duyuru", ""))
        self.assertFalse(bar.isVisible(), "a dismissed notice must not come back")
        MainWindow.show_notice(fake, rn.Notice("n2", "Yeni", ""))
        self.assertTrue(bar.isVisible())

    def test_defaults_include_the_notice_key(self):
        from src.utils.settings_manager import DEFAULT_SETTINGS

        self.assertEqual(DEFAULT_SETTINGS["dismissed_notice"], "")


if __name__ == "__main__":
    unittest.main()
