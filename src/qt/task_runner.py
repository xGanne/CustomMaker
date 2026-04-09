import threading

from src.qt.compat import QT_AVAILABLE, qt_unavailable_error

if QT_AVAILABLE:
    from src.qt.compat import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot


if QT_AVAILABLE:
    class _TaskRunnable(QRunnable):
        def __init__(self, handle, fn):
            super().__init__()
            self.handle = handle
            self.fn = fn

        @Slot()
        def run(self):
            try:
                result = self.fn(self.handle.cancel_event, self.handle.progress.emit)
                if self.handle.cancel_event.is_set():
                    self.handle.cancelled.emit()
                else:
                    self.handle.done.emit(result)
            except Exception as exc:
                self.handle.error.emit(exc)


    class QtTaskHandle(QObject):
        progress = Signal(int, int, str)
        done = Signal(object)
        error = Signal(object)
        cancelled = Signal()

        def __init__(self, task_id, fn, pool):
            super().__init__()
            self.task_id = task_id
            self.fn = fn
            self.pool = pool
            self.cancel_event = threading.Event()
            self._running = False
            self._runnable = None

        def start(self):
            self._running = True
            self._runnable = _TaskRunnable(self, self.fn)
            self.pool.start(self._runnable)

        def cancel(self):
            self.cancel_event.set()

        def is_running(self):
            return self._running

        def mark_finished(self):
            self._running = False


    class QtTaskRunner(QObject):
        def __init__(self, parent=None, thread_pool=None):
            super().__init__(parent)
            self._pool = thread_pool or QThreadPool.globalInstance()
            self._tasks = {}

        def submit(self, task_id, fn):
            existing = self._tasks.get(task_id)
            if existing and existing.is_running():
                return None

            handle = QtTaskHandle(task_id, fn, self._pool)
            self._tasks[task_id] = handle

            def cleanup(*_args):
                handle.mark_finished()
                self._tasks.pop(task_id, None)

            handle.done.connect(cleanup)
            handle.error.connect(cleanup)
            handle.cancelled.connect(cleanup)

            def start_later():
                if self._tasks.get(task_id) is not handle:
                    return
                if handle.cancel_event.is_set():
                    handle.cancelled.emit()
                    return
                handle.start()

            QTimer.singleShot(0, start_later)
            return handle

        def cancel(self, task_id):
            handle = self._tasks.get(task_id)
            if not handle:
                return False
            handle.cancel()
            return True

        def is_running(self, task_id):
            handle = self._tasks.get(task_id)
            return bool(handle and handle.is_running())
else:
    class QtTaskRunner:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
