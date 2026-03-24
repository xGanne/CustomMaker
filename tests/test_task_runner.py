import threading
import time
import unittest

from src.core.task_runner import TaskRunner


class TestTaskRunner(unittest.TestCase):
    def test_submit_runs_and_calls_done(self):
        runner = TaskRunner()
        done_event = threading.Event()

        def task_fn(cancel_event, on_progress):
            if on_progress:
                on_progress(1, 1, "ok")
            return {"ok": True}

        def on_done(result):
            if result.get("ok"):
                done_event.set()

        started = runner.submit("task_done", task_fn, on_done=on_done)
        self.assertTrue(started)
        self.assertTrue(done_event.wait(1.0))

        deadline = time.time() + 1.0
        while runner.is_running("task_done") and time.time() < deadline:
            time.sleep(0.01)
        self.assertFalse(runner.is_running("task_done"))

    def test_cancel_stops_running_task(self):
        runner = TaskRunner()
        done_event = threading.Event()

        def task_fn(cancel_event, on_progress):
            while not cancel_event.is_set():
                time.sleep(0.01)
            return {"cancelled": True}

        def on_done(_result):
            done_event.set()

        started = runner.submit("task_cancel", task_fn, on_done=on_done)
        self.assertTrue(started)
        self.assertTrue(runner.cancel("task_cancel"))

        deadline = time.time() + 1.0
        while runner.is_running("task_cancel") and time.time() < deadline:
            time.sleep(0.01)

        self.assertFalse(runner.is_running("task_cancel"))
        self.assertFalse(done_event.is_set())

    def test_submit_same_task_id_while_running_returns_false(self):
        runner = TaskRunner()
        started_event = threading.Event()
        release_event = threading.Event()

        def task_fn(cancel_event, on_progress):
            started_event.set()
            while not cancel_event.is_set() and not release_event.is_set():
                time.sleep(0.01)
            return {"done": True}

        self.assertTrue(runner.submit("dup_task", task_fn))
        self.assertTrue(started_event.wait(1.0))
        self.assertFalse(runner.submit("dup_task", task_fn))

        release_event.set()
        deadline = time.time() + 1.0
        while runner.is_running("dup_task") and time.time() < deadline:
            time.sleep(0.01)
        self.assertFalse(runner.is_running("dup_task"))

    def test_error_calls_on_error_callback(self):
        runner = TaskRunner()
        error_event = threading.Event()

        def task_fn(_cancel_event, _on_progress):
            raise RuntimeError("boom")

        def on_error(exc):
            if "boom" in str(exc):
                error_event.set()

        self.assertTrue(runner.submit("task_error", task_fn, on_error=on_error))
        self.assertTrue(error_event.wait(1.0))

    def test_cancel_unknown_task_returns_false(self):
        runner = TaskRunner()
        self.assertFalse(runner.cancel("missing_task"))
