"""Boş liste yer tutucusu: başlık ve açıklama dar genişlikte satırlara bölünse bile TAM görünmeli.

Eski hata: düzende `setAlignment` kullanıldığından sarmalı etiketin heightForWidth'i yok sayılıyor, başlığın ikinci satırı
kırpılıyordu ("Henüz kısayol / eklenmedi" → ikinci satır yarım)."""

from __future__ import annotations

import os
import pathlib
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication, QLabel

from src.gui.list_widgets import EmptyListPlaceholder


class EmptyStateFitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_title_and_hint_get_the_height_their_wrapped_text_needs(self):
        messages = (
            "Henüz kısayol eklenmedi. «Kısayol Ekle» butonunu kullanın.",
            "No hotkeys yet. Use the «Add Hotkey» button to create your first one.",
        )
        for message in messages:
            for width in (240, 300, 360, 420, 560):
                placeholder = EmptyListPlaceholder(message, action_text="Ekle", action=lambda: None)
                placeholder.setMinimumWidth(0)
                placeholder.resize(width, 600)
                placeholder.show()
                self.app.processEvents()
                # Asıl hata kaynağı: düzen düzeyinde hiza (gerçek yazı tipleriyle ikinci satırı kırpar; offscreen'de görünmez).
                self.assertEqual(placeholder.layout().alignment().value, 0, "düzene hiza verilmemeli")
                for label in placeholder.findChildren(QLabel):
                    if label.wordWrap() and label.text():
                        need = label.heightForWidth(label.width())
                        self.assertGreaterEqual(label.height() + 1, need, (width, label.text()))
                placeholder.close()


if __name__ == "__main__":
    unittest.main()
