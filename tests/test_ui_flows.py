"""M18: testes dos fluxos críticos de UI que viviam sem cobertura (F1, F2, F3, F5)."""
import importlib
import logging
import os
import shutil
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from PIL import Image, ImageDraw


compat = importlib.import_module("src.qt.compat")
QT_AVAILABLE = compat.QT_AVAILABLE


def _app():
    return compat.QApplication.instance() or compat.QApplication([])


def _wait_until(app, condition, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


@unittest.skipUnless(QT_AVAILABLE, "PySide6 not installed")
class TestBeforeAfterPreservesFraming(unittest.TestCase):
    """F2: segurar B/crase mostra o original sem corromper o enquadramento."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        cls.canvas_module = importlib.import_module("src.qt.widgets.image_canvas")

    def test_before_after_round_trip(self):
        canvas = self.canvas_module.ImageCanvas()
        canvas.resize(800, 700)
        canvas.set_image(Image.new("RGBA", (400, 600), "white"), state={"pos": (120, 80), "size": (300, 450)})
        emitted = []
        canvas.state_changed.connect(lambda pos, size: emitted.append((pos, size)))

        canvas.show_original_preview()
        self.app.processEvents()
        # a posição temporária do "antes" nunca chega ao editor_state
        self.assertEqual(emitted, [])

        canvas.restore_edit_preview()
        self.app.processEvents()
        self.assertEqual(emitted, [])
        self.assertEqual((canvas.image_item.pos().x(), canvas.image_item.pos().y()), (120, 80))
        self.assertEqual(canvas._current_size, (300, 450))

    def test_restore_without_preview_is_harmless(self):
        canvas = self.canvas_module.ImageCanvas()
        canvas.restore_edit_preview()  # sem imagem: não pode lançar
        canvas.set_image(Image.new("RGBA", (50, 50), "white"))
        canvas.restore_edit_preview()  # sem "antes" ativo: não altera nada
        self.assertEqual(canvas._current_size, (50, 50))


@unittest.skipUnless(QT_AVAILABLE, "PySide6 not installed")
class TestShortcutsDoNotStealTextKeys(unittest.TestCase):
    """F3: ←/→/Ctrl+V/Ctrl+Z pertencem ao campo de texto focado."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        from PySide6.QtTest import QTest
        cls.QTest = QTest

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        patchers = [
            patch("src.core.app_config.CONFIG_FILE", os.path.join(self.tmp, "config.json")),
            patch("src.core.preset_manager.PRESETS_FILE", os.path.join(self.tmp, "presets.json")),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        from src.core.app_config import AppConfig
        from src.qt.main_window import QtMainWindow
        self.window = QtMainWindow(AppConfig())
        self.window.resize(1200, 800)
        self.window.show()
        self.paths = []
        for i in range(3):
            path = os.path.join(self.tmp, f"img{i}.png")
            Image.new("RGBA", (300, 400), (60 * i, 80, 120, 255)).save(path)
            self.paths.append(path)
        self.window.add_images(self.paths, replace=True)
        _wait_until(self.app, lambda: self.window._active_image_load_task_id is None)

    def tearDown(self):
        self.window.editor_state.image_dirty.clear()  # evita o diálogo de "sair mesmo assim?"
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _focused_line_edit(self):
        edit = self.window.options_color_edit
        self.window.options_border_combo.setCurrentText("Cor Personalizada")  # habilita o campo
        edit.setText("#123456")
        edit.setFocus()
        edit.setCursorPosition(3)
        return edit

    def test_arrows_move_text_cursor_instead_of_navigating(self):
        edit = self._focused_line_edit()
        self.QTest.keyClick(edit, compat.Qt.Key_Right)
        self.assertEqual(edit.cursorPosition(), 4)
        self.assertEqual(self.window.current_path, self.paths[0])

    def test_ctrl_v_and_ctrl_z_go_to_the_text_field(self):
        edit = self._focused_line_edit()
        with patch.object(self.window, "paste_image") as paste, \
                patch.object(self.window, "undo_current_image") as undo:
            self.QTest.keyClick(edit, compat.Qt.Key_V, compat.Qt.ControlModifier)
            self.QTest.keyClick(edit, compat.Qt.Key_Z, compat.Qt.ControlModifier)
        paste.assert_not_called()
        undo.assert_not_called()

    def test_resize_keeps_framing_of_hidden_images(self):
        """Redimensionar recentraliza a borda: imagens fora da tela acompanham."""
        es = self.window.editor_state

        def relative(path):
            x, y = es.image_states[path]["pos"]
            return x - es.borda_pos[0], y - es.borda_pos[1]

        first = self.paths[0]
        before = relative(first)
        self.window.navigate_images(1)
        _wait_until(self.app, lambda: self.window._active_image_load_task_id is None)
        self.window.resize(900, 650)
        self.assertTrue(_wait_until(self.app, lambda: es.borda_pos == self.window.image_canvas.border_pos))
        self.app.processEvents()
        self.assertEqual(relative(first), before)
        self.assertEqual(es.borda_pos, self.window.image_canvas.border_pos)

    def test_viewing_images_does_not_mark_them_unexported(self):
        """Só ajustes de verdade disparam o aviso de "não exportado" ao sair."""
        es = self.window.editor_state
        self.window.navigate_images(1)
        _wait_until(self.app, lambda: self.window._active_image_load_task_id is None)
        self.window.resize(950, 680)
        _wait_until(self.app, lambda: es.borda_pos == self.window.image_canvas.border_pos)
        self.assertEqual(es.image_dirty, set())

        item = self.window.image_canvas.image_item
        item.setPos(item.pos().x() + 12, item.pos().y())
        self.app.processEvents()
        self.assertEqual(es.image_dirty, {self.window.current_path})

    def test_added_images_get_default_framing_in_background(self):
        """Ao adicionar imagens, o enquadramento padrão é calculado antes de abri-las."""
        es = self.window.editor_state
        self.assertTrue(_wait_until(self.app, lambda: all(p in es.image_states for p in self.paths)))
        self.assertEqual(es.auto_framed, set(self.paths))
        self.assertEqual(es.user_adjusted, set())
        self.assertEqual(es.image_dirty, set())
        # na lista, nada aparece como "ajustado" (laranja) sem ajuste do usuário
        item = self.window.image_list_panel.list_widget.item(2)
        self.assertNotIn("Enquadramento ajustado", item.toolTip())

        canvas_item = self.window.image_canvas.image_item
        canvas_item.setPos(canvas_item.pos().x() + 8, canvas_item.pos().y())
        self.app.processEvents()
        self.assertEqual(es.user_adjusted, {self.window.current_path})

    def test_undo_after_resize_restores_framing_relative_to_border(self):
        es = self.window.editor_state
        canvas = self.window.image_canvas

        def relative():
            x, y = es.image_states[self.window.current_path]["pos"]
            return x - es.borda_pos[0], y - es.borda_pos[1]

        original = relative()
        self.window.save_state_for_undo()
        canvas.image_item.setPos(canvas.image_item.pos().x() + 40, canvas.image_item.pos().y() + 25)
        self.app.processEvents()
        self.window.resize(900, 650)
        self.assertTrue(_wait_until(self.app, lambda: es.borda_pos == canvas.border_pos))
        self.window.undo_current_image()
        self.app.processEvents()
        self.assertEqual(relative(), original)

    def test_arrows_navigate_when_canvas_has_focus(self):
        self.window.image_canvas.setFocus()
        self.QTest.keyClick(self.window.image_canvas, compat.Qt.Key_Right)
        self.assertEqual(self.window.current_path, self.paths[1])


@unittest.skipUnless(QT_AVAILABLE, "PySide6 not installed")
class TestExitConfirmation(unittest.TestCase):
    """M2: confirmação ao sair com "não perguntar novamente"."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for patcher in (
            patch("src.core.app_config.CONFIG_FILE", os.path.join(self.tmp, "config.json")),
            patch("src.core.preset_manager.PRESETS_FILE", os.path.join(self.tmp, "presets.json")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        from src.core.app_config import AppConfig
        from src.qt.main_window import QtMainWindow
        self.window = QtMainWindow(AppConfig())

    def tearDown(self):
        self.window.editor_state.image_dirty.clear()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _answer(self, button, dont_ask):
        """Responde o QMessageBox assim que ele abrir."""
        def respond():
            box = self.app.activeModalWidget()
            if box is None:
                compat.QTimer.singleShot(10, respond)
                return
            box.checkBox().setChecked(dont_ask)
            box.button(button).click()
        compat.QTimer.singleShot(0, respond)

    def test_dont_ask_again_is_saved_only_when_exit_is_confirmed(self):
        QMessageBox = compat.QMessageBox
        self._answer(QMessageBox.No, dont_ask=True)
        self.assertFalse(self.window._confirm_exit_with_unexported(2))
        self.assertTrue(self.window.app_config.get("confirm_exit_with_unexported"))

        self._answer(QMessageBox.Yes, dont_ask=True)
        self.assertTrue(self.window._confirm_exit_with_unexported(2))
        self.assertFalse(self.window.app_config.get("confirm_exit_with_unexported"))

    def test_disabled_confirmation_exits_without_dialog(self):
        self.window.app_config.set("confirm_exit_with_unexported", False)
        with patch.object(compat.QMessageBox, "exec") as exec_:
            self.assertTrue(self.window._confirm_exit_with_unexported(3))
        exec_.assert_not_called()


@unittest.skipUnless(QT_AVAILABLE, "PySide6 not installed")
class TestFaceDetectionUnavailable(unittest.TestCase):
    """M17: sem o cascade, os botões de ajuste inteligente ficam desabilitados."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def _window(self, cascade):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        for patcher in (
            patch("src.core.app_config.CONFIG_FILE", os.path.join(tmp, "config.json")),
            patch("src.core.preset_manager.PRESETS_FILE", os.path.join(tmp, "presets.json")),
            patch("src.qt.main_window.ImageProcessor.load_face_cascade", return_value=cascade),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        from src.core.app_config import AppConfig
        from src.qt.main_window import QtMainWindow
        window = QtMainWindow(AppConfig())
        self.addCleanup(window.deleteLater)
        return window

    def test_buttons_disabled_and_explained_without_cascade(self):
        window = self._window(None)
        for button in (window._toolbar_smart_fit_btn, window.editor_tab.smart_fit_all_btn):
            self.assertFalse(button.isEnabled())
            self.assertIn("lbpcascade_animeface.xml", button.toolTip())

    def test_buttons_enabled_with_cascade(self):
        window = self._window(object())
        self.assertTrue(window._toolbar_smart_fit_btn.isEnabled())
        self.assertTrue(window.editor_tab.smart_fit_all_btn.isEnabled())


@unittest.skipUnless(QT_AVAILABLE, "PySide6 not installed")
class TestMissingTokenDialog(unittest.TestCase):
    """F6: o aviso de token ausente oferece abrir (e criar) o .env."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env_file = os.path.join(self.tmp, ".env")
        for patcher in (
            patch("src.core.app_config.CONFIG_FILE", os.path.join(self.tmp, "config.json")),
            patch("src.core.preset_manager.PRESETS_FILE", os.path.join(self.tmp, "presets.json")),
            patch("src.core.uploader.ENV_FILE", self.env_file),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        from src.core.app_config import AppConfig
        from src.qt.main_window import QtMainWindow
        self.window = QtMainWindow(AppConfig())
        self.addCleanup(self.window.deleteLater)
        self.window.editor_state.image_list = ["qualquer.png"]
        self.window.uploader.api_token = None

    def _click(self, label):
        def respond():
            box = self.app.activeModalWidget()
            if box is None:
                compat.QTimer.singleShot(10, respond)
                return
            for button in box.buttons():
                if button.text() == label:
                    button.click()
                    return
            box.reject()
        compat.QTimer.singleShot(0, respond)

    def test_open_button_creates_template_and_opens_env(self):
        self._click("Abrir .env")
        with patch("src.utils.file_reveal.open_with_default_app", return_value=True) as opener:
            self.window.upload_to_imgchest()
        opener.assert_called_once_with(self.env_file)
        with open(self.env_file, encoding="utf-8") as f:
            self.assertIn("IMG_CHEST_API_TOKEN=", f.read())

    def test_token_saved_in_env_is_used_without_restart(self):
        with open(self.env_file, "w", encoding="utf-8") as f:
            f.write("IMG_CHEST_API_TOKEN=token_novo\n")
        with patch("src.qt.compat.QInputDialog.getText", return_value=("", False)) as ask_title:
            self.window.upload_to_imgchest()
        # sem diálogo de erro: já seguiu para pedir o título do álbum
        ask_title.assert_called_once()
        self.assertEqual(self.window.uploader.api_token, "token_novo")


@unittest.skipUnless(QT_AVAILABLE, "PySide6 not installed")
class TestListThumbnailsOnGuiThread(unittest.TestCase):
    """F1: QPixmap/QIcon da lista só são criados na GUI thread."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_thumbnails_are_applied_on_main_thread(self):
        panel_module = importlib.import_module("src.qt.widgets.image_list_panel")
        tmp = tempfile.mkdtemp()
        try:
            paths = []
            for i in range(4):
                path = os.path.join(tmp, f"t{i}.png")
                Image.new("RGBA", (80, 100), "white").save(path)
                paths.append(path)
            panel = panel_module.ImageListPanel()
            threads = []
            original = panel._apply_thumbnail
            panel.thumbnail_ready.disconnect()
            panel.thumbnail_ready.connect(
                lambda *args: (threads.append(threading.current_thread()), original(*args))
            )
            panel.set_paths(paths)
            self.assertTrue(_wait_until(self.app, lambda: len(threads) == len(paths)))
            self.assertTrue(all(t is threading.main_thread() for t in threads))
            panel._executor.shutdown(wait=True)
            panel.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestBatchResultOrder(unittest.TestCase):
    """F5: resultados do lote saem na ordem da lista, não na de conclusão."""

    def test_results_follow_task_order_even_when_first_task_finishes_last(self):
        from src.controllers.batch_controller import BatchController
        from src.core.editor_state import EditorState

        tmp = tempfile.mkdtemp()
        controller = None
        try:
            paths = []
            # a primeira imagem é bem maior, então tende a terminar por último
            for i, size in enumerate([(3000, 4000), (200, 300), (200, 300), (200, 300)]):
                path = os.path.join(tmp, f"o{i}.png")
                image = Image.new("RGBA", size, (40 * i, 90, 160, 255))
                ImageDraw.Draw(image).line((0, 0) + size, fill="white", width=5)
                image.save(path)
                paths.append(path)
            state = EditorState(image_list=paths)

            class Cfg:
                def get(self, key, default=None):
                    return 4 if key == "max_workers" else default

            controller = BatchController(editor_state=state, app_config=Cfg(), borda_hex={"White": "#FFFFFF"})
            out_dir = os.path.join(tmp, "out")
            os.makedirs(out_dir)
            tasks = [
                controller._get_task_data(p, os.path.join(out_dir, os.path.basename(p)), source_dir=tmp)
                for p in paths
            ]
            batch = controller._run_batch(tasks)
            self.assertEqual([r.get("path") for r in batch["results"]], paths)
            self.assertTrue(all(r.get("status") == "success" for r in batch["results"]))
        finally:
            if controller is not None:
                controller.shutdown()
            shutil.rmtree(tmp, ignore_errors=True)


class TestFaceDetectionConcurrency(unittest.TestCase):
    """A detecção de rosto pode ser chamada de várias threads ao mesmo tempo."""

    def test_concurrent_detection_does_not_fail(self):
        from src.core.image_processor import ImageProcessor

        cascade = ImageProcessor.load_face_cascade()
        if cascade is None:
            self.skipTest("lbpcascade_animeface.xml indisponível")
        image = Image.new("RGBA", (1000, 750), (200, 80, 80, 255))
        logger = logging.getLogger("src.core.image_processor")
        with self.assertNoLogs(logger, level="WARNING"):
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(
                    lambda _i: ImageProcessor.detect_all_anime_faces(image, cascade), range(8)
                ))
        self.assertEqual(results, [[]] * 8)


if __name__ == "__main__":
    unittest.main()
