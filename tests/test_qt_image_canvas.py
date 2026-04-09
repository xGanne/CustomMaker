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
