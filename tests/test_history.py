import importlib
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image

from _qt_helpers import dispose_window
from src.core.history import Snapshot


compat = importlib.import_module("src.qt.compat")


def _wait_until(app, condition, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


class TestSnapshot(unittest.TestCase):
    def test_shifted_moves_only_the_position(self):
        snapshot = Snapshot(None, (10, 20), (100, 200), False, label="Mover", timestamp=5.0)
        moved = snapshot.shifted(3, -4)
        self.assertEqual(moved.pos, (13, 16))
        self.assertEqual((moved.size, moved.pixel_edited, moved.label, moved.timestamp), ((100, 200), False, "Mover", 5.0))
        self.assertEqual(snapshot.pos, (10, 20))


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestNamedHistory(unittest.TestCase):
    """Cada passo do undo tem o nome da ação; desfazer/refazer preservam o nome."""

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
        self.window.resize(1200, 800)
        self.window.show()
        path = os.path.join(self.tmp, "img.png")
        Image.new("RGBA", (300, 400), (60, 80, 120, 255)).save(path)
        self.window.add_images([path], replace=True)
        self.assertTrue(_wait_until(self.app, lambda: self.window._active_image_load_task_id is None))
        self.statuses = []
        self.window.show_status = lambda message, **_kw: self.statuses.append(message)

    def _drag(self, dx):
        item = self.window.image_canvas.image_item
        self.window.image_canvas.interaction_started.emit("Mover")
        item.setPos(item.pos().x() + dx, item.pos().y())
        self.app.processEvents()

    def _stack(self, name):
        stacks = self.window._undo_stacks if name == "undo" else self.window._redo_stacks
        return [s.label for s in stacks.get(self.window.current_path, [])]

    def test_undo_and_redo_keep_the_step_name(self):
        self._drag(10)
        self.window.apply_auto_fit()
        self.assertEqual(self._stack("undo"), ["Mover", "Auto fit"])

        self.window.undo_current_image()
        self.assertEqual(self.statuses[-1], "Desfeito: Auto fit")
        self.assertEqual(self._stack("redo"), ["Auto fit"])

        self.window.redo_current_image()
        self.assertEqual(self.statuses[-1], "Refeito: Auto fit")
        self.assertEqual(self._stack("undo"), ["Mover", "Auto fit"])

    def test_rotation_is_named(self):
        self.window.rotate_current_image("left")
        self.assertEqual(self._stack("undo"), ["Rotacionar à esquerda"])

    # ── Ctrl+Alt+Z, salto e menu ───────────────────────────────────────

    def _pos(self):
        return tuple(self.window.editor_state.image_states[self.window.current_path]["pos"])

    def _three_moves(self):
        positions = [self._pos()]
        for dx in (10, 20, 30):
            self._drag(dx)
            positions.append(self._pos())
        return positions

    def test_toggle_alternates_between_current_and_previous(self):
        positions = self._three_moves()
        self.window.toggle_last_state()
        self.assertEqual(self._pos(), positions[2])
        self.window.toggle_last_state()
        self.assertEqual(self._pos(), positions[3])
        self.window.toggle_last_state()
        self.assertEqual(self._pos(), positions[2])
        # depois de um desfazer manual, o toggle refaz
        self.window.undo_current_image()
        self.window.toggle_last_state()
        self.assertEqual(self._pos(), positions[2])

    def test_toggle_without_history_says_so(self):
        self.window.toggle_last_state()
        self.assertEqual(self.statuses[-1], "Nada para comparar.")

    def test_jump_equals_repeated_undos_but_applies_once(self):
        positions = self._three_moves()
        applied = []
        original = self.window._apply_snapshot
        self.window._apply_snapshot = lambda s: (applied.append(s.pos), original(s))
        self.window.jump_history(-3)
        self.assertEqual(self._pos(), positions[0])
        self.assertEqual(len(applied), 1)
        self.assertEqual(self._stack("undo"), [])
        self.assertEqual(self._stack("redo"), ["Mover", "Mover", "Mover"])
        self.window.jump_history(2)
        self.assertEqual(self._pos(), positions[2])
        self.assertEqual(len(self._stack("undo")), 2)
        self.assertEqual(len(self._stack("redo")), 1)

    def test_menu_lists_steps_and_jumps(self):
        self._drag(10)
        self.window.apply_auto_fit()
        self.window.undo_current_image()  # "Auto fit" fica refazível
        menu = compat.QMenu()
        self.addCleanup(menu.deleteLater)
        self.window._populate_history_menu(menu)
        texts = [a.text() for a in menu.actions() if not a.isSeparator()]
        self.assertEqual(texts[0], "↷ Auto fit")
        self.assertEqual(texts[1], "● Mover")
        self.assertEqual(texts[2], "Início (como abriu)")
        self.assertEqual(texts[-1], "Limpar histórico desta imagem")
        menu.actions()[0].trigger()  # avança até "Auto fit"
        self.assertEqual(self._stack("undo"), ["Mover", "Auto fit"])

    def test_clear_history_releases_snapshots(self):
        self.window.rotate_current_image("left")
        self.window.rotate_current_image("left")  # este passo guarda a cópia da 1ª rotação
        snapshot = self.window._undo_stacks[self.window.current_path][-1]
        closed = []
        snapshot.image.close = lambda: closed.append(True)
        self.window.clear_history()
        self.assertEqual(self._stack("undo"), [])
        self.assertEqual(closed, [True])


if __name__ == "__main__":
    unittest.main()
