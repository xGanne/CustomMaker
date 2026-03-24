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
