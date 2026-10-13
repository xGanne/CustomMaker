import importlib
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src.qt.mixins.export_mixin import DISCORD_MESSAGE_LIMIT, ExportMixin


def _links(count):
    return [f"https://cdn.imgchest.com/files/{i:011d}.png" for i in range(count)]


class TestMudaeCommands(unittest.TestCase):
    """O comando do Mudae é dividido para caber no limite do Discord."""

    def test_small_album_is_a_single_command(self):
        links = _links(5)
        self.assertEqual(ExportMixin.mudae_commands("Miku", links), [ExportMixin.mudae_command("Miku", links)])

    def test_large_album_is_split_under_the_limit_keeping_order(self):
        links = _links(120)
        parts = ExportMixin.mudae_commands("Hatsune Miku", links)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= DISCORD_MESSAGE_LIMIT for part in parts))
        self.assertTrue(all(part.startswith("$ai Hatsune Miku $\n") for part in parts))
        # todas as imagens, na ordem original, sem repetir
        recovered = [link for part in parts for link in part.split("\n")[1:]]
        recovered = [link.rstrip(" $") for link in recovered]
        self.assertEqual(recovered, links)

    def test_parts_are_filled_as_much_as_possible(self):
        parts = ExportMixin.mudae_commands("Miku", _links(200))
        # todas as partes menos a última ficam perto do limite (não sobra espaço para mais um link)
        link_cost = len(" $\n") + len(_links(1)[0])
        for part in parts[:-1]:
            self.assertGreater(len(part) + link_cost, DISCORD_MESSAGE_LIMIT)

    def test_no_links_means_no_command(self):
        self.assertEqual(ExportMixin.mudae_commands("Miku", []), [])


compat = importlib.import_module("src.qt.compat")


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestLinksDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = compat.QApplication.instance() or compat.QApplication([])

    def setUp(self):
        from _qt_helpers import dispose_window
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        for patcher in (
            patch("src.core.app_config.CONFIG_FILE", os.path.join(tmp, "config.json")),
            patch("src.core.preset_manager.PRESETS_FILE", os.path.join(tmp, "presets.json")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        from src.core.app_config import AppConfig
        from src.qt.main_window import QtMainWindow
        self.window = QtMainWindow(AppConfig())
        self.addCleanup(dispose_window, self.app, self.window)

    def test_one_copy_button_per_part(self):
        links = _links(100)
        expected = ExportMixin.mudae_commands("Miku", links)
        dialog = self.window._show_links_dialog("Miku", links)
        self.addCleanup(dialog.close)
        self.assertEqual(len(dialog.copy_buttons), len(expected))
        dialog.copy_buttons[-1].click()
        self.assertEqual(compat.QGuiApplication.clipboard().text(), expected[-1])
        self.assertIn(f"{len(expected)}/{len(expected)}", dialog.copy_buttons[-1].text())

    def test_single_part_keeps_simple_button(self):
        dialog = self.window._show_links_dialog("Miku", _links(3))
        self.addCleanup(dialog.close)
        self.assertEqual([b.text() for b in dialog.copy_buttons], ["Copiar comando"])


if __name__ == "__main__":
    unittest.main()
