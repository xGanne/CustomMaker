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


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestColorPicker(unittest.TestCase):
    """Pick Color: lupa, Shift (só esta imagem), Ctrl (média 3x3) e Esc."""

    @classmethod
    def setUpClass(cls):
        cls.app = compat.QApplication.instance() or compat.QApplication([])
        from PySide6.QtTest import QTest
        cls.QTest = QTest

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
        # metade esquerda vermelha; à direita, tabuleiro preto/branco de 1 px
        image = Image.new("RGB", (300, 400), (220, 30, 40))
        for x in range(150, 300):
            for y in range(400):
                image.putpixel((x, y), (0, 0, 0) if (x + y) % 2 else (255, 255, 255))
        path = os.path.join(self.tmp, "pick.png")
        image.save(path)
        self.window.add_images([path], replace=True)
        self.assertTrue(_wait_until(self.app, lambda: not self.window.task_runner._tasks))
        self.canvas = self.window.image_canvas
        # 1:1 dentro da borda, para cada pixel da cena ser um pixel da imagem
        bx, by = self.canvas.border_pos
        self.canvas.set_image_state((bx - 40, by), (300, 400))
        self.app.processEvents()
        self.window.toggle_color_picker()

    def _view_point(self, fx, fy):
        """Ponto do viewport numa fração (fx, fy) da prévia (que pode ser ampliada)."""
        base = self.canvas._base_image
        scene = self.canvas.image_item.mapToScene(compat.QPointF(fx * base.width, fy * base.height))
        return self.canvas.mapFromScene(scene)

    def _click(self, fx, fy, modifiers=None):
        modifiers = modifiers if modifiers is not None else compat.Qt.NoModifier
        self.QTest.mouseClick(self.canvas.viewport(), compat.Qt.LeftButton, modifiers, self._view_point(fx, fy))
        self.app.processEvents()

    def test_click_sets_global_custom_color(self):
        self._click(0.2, 0.2)
        es = self.window.editor_state
        self.assertEqual((es.selected_borda, es.custom_borda_hex), ("Cor Personalizada", "#dc1e28"))
        self.assertFalse(self.window._color_picker_enabled)

    def test_shift_click_sets_only_this_image(self):
        es = self.window.editor_state
        before = (es.selected_borda, es.custom_borda_hex)
        self._click(0.2, 0.2, compat.Qt.ShiftModifier)
        path = self.window.current_path
        self.assertEqual(es.individual_bordas[path], "Cor Personalizada")
        self.assertEqual(es.custom_borda_hex_individual[path], "#dc1e28")
        self.assertEqual((es.selected_borda, es.custom_borda_hex), before)
        self.assertIn(path, es.image_dirty)

    def test_ctrl_click_averages_3x3(self):
        self._click(0.2, 0.2, compat.Qt.ControlModifier)  # área uniforme: a média é a própria cor
        self.assertEqual(self.window.editor_state.custom_borda_hex, "#dc1e28")
        # média 3x3 num tabuleiro preto/branco de 1 px (sem a ampliação da prévia)
        checker = Image.new("RGBA", (9, 9))
        checker.putdata([(0, 0, 0, 255) if (x + y) % 2 else (255, 255, 255, 255) for y in range(9) for x in range(9)])
        self.canvas._base_image = checker
        self.assertIn(self.canvas._picked_color(4, 4), ("#000000", "#ffffff"))
        average = int(self.canvas._picked_color(4, 4, average=True)[1:3], 16)
        self.assertTrue(100 <= average <= 155, average)  # cinza

    def test_loupe_follows_cursor_and_hides_when_leaving_mode(self):
        point = self._view_point(0.25, 0.5)
        self.QTest.mouseMove(self.canvas.viewport(), point)
        self.app.processEvents()
        self.assertTrue(self.canvas._loupe is not None and self.canvas._loupe.isVisible())
        base = self.canvas._base_image
        x, y = self.canvas._image_pixel_at(point)
        self.assertLessEqual(abs(x - base.width * 0.25), 1)
        self.assertLessEqual(abs(y - base.height * 0.5), 1)
        self.window.cancel_color_picker()
        self.assertFalse(self.canvas._loupe.isVisible())

    def test_escape_leaves_pick_mode(self):
        self.canvas.setFocus()
        self.QTest.keyClick(self.canvas, compat.Qt.Key_Escape)
        self.assertFalse(self.window._color_picker_enabled)
        self._click(0.2, 0.2)  # fora do modo, o clique não escolhe cor
        self.assertNotEqual(self.window.editor_state.custom_borda_hex, "#dc1e28")


if __name__ == "__main__":
    unittest.main()
