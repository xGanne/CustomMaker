import importlib
import threading
import time
import unittest


qt_task_runner = importlib.import_module("src.qt.task_runner")


@unittest.skipUnless(getattr(qt_task_runner, "QT_AVAILABLE", False), "PySide6 not installed")
class TestQtTaskRunner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compat = importlib.import_module("src.qt.compat")
        cls.QCoreApplication = compat.QApplication
        cls.app = compat.QApplication.instance() or compat.QApplication([])

    def _pump_until(self, predicate, timeout=1.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(0.01)
        return predicate()

    def test_submit_emits_progress_and_done(self):
        runner = qt_task_runner.QtTaskRunner()
        done_event = threading.Event()
        progress = []

        def task_fn(_cancel_event, on_progress):
            on_progress(1, 2, "step")
            return {"ok": True}

        handle = runner.submit("qt_done", task_fn)
        self.assertIsNotNone(handle)
        handle.progress.connect(lambda current, total, text: progress.append((current, total, text)))
        handle.done.connect(lambda _result: done_event.set())

        self.assertTrue(self._pump_until(done_event.is_set))
        self.assertEqual(progress[-1], (1, 2, "step"))

    def test_error_emits_error_signal(self):
        runner = qt_task_runner.QtTaskRunner()
        error_event = threading.Event()

        def task_fn(_cancel_event, _on_progress):
            raise RuntimeError("boom")

        handle = runner.submit("qt_error", task_fn)
        self.assertIsNotNone(handle)
        handle.error.connect(lambda exc: error_event.set() if "boom" in str(exc) else None)

        self.assertTrue(self._pump_until(error_event.is_set))

    def test_cancel_emits_cancelled(self):
        runner = qt_task_runner.QtTaskRunner()
        cancelled_event = threading.Event()

        def task_fn(cancel_event, _on_progress):
            while not cancel_event.is_set():
                time.sleep(0.01)
            return {"cancelled": True}

        handle = runner.submit("qt_cancel", task_fn)
        self.assertIsNotNone(handle)
        handle.cancelled.connect(lambda: cancelled_event.set())
        self.assertTrue(runner.cancel("qt_cancel"))

        self.assertTrue(self._pump_until(cancelled_event.is_set))

    def test_fast_task_can_connect_done_after_submit(self):
        runner = qt_task_runner.QtTaskRunner()
        done_event = threading.Event()

        handle = runner.submit("qt_fast_done", lambda _cancel_event, _on_progress: {"ok": True})
        self.assertIsNotNone(handle)
        handle.done.connect(lambda _result: done_event.set())

        self.assertTrue(self._pump_until(done_event.is_set))

    def test_every_done_callback_runs_and_task_is_gone_first(self):
        # regressão: o handle era apagado no 1º slot e o `done` dos seguintes
        # se perdia às vezes (~1 em 8) — a imagem carregada não aparecia
        runner = qt_task_runner.QtTaskRunner()
        got = []
        for i in range(150):
            task_id = f"qt_many_{i}"
            handle = runner.submit(task_id, lambda _c, _p, i=i: i)
            handle.done.connect(lambda result, tid=task_id: got.append((result, runner.has_task(tid))))
            del handle  # como no app: quem submete não guarda o handle
            self.assertTrue(self._pump_until(lambda: len(got) > i, timeout=2.0), f"done perdido na task {i}")
        self.assertEqual(got, [(i, False) for i in range(150)])

    def test_failing_callback_does_not_stop_the_others(self):
        runner = qt_task_runner.QtTaskRunner()
        calls = []
        handle = runner.submit("qt_cb_error", lambda _c, _p: 1)
        handle.done.connect(lambda _r: 1 / 0)
        handle.done.connect(lambda r: calls.append(r))
        self.assertTrue(self._pump_until(lambda: calls == [1]))
