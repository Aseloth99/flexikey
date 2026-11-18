"""Kart ızgarası: liste tek sütuna düşmemeli; uzun bir kısayol da ne sütunları ne de metni ezmeli.

Eski hata: kartın "gereken genişliği" metne 150 px ve "Aktif" hapını da sayıyordu; varsayılan pencerede
(840 px) iki kart sığmıyor, liste tek sütuna düşüyordu."""

from __future__ import annotations

import os
import pathlib
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication

from src.gui.list_widgets import CARD_MIN_TEXT, CardListWidget, ExpansionCard, HotkeyCard

SHORTCUTS = ["Ctrl+M", "Scroll Lock", "Ctrl+B", "Ctrl+Shift+1", "Ctrl+Shift+2"]


class CardColumnsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def build(self, shortcuts, width, card_cls=HotkeyCard):
        lst = CardListWidget()
        for sc in shortcuts:
            card = card_cls()
            card.set_data(sc, "Sistem Komutu", "Görev Yöneticisi", True, state_text="Aktif")
            lst.add_card(card)
        lst.resize(width, 500)
        lst.show()
        self.app.processEvents()
        lst.resize(width, 500)  # ilk gösterimden sonra bir kez daha: gerçek pencerede de böyle yerleşir
        self.app.processEvents()
        self.addCleanup(lst.close)
        return lst

    def test_narrowest_window_still_has_two_columns(self):
        # 640 px iç genişlik: FlexiKey'in en dar penceresi (720) bu kadarını bırakır.
        lst = self.build(SHORTCUTS, 660)
        self.assertEqual(lst._column_count(), 2)
        for card in lst._cards:
            self.assertGreaterEqual(card.primary_label.width(), CARD_MIN_TEXT - 1, card._kbd_full)

    def test_a_very_long_shortcut_shortens_its_chip_instead_of_dropping_a_column(self):
        lst = self.build(SHORTCUTS + ["Ctrl+Alt+Shift+Backspace"], 780)
        self.assertEqual(lst._column_count(), 2)
        long_card = lst._cards[-1]
        self.assertGreaterEqual(long_card.primary_label.width(), CARD_MIN_TEXT - 1)
        if long_card.kbd_label.text() != long_card._kbd_full:
            self.assertTrue(long_card.kbd_label.text().endswith("…"))
            self.assertEqual(long_card.toolTip(), long_card._kbd_full)

    def test_state_pills_are_all_shown_or_all_hidden(self):
        for width in (660, 780, 900, 1500):
            lst = self.build(SHORTCUTS + ["Ctrl+Alt+Shift+Backspace"], width)
            shown = {card.state_label.isVisible() for card in lst._cards}
            self.assertEqual(len(shown), 1, f"{width}: {shown}")

    def assert_aligned(self, lst):
        chips = {card.kbd_label.width() for card in lst._cards}
        self.assertEqual(len(chips), 1, f"çipler aynı genişlikte olmalı: {chips}")
        starts = {card.primary_label.mapTo(card, card.primary_label.rect().topLeft()).x() for card in lst._cards}
        self.assertEqual(len(starts), 1, f"metin sütunu her kartta aynı yerden başlamalı: {starts}")

    def test_short_and_long_shortcuts_line_up(self):
        # Kullanıcının ekranı: "Ctrl + M" ile "Ctrl + Shift + 1" kartlarında yazılar farklı yerden başlıyordu.
        for width in (660, 900, 1500):
            lst = self.build(SHORTCUTS, width)
            self.assert_aligned(lst)
            for card in lst._cards:
                self.assertEqual(card.kbd_label.text(), card._kbd_full, "sığan kısayol kısaltılmamalı")

    def test_long_trigger_is_shortened_and_does_not_widen_the_column(self):
        # Kullanıcının ekranı: uzun bir tetikleyici çipi kartın yarısını kaplıyor, metni eziyordu.
        long = "notsitefhdfghfghdfgjdtryjtyjtyjtyjtyj"
        lst = self.build(["mail1", "mail2", "adr", long], 1200, ExpansionCard)
        self.assert_aligned(lst)
        card = lst._cards[-1]
        self.assertLessEqual(card.kbd_label.width(), ExpansionCard.KBD_CAP)
        self.assertTrue(card.kbd_label.text().endswith("…"))
        self.assertEqual(card.toolTip(), long)
        self.assertEqual(lst._cards[0].kbd_label.text(), "mail1")
        self.assertEqual(lst._cards[0].toolTip(), "")
        for c in lst._cards:
            self.assertGreaterEqual(c.primary_label.width(), CARD_MIN_TEXT - 1)

    def test_column_follows_the_list_after_the_long_card_is_gone(self):
        lst = self.build(["mail1", "notsitefhdfghfghdfgjdtryjtyjtyj"], 1200, ExpansionCard)
        wide = lst._cards[0].kbd_label.width()
        lst.set_cards([])
        card = ExpansionCard()
        card.set_data("mail1", "Genişletme", "x", True)
        lst.set_cards([card])
        self.app.processEvents()
        self.assertLess(card.kbd_label.width(), wide)

    def test_wide_window_uses_more_columns(self):
        lst = self.build(SHORTCUTS, 1500)
        self.assertGreaterEqual(lst._column_count(), 3)


if __name__ == "__main__":
    unittest.main()
