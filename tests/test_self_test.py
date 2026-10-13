import importlib
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch


compat = importlib.import_module("src.qt.compat")


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestSelfTest(unittest.TestCase):
    """O autoteste do exe (--self-test) roda e reporta falhas."""

    @classmethod
    def setUpClass(cls):
        cls.app = compat.QApplication.instance() or compat.QApplication([])

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.report = os.path.join(self.tmp, "relatorio.txt")
        from PySide6.QtCore import QTranslator

        def remove_translators():  # o autoteste instala a tradução; não vazar
            for translator in self.app.findChildren(QTranslator):
                self.app.removeTranslator(translator)

        self.addCleanup(remove_translators)

    def test_passes_from_source(self):
        from src.self_test import run_self_test
        self.assertTrue(run_self_test(self.report))
        with open(self.report, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("RESULTADO: PASSOU", text)
        self.assertNotIn("[FALHA]", text)

    def test_reports_failure_without_stopping_other_checks(self):
        from src.self_test import run_self_test
        with patch("src.core.image_processor.ImageProcessor.load_face_cascade", return_value=None):
            self.assertFalse(run_self_test(self.report))
        with open(self.report, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("[FALHA] Detecção de rosto", text)
        self.assertIn("[OK]    Sessão", text)  # os demais itens continuam rodando
        self.assertIn("RESULTADO: FALHOU", text)


if __name__ == "__main__":
    unittest.main()
