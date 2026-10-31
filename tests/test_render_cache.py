import importlib
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image

from _qt_helpers import dispose_window
from src.core.render_cache import RenderCache, custom_cache_key


compat = importlib.import_module("src.qt.compat")


class TestCustomCacheKey(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "a.png")
        Image.new("RGB", (10, 10)).save(self.path)
        self.task = {"path": self.path, "state": {"pos": (90, 80), "size": (250, 350)}, "borda_pos": (100, 100),
                     "anim_type": "Nenhuma", "border_color": "#ff0000", "border_style": "simples", "adjustments": {}}

    def key(self, edit_version=0, **changes):
        task = dict(self.task, **changes)
        return custom_cache_key(task, edit_version)

    def test_same_content_same_key(self):
        self.assertEqual(self.key(), self.key())

    def test_what_changes_the_custom_changes_the_key(self):
        base = self.key()
        for changes in ({"border_color": "#00ff00"}, {"border_style": "brilho"}, {"adjustments": {"contrast": 10}},
                        {"state": {"pos": (91, 80), "size": (250, 350)}}, {"state": {"pos": (90, 80), "size": (251, 350)}}):
            with self.subTest(changes=changes):
                self.assertNotEqual(self.key(**changes), base)

    def test_moving_border_and_framing_together_keeps_the_key(self):
        """Redimensionar a janela desloca a borda e os enquadramentos juntos."""
        moved = self.key(state={"pos": (130, 95), "size": (250, 350)}, borda_pos=(140, 115))
        self.assertEqual(moved, self.key())

    def test_animation_does_not_change_the_static_preview_key(self):
        self.assertEqual(self.key(anim_type="Rainbow"), self.key())

    def test_file_change_and_edit_version(self):
        base = self.key()
        os.utime(self.path, ns=(1, 1))
        self.assertNotEqual(self.key(), base)
        edited = self.key(edit_version=1, edited=True)
        self.assertNotEqual(self.key(edit_version=2, edited=True), edited)
        # sem edição de pixels a versão não entra: desfazer até o original acerta o cache
        self.assertEqual(self.key(edit_version=5), self.key(edit_version=0))

    def test_missing_file_has_no_key(self):
        self.assertIsNone(self.key(path=os.path.join(self.tmp, "sumiu.png")))


class TestRenderCache(unittest.TestCase):
    def test_lru_respects_the_byte_limit(self):
        cache = RenderCache(max_bytes=3 * 10 * 10 * 4)
        for name in "abcd":
            cache.put(name, Image.new("RGBA", (10, 10)))
        self.assertIsNone(cache.get("a"))  # o mais antigo saiu
        self.assertEqual(len(cache), 3)
        self.assertLessEqual(cache.used_bytes, cache.max_bytes)

    def test_get_returns_an_independent_copy(self):
        cache = RenderCache()
        cache.put("k", Image.new("RGBA", (4, 4), (1, 2, 3, 255)))
        copy = cache.get("k")
        copy.putpixel((0, 0), (9, 9, 9, 255))
        self.assertEqual(cache.get("k").getpixel((0, 0)), (1, 2, 3, 255))

    def test_recently_used_survives(self):
        cache = RenderCache(max_bytes=2 * 10 * 10 * 4)
        cache.put("a", Image.new("RGBA", (10, 10)))
        cache.put("b", Image.new("RGBA", (10, 10)))
        cache.get("a")
        cache.put("c", Image.new("RGBA", (10, 10)))
        self.assertIsNotNone(cache.get("a"))
        self.assertIsNone(cache.get("b"))


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestReviewUsesTheCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = compat.QApplication.instance() or compat.QApplication([])

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
        self.paths = []
        for i, color in enumerate(("red", "blue", "green")):
            path = os.path.join(self.tmp, f"c{i}.png")
            Image.new("RGB", (400, 600), color).save(path)
            self.paths.append(path)
        self.window.add_images(self.paths, replace=True)
        end = time.monotonic() + 5
        while self.window.task_runner._tasks and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)

    def _open(self):
        from shiboken6 import isValid
        dialog = self.window.open_review()
        self.addCleanup(lambda d=dialog: isValid(d) and d.close())  # o teste pode já ter fechado
        end = time.monotonic() + 10
        while (dialog.grid.count() < 3 or "Renderizando" in dialog.status.text()) and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        return dialog

    def test_reopening_and_refresh_render_only_what_changed(self):
        import src.qt.dialogs.review_dialog as review_module
        rendered = []
        original = review_module.render_custom_preview

        def counting(data):
            rendered.append(data["path"])
            return original(data)

        with patch.object(review_module, "render_custom_preview", counting):
            first = self._open()
            self.assertEqual(len(rendered), 3)
            first.close()
            rendered.clear()
            second = self._open()
            self.assertEqual(rendered, [])  # tudo do cache
            self.assertIn("3 do cache", second.status.text())
            # muda só a borda de uma imagem: Atualizar re-renderiza só ela
            self.window.editor_state.individual_bordas[self.paths[1]] = "Red"
            second.render()
            end = time.monotonic() + 10
            while "Renderizando" in second.status.text() and time.monotonic() < end:
                self.app.processEvents()
                time.sleep(0.01)
            self.assertEqual(rendered, [self.paths[1]])

    def test_refresh_cancels_the_render_in_progress(self):
        dialog = self.window.open_review()
        from shiboken6 import isValid
        self.addCleanup(lambda: isValid(dialog) and dialog.close())
        first = dialog._active_task_id
        with patch.object(self.window.task_runner, "cancel", wraps=self.window.task_runner.cancel) as cancel:
            dialog.render()  # antes de a primeira terminar
        cancel.assert_any_call(first)
        self.assertNotEqual(dialog._active_task_id, first)

    def test_switching_folder_clears_the_cache(self):
        self._open()
        self.assertEqual(len(self.window.render_cache), 3)
        self.window.add_images(self.paths[:1], replace=True)
        self.assertEqual(len(self.window.render_cache), 0)


if __name__ == "__main__":
    unittest.main()
