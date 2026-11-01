"""FlexiKey crash logger — yakalanmamış hataları ve native çökmeleri kaydeder."""

from __future__ import annotations

import faulthandler
import sys
import tempfile
import traceback
from pathlib import Path

from src.utils import platform_utils

_log_handle = None


def crash_log_path() -> Path:
    from src.utils.helpers import get_user_log_dir

    try:
        folder = Path(get_user_log_dir())
        platform_utils.ensure_private_dir(str(folder))
    except OSError:
        folder = Path(tempfile.gettempdir()) / "FlexiKey" / "logs"
        platform_utils.ensure_private_dir(str(folder))
    return folder / "crash.log"


def install_crash_log() -> Path:
    global _log_handle
    path = crash_log_path()
    if _log_handle is not None:
        return path
    try:
        _log_handle = path.open("a", encoding="utf-8", errors="replace")
        platform_utils.restrict_file(str(path))
        faulthandler.enable(_log_handle, all_threads=True)
    except Exception:
        pass

    def _hook(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            if _log_handle is not None:
                _log_handle.write(text + "\n")
                _log_handle.flush()
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook
    return path
