"""Uygulamalar arası tutarlılık işi (SPEC): özel kutu bağlantısı, tepsi iskeleti ve tek tık, tema sırası, Açılışta Başlat
(ilk kurulum varsayılanı + Windows/macOS/Linux dalları), pasif düğmeler, Material vurgu ailesi, nötr gri açık tema,
mikro metin kuralları, bildirim yöneticisi ve dil varsayılanı.

Gerçek kayıt defterine/ayarlara DOKUNMAZ: winreg sahte, kullanıcı dizinleri geçici klasöre yönlendirilir."""

from __future__ import annotations

import os
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

import _support  # noqa: F401  (offscreen Qt, proje kökü sys.path'te)

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from src.gui import main_window as mw
from src.gui import message_box
from src.gui.message_box import MessageBox
from src.gui.notification_manager import NotificationManager
from src.gui.tray_manager import TrayManager
from src.utils import locales, startup
from src.utils.settings_manager import SettingsManager
from src.utils.theme_manager import ACCENTS, DARK_BASE, LIGHT_BASE, ORDERED_ACCENT_KEYS, ThemeManager, accent_hex

ROOT = pathlib.Path(__file__).resolve().parents[1]


class _TempProfile:
    """APPDATA/LOCALAPPDATA/USERPROFILE/HOME geçici klasöre (gerçek kullanıcı verisine dokunulmaz)."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = {k: os.environ.get(k) for k in ("APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME")}
        for key in self.saved:
            os.environ[key] = self.tmp.name
        return pathlib.Path(self.tmp.name)

    def __exit__(self, *exc):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication([])

    def setUp(self):
        self.addCleanup(MessageBox.set_test_hook, None)
        self.addCleanup(message_box.reset_configuration)
        self.addCleanup(locales.set_preferred_language, locales.get_preferred_language())


# ---------------------------------------------------------------------------------------------------------------
# Dil: t(anahtar) dili verilmezse KULLANICININ seçtiği dil
# ---------------------------------------------------------------------------------------------------------------
class DefaultLanguageTests(_Base):
    def test_t_without_language_follows_the_users_choice_not_the_system_language(self):
        locales.set_preferred_language("en")
        self.assertEqual(locales.t("settings"), "Settings")
        self.assertEqual(locales.get_active_language(), "en")
        locales.set_preferred_language("tr")
        self.assertEqual(locales.t("settings"), "Ayarlar")
        self.assertEqual(locales.get_active_language(), "tr")

    def test_auto_choice_falls_back_to_the_system_language(self):
        locales.set_preferred_language("auto")
        with mock.patch.object(locales, "get_system_language", return_value="en"):
            self.assertEqual(locales.t("settings"), "Settings")

    def test_an_explicit_language_still_wins(self):
        locales.set_preferred_language("en")
        self.assertEqual(locales.t("settings", "tr"), "Ayarlar")

    def test_the_settings_manager_reports_the_saved_choice(self):
        with _TempProfile():
            sm = SettingsManager()
            sm._seed_file = None
            data = sm.load_settings()
            data["language"] = "en"
            sm.save_settings(data)
            self.assertEqual(locales.get_preferred_language(), "en")
            data["language"] = "tr"
            sm.save_settings(data)
            self.assertEqual(locales.get_active_language(), "tr")

    def test_files_given_by_path_do_not_leak_into_the_preference(self):
        with tempfile.TemporaryDirectory() as tmp:
            locales.set_preferred_language("tr")
            sm = SettingsManager(settings_path=os.path.join(tmp, "c.json"))
            data = sm.load_settings()
            data["language"] = "en"
            sm.save_settings(data)
            self.assertEqual(locales.get_preferred_language(), "tr")


# ---------------------------------------------------------------------------------------------------------------
# Açılışta Başlat
# ---------------------------------------------------------------------------------------------------------------
class FakeWinreg:
    HKEY_CURRENT_USER = 1
    KEY_READ, KEY_SET_VALUE, REG_SZ = 1, 2, 1

    def __init__(self, values=None):
        self.values = dict(values or {})
        self.calls = []

    def OpenKey(self, root, path, reserved=0, access=0):  # noqa: N802
        self.calls.append(("open", path, access))
        return object()

    def CloseKey(self, key):  # noqa: N802
        pass

    def SetValueEx(self, key, name, reserved, kind, value):  # noqa: N802
        self.values[name] = value

    def DeleteValue(self, key, name):  # noqa: N802
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]

    def QueryValueEx(self, key, name):  # noqa: N802
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], self.REG_SZ


@unittest.skipUnless(sys.platform == "win32", "Run kaydı dalı yalnızca Windows'ta")
class StartupWindowsTests(unittest.TestCase):
    def test_run_value_is_the_same_as_before_and_keeps_minimized(self):
        fake = FakeWinreg()
        with mock.patch.object(startup, "winreg", fake), mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "executable", r"C:\Apps\FlexiKey.exe"):
            startup.set_enabled(True, True)
            self.assertEqual(fake.values["FlexiKey"], f'"{os.path.abspath(r"C:/Apps/FlexiKey.exe")}" --minimized')
            self.assertTrue(startup.is_enabled())
            startup.set_enabled(True, False)
            self.assertFalse(fake.values["FlexiKey"].endswith("--minimized"))
            startup.set_enabled(False, True)
            self.assertNotIn("FlexiKey", fake.values)
            self.assertFalse(startup.is_enabled())
            startup.set_enabled(False, True)        # zaten yok: hata vermez

    def test_run_key_path_is_the_hkcu_run_key(self):
        fake = FakeWinreg()
        with mock.patch.object(startup, "winreg", fake):
            startup.set_enabled(True, True)
        self.assertEqual(fake.calls[0][1], r"Software\Microsoft\Windows\CurrentVersion\Run")

    def test_source_run_uses_python_and_main_py(self):
        fake = FakeWinreg()
        with mock.patch.object(startup, "winreg", fake), mock.patch.object(sys, "frozen", False, create=True):
            startup.set_enabled(True, True)
        value = fake.values["FlexiKey"]
        self.assertIn("main.py", value)
        self.assertTrue(value.endswith(" --minimized"))


class StartupUnixTests(unittest.TestCase):
    def _run(self, platform, check):
        with _TempProfile() as home, mock.patch.object(sys, "platform", platform), \
                mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "executable", "/opt/flexikey/FlexiKey"):
            self.assertFalse(startup.is_enabled())
            startup.set_enabled(True, True)
            self.assertTrue(startup.is_enabled())
            check(home)
            startup.set_enabled(False, True)
            self.assertFalse(startup.is_enabled())

    def test_linux_writes_an_xdg_autostart_entry(self):
        def check(home):
            text = (home / ".config" / "autostart" / "flexikey.desktop").read_text(encoding="utf-8")
            self.assertIn("--minimized", text)
            self.assertIn("Exec=", text)
        self._run("linux", check)

    def test_macos_writes_a_launch_agent(self):
        def check(home):
            text = (home / "Library" / "LaunchAgents" / "com.macik.flexikey.plist").read_text(encoding="utf-8")
            self.assertIn("RunAtLoad", text)
            self.assertIn("--minimized", text)
        self._run("darwin", check)

    def test_failure_is_reported_as_an_exception(self):
        with mock.patch.object(sys, "platform", "linux"), \
                mock.patch("src.utils.autostart_unix.set_enabled", return_value=False):
            with self.assertRaises(OSError):
                startup.set_enabled(True, True)


class FirstRunTests(_Base):
    def test_first_run_means_no_settings_file_and_no_seed(self):
        with _TempProfile():
            sm = SettingsManager()
            sm._seed_file = None
            self.assertTrue(sm.is_first_run())
            sm.save_settings(sm.load_settings())
            self.assertFalse(sm.is_first_run(), "ayar dosyası oluştuktan sonra ilk kurulum değil")

    def test_a_seed_file_or_a_given_path_is_never_a_first_run(self):
        with _TempProfile() as tmp:
            sm = SettingsManager()
            sm._seed_file = str(tmp / "seed.json")
            (tmp / "seed.json").write_text("{}", encoding="utf-8")
            self.assertFalse(sm.is_first_run())
            self.assertFalse(SettingsManager(settings_path=str(tmp / "x.json")).is_first_run())

    def test_default_is_on_only_on_first_run_of_a_built_app(self):
        with mock.patch.object(startup, "set_enabled") as set_enabled:
            self.assertTrue(startup.apply_first_run_default(True, True, minimized=True))
            set_enabled.assert_called_once_with(True, True)
        with mock.patch.object(startup, "set_enabled") as set_enabled:
            self.assertFalse(startup.apply_first_run_default(False, True))     # mevcut kullanıcı: değişmez
            self.assertFalse(startup.apply_first_run_default(True, False))     # kaynaktan çalışan kopya: kaydolmaz
            set_enabled.assert_not_called()
        with mock.patch.object(startup, "set_enabled", side_effect=OSError("x")):
            self.assertFalse(startup.apply_first_run_default(True, True))      # hata sessiz

    def test_app_applies_the_default_and_writes_the_settings_file_once(self):
        from src import app as app_module
        from src.app import FlexiKeyApp
        app = object.__new__(FlexiKeyApp)
        app.settings_manager = mock.Mock()
        app.settings_manager.load_settings.return_value = {"start_minimized": True}
        with mock.patch.object(app_module, "_is_frozen", return_value=True), \
                mock.patch.object(app_module.startup, "apply_first_run_default", return_value=True) as apply:
            FlexiKeyApp._apply_first_run_defaults(app, True)
        apply.assert_called_once_with(True, True, minimized=True)
        app.settings_manager.save_settings.assert_called_once()
        app.settings_manager.reset_mock()
        with mock.patch.object(app_module, "_is_frozen", return_value=True):
            FlexiKeyApp._apply_first_run_defaults(app, False)                  # mevcut kullanıcı
        app.settings_manager.save_settings.assert_not_called()


# ---------------------------------------------------------------------------------------------------------------
# Ayarlar penceresi: tema sırası Sistem / Koyu / Açık, etiketler, iki güncelleme kutusu
# ---------------------------------------------------------------------------------------------------------------
class SettingsDialogTests(_Base):
    def _dialog(self, tmp, theme="system", lang="tr"):
        sm = SettingsManager(settings_path=str(tmp / "config.json"))
        data = sm.load_settings()
        data.update(theme=theme, language=lang)
        sm.save_settings(data)
        parent = QWidget()
        self.addCleanup(parent.deleteLater)
        dialog = mw.SettingsDialog(parent, sm, ThemeManager(self.qapp), mock.Mock(), None)
        self.addCleanup(dialog.deleteLater)
        return dialog, sm

    def test_theme_order_and_the_three_index_mappings_agree(self):
        with tempfile.TemporaryDirectory() as raw, \
                mock.patch.object(startup, "is_enabled", return_value=False), \
                mock.patch.object(startup, "set_enabled") as set_enabled:
            tmp = pathlib.Path(raw)
            for theme, index in (("system", 0), ("dark", 1), ("light", 2)):
                dialog, sm = self._dialog(tmp, theme)
                self.assertEqual([dialog.theme_combo.itemText(i) for i in range(3)], ["Sistem", "Koyu", "Açık"])
                self.assertEqual(dialog.theme_combo.currentIndex(), index, f"yükle: {theme}")
                self.assertEqual(dialog.THEME_BY_INDEX[index], theme)
                if theme != "system":
                    self.assertEqual(dialog._get_current_theme_target(), theme, f"önizleme: {theme}")
            dialog, sm = self._dialog(tmp, "system")
            for index, theme in ((1, "dark"), (2, "light"), (0, "system")):
                dialog.theme_combo.setCurrentIndex(index)
                dialog.save_and_close()
                self.assertEqual(sm.load_settings()["theme"], theme, f"kaydet: {index}")
            set_enabled.assert_called()

    def test_english_order_and_labels(self):
        with tempfile.TemporaryDirectory() as raw, mock.patch.object(startup, "is_enabled", return_value=False):
            dialog, _ = self._dialog(pathlib.Path(raw), "dark", "en")
            self.assertEqual([dialog.theme_combo.itemText(i) for i in range(3)], ["System", "Dark", "Light"])
            self.assertEqual(dialog.start_at_login_check.text(), "Start at Login")
            self.assertEqual(dialog.accent_name_label.text(), "(Cyan)")       # vurgu adı seçili dilde
            self.assertEqual(dialog.auto_update_check.text(), "Check for Updates Automatically")
            self.assertEqual(dialog.auto_update_install.text(), "Install Updates Automatically")

    def test_start_at_login_label_and_tip_have_no_windows_word(self):
        with tempfile.TemporaryDirectory() as raw, mock.patch.object(startup, "is_enabled", return_value=False):
            for lang, label in (("tr", "Açılışta Başlat"), ("en", "Start at Login")):
                dialog, _ = self._dialog(pathlib.Path(raw), "dark", lang)
                check = dialog.start_at_login_check
                self.assertEqual(check.text(), label)
                self.assertNotIn("Windows", check.text() + check.toolTip())

    def test_the_two_update_boxes_share_one_tip_and_install_follows_check(self):
        with tempfile.TemporaryDirectory() as raw, mock.patch.object(startup, "is_enabled", return_value=False):
            dialog, _ = self._dialog(pathlib.Path(raw), "dark")
            self.assertTrue(dialog.auto_update_check.toolTip())
            self.assertEqual(dialog.auto_update_check.toolTip(), dialog.auto_update_install.toolTip())
            dialog.auto_update_check.setChecked(False)
            self.assertFalse(dialog.auto_update_install.isEnabled())
            dialog.auto_update_check.setChecked(True)
            self.assertTrue(dialog.auto_update_install.isEnabled())

    def test_title_bars_are_38_px(self):
        with tempfile.TemporaryDirectory() as raw, mock.patch.object(startup, "is_enabled", return_value=False):
            dialog, _ = self._dialog(pathlib.Path(raw), "dark")
            heights = {frame.height() for frame in dialog.findChildren(QWidget) if frame.objectName() == "title_bar"}
            self.assertEqual(heights, {38})

    def test_startup_failure_uses_the_custom_message_box(self):
        seen = []
        MessageBox.set_test_hook(lambda box: seen.append((box.icon(), box.text())))
        with tempfile.TemporaryDirectory() as raw, mock.patch.object(startup, "is_enabled", return_value=False), \
                mock.patch.object(startup, "set_enabled", side_effect=OSError("erişim reddedildi")):
            dialog, _ = self._dialog(pathlib.Path(raw), "dark")
            dialog.save_and_close()
        self.assertEqual(len(seen), 1)
        self.assertIn("erişim reddedildi", seen[0][1])


# ---------------------------------------------------------------------------------------------------------------
# Ana pencere: seçimsizken pasif düğmeler (diyalog yok), Hakkında/Kılavuz özel kutuda, sistem teması hatası -> koyu
# ---------------------------------------------------------------------------------------------------------------
class MainWindowTests(_Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._profile = _TempProfile()
        cls._profile.__enter__()
        from src.core.hotkey_manager import HotkeyManager
        cls.settings = SettingsManager()
        cls.settings._seed_file = None
        data = cls.settings.load_settings()
        data.update(theme="dark", language="tr", hotkeys=[], expansions=[])
        cls.settings.save_settings(data)
        cls.window = mw.MainWindow(cls.settings, ThemeManager(cls.qapp), HotkeyManager(), NotificationManager(), None)
        cls.window.show()
        cls.qapp.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls.window.deleteLater()
        cls.qapp.processEvents()
        cls._profile.__exit__(None, None, None)

    def _set(self, hotkeys=(), expansions=()):
        data = self.settings.load_settings()
        data.update(hotkeys=list(hotkeys), expansions=list(expansions))
        self.settings.save_settings(data)
        self.window.load_hotkeys()
        self.window.load_expansions()
        self.qapp.processEvents()

    def test_actions_are_disabled_with_a_hint_when_nothing_is_selected(self):
        self._set()
        for prefix, tips in (("hotkey", ("Düzenlemek için bir öğe seçin.", "Aktif/pasif yapmak için bir öğe seçin.",
                                          "Silmek için bir öğe seçin.")),
                             ("exp", ("Düzenlemek için bir öğe seçin.", "Aktif/pasif yapmak için bir öğe seçin.",
                                      "Silmek için bir öğe seçin."))):
            for suffix, tip in zip(("edit", "toggle", "delete"), tips):
                button = getattr(self.window, f"{prefix}_{suffix}_btn")
                self.assertFalse(button.isEnabled(), (prefix, suffix))
                self.assertEqual(button.toolTip(), tip)

    def test_actions_become_enabled_with_a_selection_and_no_dialog_opens_without_one(self):
        item = {"shortcut": "Ctrl+Alt+7", "action_type": "text", "action_value": "x", "enabled": True}
        self._set(hotkeys=[item])
        for suffix in ("edit", "toggle", "delete"):
            self.assertTrue(getattr(self.window, f"hotkey_{suffix}_btn").isEnabled(), suffix)
        self.assertEqual(self.window.hotkey_edit_btn.toolTip(), "")
        self._set()
        opened = []
        MessageBox.set_test_hook(lambda box: opened.append(box.text()))
        with mock.patch.object(mw.HotkeyDialog, "exec", side_effect=AssertionError("diyalog açılmamalı")):
            self.window.edit_hotkey()
            self.window.delete_hotkey()
            self.window.toggle_hotkey()
            self.window.edit_expansion()
            self.window.delete_expansion()
            self.window.toggle_expansion()
        self.assertEqual(opened, [], "seçim yokken hiçbir kutu açılmamalı")

    def test_delete_segment_is_neutral_like_its_siblings(self):
        """"Sil" kırmızı yazılmaz: Düzenle ve Aktif/Pasif ile aynı sınıf; kırmızı yalnızca onay kutusunda."""
        for prefix in ("hotkey", "exp"):
            classes = {getattr(self.window, f"{prefix}_{s}_btn").property("class") for s in ("edit", "toggle", "delete")}
            self.assertEqual(classes, {"seg"}, prefix)
        self.assertNotIn("seg-danger", QApplication.instance().styleSheet())

    def test_about_and_guide_use_the_custom_box_with_theme_coloured_link(self):
        shown = []
        MessageBox.set_test_hook(lambda box: shown.append((box.windowTitle(), box.text())))
        self.window.show_about()
        self.window.show_help()
        self.assertEqual(len(shown), 2)
        accent = self.window.theme_manager.get_palette()["accent_text"]
        for title, text in shown:
            self.assertIn("macik.com.tr", text)
            self.assertIn(accent, text, "bağlantı rengi temanın vurgusundan")
            self.assertNotIn("#2f7de1", text)
        self.assertEqual(shown[0][0], "FlexiKey Hakkında")
        self.assertEqual(shown[1][0], "Kullanım Kılavuzu")
        self.assertIn("Sürüm", shown[0][1])
        self.assertNotIn("Güncel", shown[0][1])

    def test_system_theme_read_failure_defaults_to_dark(self):
        if sys.platform != "win32":
            self.skipTest("Windows kayıt defteri dalı")

        class Broken:
            HKEY_CURRENT_USER, KEY_READ = 1, 1

            def OpenKey(self, *a, **k):  # noqa: N802
                raise OSError("okunamadı")

        with mock.patch.object(mw, "winreg", Broken()):
            self.assertTrue(mw.is_system_dark_mode())

    def test_no_native_message_box_is_left_in_the_application_code(self):
        for path in (ROOT / "src").rglob("*.py"):
            if path.name == "message_box.py":
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"QMessageBox|QInputDialog", path.name)

    def test_tab_names_have_no_emoji_but_a_vector_icon(self):
        self.assertEqual(self.window.tabs.tabText(0), "Klavye Kısayolları")
        self.assertEqual(self.window.tabs.tabText(1), "Metin Genişletme")
        self.assertFalse(self.window.tabs.tabIcon(0).isNull())
        self.assertFalse(self.window.tabs.tabIcon(1).isNull())

    def test_main_title_bar_is_38_px(self):
        bar = [w for w in self.window.findChildren(QWidget) if w.objectName() == "title_bar"][0]
        self.assertEqual(bar.height(), 38)
        # Büyüt/geri yükle düğmesi metin glifi değil, durumu izleyen vektör glif (bkz. test_window_glyphs)
        self.assertEqual((self.window.maximize_btn.text(), self.window.close_btn.text()), ("", "×"))
        self.assertEqual(self.window.maximize_btn.glyph(), "maximize")
        self.window.toggle_maximize()
        self.assertEqual(self.window.maximize_btn.glyph(), "restore")
        self.window.toggle_maximize()
        self.assertEqual(self.window.maximize_btn.glyph(), "maximize")

    def test_empty_state_has_a_title_and_one_guiding_sentence_without_guillemets(self):
        self._set()
        for lang in ("tr", "en"):
            for key in ("empty_hotkeys", "empty_expansions"):
                text = locales.LOCALES[lang][key]
                self.assertNotIn("«", text)
                self.assertNotIn("»", text)
                self.assertEqual(len(re.findall(r"\. ", text)), 1, "başlık + tek cümle rehber")


    def test_menu_rows_use_the_colored_semantic_icons(self):
        from src.gui.toolbar_icons import menu_icon

        for action, name in ((self.window.new_hotkey_action, "add"), (self.window.new_expansion_action, "rename"),
                             (self.window.exit_action, "exit"), (self.window.settings_action, "settings"),
                             (self.window.help_action, "guide"), (self.window.about_action, "info")):
            self.assertTrue(_same_icon(action.icon(), menu_icon(name)), name)
        self.window._refresh_accent_icons()   # tema/vurgu değişince de aynı simgeler
        self.assertTrue(_same_icon(self.window.settings_action.icon(), menu_icon("settings")))
        self.assertTrue(_same_icon(self.window.exit_action.icon(), menu_icon("exit")))


# ---------------------------------------------------------------------------------------------------------------
# Kartın sağ tık menüsü: Düzenle · Pasif/Aktif Yap · Kopyala · — · Sil (mevcut yöntemler; gizli değer panoya çıkmaz)
# ---------------------------------------------------------------------------------------------------------------
SECRET_VALUE = "Gizli-Deger-42"
HOTKEYS = [
    {"shortcut": "Ctrl+Alt+7", "action_type": "text", "action_value": "merhaba dünya, uzun bir metin", "enabled": True},
    {"shortcut": "Ctrl+Alt+8", "action_type": "command", "action_value": "hesap_makinesi", "enabled": False},
    {"shortcut": "Ctrl+Alt+9", "action_type": "text", "action_value": SECRET_VALUE + "h", "enabled": True,
     "is_secret": True},
]
EXPANSIONS = [
    {"trigger": ";adr", "replacement": "Atatürk Cad. No 5\nAnkara", "enabled": True},
    {"trigger": ";imza", "replacement": "<b>Kalın</b> imza", "is_rich": True, "enabled": False},
    {"trigger": ";pw", "replacement": SECRET_VALUE, "enabled": True, "is_secret": True},
]
MENU_TR = ["Düzenle", "Pasif Yap", "Kopyala", "", "Sil"]


def _menu_rows(menu):
    return [("" if a.isSeparator() else a.text()) for a in menu.actions()]


class CardMenuTests(_Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._profile = _TempProfile()
        cls._profile.__enter__()
        from src.core.hotkey_manager import HotkeyManager
        cls.settings = SettingsManager()
        cls.settings._seed_file = None
        data = cls.settings.load_settings()
        data.update(theme="dark", language="tr", hotkeys=[], expansions=[])
        cls.settings.save_settings(data)
        cls.window = mw.MainWindow(cls.settings, ThemeManager(cls.qapp), HotkeyManager(), NotificationManager(), None)
        cls.window.show()
        cls.qapp.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls.window.deleteLater()
        cls.qapp.processEvents()
        cls._profile.__exit__(None, None, None)

    def setUp(self):
        super().setUp()
        import copy
        data = self.settings.load_settings()
        data.update(hotkeys=copy.deepcopy(HOTKEYS), expansions=copy.deepcopy(EXPANSIONS))
        self.settings.save_settings(data)
        self.window.load_hotkeys(keep_row=0)
        self.window.load_expansions(keep_row=0)
        self.qapp.processEvents()
        self.toasts = []
        patcher = mock.patch.object(self.window, "show_toast",
                                    side_effect=lambda text, *a, **k: (self.toasts.append(text), True)[1])
        patcher.start()
        self.addCleanup(patcher.stop)

    def _menu(self, prefix, row):
        menu = self.window.card_menu(prefix, row)
        self.addCleanup(menu.deleteLater)
        return menu

    def _action(self, menu, text):
        return next(a for a in menu.actions() if a.text() == text)

    def test_order_labels_and_icons(self):
        from src.gui.toolbar_icons import menu_icon

        for prefix in ("hotkey", "exp"):
            menu = self._menu(prefix, 0)
            self.assertEqual(_menu_rows(menu), MENU_TR, prefix)
            self.assertTrue(menu.actions()[3].isSeparator())
            for action, name in zip([a for a in menu.actions() if not a.isSeparator()],
                                    ("rename", "bolt", "copy", "trash")):
                self.assertTrue(_same_icon(action.icon(), menu_icon(name)), (prefix, name))
        locales.set_preferred_language("en")
        self.window.lang = "en"
        self.addCleanup(setattr, self.window, "lang", "tr")
        self.assertEqual(_menu_rows(self._menu("exp", 0)), ["Edit", "Turn Off", "Copy", "", "Delete"])
        self.assertEqual(_menu_rows(self._menu("exp", 1))[1], "Turn On")

    def test_toggle_label_follows_the_state(self):
        self.assertEqual(_menu_rows(self._menu("hotkey", 0))[1], "Pasif Yap")   # aktif
        self.assertEqual(_menu_rows(self._menu("hotkey", 1))[1], "Aktif Yap")   # pasif
        self.assertEqual(_menu_rows(self._menu("exp", 1))[1], "Aktif Yap")
        self._action(self._menu("hotkey", 0), "Pasif Yap").trigger()
        self.assertFalse(self.settings.load_settings()["hotkeys"][0]["enabled"])
        self.assertEqual(_menu_rows(self._menu("hotkey", 0))[1], "Aktif Yap")

    def test_each_entry_calls_the_existing_handler_for_that_card(self):
        for prefix, names in (("hotkey", ("edit_hotkey", "toggle_hotkey", "delete_hotkey")),
                              ("exp", ("edit_expansion", "toggle_expansion", "delete_expansion"))):
            with mock.patch.object(self.window, names[0]) as edit, mock.patch.object(self.window, names[1]) as toggle, \
                    mock.patch.object(self.window, names[2]) as delete, \
                    mock.patch.object(self.window, "copy_item") as copy_item:
                menu = self._menu(prefix, 1)
                for text in ("Düzenle", "Aktif Yap", "Kopyala", "Sil"):
                    self._action(menu, text).trigger()
                mocks = {"edit": edit, "toggle": toggle, "delete": delete}
                for key, m in mocks.items():
                    m.assert_called_once_with(1)
                copy_item.assert_called_once_with(prefix, 1)

    def test_toggle_hits_the_card_of_the_menu_even_if_another_is_selected(self):
        self.window.hotkeys_list.setCurrentRow(0)
        self._action(self._menu("hotkey", 1), "Aktif Yap").trigger()
        rows = self.settings.load_settings()["hotkeys"]
        self.assertTrue(rows[1]["enabled"])
        self.assertTrue(rows[0]["enabled"], "seçili kart değil, menüsü açılan kart değişir")
        self.assertEqual(self.toasts[-1], "Kısayol 'Ctrl + Alt + 8' aktif edildi.")

    def test_delete_goes_through_the_existing_confirmation(self):
        asked = []
        MessageBox.set_test_hook(lambda box: (asked.append(box.text()), MessageBox.StandardButton.No)[1])
        self._action(self._menu("exp", 0), "Sil").trigger()
        self.assertEqual(asked, [locales.t("confirm_delete_expansion", "tr")])
        self.assertEqual(len(self.settings.load_settings()["expansions"]), 3, "Hayır: silinmez")
        MessageBox.set_test_hook(lambda box: MessageBox.StandardButton.Yes)
        self._action(self._menu("exp", 0), "Sil").trigger()
        self.assertEqual([e["trigger"] for e in self.settings.load_settings()["expansions"]], [";imza", ";pw"])

    def test_edit_opens_the_same_editor_as_double_click(self):
        seen = []
        with mock.patch.object(mw.ExpansionDialog, "exec", lambda dialog: (seen.append(dialog), 0)[1]):
            self._action(self._menu("exp", 1), "Düzenle").trigger()
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].__class__.__name__, "ExpansionDialog")

    def test_copy_puts_the_full_content_on_the_clipboard_without_echoing_it(self):
        clipboard = QApplication.clipboard()
        self._action(self._menu("hotkey", 0), "Kopyala").trigger()
        self.assertEqual(clipboard.text(), "merhaba dünya, uzun bir metin")
        self._action(self._menu("hotkey", 1), "Kopyala").trigger()
        self.assertEqual(clipboard.text(), "Hesap Makinesi", "komut: kartta görünen adı")
        self._action(self._menu("exp", 0), "Kopyala").trigger()
        self.assertEqual(clipboard.text(), "Atatürk Cad. No 5\nAnkara")
        self._action(self._menu("exp", 1), "Kopyala").trigger()
        mime = clipboard.mimeData()
        self.assertTrue(mime.hasHtml())
        self.assertIn("<b>Kalın</b>", mime.html())
        self.assertEqual(mime.text(), "Kalın imza", "biçimli metin: düz hâli de panoda")
        self.assertEqual(self.toasts, ["Kısayol 'Ctrl + Alt + 7' içeriği panoya kopyalandı.",
                                       "Kısayol 'Ctrl + Alt + 8' içeriği panoya kopyalandı.",
                                       "Genişletme ';adr' içeriği panoya kopyalandı.",
                                       "Genişletme ';imza' içeriği panoya kopyalandı."])
        for toast in self.toasts:
            self.assertNotIn("merhaba", toast)
            self.assertNotIn("Ankara", toast)

    def test_secret_value_never_reaches_the_clipboard_or_the_screen(self):
        clipboard = QApplication.clipboard()
        clipboard.setText("önceki pano")
        for prefix in ("hotkey", "exp"):
            menu = self._menu(prefix, 2)
            copy_action = self._action(menu, "Kopyala")
            self.assertFalse(copy_action.isEnabled(), prefix)
            self.assertEqual(copy_action.toolTip(), "Gizli değerler panoya kopyalanmaz.")
            self.assertTrue(menu.toolTipsVisible())
            copy_action.trigger()                          # pasif eylem tetiklenmez; yöntem de reddeder
            self.assertFalse(self.window.copy_item(prefix, 2))
            for action in menu.actions():
                self.assertNotIn(SECRET_VALUE, action.text() + action.toolTip() + action.statusTip())
            self.assertEqual([a.isEnabled() for a in menu.actions() if not a.isSeparator()],
                             [True, True, False, True], "gizli öğe de düzenlenir / silinir")
        self.assertEqual(clipboard.text(), "önceki pano")
        self.assertEqual(self.toasts, [])

    def test_delete_label_is_neutral_and_only_the_trash_icon_is_red(self):
        menu = self._menu("exp", 0)
        menu.ensurePolished()
        menu.adjustSize()
        image = menu.grab().toImage()
        ratio = image.devicePixelRatio()

        def region(action, x0, x1):
            geo = menu.actionGeometry(action)
            return {image.pixelColor(x, y).name()
                    for y in range(int(geo.top() * ratio), int(geo.bottom() * ratio))
                    for x in range(int((geo.left() + x0) * ratio), int(min(geo.left() + x1, geo.right()) * ratio))}

        def reddish(name):
            from PyQt6.QtGui import QColor
            c = QColor(name)
            return c.red() >= 150 and c.red() - max(c.green(), c.blue()) >= 70

        edit, delete = self._action(menu, "Düzenle"), self._action(menu, "Sil")
        self.assertTrue(any(reddish(c) for c in region(delete, 0, 36)), "çöp simgesi kırmızı kalır")
        text_sil, text_edit = region(delete, 40, 10_000), region(edit, 40, 10_000)
        self.assertFalse([c for c in text_sil if reddish(c)], "Sil yazısı kırmızı değil")
        self.assertEqual(text_sil, text_edit, "Sil ile Düzenle yazısı aynı renk")

    def test_right_click_selects_the_card_under_the_cursor_and_opens_its_menu(self):
        from PyQt6.QtCore import QPoint
        from PyQt6.QtGui import QContextMenuEvent
        from PyQt6.QtWidgets import QMenu

        listing = self.window.hotkeys_list
        listing.setCurrentRow(0)
        opened, changes = [], []
        listing.selection_changed.connect(changes.append)
        self.addCleanup(listing.selection_changed.disconnect, changes.append)

        def fake_exec(menu, *args):
            opened.append((_menu_rows(menu), args[0] if args else None))
            return None

        card = listing.card_at(1)
        where = card.mapToGlobal(QPoint(20, 10))
        with mock.patch.object(QMenu, "exec", fake_exec):
            QApplication.sendEvent(card, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(20, 10), where))
            self.assertEqual(listing.selected_index(), 1, "sağ tık altta kalan kartı seçer")
            self.assertEqual(changes, [1])
            QApplication.sendEvent(card, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(20, 10), where))
            self.assertEqual(changes, [1], "zaten seçili kart: seçim yeniden değişmez")
        self.assertEqual(opened, [(["Düzenle", "Aktif Yap", "Kopyala", "", "Sil"], where)] * 2)
        self.assertTrue(listing.hasFocus() or not self.window.isActiveWindow())

    def test_menu_key_and_shift_f10_open_the_selected_cards_menu(self):
        from PyQt6.QtCore import QPoint, Qt
        from PyQt6.QtGui import QContextMenuEvent
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QMenu

        listing = self.window.expansions_list
        listing.setCurrentRow(1)
        opened = []
        with mock.patch.object(QMenu, "exec", lambda menu, *a: opened.append(_menu_rows(menu)[1])):
            QTest.keyClick(listing, Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)
            QApplication.sendEvent(listing, QContextMenuEvent(QContextMenuEvent.Reason.Keyboard, QPoint(1, 1)))
            QApplication.sendEvent(listing, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(1, 1)))
            listing.set_filter("bulunmayan")               # süzgeç seçili kartı gizledi: menü açılmaz
            self.addCleanup(listing.set_filter, "")
            QTest.keyClick(listing, Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(opened, ["Aktif Yap", "Aktif Yap"], "boşlukta fare sağ tıkı ve gizli kart menü açmaz")
        self.assertEqual(listing.selected_index(), -1)

# ---------------------------------------------------------------------------------------------------------------
# Tepsi: iskelet, tek tık, dinamik Göster/Gizle, vurguya uyan simgeler
# ---------------------------------------------------------------------------------------------------------------
class FakeSettings:
    def __init__(self, lang="tr"):
        self.lang = lang

    def load_settings(self):
        return {"language": self.lang, "theme": "system"}


class FakeWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.settings_manager = FakeSettings()
        self.settings_requests = 0

    def show_settings(self):
        self.settings_requests += 1

    def show_pending_update(self):
        pass

    def close_app(self):
        pass


class TraySkeletonTests(_Base):
    def setUp(self):
        super().setUp()
        self.window = FakeWindow()
        self.addCleanup(self.window.deleteLater)
        self.tray = TrayManager(self.window, mock.Mock(), mock.Mock())
        self.addCleanup(self.tray.tray_icon.hide)

    def visible(self):
        return [("-" if a.isSeparator() else a.text()) for a in self.tray.menu.actions() if a.isVisible()]

    def test_skeleton_order(self):
        self.assertEqual(self.visible(), ["Göster", "Ayarlar", "Tema", "Dil", "-", "Hızlı İşlemler", "-", "Çıkış"])
        self.tray.set_update_available("1.2.3")
        self.assertEqual(self.visible()[:3], ["Güncelle · v1.2.3", "-", "Göster"])

    def test_submenus_hold_system_dark_light_and_auto_tr_us(self):
        self.assertEqual([a.text() for a in self.tray.theme_menu.actions()], ["Sistem", "Koyu", "Açık"])
        labels = [a.text() for a in self.tray.lang_menu.actions()]
        self.assertTrue(labels[0].startswith("Otomatik"))
        self.assertEqual(labels[1:], ["TR · Türkçe", "US · English"])

    def test_single_click_and_double_click_open_and_raise_the_window(self):
        for reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.window.hide()
            self.assertFalse(self.window.isVisible())
            self.tray.on_tray_activated(reason)
            self.assertTrue(self.window.isVisible(), reason)
            self.tray.on_tray_activated(reason)          # ikinci tık pencereyi GİZLEMEZ
            self.assertTrue(self.window.isVisible(), reason)

    def test_other_activation_reasons_do_nothing(self):
        self.window.hide()
        self.tray.on_tray_activated(QSystemTrayIcon.ActivationReason.MiddleClick)
        self.assertFalse(self.window.isVisible())

    def test_show_hide_label_follows_the_real_window_state(self):
        self.window.hide()
        self.tray.menu.aboutToShow.emit()
        self.assertEqual(self.tray.show_action.text(), "Göster")
        self.window.show()
        self.tray.menu.aboutToShow.emit()
        self.assertEqual(self.tray.show_action.text(), "Gizle")
        self.tray.toggle_window()
        self.assertFalse(self.window.isVisible())
        self.assertEqual(self.tray.show_action.text(), "Göster")

    def test_icons_follow_the_accent(self):
        manager = ThemeManager(self.qapp)
        manager.set_theme("dark", "rose")
        self.assertEqual(accent_hex().lower(), ACCENTS["rose"]["accent"].lower())
        self.tray.refresh_icons()
        self.assertFalse(self.tray.show_action.icon().isNull())

    def test_rows_use_the_colored_semantic_icons(self):
        from src.gui.toolbar_icons import menu_icon

        self.tray.refresh_icons()
        for item, name in ((self.tray.update_action, "update"), (self.tray.show_action, "view"),
                           (self.tray.settings_action, "settings"), (self.tray.lang_menu, "globe"),
                           (self.tray.quick_menu, "bolt"), (self.tray.exit_action, "exit")):
            self.assertTrue(_same_icon(item.icon(), menu_icon(name)), name)


# ---------------------------------------------------------------------------------------------------------------
# Görünüm: Material vurgu ailesi, nötr gri açık tema, lacivert/slate yok
# ---------------------------------------------------------------------------------------------------------------
class PaletteTests(unittest.TestCase):
    MATERIAL = {
        "cyan": ("#00ACC1", "#00838F"), "blue": ("#2196F3", "#1976D2"), "teal": ("#00897B", "#00695C"),
        "indigo": ("#3F51B5", "#303F9F"), "violet": ("#7C4DFF", "#651FFF"), "rose": ("#E91E63", "#C2185B"),
        "orange": ("#FB8C00", "#EF6C00"), "red": ("#E53935", "#C62828"), "green": ("#43A047", "#2E7D32"),
        "yellow": ("#F9A825", "#F57F17"),
    }

    def test_accents_are_the_material_family_shared_with_the_other_apps(self):
        self.assertEqual(ORDERED_ACCENT_KEYS, list(self.MATERIAL))
        for key, (accent, accent2) in self.MATERIAL.items():
            self.assertEqual((ACCENTS[key]["accent"], ACCENTS[key]["accent2"]), (accent, accent2), key)
        self.assertEqual((ACCENTS["cyan"]["label_tr"], ACCENTS["cyan"]["label_en"]), ("Turkuaz", "Cyan"))

    def test_light_theme_is_the_neutral_grey_family(self):
        expected = {"base": "#e0e0e0", "raised": "#f5f5f5", "sunken": "#d8d8d8", "border": "#c5c5c5",
                    "text": "#1a1a1a", "text_muted": "#616161"}
        for key, value in expected.items():
            self.assertEqual(LIGHT_BASE[key], value, key)
        self.assertEqual(LIGHT_BASE["surface2"], "#ececec")        # MC LIGHT "surface"

    def test_no_cold_blue_grey_or_navy_remains(self):
        text = (ROOT / "src" / "utils" / "theme_manager.py").read_text(encoding="utf-8").lower()
        for banned in ("#f4f6fa", "#e2e8f0", "#0f172a", "#1e293b", "#94a3b8", "#1e1b4b", "#0b0f19", "#334155", "#38bdf8"):
            self.assertNotIn(banned, text, banned)
        for table in (LIGHT_BASE, DARK_BASE):
            for key in ("base", "surface", "surface2", "border"):
                r, g, b = (int(table[key][i:i + 2], 16) for i in (1, 3, 5))
                self.assertLess(max(r, g, b) - min(r, g, b), 4, f"{key} nötr gri olmalı")

    def test_theme_manager_publishes_the_icon_accent(self):
        app = QApplication.instance() or QApplication([])
        manager = ThemeManager(app)
        manager.set_theme("light", "yellow")
        self.assertEqual(accent_hex(), ACCENTS["yellow"]["accent2"])       # açıkta okunur derin ton
        manager.set_theme("dark", "yellow")
        self.assertEqual(accent_hex(), ACCENTS["yellow"]["accent"])


class CheckboxSpecTests(unittest.TestCase):
    """Onay kutusu MediaCompressor/TransferTCP/Lumina ile aynı: 18 px kutu, 5 px köşe, 1 px kenar, seçiliyken vurgu
    dolgu + 4x çizilmiş beyaz tik, pasif+seçiliyken gri dolgu + soluk tik."""

    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication([])   # _build_qss ok simgesini QPixmap ile çizer

    @staticmethod
    def _rule(qss: str, selector: str) -> str:
        match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", qss)
        assert match, selector
        return " ".join(match.group(1).split())

    def test_states_use_the_shared_geometry_and_the_chosen_accent(self):
        from src.utils.theme_manager import _build_palette, _build_qss

        for dark, accent in ((True, "violet"), (False, "rose")):
            p = _build_palette(dark, accent)
            qss = _build_qss(p)
            base = self._rule(qss, "QCheckBox::indicator")
            for decl in ("width: 18px;", "height: 18px;", "border-radius: 5px;",
                         f"background-color: {p['surface2']};", f"border: 1px solid {p['border_strong']};"):
                self.assertIn(decl, base)
            self.assertIn(f"border-color: {p['accent']};", self._rule(qss, "QCheckBox::indicator:unchecked:hover"))
            checked = self._rule(qss, "QCheckBox::indicator:checked")
            self.assertIn(f"background-color: {ACCENTS[accent]['accent2']};", checked)
            self.assertRegex(checked, r'image: url\("[^"]*flexikey_check_ffffff_x4\.png"\)')
            disabled = self._rule(qss, "QCheckBox::indicator:checked:disabled")
            self.assertIn(f"background-color: {p['border_strong']};", disabled)
            self.assertIn(f"flexikey_check_{p['text_muted'].lstrip('#')}_x4.png", disabled)
            # aynı özgüllük: pasif kuralları üzerine gelme kurallarından SONRA gelir
            self.assertLess(qss.index("QCheckBox::indicator:checked:hover"),
                            qss.index("QCheckBox::indicator:unchecked:disabled"))

    def test_tick_is_drawn_at_four_times_the_box(self):
        from PyQt6.QtGui import QImage
        from src.utils.theme_manager import get_checkmark_icon_path

        img = QImage(get_checkmark_icon_path("#ffffff"))
        self.assertEqual((img.width(), img.height()), (64, 64))
        self.assertEqual(img.pixelColor(24, 44).name(), "#ffffff")   # (6, 11) köşesi x4
        self.assertEqual(img.pixelColor(2, 2).alpha(), 0)


# ---------------------------------------------------------------------------------------------------------------
# Metin kuralları
# ---------------------------------------------------------------------------------------------------------------
class MicrocopyTests(unittest.TestCase):
    def test_no_three_dots_and_no_trailing_colon_on_labels(self):
        for lang, table in locales.LOCALES.items():
            for key, value in table.items():
                self.assertNotIn("...", value, (lang, key))
            for key in ("theme", "language", "accent_color", "hotkey_label", "action_type_label", "params_label",
                        "trigger_label", "expanded_label", "update_notes"):
                self.assertFalse(table[key].endswith(":"), (lang, key))

    def test_control_labels_are_title_case(self):
        expected = {
            "tr": {"update_now": "Şimdi Güncelle", "update_later": "Daha Sonra", "check_updates": "Kontrol Et",
                   "update_retry": "Tekrar Dene", "update_notes": "Sürüm Notları", "start_at_login": "Açılışta Başlat",
                   "auto_update_check": "Güncellemeleri Otomatik Kontrol Et", "auto_update_install": "Güncellemeleri Otomatik Kur",
                   "updates": "Güncellemeler", "show_notifications": "Masaüstü Bildirimlerini Göster"},
            "en": {"update_now": "Update Now", "update_later": "Later", "check_updates": "Check for Updates",
                   "update_retry": "Try Again", "update_notes": "Release Notes", "start_at_login": "Start at Login",
                   "auto_update_check": "Check for Updates Automatically", "auto_update_install": "Install Updates Automatically",
                   "updates": "Updates", "show_notifications": "Show Desktop Notifications"},
        }
        for lang, items in expected.items():
            for key, value in items.items():
                self.assertEqual(locales.LOCALES[lang][key], value, (lang, key))

    def test_up_to_date_has_one_form(self):
        self.assertEqual(locales.t("up_to_date", "tr").format("1.0.0"), "Güncel · v1.0.0")
        self.assertEqual(locales.t("up_to_date", "en").format("1.0.0"), "Up to date · v1.0.0")

    def test_user_facing_texts_do_not_say_windows(self):
        allowed = {"cmd_minimize_all"}      # İngilizce çoğul "windows" (pencereler)
        for lang, table in locales.LOCALES.items():
            for key, value in table.items():
                if key not in allowed:
                    self.assertNotIn("Windows", value, (lang, key))

    def test_start_at_login_keys_replaced_the_old_windows_keys(self):
        for table in locales.LOCALES.values():
            self.assertNotIn("start_with_windows", table)
            self.assertIn("start_at_login", table)


# ---------------------------------------------------------------------------------------------------------------
# Bildirim yöneticisi: tek yol Notifier, show_notifications ayarı aynen geçit
# ---------------------------------------------------------------------------------------------------------------
class NotificationManagerTests(_Base):
    def test_disabled_setting_blocks_every_notification(self):
        manager = NotificationManager()
        manager._notifier = mock.Mock()
        manager.show("a", "b")
        manager.error("x")
        manager._notifier.notify.assert_not_called()

    def test_enabled_goes_through_the_shared_notifier_and_errors_are_critical(self):
        manager = NotificationManager()
        manager._notifier = mock.Mock()
        manager.set_enabled(True)
        manager.info("merhaba")
        manager.error("hata")
        calls = manager._notifier.notify.call_args_list
        self.assertEqual([c.kwargs["critical"] for c in calls], [False, True])
        self.assertEqual(calls[0].args[1], "merhaba")

    def test_default_stays_off_and_winotify_is_gone(self):
        from src.utils.settings_manager import DEFAULT_SETTINGS
        self.assertFalse(NotificationManager().is_enabled())
        self.assertIs(DEFAULT_SETTINGS["show_notifications"], False)
        source = (ROOT / "src" / "gui" / "notification_manager.py").read_text(encoding="utf-8")
        self.assertNotIn("winotify", source)

    def test_enabled_manager_shows_a_tray_balloon_on_the_real_notifier(self):
        tray = mock.Mock()
        tray.isVisible.return_value = True
        with mock.patch.object(QSystemTrayIcon, "supportsMessages", staticmethod(lambda: True)):
            manager = NotificationManager(tray)     # Notifier, destek sorgusunu kurulumda bağlar
            manager.set_enabled(True)
            manager.success("tamam")
        tray.showMessage.assert_called_once()


# ---------------------------------------------------------------------------------------------------------------
# Yıkıcı komut onayı: özel kutu
# ---------------------------------------------------------------------------------------------------------------
class DestructiveConfirmTests(_Base):
    def test_default_confirmation_uses_the_custom_box_and_defaults_to_no(self):
        from src.core.hotkey_manager import HotkeyManager
        manager = HotkeyManager()
        seen = []

        def hook(box):
            seen.append((box.windowTitle(), box.icon(), box.defaultButton()))
            return MessageBox.StandardButton.Yes

        MessageBox.set_test_hook(hook)
        self.assertTrue(manager._ask_user_to_confirm("bilgisayari_kapat"))
        MessageBox.set_test_hook(lambda box: MessageBox.StandardButton.No)
        self.assertFalse(manager._ask_user_to_confirm("bilgisayari_kapat"))
        self.assertEqual(seen[0][0], "Onay Gerekli" if manager.lang == "tr" else "Confirmation Required")
        self.assertEqual(seen[0][1], MessageBox.Icon.Warning)


# ---------------------------------------------------------------------------------------------------------------
# Ayarlar iskeleti (Lumina ile aynı): solda renkli simgeli sekmeler; seçili sekme vurgu tonlu zemin + okunur vurgu
# yazı + solda 3 px vurgu çizgisi. Menü satırlarında renkli anlam simgeleri (aynı anlam her uygulamada aynı renk).
# ---------------------------------------------------------------------------------------------------------------
def _rgb(color):
    h = color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lumina_mix(a, b, amount):
    (ra, ga, ba), (rb, gb, bb) = _rgb(a), _rgb(b)
    return "#" + "".join(f"{max(0, min(255, round(x + (y - x) * amount))):02x}" for x, y in ((ra, rb), (ga, gb), (ba, bb)))


def _lumina_luminance(color):
    def lin(v):
        s = v / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(v) for v in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _lumina_contrast(a, b):
    la, lb = _lumina_luminance(a), _lumina_luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _close(a, b, tolerance=1):
    return all(abs(x - y) <= tolerance for x, y in zip(_rgb(a), _rgb(b)))


def _same_icon(a, b, size=32):
    return a.pixmap(size, size).toImage() == b.pixmap(size, size).toImage()


def _top_colors(icon, size=32, count=3):
    from collections import Counter

    img = icon.pixmap(size, size).toImage()
    seen = Counter(img.pixelColor(x, y).name() for x in range(size) for y in range(size)
                   if img.pixelColor(x, y).alpha() == 255)
    return [name for name, _ in seen.most_common(count)]


def _rule(qss, selector):
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", qss)
    assert match, selector
    return " ".join(match.group(1).split())


class SettingsNavTests(_Base):
    def _dialog(self, tmp):
        sm = SettingsManager(settings_path=str(tmp / "config.json"))
        data = sm.load_settings()
        data.update(theme="dark", language="tr")
        sm.save_settings(data)
        parent = QWidget()
        self.addCleanup(parent.deleteLater)
        dialog = mw.SettingsDialog(parent, sm, ThemeManager(self.qapp), mock.Mock(), None)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_sidebar_has_checkable_nav_buttons_with_colored_icons(self):
        from src.gui.toolbar_icons import menu_icon

        with tempfile.TemporaryDirectory() as raw, mock.patch.object(startup, "is_enabled", return_value=False):
            dialog = self._dialog(pathlib.Path(raw))
            self.assertEqual(dialog.sidebar.objectName(), "sidebar")
            self.assertEqual([b.text() for b in dialog.nav_buttons], ["Genel", "Yedekleme", "Güncellemeler"])
            self.assertEqual(dialog.stack.count(), 3)
            for btn, name in zip(dialog.nav_buttons, ("settings", "backup", "update")):
                self.assertEqual(btn.objectName(), "nav_btn")
                self.assertTrue(btn.isCheckable() and btn.autoExclusive())
                btn.ensurePolished()   # stil sayfası uygulandıktan sonra da 38 px (genel düğmenin 32 px sınırı ezmesin)
                self.assertEqual((btn.minimumHeight(), btn.maximumHeight()), (38, 38))
                self.assertTrue(_same_icon(btn.icon(), menu_icon(name)), name)
            self.assertEqual([b.isChecked() for b in dialog.nav_buttons], [True, False, False])
            dialog.nav_buttons[2].click()
            self.assertEqual(dialog.stack.currentIndex(), 2)
            self.assertEqual([b.isChecked() for b in dialog.nav_buttons], [False, False, True])
            # kartlar sayfalara dağıldı: güncelleme düğmesi Güncellemeler sayfasında
            self.assertTrue(dialog.stack.widget(2).isAncestorOf(dialog.check_update_btn))
            self.assertTrue(dialog.stack.widget(0).isAncestorOf(dialog.theme_combo))
            self.assertGreaterEqual(dialog.sidebar.width(), 150)

    def test_nav_rules_match_lumina(self):
        from src.utils.theme_manager import _build_palette, _build_qss

        for dark, accent in ((True, "violet"), (False, "rose"), (True, "yellow"), (False, "cyan")):
            p = _build_palette(dark, accent)
            qss = _build_qss(p)
            base = _rule(qss, "QPushButton#nav_btn")
            for decl in ("padding-left: 7px;", "border: none;", "border-left: 3px solid transparent;",
                         "border-radius: 6px;", f"color: {p['text_muted']};", "min-height: 38px;", "max-height: 38px;"):
                self.assertIn(decl, base)
            checked = _rule(qss, "QPushButton#nav_btn:checked")
            tint = re.search(r"background-color: (#[0-9a-fA-F]{6});", checked).group(1)
            ink = re.search(r"(?<!-)color: (#[0-9a-fA-F]{6});", checked).group(1)
            self.assertTrue(_close(tint, _lumina_mix(p["surface"], p["accent"], 0.16 if dark else 0.13)), (tint, accent))
            self.assertGreaterEqual(_lumina_contrast(ink, tint), 4.5, (ink, tint))
            if _lumina_contrast(p["accent_hi"] if dark else p["accent2"], tint) >= 4.5:
                self.assertEqual(ink.lower(), (p["accent_hi"] if dark else p["accent2"]).lower())
            self.assertIn(f"border-left: 3px solid {p['accent']};", checked)
            self.assertIn("font-weight: 700;", checked)
            self.assertLess(qss.index("QPushButton#nav_btn:hover"), qss.index("QPushButton#nav_btn:checked"))


class MenuIconTableTests(_Base):
    """Renk anlamla gelir (Lumina `MENU_PALETTE`): ayarlar mor, güncelle zümrüt, çıkış/sil kırmızı, göz/kılavuz çivit,
    klasör amber; mavi/gök aile (bilgi, küre, kopya, belge) seçili vurguyu izler."""

    FIXED = {"settings": "#8b5cf6", "update": "#10b981", "exit": "#ef4444", "view": "#7c7ff5", "guide": "#7c7ff5",
             "trash": "#ef4444", "folder": "#fcd34d", "backup": "#d97706", "add": "#22c55e", "trim": "#22c55e",
             "adjust": "#f97316", "send": "#14b8a6", "network": "#06b6d4", "open_with": "#a855f7",
             "rename": "#f59e0b", "star": "#eab308", "bolt": "#eab308", "pause": "#f59e0b", "play": "#22c55e"}

    def test_same_meaning_same_color(self):
        from src.gui.toolbar_icons import MENU_ICON_NAMES, menu_icon

        self.assertLessEqual(set(self.FIXED), set(MENU_ICON_NAMES))
        for name, color in self.FIXED.items():
            self.assertIn(color, _top_colors(menu_icon(name)), name)

    def test_blue_family_follows_the_accent(self):
        from src.gui.toolbar_icons import menu_icon
        from src.utils.theme_manager import DEFAULT_ACCENT

        manager = ThemeManager(self.qapp)
        self.addCleanup(manager.set_theme, "dark", DEFAULT_ACCENT)
        for key in ("rose", "green"):
            manager.set_theme("dark", key)
            self.assertEqual(_top_colors(menu_icon("info"), count=1), [ACCENTS[key]["accent"].lower()], key)
            self.assertEqual(_top_colors(menu_icon("settings"), count=1), ["#8b5cf6"], "mor dişli vurguyu izlemez")


if __name__ == "__main__":
    unittest.main()
