import importlib
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image

from _qt_helpers import dispose_window


compat = importlib.import_module("src.qt.compat")


def _wait(app, condition, timeout=20.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


class TestExportSummarySizes(unittest.TestCase):
    def test_summary_line_has_total_and_largest(self):
        from src.qt.mixins.export_mixin import ExportMixin
        line = ExportMixin._format_sizes({"sizes": {"/a/x.png": 1024 * 1024, "/a/grande.gif": 3 * 1024 * 1024}})
        self.assertEqual(line, "Tamanho: 4,0 MB no total · maior 3,0 MB (grande.gif)")
        self.assertIsNone(ExportMixin._format_sizes({}))


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestUploadSizeWarning(unittest.TestCase):
    """Antes do upload, customs acima do limite pedem confirmação."""

    @classmethod
    def setUpClass(cls):
        cls.app = compat.QApplication.instance() or compat.QApplication([])

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for patcher in (
            patch("src.core.app_config.CONFIG_FILE", os.path.join(self.tmp, "config.json")),
            patch("src.core.preset_manager.PRESETS_FILE", os.path.join(self.tmp, "presets.json")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        from src.core.app_config import AppConfig
        from src.qt.main_window import QtMainWindow
        self.window = QtMainWindow(AppConfig())
        self.addCleanup(dispose_window, self.app, self.window)
        self.paths = []
        for i in range(2):
            path = os.path.join(self.tmp, f"u{i}.png")
            Image.new("RGB", (400, 600), (80 * i, 90, 160)).save(path)
            self.paths.append(path)
        self.window.add_images(self.paths, replace=True)
        _wait(self.app, lambda: self.window._active_image_load_task_id is None)
        self.uploads = []

        class FakeUploader:
            api_token = "token"

            def reload_token(self):
                return True

            def upload_images(inner, files, title, progress_callback=None, cancel_event=None):
                self.uploads.append([f["filename"] for f in files])
                return [f"https://example.invalid/{i}" for i in range(len(files))], []

        self.window.uploader = FakeUploader()
        self.window.batch_controller.uploader = self.window.uploader
        self.window._show_links_dialog = lambda title, links: None
        self.window._show_result_summary = lambda *a, **k: None

    def _upload(self, choice):
        asked = []

        def ask(over, limit):
            asked.append([os.path.basename(r["path"]) for r in over])
            return choice

        with patch.object(compat.QInputDialog, "getText", return_value=("Album", True)), \
                patch.object(self.window, "_ask_oversized_upload", side_effect=ask), \
                patch.object(self.window, "open_review") as review:
            self.window.upload_to_imgchest()
            # _tasks inclui as tarefas já submetidas que ainda vão começar
            # (a medição termina e só então o upload é submetido)
            self.assertTrue(_wait(self.app, lambda: not self.window.task_runner._tasks))
        return asked, review

    def test_cancel_does_not_upload(self):
        self.window.app_config.set("export_size_warn_mb", 0.0001)
        asked, _review = self._upload("cancel")
        self.assertEqual(asked, [["u0.png", "u1.png"]])
        self.assertEqual(self.uploads, [])

    def test_send_anyway_uploads(self):
        self.window.app_config.set("export_size_warn_mb", 0.0001)
        asked, _review = self._upload("send")
        self.assertEqual(len(asked), 1)
        self.assertEqual(self.uploads, [["u0_custom.png", "u1_custom.png"]])

    def test_review_opens_the_grid_with_sizes(self):
        self.window.app_config.set("export_size_warn_mb", 0.0001)
        _asked, review = self._upload("review")
        self.assertEqual(self.uploads, [])
        review.assert_called_once()
        self.assertTrue(review.call_args.kwargs["measure"])

    def test_no_warning_under_the_limit_or_when_disabled(self):
        for limit in (8.0, 0):
            with self.subTest(limit=limit):
                self.uploads.clear()
                self.window.app_config.set("export_size_warn_mb", limit)
                asked, _review = self._upload("cancel")
                self.assertEqual(asked, [])
                self.assertEqual(len(self.uploads), 1)


if __name__ == "__main__":
    unittest.main()
