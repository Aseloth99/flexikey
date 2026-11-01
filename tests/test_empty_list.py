"""Bos liste mesaji kesilmemeli: yer tutucu, listenin tum genisligini kullanmali."""

from __future__ import annotations

import os
import pathlib
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication, QLabel

from PyQt6.QtCore import Qt

from src.gui.list_widgets import CardListWidget, HotkeyCard


class EmptyListTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_message_uses_the_full_width(self):
        lst = CardListWidget()
        lst.resize(780, 320)
        lst.show()
        msg = "Henüz kısayol eklenmedi. «Kısayol Ekle» butonunu kullanın."
        lst.show_empty(msg)
        self.app.processEvents()
        placeholder = lst._empty_widget
        label = placeholder.findChild(QLabel)
        # the placeholder spans the list (a left-aligned grid used to squeeze it to its narrowest width)
        self.assertGreater(placeholder.width(), 600)
        # and the label is tall enough for every wrapped line
        self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()))
        lst.close()

    def test_cards_return_to_the_left_aligned_grid_after_an_empty_state(self):
        lst = CardListWidget()
        lst.resize(780, 320)
        lst.show()
        lst.show_empty("bos")
        card = HotkeyCard()
        card.set_data("Ctrl+M", "Web", "example.com", True)
        lst.set_cards([card])
        self.app.processEvents()
        self.assertTrue(lst._grid.alignment() & Qt.AlignmentFlag.AlignLeft)
        self.assertEqual(lst.count(), 1)
        lst.close()


if __name__ == "__main__":
    unittest.main()
