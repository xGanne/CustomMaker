import importlib
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image


compat = importlib.import_module("src.qt.compat")


def _png_bytes():
    buffer = BytesIO()
    Image.new("RGB", (40, 60), "red").save(buffer, format="PNG")
    return buffer.getvalue()


class _SlowClient:
    """Download que só termina quando o teste libera."""

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def download_image(self, _url):
        self.started.set()
        self.release.wait(10)
        return _png_bytes()


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestDanbooruImageViewer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = compat.QApplication.instance() or compat.QApplication([])

    def test_fechar_durante_o_download_nao_mexe_em_widgets_destruidos(self):
        """Fechar o visualizador antes do fim do download gerava
        'Internal C++ object (QLabel) already deleted' no on_progress."""
        from PySide6.QtCore import QCoreApplication

        from src.qt.dialogs import danbooru_image_viewer as module

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        client = _SlowClient()
        post = {"id": 1, "file_url": "https://example.invalid/a.png"}
        with patch("src.utils.resource_loader.app_data_path", lambda rel: os.path.join(tmp, rel)):
            viewer = module.DanbooruImageViewer(post, client)
        viewer.setAttribute(compat.Qt.WA_DeleteOnClose, True)
        viewer.show()

        end = time.monotonic() + 5
        while not client.started.is_set() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(client.started.is_set())

        errors = []
        original_hook = sys.excepthook
        sys.excepthook = lambda *exc: errors.append(exc)
        try:
            viewer.close()
            QCoreApplication.sendPostedEvents(None, compat.QEvent.DeferredDelete)
            client.release.set()
            end = time.monotonic() + 3
            while time.monotonic() < end:
                self.app.processEvents()
                time.sleep(0.01)
        finally:
            sys.excepthook = original_hook
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
