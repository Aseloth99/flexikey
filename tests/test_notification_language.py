"""Bildirimler uygulama dilinde olmali: notification_manager'a sabit Turkce metin verilmez."""

from __future__ import annotations

import ast
import pathlib
import re
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
TURKISH = re.compile(r"[ğüşıöçĞÜŞİÖÇ]")
METHODS = {"success", "info", "error", "warning", "show"}


def _literal_parts(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return [v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
    return []


class NotificationLanguageTest(unittest.TestCase):
    def test_notifications_use_locale_keys(self):
        offenders = []
        for path in sorted((SRC / "gui").glob("*.py")) + [SRC / "app.py"]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in METHODS):
                    continue
                owner = node.func.value
                owner_name = owner.attr if isinstance(owner, ast.Attribute) else getattr(owner, "id", "")
                if "notification" not in owner_name.lower() or not node.args:
                    continue
                if any(TURKISH.search(part) for part in _literal_parts(node.args[0])):
                    offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [], "sabit Turkce bildirim metni: t('anahtar', self.lang) kullanin")

    def test_the_keys_used_for_toggling_exist_in_both_languages(self):
        from src.utils.locales import LOCALES

        for key in ("hotkey_enabled", "hotkey_disabled", "expansion_enabled", "expansion_disabled",
                    "settings_reloaded", "running_in_tray"):
            for lang in ("tr", "en"):
                self.assertIn(key, LOCALES[lang], f"{lang}: {key}")
        self.assertNotEqual(LOCALES["tr"]["hotkey_enabled"], LOCALES["en"]["hotkey_enabled"])


if __name__ == "__main__":
    unittest.main()
