import gc
import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

from src.core.spilled_image import SpilledImage, is_lazy_edit


def _gradient(size=(300, 500)):
    return Image.merge("RGBA", [
        Image.linear_gradient("L").resize(size),
        Image.linear_gradient("L").rotate(90).resize(size),
        Image.new("L", size, 90),
        Image.linear_gradient("L").resize(size),  # alfa variado: o TIFF guarda exato
    ])


class TestSpilledImage(unittest.TestCase):
    def test_round_trip_is_exact_and_reduced_load_fits(self):
        image = _gradient()
        spilled = SpilledImage(image)
        self.assertEqual((spilled.size, spilled.mode), (image.size, "RGBA"))
        self.assertEqual(spilled.load().tobytes(), image.tobytes())
        self.assertLessEqual(max(spilled.load(200).size), 200)
        self.assertIs(spilled.copy(), spilled)  # imutável: o histórico compartilha
        self.assertTrue(is_lazy_edit(spilled))

    def test_file_is_removed_when_nobody_references_it(self):
        spilled = SpilledImage(_gradient((20, 20)))
        path = spilled.path
        self.assertTrue(os.path.exists(path))
        del spilled
        gc.collect()
        self.assertFalse(os.path.exists(path))

    def test_without_disk_keeps_a_copy_in_memory(self):
        image = _gradient((20, 20))
        with patch.object(SpilledImage, "__init__", side_effect=OSError("disco cheio")):
            kept = SpilledImage.from_image(image)
        self.assertIsInstance(kept, Image.Image)
        self.assertEqual(kept.tobytes(), image.tobytes())


class TestSpilledImageExport(unittest.TestCase):
    def test_export_reads_the_file_without_new_temporaries(self):
        from src.controllers.batch_controller import BatchController
        from src.core.batch_worker import render_custom_crop
        from src.core.editor_state import EditorState
        with TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "img.png")
            Image.new("RGB", (300, 500), "white").save(path)
            edit = _gradient()
            state = EditorState(image_list=[path])
            state.set_image_state(path, (10, 20), (260, 380))
            spilled = SpilledImage(edit)
            batch = BatchController(editor_state=state, edited_source_images={path: spilled}).frozen()
            del spilled  # o lote congelado mantém o arquivo vivo
            gc.collect()
            data = batch._get_task_data(path, source_dir=os.path.join(tmp, "src"))
            self.assertTrue(os.path.exists(data["source_path"]))
            self.assertFalse(os.path.exists(os.path.join(tmp, "src")))  # nada regravado
            in_memory = BatchController(editor_state=state, edited_source_images={path: edit})
            expected = render_custom_crop(in_memory._get_task_data(path, source_dir=os.path.join(tmp, "mem")))
            self.assertEqual(render_custom_crop(data).tobytes(), expected.tobytes())


if __name__ == "__main__":
    unittest.main()
