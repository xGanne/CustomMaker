import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


logger = logging.getLogger(__name__)


ProgressCallback = Callable[[Any], None]
DoneCallback = Callable[[Any], None]
ErrorCallback = Callable[[Exception], None]


@dataclass
class TaskState:
    thread: threading.Thread
    cancel_event: threading.Event


class TaskRunner:
    """Runs background tasks and exposes cancellation/status by task id."""

    def __init__(self):
        self._tasks: Dict[str, TaskState] = {}
        self._lock = threading.Lock()

    def submit(
        self,
        task_id: str,
        fn: Callable[[threading.Event, Optional[ProgressCallback]], Any],
        on_progress: Optional[ProgressCallback] = None,
        on_done: Optional[DoneCallback] = None,
        on_error: Optional[ErrorCallback] = None,
    ) -> bool:
        with self._lock:
            if task_id in self._tasks:
                state = self._tasks[task_id]
                if state.thread.is_alive():
                    logger.warning("Task '%s' já está em execução.", task_id)
                    return False
                del self._tasks[task_id]

            cancel_event = threading.Event()
            thread = threading.Thread(
                target=self._run_task,
                args=(task_id, fn, cancel_event, on_progress, on_done, on_error),
                daemon=True,
            )
            self._tasks[task_id] = TaskState(thread=thread, cancel_event=cancel_event)
            thread.start()
            return True

    def _run_task(
        self,
        task_id: str,
        fn: Callable[[threading.Event, Optional[ProgressCallback]], Any],
        cancel_event: threading.Event,
        on_progress: Optional[ProgressCallback],
        on_done: Optional[DoneCallback],
        on_error: Optional[ErrorCallback],
    ) -> None:
        try:
            result = fn(cancel_event, on_progress)
            if cancel_event.is_set():
                return
            if on_done:
                on_done(result)
        except Exception as exc:
            logger.exception("Erro na task '%s': %s", task_id, exc)
            if on_error:
                on_error(exc)
        finally:
            with self._lock:
                self._tasks.pop(task_id, None)

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            state = self._tasks.get(task_id)
            if not state:
                return False
            state.cancel_event.set()
            return True

    def is_running(self, task_id: str) -> bool:
        with self._lock:
            state = self._tasks.get(task_id)
            if not state:
                return False
            return state.thread.is_alive()
