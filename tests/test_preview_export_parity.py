"""Paridade canvas × export: o que o canvas mostra dentro da borda é o que sai no arquivo.

Os pixels nunca são idênticos (o canvas reamostra a prévia com o filtro do Qt; o export
redimensiona o original com LANCZOS), então a geometria é comparada com exatidão
(±1 px, pelos limites de quadrantes de cor) e a cor com tolerância, fora das bordas
entre cores, onde os filtros divergem legitimamente.
"""
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
from src.config.settings import BORDA_HEIGHT as H, BORDA_WIDTH as W, BORDER_THICKNESS


compat = importlib.import_module("src.qt.compat")

QUADRANTS = [(200, 40, 40), (40, 180, 60), (40, 70, 200), (220, 200, 40)]


def _target_image(width, height):
    """Quatro quadrantes de cor, divididos fora do centro (45% x 60%): um erro de
    escala ou de posição desloca os limites entre eles."""
    image = Image.new("RGB", (width, height))
    split_x, split_y = int(width * 0.45), int(height * 0.6)
    image.paste(QUADRANTS[0], (0, 0, split_x, split_y))
    image.paste(QUADRANTS[1], (split_x, 0, width, split_y))
    image.paste(QUADRANTS[2], (0, split_y, split_x, height))
    image.paste(QUADRANTS[3], (split_x, split_y, width, height))
    return image


def _wait_until(app, condition, timeout=8.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def capture_canvas(window):
    """A cena só na área da borda, 1:1, sem fundo (o que o canvas mostra como custom)."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    canvas = window.image_canvas
    bx, by = canvas.border_pos
    # sobreposições de ajuda do editor (não fazem parte da custom)
    helpers = [canvas.uncovered_item, *canvas._guide_lines.values()]
    visible = [item for item in helpers if item.isVisible()]
    for item in visible:
        item.setVisible(False)
    image = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    canvas.scene.render(painter, QRectF(0, 0, W, H), QRectF(bx, by, W, H))
    painter.end()
    for item in visible:
        item.setVisible(True)
    rgba = image.convertToFormat(QImage.Format_RGBA8888)
    return Image.frombuffer("RGBA", (W, H), bytes(rgba.constBits()), "raw", "RGBA", rgba.bytesPerLine(), 1).copy()


def capture_export(window, path, tmp):
    from src.core.batch_worker import render_custom_preview
    batch = window.batch_controller.frozen()
    data = batch._get_task_data(path, None, source_dir=tmp)
    return render_custom_preview(data)


def _edge_mask(arr, threshold=40):
    """Pixels perto de uma transição de cor no export (vizinho muito diferente), +1 px."""
    rgb = arr[..., :3]
    diff = np.zeros(arr.shape[:2], dtype=bool)
    diff[:, :-1] |= np.abs(rgb[:, 1:] - rgb[:, :-1]).max(axis=2) > threshold
    diff[:-1, :] |= np.abs(rgb[1:, :] - rgb[:-1, :]).max(axis=2) > threshold
    alpha = arr[..., 3]
    diff[:, :-1] |= np.abs(alpha[:, 1:] - alpha[:, :-1]) > threshold
    diff[:-1, :] |= np.abs(alpha[1:, :] - alpha[:-1, :]) > threshold
    grown = diff.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            grown |= np.roll(np.roll(diff, dy, axis=0), dx, axis=1)
    return grown


def _bbox(arr, color, tolerance=30):
    mask = (np.abs(arr[..., :3] - np.array(color)).max(axis=2) <= tolerance) & (arr[..., 3] > 200)
    if mask.sum() < 30:
        return None
    ys, xs = np.nonzero(mask)
    return xs.min(), ys.min(), xs.max(), ys.max()


def parity_problems(canvas_img, export_img):
    """Lista de diferenças (vazia = paridade). Geometria ±1 px; cor com tolerância."""
    a = np.asarray(canvas_img.convert("RGBA")).astype(int)
    b = np.asarray(export_img.convert("RGBA")).astype(int)
    problems = []
    # transparência: as mesmas regiões vazias
    mismatch = ((a[..., 3] > 127) != (b[..., 3] > 127)) & ~_edge_mask(b)
    if mismatch.mean() > 0.002:
        problems.append(f"transparência difere em {mismatch.mean():.1%} dos pixels")
    # geometria: limites de cada quadrante
    for color in QUADRANTS:
        box_a, box_b = _bbox(a, color), _bbox(b, color)
        if (box_a is None) != (box_b is None):
            problems.append(f"quadrante {color}: visível só em um dos dois ({box_a} × {box_b})")
        elif box_a is not None and max(abs(int(p) - int(q)) for p, q in zip(box_a, box_b)) > 1:
            problems.append(f"quadrante {color}: limites {box_a} no canvas × {box_b} no export")
    # cor fora das transições, onde os dois são opacos
    valid = (a[..., 3] > 200) & (b[..., 3] > 200) & ~_edge_mask(b)
    if valid.any():
        diff = np.abs(a[..., :3] - b[..., :3])[valid]
        if diff.mean() > 3 or np.percentile(diff, 99) > 40:
            problems.append(f"cor: média {diff.mean():.1f}, p99 {np.percentile(diff, 99):.0f}")
    return problems


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestPreviewExportParity(unittest.TestCase):
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
        self.window.resize(1200, 820)
        self.window.show()
        self.canvas = self.window.image_canvas

    def _load(self, image, name="alvo.png"):
        path = os.path.join(self.tmp, name)
        image.save(path, quality=95) if name.endswith(".jpg") else image.save(path)
        self.window.add_images([path], replace=True)
        self._idle()
        return path

    def _idle(self):
        window = self.window

        def idle():
            timer = getattr(window, "_adjust_preview_timer", None)
            return not window.task_runner._tasks and not (timer is not None and timer.isActive())

        self.assertTrue(_wait_until(self.app, idle))
        self.app.processEvents()

    def _assert_parity(self, path, label):
        self._idle()
        problems = parity_problems(capture_canvas(self.window), capture_export(self.window, path, self.tmp))
        self.assertEqual(problems, [], label)

    def _zoom(self, factor):
        self.canvas.zoom_by(factor)
        self.app.processEvents()

    def test_framing_scenarios(self):
        path = self._load(_target_image(800, 1200))
        bx, by = self.canvas.border_pos
        scenarios = [
            ("auto fit", lambda: self.window.apply_auto_fit()),
            ("zoom 37%", lambda: self._zoom(0.37)),
            ("zoom 100% (Ctrl+0)", lambda: self.window.zoom_to_actual_size()),
            ("zoom 250%", lambda: (self.window.apply_auto_fit(), self._zoom(2.5))),
            ("fora da borda (área vazia)", lambda: self.canvas.set_image_state((bx + 40, by + 30), (300, 450))),
            ("borda individual", lambda: (
                self.window.apply_auto_fit(),
                self.window.editor_state.individual_bordas.__setitem__(path, "Red"),
                self.window.refresh_current_canvas(),
            )),
        ]
        for label, action in scenarios:
            with self.subTest(label):
                action()
                self._assert_parity(path, label)

    def test_after_resizing_the_window(self):
        path = self._load(_target_image(800, 1200))
        self.window.apply_auto_fit()
        before = self.canvas.border_pos
        self.window.resize(1000, 700)
        self.assertTrue(_wait_until(self.app, lambda: self.canvas.border_pos != before))
        self._assert_parity(path, "depois de redimensionar")

    def test_landscape_small_and_large_sources(self):
        for label, image, name in (
            ("paisagem", _target_image(1600, 900), "paisagem.png"),
            ("pequena (menor que a borda)", _target_image(150, 200), "pequena.png"),
            ("grande (prévia reduzida, JPEG com draft)", _target_image(2000, 2800), "grande.jpg"),
        ):
            with self.subTest(label):
                path = self._load(image, name)
                self.window.apply_auto_fit()
                self._assert_parity(path, label)

    def test_rotated_image(self):
        path = self._load(_target_image(800, 1200))
        self.window.rotate_current_image("left")
        self._assert_parity(path, "rotacionada")

    def test_border_styles_and_color_adjustments(self):
        path = self._load(_target_image(800, 1200))
        self.window.apply_auto_fit()
        combo = self.window.options_style_combo
        for style in ("dupla", "brilho", "sombra", "degrade"):
            with self.subTest(style):
                combo.setCurrentIndex(combo.findData(style))
                self._assert_parity(path, f"estilo {style}")
        combo.setCurrentIndex(combo.findData("simples"))
        with self.subTest("ajustes de tom"):
            self.window.editor_state.set_image_adjustments(path, {"brightness": 25, "contrast": 30, "saturation": -40})
            self.window._schedule_adjustment_preview()
            self._assert_parity(path, "ajustes de tom")

    def test_border_band_is_drawn_inside_like_the_export(self):
        """A faixa de 5 px da borda é inteira para dentro nas duas (suspeita 9.a do plano)."""
        path = self._load(_target_image(800, 1200))
        self.window.apply_auto_fit()
        self._idle()
        canvas_img = capture_canvas(self.window)
        export_img = capture_export(self.window, path, self.tmp)
        border_rgb = export_img.getpixel((0, 0))[:3]  # a cor que o export usou
        for x, y in ((BORDER_THICKNESS - 1, H // 2), (W - BORDER_THICKNESS, H // 2), (W // 2, BORDER_THICKNESS - 1),
                     (W // 2, H - BORDER_THICKNESS), (0, 0), (W - 1, H - 1)):
            with self.subTest(pixel=(x, y)):
                self.assertEqual(export_img.getpixel((x, y))[:3], border_rgb)
                self.assertEqual(canvas_img.getpixel((x, y))[:3], border_rgb, "borda do canvas não cobre este pixel")
        for x, y in ((BORDER_THICKNESS, H // 2), (W // 2, BORDER_THICKNESS)):
            with self.subTest(inside=(x, y)):
                self.assertNotEqual(canvas_img.getpixel((x, y))[:3], border_rgb, "borda do canvas invade a imagem")

    def test_animation_first_frame(self):
        from src.core.batch_worker import _generate_frames, render_custom_crop
        path = self._load(_target_image(800, 1200))
        self.window.apply_auto_fit()
        self.window.options_anim_combo.setCurrentText("Rainbow")
        self.assertTrue(_wait_until(self.app, lambda: bool(self.window._preview_frames)))
        self.window._preview_timer.stop()
        self.window._preview_index = 0
        self.window._advance_preview_frame()  # primeiro quadro na tela
        self.app.processEvents()
        batch = self.window.batch_controller.frozen()
        crop = render_custom_crop(batch._get_task_data(path, None, source_dir=self.tmp))
        frames, _duration = _generate_frames(crop, "Rainbow", "#FFFFFF")
        self.assertEqual(parity_problems(capture_canvas(self.window), frames[0]), [])


class TestReviewEqualsExportedFile(unittest.TestCase):
    """9.d: a Revisão e o arquivo gravado são o mesmo código — pixel a pixel iguais."""

    def test_review_preview_is_the_exported_png(self):
        from src.core.batch_worker import process_image_task, render_custom_preview
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "s.png")
            _target_image(800, 1200).save(source)
            for style, adjustments in (("simples", {}), ("brilho", {"contrast": 20}), ("dupla", {"sharpness": 40})):
                with self.subTest(style=style):
                    task = {"path": source, "state": {"pos": (-60, -80), "size": (330, 495)}, "borda_pos": (0, 0),
                            "anim_type": "Nenhuma", "border_color": "#3366ff", "border_style": style,
                            "adjustments": adjustments}
                    out = os.path.join(tmp, f"{style}.png")
                    process_image_task(dict(task, output_path=out))
                    with Image.open(out) as exported:
                        self.assertEqual(exported.convert("RGBA").tobytes(), render_custom_preview(task).tobytes())


if __name__ == "__main__":
    unittest.main()
