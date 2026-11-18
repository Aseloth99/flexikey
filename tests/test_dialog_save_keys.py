"""Kısayol / genişletme pencerelerinde Enter ve Ctrl+Enter.

Kullanıcı: "Enter kaydet yapmasın alt satıra geçsin, Ctrl+Enter kaydetsin." Eskiden metin kutusunda Enter alt satıra
geçiyor, tek satırlık alanda ise QDialog ilk "otomatik varsayılan" düğmeye (Biçimsiz Yapıştır vb.) basıyordu."""

from __future__ import annotations

import os
import pathlib
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from src.gui.main_window import ExpansionDialog, HotkeyDialog
from src.utils.locales import t

CTRL = Qt.KeyboardModifier.ControlModifier


class DialogSaveKeysTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def open(self, cls):
        dlg = cls()
        dlg.show()
        dlg.activateWindow()
        self.app.processEvents()
        self.accepted = []
        dlg.accepted.connect(lambda: self.accepted.append(True))
        self.addCleanup(dlg.deleteLater)
        self.addCleanup(dlg.close)
        return dlg

    def test_enter_in_expansion_text_adds_a_line_and_does_not_save(self):
        dlg = self.open(ExpansionDialog)
        dlg.trigger_input.setText("imza")
        dlg.replacement_text.setFocus()
        QTest.keyClicks(dlg.replacement_text, "Saygilarimla")
        QTest.keyClick(dlg.replacement_text, Qt.Key.Key_Return)
        QTest.keyClicks(dlg.replacement_text, "Mustafa")
        self.app.processEvents()
        self.assertEqual(self.accepted, [])
        self.assertTrue(dlg.isVisible())
        self.assertEqual(dlg.replacement_text.toPlainText(), "Saygilarimla\nMustafa")

    def test_ctrl_enter_saves_from_the_text_box(self):
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            dlg = self.open(ExpansionDialog)
            dlg.trigger_input.setText("imza")
            dlg.replacement_text.setFocus()
            QTest.keyClicks(dlg.replacement_text, "Saygilarimla")
            QTest.keyClick(dlg.replacement_text, key, CTRL)
            self.app.processEvents()
            self.assertEqual(self.accepted, [True], key)
            self.assertEqual(dlg.get_data()["replacement"], "Saygilarimla", "Ctrl+Enter metne satır eklememeli")

    def test_enter_in_the_trigger_field_moves_on_instead_of_pressing_a_button(self):
        dlg = self.open(ExpansionDialog)
        pasted = []
        dlg.paste_plain_btn.clicked.connect(lambda: pasted.append(True))
        dlg.trigger_input.setFocus()
        self.app.processEvents()
        QTest.keyClick(dlg.trigger_input, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.accepted, [])
        self.assertEqual(pasted, [])
        self.assertIsNot(dlg.focusWidget(), dlg.trigger_input)
        for button in dlg.findChildren(QPushButton):
            self.assertFalse(button.autoDefault() or button.isDefault(), button.text())

    def test_ctrl_enter_saves_the_hotkey_dialog_but_is_recorded_in_the_capture_field(self):
        dlg = self.open(HotkeyDialog)
        dlg.shortcut_input.setFocus()
        self.app.processEvents()
        QTest.keyClick(dlg.shortcut_input, Qt.Key.Key_Return, CTRL)
        self.app.processEvents()
        self.assertEqual(self.accepted, [], "kısayol alanında Ctrl+Enter kısayol olarak kaydedilir")
        self.assertEqual(dlg.shortcut_input.get_shortcut(), "ctrl+enter")
        dlg.text_input.setFocus()
        QTest.keyClicks(dlg.text_input, "merhaba")
        QTest.keyClick(dlg.text_input, Qt.Key.Key_Return, CTRL)
        self.app.processEvents()
        self.assertEqual(self.accepted, [True])

    def test_save_button_and_footer_tell_about_ctrl_enter(self):
        for cls in (ExpansionDialog, HotkeyDialog):
            dlg = self.open(cls)
            lang = dlg.lang
            hints = [lab for lab in dlg.findChildren(QLabel) if lab.text() == t("save_shortcut_hint", lang)]
            self.assertEqual(len(hints), 1, cls.__name__)
            self.assertTrue(hints[0].isVisible())
            self.assertIn("Ctrl+Enter", dlg._save_btn.toolTip())
            self.assertEqual(dlg._save_btn.text(), t("save", lang))
            # ipucu düğmelerin solunda, aynı satırda
            self.assertLess(hints[0].mapToGlobal(hints[0].rect().topRight()).x(),
                            dlg._save_btn.mapToGlobal(dlg._save_btn.rect().topLeft()).x())

    def test_hint_texts_exist_in_both_languages(self):
        for lang in ("tr", "en"):
            self.assertIn("Ctrl+Enter", t("save_shortcut_hint", lang))
            self.assertIn("Ctrl+Enter", t("save_shortcut_tip", lang))


if __name__ == "__main__":
    unittest.main()
