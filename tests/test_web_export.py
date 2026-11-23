"""O app web usa regras, máscaras e customs de referência geradas do código do PC.

Mudou algo em src/ que o web reproduz (cores, estilos de borda, render)? Estes
testes falham até os arquivos serem gerados de novo:

    python scripts/export_web_rules.py
    python scripts/web_fixtures.py
"""
import gzip
import importlib.util
import json
import os
import unittest

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGENERATE = "rode python scripts/export_web_rules.py e python scripts/web_fixtures.py"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestWebRulesAreCurrent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.export = _load("export_web_rules")

    def test_rules_json_matches_the_pc_code(self):
        with open(self.export.RULES_PATH, encoding="utf-8") as file_obj:
            self.assertEqual(json.load(file_obj), self.export.build_rules(), REGENERATE)

    def test_border_masks_match_the_pc_code(self):
        with open(self.export.MASKS_PATH, "rb") as file_obj:
            stored = gzip.decompress(file_obj.read())
        masks = self.export.build_masks()  # também confere as premissas do web
        expected = b"".join(masks[name].tobytes() for name in self.export.MASK_ORDER)
        self.assertEqual(stored, expected, REGENERATE)


class TestWebFixturesAreCurrent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = _load("web_fixtures")
        cls.sources, cls.cases, cls.autofit, cls.gradient = cls.fixtures.build_all()

    def _stored(self, name):
        with Image.open(os.path.join(self.fixtures.FIXTURES_DIR, name)) as image:
            return np.asarray(image.convert("RGBA"))

    def test_manifest_is_current(self):
        with open(os.path.join(self.fixtures.FIXTURES_DIR, "cases.json"), encoding="utf-8") as file_obj:
            manifest = json.load(file_obj)
        self.assertEqual(manifest, {"cases": self.cases, "autofit": self.autofit, "gradient": self.gradient},
                         REGENERATE)

    def test_sources_and_reference_customs_are_current(self):
        for name, image in self.sources.items():
            np.testing.assert_array_equal(self._stored(f"source-{name}.png"), np.asarray(image),
                                          err_msg=f"source-{name}: {REGENERATE}")
        for case in self.cases:
            rendered = np.asarray(self.fixtures.render_case(self.sources, case))
            np.testing.assert_array_equal(self._stored(case["expected"]), rendered,
                                          err_msg=f"{case['name']}: {REGENERATE}")


if __name__ == "__main__":
    unittest.main()
