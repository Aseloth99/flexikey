"""FlexiKey"""

import os
import sys

os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts=false")

# Proje kökünü path'e ekle (kaynaktan çalışırken `src` paketi bulunsun)
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    from src.utils.crashlog import install_crash_log
    install_crash_log()

    # Kaynak dosyaları (ikon vb.) göreli yoldan bulunsun diye CWD = uygulama klasörü.
    # Ayarlar artık bu dizine yazılmaz; kullanıcı config dizinine kaydedilir.
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if os.path.exists(exe_dir):
            os.chdir(exe_dir)
    else:
        if os.path.exists(ROOT):
            os.chdir(ROOT)

    # Güncellemeden gelen yeniden başlatma (`--wait-pid N`): eski sürüm tamamen çıkana (tek kopya kilidi, tepsi simgesi)
    # dek bekle. Kilit ve QApplication'dan ÖNCE olmalı.
    from src.utils import self_update
    self_update.wait_for_previous_instance(sys.argv)
    after_update = self_update.flag_value(sys.argv, "--wait-pid") is not None or self_update.updated_from() is not None

    # Windows başlangıcında sistemin hazır olması için kısa bir gecikme
    # (sadece --minimized argümanı varsa, yani startup'tan geliyorsa; güncelleme sonrası sistem zaten hazırdır)
    if "--minimized" in sys.argv and not after_update:
        import time
        time.sleep(2)  # 2 saniye bekle, sistem hazır olsun

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    from src.app import FlexiKeyApp
    from src.utils.helpers import log_info

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Qt 6 zaten PER_MONITOR_AWARE_V2 kullanır; ikinci kez ayarlamak
    # SetProcessDpiAwarenessContext erişim hatası basar.
    if sys.platform == "win32":
        try:
            import ctypes
            set_app_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
            set_app_id.argtypes = [ctypes.c_wchar_p]
            set_app_id.restype = ctypes.HRESULT
            set_app_id("FlexiKey.App")
        except Exception:
            pass

    log_info("FlexiKey baslatiliyor...")

    app = FlexiKeyApp()
    return app.run()


if __name__ == '__main__':
    sys.exit(main())
