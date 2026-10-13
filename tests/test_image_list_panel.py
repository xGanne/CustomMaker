import importlib
import os
import tempfile
import unittest

from PIL import Image

from src.utils.file_reveal import reveal_command


panel_module = importlib.import_module("src.qt.widgets.image_list_panel")


class TestRevealCommand(unittest.TestCase):
    """M9: "Revelar no Explorer" monta o comando certo por plataforma."""

    def test_windows_selects_file_in_explorer(self):
        cmd = reveal_command("C:/imgs/a.png", platform="win32")
        self.assertEqual(cmd[0], "explorer")
        self.assertEqual(cmd[1], "/select," + os.path.normpath("C:/imgs/a.png"))

    def test_macos_reveals_in_finder(self):
        self.assertEqual(reveal_command("/imgs/a.png", platform="darwin"), ["open", "-R", "/imgs/a.png"])

    def test_linux_opens_parent_folder(self):
        self.assertEqual(reveal_command("/imgs/a.png", platform="linux"), ["xdg-open", "/imgs"])


@unittest.skipUnless(getattr(panel_module, "QT_AVAILABLE", False), "PySide6 not installed")
class TestImageListPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compat = importlib.import_module("src.qt.compat")
        cls.compat = compat
        cls.app = compat.QApplication.instance() or compat.QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = []
        for i in range(3):
            path = os.path.join(self.tmp.name, f"img{i}.png")
            Image.new("RGBA", (20, 30), "white").save(path)
            self.paths.append(path)
        self.panel = panel_module.ImageListPanel()
        self.panel.set_paths(self.paths)

    def tearDown(self):
        # no Windows a thread de thumbnail ainda pode estar com o arquivo aberto
        self.panel._executor.shutdown(wait=True)
        self.panel.close()
        self.panel.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def _item(self, row):
        return self.panel.list_widget.item(row)

    def test_list_allows_extended_selection(self):
        self.assertEqual(
            self.panel.list_widget.selectionMode(),
            self.compat.QAbstractItemView.ExtendedSelection,
        )

    def test_delete_key_requests_removal_of_selected_rows(self):
        captured = []
        self.panel.remove_requested.connect(captured.append)
        self._item(0).setSelected(True)
        self._item(2).setSelected(True)
        from src.qt.compat import QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier)
        self.panel.list_widget.keyPressEvent(event)
        self.assertEqual(captured, [[0, 2]])

    def test_border_badges_set_color_and_tooltip(self):
        self.panel.update_border_badges({self.paths[1]: ("Red", "#f38ba8")})
        role = panel_module.BORDER_BADGE_ROLE
        self.assertEqual(self._item(1).data(role), "#f38ba8")
        self.assertIn("Borda individual: Red", self._item(1).toolTip())
        self.assertIsNone(self._item(0).data(role))

    def test_badges_and_indicators_survive_list_rebuild(self):
        self.panel.update_indicators({self.paths[0]}, set())
        self.panel.update_border_badges({self.paths[0]: ("Blue", "#89b4fa")})
        self.panel.set_paths(self.paths[:2])
        tooltip = self._item(0).toolTip()
        self.assertIn("Pixels editados", tooltip)
        self.assertIn("Borda individual: Blue", tooltip)


if __name__ == "__main__":
    unittest.main()
