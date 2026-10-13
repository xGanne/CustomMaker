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
        self.assertEqual(result["target_dir"], "unused")

    def test_upload_returns_cancelled_without_calling_uploader(self):
        app = DummyApp()
        controller = BatchController(app)
        with patch.object(controller, "_run_batch", return_value={"results": [], "cancelled": True}):
            result = controller.upload_to_imgchest("Album")

        self.assertTrue(result["cancelled"])
        self.assertEqual(result["links"], [])
        self.assertTrue(result["errors"])
        self.assertEqual(result["uploaded"], 0)
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

    def test_save_zip_summary_includes_written_processed_and_errors(self):
        app = DummyApp()
        controller = BatchController(app)
        batch_result = {
            "cancelled": False,
            "results": [
                {"status": "success", "saved_to": "C:/tmp/ok.png"},
                {"status": "error", "path": "bad.png", "error": "boom"},
            ],
        }
        with patch.object(controller, "_run_batch", return_value=batch_result), patch("zipfile.ZipFile"):
            result = controller.save_zip("out.zip")

        self.assertFalse(result["cancelled"])
        self.assertEqual(result["written"], 1)
        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["zip_path"], "out.zip")


class FakeExecutor:
    instances = []

    def __init__(self, max_workers=None):
        self.max_workers = max_workers
        self.shutdown_called = False
        self._broken = False
        FakeExecutor.instances.append(self)

    def shutdown(self, wait=True, cancel_futures=False):
        self.shutdown_called = True


class TestBatchControllerExecutorReuse(unittest.TestCase):
    """M15: o pool de processos é preguiçoso e reaproveitado entre lotes."""

    def setUp(self):
        FakeExecutor.instances = []
        patcher = patch("src.controllers.batch_controller.concurrent.futures.ProcessPoolExecutor", FakeExecutor)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.controller = BatchController(DummyApp())

    def test_pool_is_created_lazily_and_reused(self):
        self.assertIsNone(self.controller._executor)
        first = self.controller._get_executor(2)
        second = self.controller._get_executor(2)
        self.assertIs(first, second)
        self.assertEqual(len(FakeExecutor.instances), 1)

    def test_pool_is_recreated_when_worker_count_changes(self):
        first = self.controller._get_executor(2)
        second = self.controller._get_executor(4)
        self.assertIsNot(first, second)
        self.assertTrue(first.shutdown_called)
        self.assertEqual(second.max_workers, 4)

    def test_broken_pool_is_replaced(self):
        first = self.controller._get_executor(2)
        first._broken = True
        second = self.controller._get_executor(2)
        self.assertIsNot(first, second)

    def test_shutdown_releases_pool(self):
        executor = self.controller._get_executor(2)
        self.controller.shutdown()
        self.assertTrue(executor.shutdown_called)
        self.assertIsNone(self.controller._executor)
        # shutdown repetido é inofensivo
        self.controller.shutdown()


class TestBatchControllerDefaultFraming(unittest.TestCase):
    """M11: imagens nunca abertas seguem o enquadramento padrão escolhido."""

    def _controller(self, mode):
        from src.core.editor_state import EditorState
        state = EditorState(image_list=["img.png"], default_framing=mode)
        state.borda_pos = (0, 0)
        return BatchController(editor_state=state, edited_source_images={"img.png": Image.new("RGBA", (800, 600))})

    def test_auto_fit_mode_does_not_load_cascade(self):
        controller = self._controller("auto_fit")
        with patch("src.controllers.batch_controller.ImageProcessor.load_face_cascade") as load:
            state = controller._default_state_for("img.png")
        load.assert_not_called()
        self.assertIsNotNone(state)

    def test_intelligent_mode_uses_own_cascade_once(self):
        controller = self._controller("intelligent")
        fake_cascade = object()
        with patch(
            "src.controllers.batch_controller.ImageProcessor.load_face_cascade", return_value=fake_cascade
        ) as load, patch(
            "src.controllers.batch_controller.ImageProcessor.calculate_default_fit", return_value=(10, 20, 3, 4)
        ) as default_fit:
            first = controller._default_state_for("img.png")
            controller._default_state_for("img.png")
        load.assert_called_once()
        self.assertEqual(default_fit.call_args.args[2:], ("intelligent", fake_cascade))
        self.assertEqual(first, {"pos": (3, 4), "size": (10, 20)})


class TestBatchControllerExplicitPaths(unittest.TestCase):
    """O fluxo "Gerar customs" exporta só os arquivos recém-baixados."""

    def test_paths_restricts_export_to_given_files(self):
        app = DummyApp()
        app.image_list = ["editor_a.png", "editor_b.png"]
        controller = BatchController(app)
        captured = {}

        def fake_run_batch(tasks, **_kw):
            captured["paths"] = [t["path"] for t in tasks]
            return {"results": [], "cancelled": False}

        with patch.object(controller, "_get_task_data", side_effect=lambda p, *a, **k: {"path": p}), \
                patch.object(controller, "_run_batch", side_effect=fake_run_batch):
            controller.save_all_images("out", paths=["novo1.png", "novo2.png"])
            self.assertEqual(captured["paths"], ["novo1.png", "novo2.png"])
            controller.save_all_images("out")
            self.assertEqual(captured["paths"], ["editor_a.png", "editor_b.png"])


class TestUniqueOutputNames(unittest.TestCase):
    """Imagens com o mesmo nome em pastas diferentes não se sobrescrevem."""

    def test_collisions_get_numbered_case_insensitively(self):
        from src.controllers.batch_controller import unique_output_names
        names = unique_output_names(
            ["A/001.png", "B/001.png", "C/001.jpg", "D/Foto.png", "E/foto.jpg", "F/002.png"], "_custom.png"
        )
        self.assertEqual(
            list(names.values()),
            ["001_custom.png", "001_custom_2.png", "001_custom_3.png", "Foto_custom.png", "foto_custom_2.png",
             "002_custom.png"],
        )

    def test_upload_sends_both_colliding_images(self):
        import os
        from src.core.editor_state import EditorState

        with TemporaryDirectory() as tmp:
            paths = []
            for folder, color in (("a", "red"), ("b", "blue")):
                os.makedirs(os.path.join(tmp, folder))
                path = os.path.join(tmp, folder, "001.png")
                Image.new("RGBA", (300, 450), color).save(path)
                paths.append(path)
            uploaded = {}

            class CapturingUploader:
                def upload_images(self, files, title, progress_callback=None, cancel_event=None):
                    for item in files:
                        with Image.open(item["path"]) as img:
                            uploaded[item["filename"]] = img.convert("RGB").getpixel((112, 175))
                    return ["link1", "link2"], []

            controller = BatchController(
                editor_state=EditorState(image_list=paths), uploader=CapturingUploader(), borda_hex={"White": "#FFFFFF"}
            )
            try:
                result = controller.upload_to_imgchest("Album")
            finally:
                controller.shutdown()
        self.assertEqual(result["uploaded"], 2)
        self.assertEqual(set(uploaded), {"001_custom.png", "001_custom_2.png"})
        # cada arquivo enviado é a sua própria custom (vermelha e azul)
        self.assertEqual(sorted(uploaded.values()), sorted([(255, 0, 0), (0, 0, 255)]))
