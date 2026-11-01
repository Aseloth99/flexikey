"""Kısayol kartları: pasif kayıt da tıklanabilir kalmalı (eskiden `enabled` özelliği kartı gerçekten kapatıyordu);
durum hapı yazıyla gösterilir; boş listede eylem düğmesi çalışır."""

from __future__ import annotations

import os
import pathlib
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from src.gui.list_widgets import CardListWidget, EmptyListPlaceholder, ExpansionCard, HotkeyCard


class CardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_disabled_hotkey_card_stays_enabled_as_a_widget(self):
        card = HotkeyCard()
        card.set_data("Ctrl+B", "Sistem Komutu", "media_play_pause", False, state_text="Pasif")
        self.assertTrue(card.isEnabled(), "pasif kayıt kartı tıklanamaz olmamalı")
        self.assertFalse(card.property("cardEnabled"))

    def test_clicking_a_disabled_card_selects_it(self):
        lst = CardListWidget()
        lst.resize(800, 300)
        on, off = HotkeyCard(), HotkeyCard()
        on.set_data("Ctrl+1", "Metin Yaz", "a", True, state_text="Aktif")
        off.set_data("Ctrl+2", "Metin Yaz", "b", False, state_text="Pasif")
        lst.set_cards([on, off], select_row=0)
        lst.show()
        self.app.processEvents()
        QTest.mouseClick(off, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
        self.assertEqual(lst.selected_index(), 1, "pasif karta tıklayınca seçilmeli (yeniden açabilmek için)")
        lst.close()

    def test_state_pill_shows_text_for_both_card_kinds(self):
        for cls in (HotkeyCard, ExpansionCard):
            card = cls()
            card.set_data("x", "chip", "detail", True, state_text="Aktif")
            self.assertEqual(card.state_label.text(), "Aktif")
            self.assertFalse(card.state_label.isHidden())
            card.set_data("x", "chip", "detail", False)
            self.assertTrue(card.state_label.isHidden(), "metin verilmezse hap gizli kalır")

    def test_empty_placeholder_button_runs_the_action(self):
        calls = []
        placeholder = EmptyListPlaceholder("Henüz kısayol eklenmedi. Ekle butonunu kullanın.", action_text="Ekle", action=lambda: calls.append(1))
        placeholder.action_button.click()
        self.assertEqual(calls, [1])

    def test_empty_placeholder_splits_title_and_hint(self):
        placeholder = EmptyListPlaceholder("Henüz kısayol yok. Ekle butonunu kullanın.")
        texts = [label.text() for label in placeholder.findChildren(__import__("PyQt6.QtWidgets", fromlist=["QLabel"]).QLabel) if label.text()]
        self.assertIn("Henüz kısayol yok", texts)
        self.assertIn("Ekle butonunu kullanın.", texts)


if __name__ == "__main__":
    unittest.main()
