import importlib
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from _qt_helpers import dispose_window
from src.qt.commands import Command, CommandRegistry


compat = importlib.import_module("src.qt.compat")


def _registry(calls):
    reg = CommandRegistry()
    for cid, title, category, keywords in (
        ("export.zip", "Exportar ZIP", "Exportar", ("compactar",)),
        ("export.all", "Salvar todas", "Exportar", ("exportar",)),
        ("frame.auto", "Auto fit", "Enquadramento", ()),
        ("frame.smart_all", "Ajuste inteligente em todas", "Enquadramento", ("lote",)),
    ):
        reg.register(Command(cid, title, lambda c=cid: calls.append(c), category, keywords=keywords))
    reg.add_provider(lambda: [Command("anim.Rainbow", "Animação: Rainbow", lambda: calls.append("rainbow"), "Animação")])
    return reg


class TestCommandSearch(unittest.TestCase):
    def setUp(self):
        self.reg = _registry([])

    def ids(self, query, recent=()):
        return [c.id for c in self.reg.search(query, recent)]

    def test_accents_and_case_are_ignored(self):
        self.assertEqual(self.ids("animacao")[0], "anim.Rainbow")
        self.assertEqual(self.ids("ZIP")[0], "export.zip")

    def test_typo_matches_by_subsequence(self):
        self.assertEqual(self.ids("rnbow"), ["anim.Rainbow"])

    def test_all_words_must_match(self):
        self.assertEqual(self.ids("inteligente todas"), ["frame.smart_all"])
        self.assertEqual(self.ids("inteligente zip"), [])

    def test_title_prefix_ranks_above_keyword(self):
        # "exportar" é prefixo de "Exportar ZIP" e só palavra-chave de "Salvar todas"
        self.assertEqual(self.ids("exportar"), ["export.zip", "export.all"])

    def test_empty_query_lists_recent_first(self):
        ids = self.ids("", recent=("frame.auto", "export.zip"))
        self.assertEqual(ids[:2], ["frame.auto", "export.zip"])
        self.assertEqual(len(ids), 5)

    def test_providers_are_included(self):
        self.assertIsNotNone(self.reg.get("anim.Rainbow"))


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestCommandPalette(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = compat.QApplication.instance() or compat.QApplication([])
        from PySide6.QtTest import QTest
        cls.QTest = QTest

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for patcher in (
            patch("src.core.app_config.CONFIG_FILE", os.path.join(self.tmp, "config.json")),
            patch("src.core.preset_manager.PRESETS_FILE", os.path.join(self.tmp, "presets.json")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        from src.core.app_config import AppConfig
        from src.qt.main_window import QtMainWindow
        self.window = QtMainWindow(AppConfig())
        self.addCleanup(dispose_window, self.app, self.window)
        self.window.show()

    def _type_and_enter(self, palette, text):
        self.QTest.keyClicks(palette.input, text)
        self.QTest.keyClick(palette.input, compat.Qt.Key_Return)
        for _ in range(5):
            self.app.processEvents()

    def test_enter_runs_the_best_match_and_remembers_it(self):
        with patch.object(self.window, "save_zip") as save_zip:
            self.window.commands = self.window._build_command_registry()  # handlers com o mock
            self.window.editor_state.image_list = ["/x.png"]
            palette = self.window.open_command_palette()
            self._type_and_enter(palette, "zip")
        save_zip.assert_called_once()
        self.assertEqual(self.window.app_config.get("command_palette_recent")[0], "export.zip")

    def test_escape_closes_without_running(self):
        with patch.object(self.window, "save_zip") as save_zip:
            self.window.commands = self.window._build_command_registry()
            palette = self.window.open_command_palette()
            self.QTest.keyClicks(palette.input, "zip")
            self.QTest.keyClick(palette.input, compat.Qt.Key_Escape)
            self.app.processEvents()
        save_zip.assert_not_called()
        from shiboken6 import isValid
        self.assertFalse(isValid(palette) and palette.isVisible())  # fechada (e destruída)

    def test_disabled_command_does_not_run(self):
        with patch.object(self.window, "save_zip") as save_zip:
            self.window.commands = self.window._build_command_registry()
            palette = self.window.open_command_palette()  # sem imagens: ZIP indisponível
            self._type_and_enter(palette, "zip")
        save_zip.assert_not_called()

    def test_dynamic_commands_and_shortcuts_match(self):
        ids = {c.id for c in self.window.commands.all()}
        self.assertIn("border.set.Red", ids)
        self.assertIn("anim.set.Rainbow", ids)
        registered = sorted(a.shortcut().toString() for a in self.window.actions() if not a.shortcut().isEmpty())
        expected = sorted(
            [compat.QKeySequence(c.shortcut).toString() for c in self.window.commands.all() if c.register_shortcut]
            + [compat.QKeySequence("Ctrl+K").toString(), compat.QKeySequence("Ctrl+Shift+P").toString()]
        )
        self.assertEqual(registered, expected)


if __name__ == "__main__":
    unittest.main()
