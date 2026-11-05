"""One long-lived thread that owns every Windows COM object StreamDesk touches.

COM pointers must be released on the thread that created them. Python's cyclic
garbage collector can run on any thread, so a pointer created on a short-lived
worker could be released elsewhere, after its apartment was gone, and crash the
whole process with an access violation. Running all pycaw/comtypes work here,
and collecting right after each call, keeps creation and release on one thread.
"""

import concurrent.futures
import gc
import queue
import threading
from typing import Any, Callable

import comtypes


class ComWorker:
    def __init__(self) -> None:
        self._tasks: "queue.Queue" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()

    def _ensure_started(self) -> None:
        with self._start_lock:
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="com-worker", daemon=True)
                self._thread.start()

    def _run(self) -> None:
        comtypes.CoInitialize()
        while True:
            fn, args, future = self._tasks.get()
            if not future.set_running_or_notify_cancel():
                continue
            try:
                future.set_result(fn(*args))
            except BaseException as exc:
                future.set_exception(exc)
            finally:
                del fn, args
                # Young generations are enough: the garbage comes from the call that just ended.
                gc.collect(1)

    def submit(self, fn: Callable[..., Any], *args: Any) -> concurrent.futures.Future:
        """Queue a call; calls run one at a time, in the order they were submitted."""
        future: concurrent.futures.Future = concurrent.futures.Future()
        if threading.current_thread() is self._thread:
            # Already on the COM thread (a COM function calling another): run it inline, waiting would deadlock.
            try:
                future.set_result(fn(*args))
            except BaseException as exc:
                future.set_exception(exc)
            return future
        self._ensure_started()
        self._tasks.put((fn, args, future))
        return future

    def call(self, fn: Callable[..., Any], *args: Any, timeout: float = 20) -> Any:
        future = self.submit(fn, *args)
        try:
            return future.result(timeout)
        except concurrent.futures.TimeoutError:
            # Taken off the queue if it has not started: otherwise it would run minutes later, when nobody waits for it
            # (a sound that plays by itself, a ghost reading of the Discord window).
            future.cancel()
            raise TimeoutError("Windows tardó demasiado en responder. Inténtalo de nuevo.") from None


com_worker = ComWorker()
