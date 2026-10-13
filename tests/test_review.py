import importlib
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from _qt_helpers import dispose_window


compat = importlib.import_module("src.qt.compat")


def _wait(app, condition, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestReviewDialog(unittest.TestCase):
    """Revisão em grade: prévia igual ao export, duplo clique abre no editor."""

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
        for i, color in enumerate(("red", "blue", "green")):
            path = os.path.join(self.tmp, f"r{i}.png")
            Image.new("RGB", (400, 600), color).save(path)
            self.paths.append(path)
        self.window.add_images(self.paths, replace=True)
        _wait(self.app, lambda: self.window._active_image_load_task_id is None)

    def _open(self, paths=None):
        dialog = self.window.open_review(paths)
        self.assertTrue(_wait(self.app, lambda: dialog.grid.count() == len(paths or self.paths)
                              and "Renderizando" not in dialog.status.text()))
        return dialog

    def test_previews_match_the_exported_customs(self):
        from src.core.batch_worker import render_custom_preview
        self.window.editor_state.individual_bordas[self.paths[1]] = "Red"
        dialog = self._open()
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.status.text(), "3 custom(s)")
        batch = self.window.batch_controller.frozen()
        out = os.path.join(self.tmp, "out")
        os.makedirs(out)
        try:
            batch.save_all_images(out)
        finally:
            batch.shutdown()
        for path in self.paths:
            preview = render_custom_preview(batch._get_task_data(path, None, source_dir=self.tmp))
            stem = os.path.splitext(os.path.basename(path))[0]
            with Image.open(os.path.join(out, f"{stem}_custom.png")) as exported:
                self.assertTrue(np.array_equal(np.asarray(preview.convert("RGBA")),
                                               np.asarray(exported.convert("RGBA"))))

    def test_double_click_opens_image_in_editor(self):
        dialog = self._open()
        self.addCleanup(dialog.close)
        dialog.grid.itemDoubleClicked.emit(dialog.grid.item(2))
        self.assertEqual(self.window.current_path, self.paths[2])

    def test_only_given_paths_and_missing_file_shows_problem(self):
        os.remove(self.paths[1])
        dialog = self._open(self.paths[:2])
        self.addCleanup(dialog.close)
        self.assertIn("1 com problema", dialog.status.text())
        self.assertIn("⚠", dialog.grid.item(1).text())

    def test_closing_while_rendering_is_safe(self):
        dialog = self.window.open_review()
        dialog.close()  # fecha antes da renderização terminar
        _wait(self.app, lambda: not self.window.task_runner.running_task_ids(), timeout=5)
        self.app.processEvents()  # o resultado atrasado não pode tocar no diálogo destruído


if __name__ == "__main__":
    unittest.main()
