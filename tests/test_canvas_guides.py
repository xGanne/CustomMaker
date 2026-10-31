import importlib
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image

from _qt_helpers import dispose_window
from src.core.image_processor import uncovered_regions


compat = importlib.import_module("src.qt.compat")
canvas_module = importlib.import_module("src.qt.widgets.image_canvas")

BORDER = (100, 50, 225, 350)


class TestUncoveredRegions(unittest.TestCase):
    def test_fully_covered(self):
        self.assertEqual(uncovered_regions((90, 40, 300, 400), BORDER), [])

    def test_shifted_right_leaves_left_strip(self):
        self.assertEqual(uncovered_regions((110, 40, 300, 400), BORDER), [(100, 50, 10, 350)])

    def test_smaller_image_leaves_four_strips(self):
        regions = uncovered_regions((150, 100, 100, 100), BORDER)
        self.assertEqual(len(regions), 4)
        self.assertEqual(sum(w * h for _x, _y, w, h in regions), 225 * 350 - 100 * 100)

    def test_no_overlap_is_the_whole_border(self):
        self.assertEqual(uncovered_regions((0, 0, 50, 50), BORDER), [BORDER])


class TestSnapOffsets(unittest.TestCase):
    def test_edge_within_threshold_snaps(self):
        dx, dy, centered = canvas_module.snap_offsets((105, 30, 300, 400), BORDER)
        self.assertEqual(dx, -5)
        self.assertFalse(centered)

    def test_far_from_edges_does_not_snap(self):
        self.assertEqual(canvas_module.snap_offsets((120, 20, 300, 400), BORDER)[:2], (0, 0))

    def test_narrow_image_prefers_center(self):
        # 215 px (10 a menos que a borda): esquerda (-4), centro (+1) e direita (+6)
        # estão todas no limiar; com a imagem mais estreita, vale o centro
        dx, _dy, centered = canvas_module.snap_offsets((104, 60, 215, 300), BORDER)
        self.assertTrue(centered)
        self.assertEqual(104 + dx + 215 / 2, 100 + 225 / 2)

    def test_vertical_edges(self):
        _dx, dy, _ = canvas_module.snap_offsets((60, 44, 300, 300), BORDER)
        self.assertEqual(dy, 6)


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestCanvasGuidesAndSnap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = compat.QApplication.instance() or compat.QApplication([])

    def setUp(self):
        self.canvas = canvas_module.ImageCanvas()
        self.canvas.resize(800, 700)
        self.canvas.set_image(Image.new("RGBA", (400, 600), "white"))
        bx, by = self.canvas.border_pos
        self.border = (bx, by)
        self.canvas.set_image_state((bx - 50, by - 50), (400, 600))  # cobre a borda
        self.item = self.canvas.image_item

    def tearDown(self):
        self.canvas.deleteLater()

    def test_drag_snaps_but_code_positions_do_not(self):
        bx, by = self.border
        self.item.dragging = True
        self.item.setPos(bx - 4, by - 100)  # a 4 px de alinhar a esquerda
        self.assertEqual(self.item.pos().x(), bx)
        self.item.dragging = False
        self.item.setPos(bx - 4, by - 100)  # auto fit / undo / sessão: sem encaixe
        self.assertEqual(self.item.pos().x(), bx - 4)

    def test_alt_disables_snap(self):
        bx, by = self.border
        self.item.dragging = True
        with patch.object(compat.QApplication, "keyboardModifiers", return_value=compat.Qt.AltModifier):
            self.item.setPos(bx - 4, by - 100)
        self.assertEqual(self.item.pos().x(), bx - 4)

    def test_guides_follow_drag_and_pin(self):
        lines = self.canvas._guide_lines.values()
        self.assertFalse(any(line.isVisible() for line in lines))
        self.canvas._on_image_drag(True)
        self.assertTrue(all(line.isVisible() for line in lines))
        self.canvas._on_image_drag(False)
        self.assertFalse(any(line.isVisible() for line in lines))
        self.canvas.set_guides_pinned(True)
        self.assertTrue(all(line.isVisible() for line in lines))

    def test_center_highlight_ends_with_the_drag_even_when_pinned(self):
        self.canvas.set_guides_pinned(True)
        bx, by = self.border
        self.canvas._on_image_drag(True)
        self.item.dragging = True
        self.item.setPos(bx + 225 / 2 - 200 + 3, by - 100)  # centro a 3 px: encaixa e destaca
        self.assertEqual(self.canvas._guide_lines["vc"].pen().width(), 2)
        self.item.dragging = False
        self.canvas._on_image_drag(False)
        self.assertEqual(self.canvas._guide_lines["vc"].pen().width(), 1)
        self.assertTrue(self.canvas._guide_lines["vc"].isVisible())  # continua fixa

    def test_uncovered_area_is_hatched_and_reported(self):
        reports = []
        self.canvas.uncovered_changed.connect(reports.append)
        bx, by = self.border
        self.canvas.set_image_state((bx + 20, by - 50), (400, 600))  # deixa 20 px vazios à esquerda
        self.assertTrue(self.canvas.has_uncovered_area)
        self.assertFalse(self.canvas.uncovered_item.path().isEmpty())
        self.canvas.set_image_state((bx - 50, by - 50), (400, 600))
        self.assertFalse(self.canvas.has_uncovered_area)
        self.assertTrue(self.canvas.uncovered_item.path().isEmpty())
        self.assertEqual(reports, [True, False])

    def test_before_after_hides_hatch(self):
        bx, by = self.border
        self.canvas.set_image_state((bx + 20, by - 50), (400, 600))
        self.canvas.show_original_preview()
        self.assertTrue(self.canvas.uncovered_item.path().isEmpty())
        self.canvas.restore_edit_preview()
        self.assertFalse(self.canvas.uncovered_item.path().isEmpty())


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestGuidesKey(unittest.TestCase):
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
        self.window.show()

    def test_g_toggles_and_persists(self):
        self.window.image_canvas.setFocus()
        self.QTest.keyClick(self.window.image_canvas, compat.Qt.Key_G)
        self.assertTrue(self.window.image_canvas.guides_pinned)
        self.assertTrue(self.window.app_config.get("canvas_guides_pinned"))
        from src.core.app_config import AppConfig
        self.assertTrue(AppConfig().get("canvas_guides_pinned"))  # gravado em disco


if __name__ == "__main__":
    unittest.main()
