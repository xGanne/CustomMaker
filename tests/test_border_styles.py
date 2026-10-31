import unittest

from PIL import Image

from src.config.settings import BORDA_HEIGHT, BORDA_WIDTH
from src.core.border_styles import BORDER_STYLES, apply_border, border_overlay, normalize_style
from src.core.image_processor import ImageProcessor


def _crop():
    image = Image.new("RGBA", (BORDA_WIDTH, BORDA_HEIGHT), (40, 120, 200, 255))
    image.paste((230, 210, 60, 255), (60, 100, 160, 250))
    return image


class TestBorderStyles(unittest.TestCase):
    def test_simple_is_byte_identical_to_the_old_border(self):
        crop = _crop()
        self.assertEqual(
            apply_border(crop, "simples", "#ff3366").tobytes(),
            ImageProcessor.add_borda_to_image(crop, "#ff3366").tobytes(),
        )

    def test_every_style_returns_a_custom_sized_rgba(self):
        for style in BORDER_STYLES:
            with self.subTest(style=style):
                result = apply_border(_crop(), style, "#33aa77")
                self.assertEqual((result.size, result.mode), ((BORDA_WIDTH, BORDA_HEIGHT), "RGBA"))

    def test_center_untouched_by_simple_and_double(self):
        crop = _crop()
        center = crop.getpixel((BORDA_WIDTH // 2, BORDA_HEIGHT // 2))
        for style in ("simples", "dupla"):
            with self.subTest(style=style):
                self.assertEqual(apply_border(crop, style, "#ffffff").getpixel((BORDA_WIDTH // 2, BORDA_HEIGHT // 2)), center)

    def test_double_shows_the_image_in_the_gap(self):
        crop = _crop()
        result = apply_border(crop, "dupla", "#ffffff")
        self.assertEqual(result.getpixel((1, 150))[:3], (255, 255, 255))  # linha externa
        self.assertEqual(result.getpixel((3, 150)), crop.getpixel((3, 150)))  # vão
        self.assertEqual(result.getpixel((5, 150))[:3], (255, 255, 255))  # linha interna

    def test_glow_and_shadow_reach_inside_the_border(self):
        crop = _crop()
        inside = (12, 150)  # logo dentro da faixa de 5 px
        glow = apply_border(crop, "brilho", "#ff0000").getpixel(inside)
        shadow = apply_border(crop, "sombra", "#ff0000").getpixel(inside)
        original = crop.getpixel(inside)
        self.assertGreater(glow[0], original[0])  # mais vermelho
        self.assertLess(sum(shadow[:3]), sum(original[:3]))  # mais escuro

    def test_gradient_goes_from_the_color_to_a_lighter_one(self):
        result = apply_border(_crop(), "degrade", "#204080")
        top, bottom = result.getpixel((2, 0)), result.getpixel((2, BORDA_HEIGHT - 1))
        self.assertEqual(top[:3], (0x20, 0x40, 0x80))
        self.assertGreater(sum(bottom[:3]), sum(top[:3]))
        # branco não "clareia" mais: escurece
        white = apply_border(_crop(), "degrade", "#ffffff")
        self.assertLess(sum(white.getpixel((2, BORDA_HEIGHT - 1))[:3]), 3 * 255)

    def test_unknown_style_falls_back_to_simple(self):
        self.assertEqual(normalize_style("neon-3000"), "simples")
        crop = _crop()
        self.assertEqual(apply_border(crop, "neon-3000", "#ff0000").tobytes(), apply_border(crop, "simples", "#ff0000").tobytes())

    def test_overlay_is_cached_but_returned_as_a_new_image(self):
        a = border_overlay("brilho", "#123456")
        b = border_overlay("brilho", "#123456")
        self.assertIsNot(a, b)
        self.assertEqual(a.tobytes(), b.tobytes())
        a.putpixel((0, 0), (1, 2, 3, 4))
        self.assertNotEqual(a.tobytes(), border_overlay("brilho", "#123456").tobytes())


class TestBorderStylePipeline(unittest.TestCase):
    """O estilo passa pelo export, pela sessão e pelos presets."""

    def test_export_uses_the_style_and_ignores_it_on_animations(self):
        import os
        import tempfile
        from src.core.batch_worker import process_image_task, render_custom_preview
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "s.png")
            Image.new("RGBA", (400, 600), (40, 120, 200, 255)).save(source)
            task = {"path": source, "state": {"pos": (0, 0), "size": (225, 350)}, "borda_pos": (0, 0),
                    "anim_type": "Nenhuma", "border_color": "#ff0000", "border_style": "sombra"}
            out = os.path.join(tmp, "o.png")
            self.assertEqual(process_image_task(dict(task, output_path=out))["status"], "success")
            preview = render_custom_preview(task)
            with Image.open(out) as exported:
                self.assertEqual(exported.convert("RGBA").tobytes(), preview.tobytes())
            with Image.open(source) as src:
                crop = src.convert("RGBA").crop((0, 0, 225, 350))
            self.assertEqual(preview.tobytes(), apply_border(crop, "sombra", "#ff0000").tobytes())

    def test_session_round_trip_and_old_sessions(self):
        import os
        import tempfile
        from src.core.editor_state import EditorState
        from src.core.session_store import apply_session, snapshot_session
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.png")
            Image.new("RGB", (10, 10)).save(path)
            state = EditorState(image_list=[path], border_style="degrade")
            data = snapshot_session(state, [])
            restored = EditorState()
            apply_session(data, restored)
            self.assertEqual(restored.border_style, "degrade")
            data.pop("border_style")  # sessão de antes dos estilos
            old = EditorState()
            apply_session(data, old)
            self.assertEqual(old.border_style, "simples")

    def test_measure_cache_key_includes_the_style(self):
        from src.controllers.batch_controller import BatchController
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "s.png")
            Image.new("RGB", (10, 10)).save(source)
            task = {"path": source, "state": {"pos": (0, 0), "size": (225, 350)}, "borda_pos": (0, 0),
                    "anim_type": "Nenhuma", "border_color": "#ff0000", "border_style": "simples"}
            self.assertNotEqual(
                BatchController._size_cache_key(task), BatchController._size_cache_key(dict(task, border_style="brilho"))
            )


def _qt_available():
    import importlib
    return importlib.import_module("src.qt.compat").QT_AVAILABLE


@unittest.skipUnless(_qt_available(), "PySide6 not installed")
class TestBorderStyleInWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.qt.compat import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        import os
        import shutil
        import tempfile
        from unittest.mock import patch
        from _qt_helpers import dispose_window
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
        path = os.path.join(self.tmp, "a.png")
        Image.new("RGB", (300, 400), (40, 120, 200)).save(path)
        self.window.add_images([path], replace=True)
        import time
        end = time.monotonic() + 5
        while self.window.task_runner._tasks and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)

    def _choose(self, style):
        combo = self.window.options_style_combo
        combo.setCurrentIndex(combo.findData(style))

    def test_canvas_preview_is_the_export_overlay(self):
        self._choose("brilho")
        canvas = self.window.image_canvas
        self.assertEqual(self.window.editor_state.border_style, "brilho")
        self.assertTrue(canvas.style_overlay_item.isVisible())
        self.assertFalse(canvas.border_item.isVisible())
        # mesma imagem de origem que o export: comparar pelo mesmo caminho de
        # conversão (o QPixmap guarda alfa pré-multiplicado e arredonda ao ler)
        from src.qt.pixmap_utils import pil_to_qpixmap
        expected = pil_to_qpixmap(border_overlay("brilho", canvas._border_color)).toImage()
        self.assertEqual(canvas.style_overlay_item.pixmap().toImage(), expected)
        self.assertIn(self.window.current_path, self.window.editor_state.image_dirty)

    def test_animation_disables_the_style(self):
        self._choose("dupla")
        self.window.options_anim_combo.setCurrentText("Rainbow")
        self.assertFalse(self.window.options_style_combo.isEnabled())
        self.assertEqual(self.window.image_canvas.border_style, "simples")
        self.window.options_anim_combo.setCurrentText("Nenhuma")
        self.assertTrue(self.window.options_style_combo.isEnabled())
        self.assertEqual(self.window.image_canvas.border_style, "dupla")

    def test_preset_saves_and_applies_the_style(self):
        self._choose("sombra")
        tab = self.window.editor_tab
        tab.preset_name_edit.setText("Meu")
        tab._save_preset()
        self._choose("simples")
        self.window.apply_preset(self.window.preset_manager.get_preset("Meu"))
        self.assertEqual(self.window.editor_state.border_style, "sombra")
        self.assertEqual(self.window.options_style_combo.currentData(), "sombra")


if __name__ == "__main__":
    unittest.main()
