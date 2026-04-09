import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

from src.controllers.batch_controller import BatchController


class DummyVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class DummyConfig:
    def __init__(self, max_workers=None):
        self._max_workers = max_workers

    def get(self, key):
        if key == "max_workers":
            return self._max_workers
        return None


class DummyUploader:
    def __init__(self):
        self.called = False

    def upload_images(self, files, title, progress_callback=None, cancel_event=None):
        self.called = True
        return ["https://imgchest.com/p/test"], []


class DummyApp:
    def __init__(self, max_workers=None):
        self.app_config = DummyConfig(max_workers=max_workers)
        self.image_states = {"image.png": {"pos": (0, 0), "size": (512, 512)}}
        self.image_list = ["image.png"]
        self.animation_type = DummyVar("Nenhuma")
        self.individual_bordas = {}
        self.selected_borda = DummyVar("White")
        self.custom_borda_hex_individual = {}
        self.custom_borda_hex = "#FFFFFF"
        self.borda_hex = {"White": "#FFFFFF"}
        self.borda_pos = (0, 0)
        self.uploader = DummyUploader()
        self.edited_source_images = {}


class TestBatchController(unittest.TestCase):
    def test_save_all_images_returns_cancelled_when_batch_cancelled(self):
        app = DummyApp()
        controller = BatchController(app)
        with patch.object(controller, "_run_batch", return_value={"results": [], "cancelled": True}):
            result = controller.save_all_images("unused")

        self.assertEqual(result["cancelled"], True)
        self.assertEqual(result["processed"], 0)
        self.assertEqual(result["errors"], 0)

    def test_upload_returns_cancelled_without_calling_uploader(self):
        app = DummyApp()
        controller = BatchController(app)
        with patch.object(controller, "_run_batch", return_value={"results": [], "cancelled": True}):
            result = controller.upload_to_imgchest("Album")

        self.assertTrue(result["cancelled"])
        self.assertEqual(result["links"], [])
        self.assertTrue(result["errors"])
        self.assertFalse(app.uploader.called)

    def test_resolve_max_workers_clamps_configured_value(self):
        with patch("src.controllers.batch_controller.os.cpu_count", return_value=4):
            app = DummyApp(max_workers=99)
            controller = BatchController(app)
            self.assertEqual(controller._resolve_max_workers(), 4)

            app_low = DummyApp(max_workers=0)
            controller_low = BatchController(app_low)
            self.assertEqual(controller_low._resolve_max_workers(), 1)

            app_invalid = DummyApp(max_workers="abc")
            controller_invalid = BatchController(app_invalid)
            self.assertEqual(controller_invalid._resolve_max_workers(), 4)

    def test_get_task_data_uses_edited_source_override(self):
        app = DummyApp()
        app.edited_source_images["image.png"] = Image.new("RGBA", (32, 32), "red")
        controller = BatchController(app)
        try:
            with TemporaryDirectory() as temp_dir:
                data = controller._get_task_data("image.png", output_path="out.png", source_dir=temp_dir)

                self.assertIsNotNone(data)
                self.assertIn("source_path", data)
                self.assertTrue(data["source_path"].startswith(temp_dir))
        finally:
            app.edited_source_images["image.png"].close()
