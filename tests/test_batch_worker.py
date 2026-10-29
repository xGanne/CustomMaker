import tempfile
import unittest

from PIL import Image

from src.config.settings import BORDA_HEIGHT, BORDA_WIDTH
from src.core.batch_worker import process_image_task


class TestBatchWorker(unittest.TestCase):
    def test_process_image_task_static_saves_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = f"{tmp}/source.png"
            output = f"{tmp}/output.png"
            Image.new("RGBA", (512, 512), "blue").save(source)

            result = process_image_task(
                {
                    "path": source,
                    "state": {"pos": (0, 0), "size": (BORDA_WIDTH, BORDA_HEIGHT)},
                    "borda_pos": (0, 0),
                    "anim_type": "Nenhuma",
                    "border_color": "#FFFFFF",
                    "output_path": output,
                }
            )

            self.assertEqual(result["status"], "success")
            self.assertTrue(result["saved_to"].endswith("output.png"))
            with Image.open(output) as img:
                self.assertEqual(img.size, (BORDA_WIDTH, BORDA_HEIGHT))

    def test_process_image_task_returns_error_for_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = f"{tmp}/missing.png"
            result = process_image_task(
                {
                    "path": missing,
                    "state": {"pos": (0, 0), "size": (BORDA_WIDTH, BORDA_HEIGHT)},
                    "borda_pos": (0, 0),
                    "anim_type": "Nenhuma",
                    "border_color": "#FFFFFF",
                }
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["path"], missing)

    def test_process_image_task_animated_saves_gif(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = f"{tmp}/source.png"
            output = f"{tmp}/output.gif"
            Image.new("RGBA", (512, 512), "blue").save(source)

            result = process_image_task(
                {
                    "path": source,
                    "state": {"pos": (0, 0), "size": (BORDA_WIDTH, BORDA_HEIGHT)},
                    "borda_pos": (0, 0),
                    "anim_type": "Rainbow",
                    "border_color": "#FFFFFF",
                    "output_path": output,
                }
            )

            self.assertEqual(result["status"], "success")
            self.assertTrue(result["saved_to"].endswith("output.gif"))
            with Image.open(output) as img:
                self.assertEqual(img.format, "GIF")


class TestEncodeCustom(unittest.TestCase):
    """encode_custom gera exatamente os bytes que a exportação grava."""

    def _task(self, tmp, anim_type):
        import os
        source = os.path.join(tmp, "source.png")
        image = Image.new("RGBA", (400, 600), (30, 140, 200, 255))
        image.paste((240, 200, 40, 255), (100, 150, 300, 450))
        image.save(source)
        return {
            "path": source,
            "state": {"pos": (-40, -60), "size": (320, 480)},
            "borda_pos": (0, 0),
            "anim_type": anim_type,
            "border_color": "#FF3366",
        }

    def test_bytes_match_the_exported_file(self):
        import os
        from src.core.batch_worker import encode_custom
        for anim_type, ext in (("Nenhuma", ".png"), ("Rainbow", ".gif"), ("Neon Pulsante", ".gif")):
            with self.subTest(anim_type=anim_type), tempfile.TemporaryDirectory() as tmp:
                task = self._task(tmp, anim_type)
                output = os.path.join(tmp, "out" + ext)
                self.assertEqual(process_image_task(dict(task, output_path=output))["status"], "success")
                data, fmt = encode_custom(task)
                self.assertEqual(fmt, ext.lstrip("."))
                with open(output, "rb") as f:
                    self.assertEqual(data, f.read())

    def test_measure_custom_reports_size_or_error(self):
        from src.core.batch_worker import encode_custom, measure_custom
        with tempfile.TemporaryDirectory() as tmp:
            task = self._task(tmp, "Rainbow")
            result = measure_custom(task)
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["format"], "gif")
            self.assertEqual(result["bytes"], len(encode_custom(task)[0]))
            missing = measure_custom(dict(task, path="/nao/existe.png"))
            self.assertEqual(missing["status"], "error")

    def test_frames_returned_without_output_path_stay_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = process_image_task(self._task(tmp, "Rainbow"))
            self.assertEqual(result["type"], "anim")
            frames = result["frames"]
            self.assertEqual(frames[0].getpixel((0, 0))[3], 255)  # fechado lançaria erro
            for frame in frames:
                frame.close()


class TestJpegDraftDecoding(unittest.TestCase):
    """JPEG grande é decodificado reduzido (draft) sem mudar o resultado."""

    def test_large_jpeg_export_matches_full_decode(self):
        import os
        from unittest.mock import patch

        import numpy as np
        from PIL import ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "grande.jpg")
            image = Image.new("RGB", (3000, 4200), (240, 230, 220))
            draw = ImageDraw.Draw(image)
            for i in range(0, 3000, 60):
                draw.line((i, 0, 3000 - i, 4200), fill=(i % 255, 80, 160), width=12)
            image.save(source, quality=92)
            task = {
                "path": source,
                "state": {"pos": (0, 0), "size": (250, 350)},
                "borda_pos": (0, 0),
                "anim_type": "Nenhuma",
                "border_color": "#FFFFFF",
            }
            drafted = process_image_task(dict(task, output_path=os.path.join(tmp, "a.png")))
            with patch.object(Image.Image, "draft", lambda self, *a, **k: None):
                full = process_image_task(dict(task, output_path=os.path.join(tmp, "b.png")))
            self.assertEqual(drafted["status"], "success")
            self.assertEqual(full["status"], "success")
            with Image.open(drafted["saved_to"]) as a, Image.open(full["saved_to"]) as b:
                self.assertEqual(a.size, (BORDA_WIDTH, BORDA_HEIGHT))
                diff = np.abs(np.asarray(a.convert("RGB"), dtype=int) - np.asarray(b.convert("RGB"), dtype=int))
            self.assertLess(diff.mean(), 2.0)
