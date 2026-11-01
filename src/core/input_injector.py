"""Klavye girdisi enjeksiyonu için arka plan iş kuyruğu (platformdan bağımsız)."""

from __future__ import annotations

import queue
import threading
import time

from src.utils.helpers import log_error


class _InputInjector:
    """Uyuyan/uzun klavye girdisi işlerini GUI iş parçacığı dışında, sırayla (FIFO) çalıştırır.

    kb.write her karakter için SendInput + kanca gidiş-dönüşü yaptığından uzun metin GUI'yi
    dondurur; tuş kombinasyonlarındaki time.sleep'ler de her tetiklemede GUI'yi bekletir.
    Tek bir arka plan iş parçacığı kullanıldığı için art arda gelen işler sırasını korur
    ve birbirinin içine girmez.
    """

    def __init__(self):
        self._queue = queue.Queue()
        self._thread = None
        self._thread_lock = threading.Lock()

    def submit(self, job, on_error=None):
        """job() arka planda çalışır; hata olursa loglanır ve on_error(exc) çağrılır."""
        self._queue.put((job, on_error))
        with self._thread_lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._run, name='FlexiKey-input', daemon=True
                )
                self._thread.start()

    def _run(self):
        while True:
            job, on_error = self._queue.get()
            try:
                job()
            except Exception as exc:
                log_error("Klavye girdisi gönderilemedi", exc)
                if on_error is not None:
                    try:
                        on_error(exc)
                    except Exception:
                        pass
            finally:
                self._queue.task_done()

    def wait_idle(self, timeout: float = 5.0) -> bool:
        """Kuyruktaki tüm işler bitene kadar bekler (testler/kapanış için)."""
        deadline = time.monotonic() + timeout
        while self._queue.unfinished_tasks:
            if time.monotonic() > deadline:
                return False
            threading.Event().wait(0.005)
        return True


INPUT_INJECTOR = _InputInjector()
