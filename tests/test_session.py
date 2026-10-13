import importlib
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image

from src.core.editor_state import EditorState
from src.core.session_store import SESSION_VERSION, SessionStore, apply_session, snapshot_session

from _qt_helpers import dispose_window


class _TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.paths = []
        for i in range(3):
            path = os.path.join(self.tmp, f"img{i}.png")
            Image.new("RGBA", (40, 60), "white").save(path)
            self.paths.append(path)
        self.store = SessionStore(os.path.join(self.tmp, "session.json"), os.path.join(self.tmp, "edits"))


class TestSessionSnapshot(_TempDirTestCase):
    """O estado de trabalho sobrevive a fechar/travar o app."""

    def _state(self):
        state = EditorState(image_list=list(self.paths), current_image_index=1)
        state.borda_pos = (300, 200)
        state.set_image_state(self.paths[0], (310, 190), (250, 350))
        state.set_auto_state(self.paths[1], (300, 200), (225, 350))
        state.individual_bordas[self.paths[2]] = "Red"
        state.animation_type = "Rainbow"
        return state

    def test_framing_is_restored_relative_to_the_border(self):
        data = snapshot_session(self._state(), edited_paths=[])
        restored = EditorState()
        restored.borda_pos = (100, 50)  # janela aberta em outro tamanho
        apply_session(json.loads(json.dumps(data)), restored)
        self.assertEqual(restored.image_states[self.paths[0]], {"pos": (110, 40), "size": (250, 350)})
        self.assertEqual(restored.auto_framed, {self.paths[1]})
        self.assertEqual(restored.image_dirty, {self.paths[0]})
        self.assertEqual(restored.individual_bordas, {self.paths[2]: "Red"})
        self.assertEqual(restored.animation_type, "Rainbow")
        self.assertEqual(restored.current_image_index, 1)

    def test_missing_files_are_skipped_and_reported(self):
        data = snapshot_session(self._state(), edited_paths=[])
        os.remove(self.paths[0])
        restored = EditorState()
        missing = apply_session(data, restored)
        self.assertEqual(missing, [self.paths[0]])
        self.assertEqual(restored.image_list, self.paths[1:])
        self.assertNotIn(self.paths[0], restored.image_states)
        self.assertNotIn(self.paths[0], restored.image_dirty)

    def test_store_round_trip_clear_and_version_check(self):
        data = snapshot_session(self._state(), edited_paths=[self.paths[0]])
        self.store.write_edit(self.paths[0], Image.new("RGBA", (60, 40), "red"))
        self.assertTrue(self.store.save(data))
        self.assertEqual(self.store.load()["images"], self.paths)
        self.assertTrue(os.path.exists(self.store.edit_path(self.paths[0])))

        # sessão de versão desconhecida ou corrompida é ignorada
        with open(self.store.session_file, "w", encoding="utf-8") as f:
            json.dump(dict(data, version=SESSION_VERSION + 1), f)
        self.assertIsNone(self.store.load())
        with open(self.store.session_file, "w", encoding="utf-8") as f:
            f.write("{quebrado")
        self.assertIsNone(self.store.load())

        self.store.clear()
        self.assertFalse(os.path.exists(self.store.session_file))
        self.assertEqual(os.listdir(self.store.edits_dir), [])

    def test_save_prunes_edits_no_longer_referenced(self):
        self.store.write_edit(self.paths[0], Image.new("RGBA", (5, 5)))
        self.store.write_edit(self.paths[1], Image.new("RGBA", (5, 5)))
        data = snapshot_session(self._state(), edited_paths=[self.paths[1]])
        self.store.save(data)
        self.assertEqual(os.listdir(self.store.edits_dir), [os.path.basename(self.store.edit_path(self.paths[1]))])


compat = importlib.import_module("src.qt.compat")


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestSessionInWindow(_TempDirTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = compat.QApplication.instance() or compat.QApplication([])

    def setUp(self):
        super().setUp()
        for patcher in (
            patch("src.core.app_config.CONFIG_FILE", os.path.join(self.tmp, "config.json")),
            patch("src.core.preset_manager.PRESETS_FILE", os.path.join(self.tmp, "presets.json")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _pump(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.02)

    def _window(self, answer):
        from src.core.app_config import AppConfig
        from src.qt.main_window import QtMainWindow
        config = AppConfig()
        config.set("confirm_exit_with_unexported", False)
        with patch.object(compat.QMessageBox, "question", return_value=answer):
            window = QtMainWindow(config, session_store=self.store)
            self._pump(0.3)
        self.addCleanup(dispose_window, self.app, window)
        return window

    def test_closing_saves_and_reopening_restores(self):
        window = self._window(compat.QMessageBox.Yes)
        window.add_images(self.paths, replace=True)
        self._pump(1.0)
        window.toggle_individual_border(2)
        window.close()
        self.assertTrue(os.path.exists(self.store.session_file))

        restored = self._window(compat.QMessageBox.Yes)
        self.assertEqual(restored.editor_state.image_list, self.paths)
        self.assertEqual(restored.editor_state.individual_bordas, {self.paths[2]: restored.editor_state.selected_borda})
        restored.close()

    def test_declining_restore_discards_session(self):
        window = self._window(compat.QMessageBox.Yes)
        window.add_images(self.paths, replace=True)
        self._pump(0.5)
        window.close()
        fresh = self._window(compat.QMessageBox.No)
        self.assertEqual(fresh.editor_state.image_list, [])
        self.assertIsNone(self.store.load())
        fresh.close()

    def test_window_without_store_never_touches_session(self):
        from src.core.app_config import AppConfig
        from src.qt.main_window import QtMainWindow
        window = QtMainWindow(AppConfig())
        self.addCleanup(dispose_window, self.app, window)
        window.add_images(self.paths, replace=True)
        window._autosave_session(force=True)
        self.assertFalse(os.path.exists(self.store.session_file))


if __name__ == "__main__":
    unittest.main()
