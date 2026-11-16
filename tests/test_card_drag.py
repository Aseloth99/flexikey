"""Kartları sürükleyerek sıralama (Trello gibi): tutulan kart süzülür, bırakılacağı yerde boş yuva açılır, bırakınca
sıra kaydedilir; Esc geri alır; kısa kıpırdama tıklama sayılır; liste yenilenirse fare/klavye takılı kalmaz."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget

from src.gui.list_widgets import CardListWidget, HotkeyCard
from src.utils.settings_manager import SettingsManager

LEFT = Qt.MouseButton.LeftButton


def mouse(widget: QWidget, kind: QEvent.Type, local: QPoint, held: bool = True):
    """Gerçek fareden gelir gibi: konum widget'a göre, düğme durumu ayrı."""
    button = LEFT if kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton
    buttons = LEFT if held else Qt.MouseButton.NoButton
    event = QMouseEvent(kind, QPointF(local), QPointF(widget.mapToGlobal(local)), button, buttons,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, event)


class CardDragTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.lst = CardListWidget()
        self.lst.resize(800, 400)  # iki sütun
        self.cards = []
        for i in range(4):
            card = HotkeyCard()
            card.set_data(f"Ctrl+{i}", "Metin Yaz", f"kart {i}", True, state_text="Aktif")
            self.cards.append(card)
        self.lst.set_cards(self.cards, select_row=0)
        self.lst.show()
        self.app.processEvents()
        self.moves = []
        self.lst.reordered.connect(lambda a, b: self.moves.append((a, b)))

    def tearDown(self):
        self.lst.close()

    def start_drag(self, card, to_card):
        """Kartı tutup öteki kartın ortasına götürür; sürükleme açık kalır."""
        grab = QPoint(20, 20)
        mouse(card, QEvent.Type.MouseButtonPress, grab)
        mouse(card, QEvent.Type.MouseMove, grab + QPoint(30, 0))
        self.assertTrue(self.lst.is_dragging())
        floating = self.lst._drag["float"]
        target = to_card.mapToGlobal(QPoint(to_card.width() // 2, to_card.height() // 2))
        # kartın ortası hedefin ortasına gelsin: tutulan nokta kadar kaydır
        local = floating.mapFromGlobal(target - QPoint(card.width() // 2 - grab.x(), card.height() // 2 - grab.y()))
        mouse(floating, QEvent.Type.MouseMove, local)
        return floating, local

    def order(self):
        return [self.cards.index(c) for c in self.lst._cards]

    def test_dropping_a_card_on_another_place_moves_it_there(self):
        floating, local = self.start_drag(self.cards[0], self.cards[3])
        self.assertTrue(self.cards[0].isHidden(), "tutulan kart yerinden kalkar")
        self.assertTrue(floating.isVisible(), "kopyası imleçle süzülür")
        self.assertIs(QWidget.mouseGrabber(), floating)
        slot = self.lst._drag["slot"]
        self.assertEqual(self.lst._grid.indexOf(slot), 3, "bırakılacak yerde boş yuva")
        self.assertEqual(slot.objectName(), "card_drop_slot")
        mouse(floating, QEvent.Type.MouseButtonRelease, local, held=False)
        self.assertFalse(self.lst.is_dragging())
        self.assertEqual(self.moves, [(0, 3)])
        self.assertEqual(self.order(), [1, 2, 3, 0])
        self.assertEqual(self.lst.selected_index(), 3, "taşınan kart seçili kalır")
        self.assertIsNone(QWidget.mouseGrabber(), "fare serbest")
        self.assertTrue(all(c.isVisibleTo(self.lst) for c in self.cards))
        self.assertEqual(self.lst._grid.count(), 4, "yuva gitti")

    def test_clicks_after_a_move_select_the_card_at_its_new_place(self):
        floating, local = self.start_drag(self.cards[0], self.cards[2])
        mouse(floating, QEvent.Type.MouseButtonRelease, local, held=False)
        self.assertEqual(self.moves, [(0, 2)])
        mouse(self.cards[1], QEvent.Type.MouseButtonPress, QPoint(10, 10))
        mouse(self.cards[1], QEvent.Type.MouseButtonRelease, QPoint(10, 10), held=False)
        self.assertEqual(self.lst.selected_index(), 0, "kart 1 artık en başta")

    def test_escape_puts_the_card_back(self):
        floating, _ = self.start_drag(self.cards[1], self.cards[3])
        QApplication.sendEvent(floating, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
        self.assertFalse(self.lst.is_dragging())
        self.assertEqual(self.moves, [])
        self.assertEqual(self.order(), [0, 1, 2, 3])
        self.assertIsNone(QWidget.mouseGrabber())
        self.assertIsNone(QWidget.keyboardGrabber())

    def test_dropping_where_it_started_changes_nothing(self):
        floating, local = self.start_drag(self.cards[2], self.cards[2])
        mouse(floating, QEvent.Type.MouseButtonRelease, local, held=False)
        self.assertEqual(self.moves, [])
        self.assertEqual(self.order(), [0, 1, 2, 3])

    def test_a_small_wobble_is_still_a_click(self):
        mouse(self.cards[2], QEvent.Type.MouseButtonPress, QPoint(20, 20))
        mouse(self.cards[2], QEvent.Type.MouseMove, QPoint(21, 21))
        self.assertFalse(self.lst.is_dragging())
        mouse(self.cards[2], QEvent.Type.MouseButtonRelease, QPoint(21, 21), held=False)
        self.assertEqual(self.lst.selected_index(), 2)

    def test_moving_without_the_button_never_drags(self):
        mouse(self.cards[0], QEvent.Type.MouseMove, QPoint(20, 20), held=False)
        mouse(self.cards[0], QEvent.Type.MouseMove, QPoint(90, 20), held=False)
        self.assertFalse(self.lst.is_dragging())

    def test_a_lost_release_does_not_leave_the_card_stuck(self):
        floating, local = self.start_drag(self.cards[0], self.cards[1])
        mouse(floating, QEvent.Type.MouseMove, local, held=False)  # düğme başka pencerede bırakıldı
        self.assertFalse(self.lst.is_dragging())
        self.assertIsNone(QWidget.mouseGrabber())

    def test_reloading_the_list_mid_drag_releases_the_mouse(self):
        self.start_drag(self.cards[0], self.cards[3])
        fresh = [HotkeyCard() for _ in range(2)]
        self.lst.set_cards(fresh)
        self.assertFalse(self.lst.is_dragging())
        self.assertIsNone(QWidget.mouseGrabber())
        self.assertIsNone(QWidget.keyboardGrabber())
        self.assertEqual(self.moves, [], "yarım kalan sürükleme kaydedilmez")
        self.assertEqual(self.lst.count(), 2)

    def test_old_cards_never_pop_up_as_windows_after_a_drop(self):
        # ana pencere gibi: bırakınca liste yeni kartlarla yeniden kurulur; eski kartlar ayrı pencere olarak açılıyordu
        self.lst.reordered.connect(lambda a, b: self.lst.set_cards([HotkeyCard() for _ in range(4)], select_row=b))
        for _ in range(3):
            card = self.lst._cards[0]
            floating, local = self.start_drag(card, self.lst._cards[3])
            mouse(floating, QEvent.Type.MouseButtonRelease, local, held=False)
            self.app.processEvents()
        strays = [w for w in QApplication.topLevelWidgets() if w.isVisible() and w is not self.lst]
        self.assertEqual(strays, [])

    def test_a_single_card_has_nowhere_to_go(self):
        self.lst.set_cards(self.cards[:1])
        mouse(self.cards[0], QEvent.Type.MouseButtonPress, QPoint(20, 20))
        mouse(self.cards[0], QEvent.Type.MouseMove, QPoint(90, 60))
        self.assertFalse(self.lst.is_dragging())


class SettingsMoveTest(unittest.TestCase):
    def test_move_keeps_every_record_and_changes_only_the_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            sm = SettingsManager(settings_path=os.path.join(tmp, "c.json"))
            for i in range(3):
                sm.add_hotkey(f"ctrl+{i}", "text", f"v{i}")
                sm.add_expansion(f";t{i}", f"r{i}")
            sm.move_hotkey(0, 2)
            sm.move_expansion(2, 0)
            data = SettingsManager(settings_path=os.path.join(tmp, "c.json")).load_settings()
            self.assertEqual([h["shortcut"] for h in data["hotkeys"]], ["ctrl+1", "ctrl+2", "ctrl+0"])
            self.assertEqual([e["trigger"] for e in data["expansions"]], [";t2", ";t0", ";t1"])
            sm.move_hotkey(0, 9)  # liste bu arada kısaldıysa: dokunulmaz
            sm.move_hotkey(-1, 0)
            again = sm.load_settings()
            self.assertEqual([h["shortcut"] for h in again["hotkeys"]], ["ctrl+1", "ctrl+2", "ctrl+0"])


class MainWindowWiringTest(unittest.TestCase):
    def test_a_drop_saves_the_order_and_keeps_the_moved_card_selected(self):
        from src.gui import main_window

        for name, move, load in (("_on_hotkeys_reordered", "move_hotkey", "load_hotkeys"),
                                 ("_on_expansions_reordered", "move_expansion", "load_expansions")):
            window = mock.Mock()
            getattr(main_window.MainWindow, name)(window, 0, 2)
            getattr(window.settings_manager, move).assert_called_once_with(0, 2)
            getattr(window, load).assert_called_once_with(keep_row=2)

    def test_both_lists_are_wired(self):
        source = (pathlib.Path(__file__).resolve().parents[1] / "src" / "gui" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn("self.hotkeys_list.reordered.connect(self._on_hotkeys_reordered)", source)
        self.assertIn("self.expansions_list.reordered.connect(self._on_expansions_reordered)", source)


if __name__ == "__main__":
    unittest.main()
