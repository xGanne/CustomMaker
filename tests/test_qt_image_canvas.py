import importlib
import threading
import unittest

from PIL import Image


image_canvas_module = importlib.import_module("src.qt.widgets.image_canvas")


@unittest.skipUnless(getattr(image_canvas_module, "QT_AVAILABLE", False), "PySide6 not installed")
class TestQtImageCanvas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compat = importlib.import_module("src.qt.compat")
        cls.app = compat.QApplication.instance() or compat.QApplication([])

    def test_dragged_position_emits_state_changed(self):
        canvas = image_canvas_module.ImageCanvas()
        captured = []
        state_event = threading.Event()

        def on_state(pos, size):
            captured.append((pos, size))
            state_event.set()

        canvas.state_changed.connect(on_state)
        canvas.resize(800, 700)
        canvas.show()
        self.app.processEvents()

        image = Image.new("RGBA", (400, 600), "white")
        canvas.set_image(image, state={"pos": (100, 120), "size": (400, 600)})
        self.app.processEvents()

        captured.clear()
        state_event.clear()

        canvas.image_item.setPos(145, 205)
        self.app.processEvents()

        self.assertTrue(state_event.is_set())
        self.assertEqual(captured[-1][0], (145, 205))
        self.assertEqual(captured[-1][1], (400, 600))

    # ── M8: zoom ────────────────────────────────────────────────────────

    def _canvas_with_image(self, size=(400, 600), state_size=(400, 600)):
        canvas = image_canvas_module.ImageCanvas()
        canvas.resize(800, 700)
        canvas.show()
        self.app.processEvents()
        canvas.set_image(Image.new("RGBA", size, "white"), state={"pos": (100, 100), "size": state_size})
        self.app.processEvents()
        return canvas

    def test_zoom_label_shows_current_zoom(self):
        canvas = self._canvas_with_image(state_size=(200, 300))
        self.assertTrue(canvas._zoom_label.isVisible())
        self.assertEqual(canvas._zoom_label.text(), "50%")
        canvas.clear_image()
        self.assertFalse(canvas._zoom_label.isVisible())

    def test_zoom_to_actual_size_keeps_center_and_pushes_undo(self):
        canvas = self._canvas_with_image(state_size=(200, 300))
        snapshots = []
        canvas.interaction_started.connect(lambda: snapshots.append(True))
        canvas.zoom_to_actual_size()
        self.assertEqual(canvas._current_size, (400, 600))
        self.assertEqual((canvas.image_item.pos().x(), canvas.image_item.pos().y()), (0, -50))
        self.assertEqual(canvas._zoom_label.text(), "100%")
        self.assertEqual(len(snapshots), 1)
        # já em 100%: não gera snapshot de undo inútil
        canvas.zoom_to_actual_size()
        self.assertEqual(len(snapshots), 1)

    def test_zoom_by_keeps_anchor_point_fixed(self):
        canvas = self._canvas_with_image()
        anchor = (300, 400)  # centro da imagem em (100,100)+(400,600)/2
        canvas.zoom_by(image_canvas_module.ZOOM_STEP_FAST, anchor=anchor)
        width, height = canvas._current_size
        center = (canvas.image_item.pos().x() + width / 2, canvas.image_item.pos().y() + height / 2)
        self.assertEqual((width, height), (480, 720))
        self.assertAlmostEqual(center[0], anchor[0], delta=1)
        self.assertAlmostEqual(center[1], anchor[1], delta=1)


class TestScaledPlacement(unittest.TestCase):
    def test_anchor_at_top_left_keeps_position(self):
        pos, size = image_canvas_module.scaled_placement((10, 20), (100, 200), 2.0, (10, 20))
        self.assertEqual(pos, (10, 20))
        self.assertEqual(size, (200, 400))

    def test_anchor_at_center_grows_symmetrically(self):
        pos, size = image_canvas_module.scaled_placement((0, 0), (100, 100), 1.2, (50, 50))
        self.assertEqual(size, (120, 120))
        self.assertEqual(pos, (-10, -10))


@unittest.skipUnless(getattr(image_canvas_module, "QT_AVAILABLE", False), "PySide6 not installed")
class TestQtImageCanvasNaturalSize(unittest.TestCase):
    """M8: o zoom é relativo ao original, mesmo quando a preview foi redimensionada."""

    @classmethod
    def setUpClass(cls):
        compat = importlib.import_module("src.qt.compat")
        cls.app = compat.QApplication.instance() or compat.QApplication([])

    def test_zoom_uses_natural_size_instead_of_preview_size(self):
        canvas = image_canvas_module.ImageCanvas()
        preview = Image.new("RGBA", (1000, 1400), "white")  # preview ampliada de um 500x700
        canvas.set_image(preview, state={"pos": (0, 0), "size": (250, 350)}, natural_size=(500, 700))
        self.assertAlmostEqual(canvas.zoom_factor, 0.5)
        canvas.zoom_to_actual_size()
        self.assertEqual(canvas._current_size, (500, 700))
        self.assertAlmostEqual(canvas.zoom_factor, 1.0)


@unittest.skipUnless(getattr(image_canvas_module, "QT_AVAILABLE", False), "PySide6 not installed")
class TestQtImageCanvasLoading(unittest.TestCase):
    """M4: indicador de carregamento no canvas."""

    @classmethod
    def setUpClass(cls):
        compat = importlib.import_module("src.qt.compat")
        cls.compat = compat
        cls.app = compat.QApplication.instance() or compat.QApplication([])

    def _wait(self, ms):
        loop_timer = self.compat.QTimer()
        loop_timer.setSingleShot(True)
        done = []
        loop_timer.timeout.connect(lambda: done.append(True))
        loop_timer.start(ms)
        while not done:
            self.app.processEvents()

    def test_loading_hides_empty_hint_and_shows_label_after_delay(self):
        canvas = image_canvas_module.ImageCanvas()
        canvas.resize(800, 700)
        canvas.show()
        canvas.set_loading(True)
        canvas.clear_image()
        self.assertFalse(canvas.empty_hint_item.isVisible())
        # carregamentos rápidos não piscam o indicador
        self.assertFalse(canvas._loading_label.isVisible())
        self._wait(canvas.LOADING_SHOW_DELAY_MS + 100)
        self.assertTrue(canvas._loading_label.isVisible())
        self.assertTrue(canvas._loading_label.text().startswith("Carregando"))

        canvas.set_loading(False)
        self.assertFalse(canvas._loading_label.isVisible())
        self.assertTrue(canvas.empty_hint_item.isVisible())

    def test_fast_load_never_shows_label(self):
        canvas = image_canvas_module.ImageCanvas()
        canvas.set_loading(True)
        canvas.set_image(Image.new("RGBA", (100, 100), "white"))
        canvas.set_loading(False)
        self._wait(canvas.LOADING_SHOW_DELAY_MS + 100)
        self.assertFalse(canvas._loading_label.isVisible())
        self.assertFalse(canvas.empty_hint_item.isVisible())
