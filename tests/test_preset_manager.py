import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.core.preset_manager import PresetManager


class TestPresetManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.presets_path = os.path.join(self.tmp, "presets.json")
        self.patch_file = patch("src.core.preset_manager.PRESETS_FILE", self.presets_path)
        self.patch_file.start()

    def tearDown(self):
        self.patch_file.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_returns_empty_when_file_missing(self):
        manager = PresetManager()
        self.assertEqual(manager.list_presets(), [])

    def test_add_and_get_preset(self):
        manager = PresetManager()
        manager.add_preset("vermelho", {"border": "Red", "color": "#FF0000"})
        self.assertEqual(manager.get_preset("vermelho"), {"border": "Red", "color": "#FF0000"})

    def test_add_persists_to_disk(self):
        manager = PresetManager()
        manager.add_preset("verde", {"border": "Green"})
        with open(self.presets_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("verde", data)

    def test_delete_existing_preset(self):
        manager = PresetManager()
        manager.add_preset("azul", {"border": "Blue"})
        result = manager.delete_preset("azul")
        self.assertTrue(result)
        self.assertIsNone(manager.get_preset("azul"))

    def test_delete_nonexistent_returns_false(self):
        manager = PresetManager()
        result = manager.delete_preset("nao_existe")
        self.assertFalse(result)

    def test_list_presets_returns_names(self):
        manager = PresetManager()
        manager.add_preset("a", {})
        manager.add_preset("b", {})
        self.assertCountEqual(manager.list_presets(), ["a", "b"])

    def test_load_corrupted_json_fallbacks_to_empty(self):
        with open(self.presets_path, "w") as f:
            f.write("not json {{{")
        manager = PresetManager()
        self.assertEqual(manager.list_presets(), [])

    def test_load_presets_from_existing_file(self):
        with open(self.presets_path, "w", encoding="utf-8") as f:
            json.dump({"carregado": {"border": "White"}}, f)
        manager = PresetManager()
        self.assertEqual(manager.get_preset("carregado"), {"border": "White"})
