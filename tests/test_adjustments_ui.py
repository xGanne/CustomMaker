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


def _wait_until(app, condition, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


class TestAdjustmentsPipeline(unittest.TestCase):
    """Os ajustes de cor saem no export, a borda não muda e a sessão os guarda."""

    def test_export_applies_adjustments_before_the_border(self):
        from src.core.batch_worker import process_image_task
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "s.png")
            Image.new("RGB", (400, 600), (100, 100, 100)).save(source)
            task = {"path": source, "state": {"pos": (0, 0), "size": (225, 350)}, "borda_pos": (0, 0),
                    "anim_type": "Nenhuma", "border_color": "#00ff00"}
            plain, bright = os.path.join(tmp, "a.png"), os.path.join(tmp, "b.png")
            process_image_task(dict(task, output_path=plain))
            process_image_task(dict(task, output_path=bright, adjustments={"brightness": 50}))
            with Image.open(plain) as a, Image.open(bright) as b:
                self.assertGreater(b.getpixel((112, 175))[0], a.getpixel((112, 175))[0])
                self.assertEqual(b.getpixel((1, 1))[:3], (0, 255, 0))  # a borda manteve a cor exata

    def test_session_round_trip(self):
        from src.core.editor_state import EditorState
        from src.core.session_store import apply_session, snapshot_session
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.png")
            Image.new("RGB", (10, 10)).save(path)
            state = EditorState(image_list=[path])
            state.set_image_adjustments(path, {"contrast": 30, "saturation": -20})
            restored = EditorState()
            apply_session(snapshot_session(state, []), restored)
            self.assertEqual(restored.image_adjustments, {path: {"contrast": 30, "saturation": -20}})


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestAdjustmentsInWindow(unittest.TestCase):
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
            path = os.path.join(self.tmp, f"a{i}.png")
            Image.new("RGB", (300, 400), (100, 110, 120)).save(path)
            self.paths.append(path)
        self.window.add_images(self.paths, replace=True)
        self.assertTrue(_wait_until(self.app, lambda: not self.window.task_runner._tasks))
        self.tab = self.window.editor_tab

    def _settle(self):
        """Prévia em dia: sem tarefa, sem refazer pendente e sem debounce armado."""
        window = self.window

        def idle():
            timer = getattr(window, "_adjust_preview_timer", None)
            return (
                not window.task_runner._tasks
                and not getattr(window, "_adjust_preview_pending", False)
                and not (timer is not None and timer.isActive())
            )

        self.assertTrue(_wait_until(self.app, idle))
        self.app.processEvents()

    def _center_pixel(self):
        base = self.window.image_canvas._base_image
        return base.getpixel((base.width // 2, base.height // 2))

    def test_slider_changes_state_and_live_preview(self):
        before = self._center_pixel()
        self.tab.adjust_sliders["brightness"].setValue(60)
        self._settle()
        path = self.window.current_path
        canvas = self.window.image_canvas
        context = (f"base={canvas._base_image.size} original={canvas._original_image.size} "
                   f"pending={getattr(self.window, '_adjust_preview_pending', None)} tasks={list(self.window.task_runner._tasks)}")
        self.assertEqual(self.window.editor_state.image_adjustments.get(path), {"brightness": 60}, context)
        self.assertEqual(self.tab.adjust_spins["brightness"].value(), 60, context)
        self.assertGreater(self._center_pixel()[0], before[0], context)
        self.assertIn(path, self.window.editor_state.image_dirty)
        # o original guardado para o antes/depois (B) continua sem ajuste
        original = self.window.image_canvas._original_image
        self.assertEqual(original.getpixel((original.width // 2, original.height // 2))[:3], before[:3])

    def test_sharpness_is_not_previewed_live(self):
        before = self._center_pixel()
        self.tab.adjust_sliders["sharpness"].setValue(80)
        self._settle()
        self.assertEqual(self._center_pixel(), before)
        self.assertEqual(self.window.editor_state.image_adjustments[self.window.current_path], {"sharpness": 80})

    def test_undo_restores_controls_and_preview(self):
        before = self._center_pixel()
        self.tab.adjust_sliders["contrast"].setValue(-40)
        self._settle()
        self.window.undo_current_image()
        self._settle()
        self.assertEqual(self.window.editor_state.image_adjustments.get(self.window.current_path), None)
        self.assertEqual(self.tab.adjust_sliders["contrast"].value(), 0)
        self.assertEqual(self._center_pixel(), before)

    def test_navigation_shows_each_image_adjustments(self):
        self.tab.adjust_sliders["saturation"].setValue(-50)
        self._settle()
        self.window.navigate_images(1)
        self.assertTrue(_wait_until(self.app, lambda: self.window.current_path == self.paths[1]))
        self._settle()
        self.assertEqual(self.tab.adjust_sliders["saturation"].value(), 0)
        self.window.navigate_images(-1)
        self.assertTrue(_wait_until(self.app, lambda: self.window.current_path == self.paths[0]))
        self._settle()
        self.assertEqual(self.tab.adjust_sliders["saturation"].value(), -50)

    def test_reset_and_apply_to_all(self):
        self.tab.adjust_spins["brightness"].setValue(25)
        self._settle()
        self.window.apply_adjustments_to_all()
        self.assertEqual(self.window.editor_state.image_adjustments.get(self.paths[1]), {"brightness": 25})
        self.window.reset_current_adjustments()
        self.assertNotIn(self.window.current_path, self.window.editor_state.image_adjustments)
        self.assertEqual(self.tab.adjust_sliders["brightness"].value(), 0)

    def test_wheel_over_unfocused_control_scrolls_instead_of_changing(self):
        from PySide6.QtCore import QPoint, QPointF
        from PySide6.QtGui import QWheelEvent
        slider = self.tab.adjust_sliders["brightness"]
        spin = self.tab.adjust_spins["brightness"]
        for widget in (slider, spin):
            widget.clearFocus()
            event = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120),
                                compat.Qt.NoButton, compat.Qt.NoModifier, compat.Qt.NoScrollPhase, False)
            compat.QApplication.sendEvent(widget, event)
            self.assertEqual(widget.value(), 0)
        self.assertEqual(self.window.editor_state.image_adjustments, {})

    def test_undo_on_another_image_does_not_silently_drop_apply_to_all(self):
        es = self.window.editor_state
        # a imagem 2 tem um passo próprio antigo ("Mover")
        self.window.navigate_images(1)
        self.assertTrue(_wait_until(self.app, lambda: self.window.current_path == self.paths[1]))
        self._settle()
        item = self.window.image_canvas.image_item
        self.window.image_canvas.interaction_started.emit("Mover")
        item.setPos(item.pos().x() + 15, item.pos().y())
        self.app.processEvents()
        moved = tuple(es.image_states[self.paths[1]]["pos"])
        # volta para a 1, ajusta e aplica a todas
        self.window.navigate_images(-1)
        self.assertTrue(_wait_until(self.app, lambda: self.window.current_path == self.paths[0]))
        self._settle()
        self.tab.adjust_spins["brightness"].setValue(30)
        self._settle()
        self.window.apply_adjustments_to_all()
        self.assertEqual(es.image_adjustments.get(self.paths[1]), {"brightness": 30})
        # na 2, desfazer volta o "aplicar a todas" — e só ele
        self.window.navigate_images(1)
        self.assertTrue(_wait_until(self.app, lambda: self.window.current_path == self.paths[1]))
        self._settle()
        self.window.undo_current_image()
        self.assertEqual(es.image_adjustments.get(self.paths[1]), None)
        self.assertEqual(tuple(es.image_states[self.paths[1]]["pos"]), moved)

    def test_copy_framing_to_all_is_undoable_on_each_image(self):
        es = self.window.editor_state
        before = tuple(es.image_states[self.paths[1]]["pos"])
        item = self.window.image_canvas.image_item
        item.setPos(item.pos().x() + 25, item.pos().y())
        self.app.processEvents()
        self.window.copy_framing_to_all()
        self.assertNotEqual(tuple(es.image_states[self.paths[1]]["pos"]), before)
        self.window.navigate_images(1)
        self.assertTrue(_wait_until(self.app, lambda: self.window.current_path == self.paths[1]))
        self._settle()
        self.window.undo_current_image()
        self.assertEqual(tuple(es.image_states[self.paths[1]]["pos"]), before)

    def test_live_preview_runs_one_task_at_a_time_and_ends_on_the_latest_value(self):
        peak = []
        original_submit = self.window.task_runner.submit

        def counting_submit(task_id, fn):
            handle = original_submit(task_id, fn)
            peak.append(sum(1 for t in self.window.task_runner._tasks if t.startswith("qt_adjust_preview")))
            return handle

        self.window.task_runner.submit = counting_submit
        for value in range(5, 80, 5):  # arrasto rápido
            self.tab.adjust_spins["contrast"].setValue(value)
            self.window._render_adjustment_preview()
        self._settle()
        self.assertTrue(peak and max(peak) == 1, peak)
        from src.core.color_adjustments import apply_tone
        expected = apply_tone(self.window.image_canvas._original_image, {"contrast": 75})
        self.assertEqual(self.window.image_canvas._base_image.tobytes(), expected.convert("RGBA").tobytes())

    def test_preset_with_adjustments(self):
        self.tab.adjust_spins["contrast"].setValue(35)
        self._settle()
        self.tab.preset_include_adjustments.setChecked(True)
        self.tab.preset_name_edit.setText("Contraste")
        self.tab._save_preset()
        self.window.reset_current_adjustments()
        self.window.apply_preset(self.window.preset_manager.get_preset("Contraste"))
        self.assertEqual(self.window.editor_state.image_adjustments[self.window.current_path], {"contrast": 35})
        self.assertEqual(self.tab.adjust_sliders["contrast"].value(), 35)


if __name__ == "__main__":
    unittest.main()
