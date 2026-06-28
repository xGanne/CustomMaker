import os
from collections import OrderedDict

from PIL import Image, ImageGrab

from src.config.settings import BORDA_HEIGHT, BORDA_HEX, BORDA_WIDTH, BORDER_THICKNESS, SUPPORTED_EXTENSIONS
from src.controllers.batch_controller import BatchController
from src.core.animation_processor import AnimationProcessor
from src.core.editor_state import EditorState, UiPreferences
from src.core.image_processor import ImageProcessor
from src.core.preset_manager import PresetManager
from src.core.uploader import ImgChestUploader
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error
from src.qt.dialogs.progress_dialog import ProgressDialog
from src.qt.task_runner import QtTaskRunner
from src.qt.tabs.ai_tab import AiTab
from src.qt.tabs.editor_tab import EditorTab
from src.qt.tabs.online_tab import OnlineTab
from src.qt.widgets.image_canvas import ImageCanvas
from src.qt.widgets.image_list_panel import ImageListPanel
from src.utils.resource_loader import resource_path

if QT_AVAILABLE:
    from src.qt.compat import (
        QAction,
        QApplication,
        QFileDialog,
        QGuiApplication,
        QIcon,
        QInputDialog,
        QKeySequence,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QSplitter,
        QTabWidget,
        QTimer,
        QVBoxLayout,
        QWidget,
        Qt,
    )


if QT_AVAILABLE:
    class QtMainWindow(QMainWindow):
        def __init__(self, app_config):
            super().__init__()
            self.app_config = app_config
            self.ui_preferences = UiPreferences.from_app_config(app_config)
            self.editor_state = EditorState(selected_borda=self.ui_preferences.last_global_borda)
            self.preset_manager = PresetManager()
            self.uploader = ImgChestUploader()
            self.face_cascade = ImageProcessor.load_face_cascade()
            self.task_runner = QtTaskRunner(self)
            self.edited_images = {}
            self.batch_controller = BatchController(
                editor_state=self.editor_state,
                app_config=self.app_config,
                uploader=self.uploader,
                borda_hex=BORDA_HEX,
                edited_source_images=self.edited_images,
            )

            self.current_original_image = None
            self.current_path = None
            self._image_load_seq = 0
            self._active_image_load_task_id = None
            self._preview_cache = OrderedDict()
            self._preview_cache_current_bytes = 0
            cache_mb = max(32, min(1024, int(self.ui_preferences.image_cache_max_mb or 256)))
            self._preview_cache_limit_bytes = cache_mb * 1024 * 1024
            self._undo_stacks = {}
            self._active_preview_task_id = None
            self._preview_seq = 0
            self._preview_frames = []
            self._preview_duration = 50
            self._preview_index = 0
            self._color_picker_enabled = False
            self._preview_timer = QTimer(self)
            self._preview_timer.timeout.connect(self._advance_preview_frame)

            self.setWindowTitle("Custom Maker Pro (Qt)")
            self.resize(1440, 920)
            self._apply_icon()
            self.setAcceptDrops(True)

            self._build_ui()
            self._register_shortcuts()
            self.show_status("UI Qt pronta.")

        def _apply_icon(self):
            for candidate in ("icon.ico", "icon.png"):
                icon_path = resource_path(candidate)
                if os.path.exists(icon_path):
                    self.setWindowIcon(QIcon(icon_path))
                    break

        def _build_ui(self):
            central = QWidget(self)
            self.setCentralWidget(central)
            root_layout = QVBoxLayout(central)
            root_layout.setContentsMargins(10, 10, 10, 10)
            root_layout.setSpacing(10)

            splitter = QSplitter(Qt.Horizontal, self)
            root_layout.addWidget(splitter)

            left_widget = QWidget(self)
            left_layout = QVBoxLayout(left_widget)
            left_layout.setContentsMargins(0, 0, 0, 0)
            self.image_canvas = ImageCanvas(self)
            self.image_canvas.state_changed.connect(self.on_canvas_state_changed)
            self.image_canvas.border_pos_changed.connect(self.on_border_pos_changed)
            self.image_canvas.interaction_started.connect(self.save_state_for_undo)
            self.image_canvas.color_picked.connect(self.on_canvas_color_picked)
            left_layout.addWidget(self.image_canvas)
            splitter.addWidget(left_widget)

            right_widget = QWidget(self)
            right_layout = QVBoxLayout(right_widget)
            right_layout.setContentsMargins(0, 0, 0, 0)
            right_layout.setSpacing(10)
            right_widget.setMinimumWidth(420)
            self.tabs = QTabWidget(self)
            self.tabs.setDocumentMode(True)
            self.editor_tab = EditorTab(self, self.tabs)
            self.online_tab = OnlineTab(self, self.tabs)
            self.ai_tab = AiTab(self, self.tabs)
            self.tabs.addTab(self.editor_tab, "Edição")
            self.tabs.addTab(self.online_tab, "Online")
            self.tabs.addTab(self.ai_tab, "IA")
            self.image_list_panel = ImageListPanel(self)
            self.image_list_panel.selection_changed.connect(self.load_image)
            self.image_list_panel.remove_requested.connect(self.remove_image_at)
            self.image_list_panel.toggle_individual_requested.connect(self.toggle_individual_border)
            right_layout.addWidget(self.tabs, 3)
            right_layout.addWidget(self.image_list_panel, 2)
            splitter.addWidget(right_widget)
            splitter.setSizes([960, 420])

        def _register_shortcuts(self):
            shortcuts = [
                ("Ctrl+O", self.load_folder),
                ("Ctrl+S", self.save_all_images),
                ("Alt+F", self.apply_intelligent_fit),
                ("Alt+B", self.apply_auto_fit),
                ("Ctrl+Q", lambda: self.rotate_current_image("left")),
                ("Ctrl+E", lambda: self.rotate_current_image("right")),
                ("Ctrl+Z", self.undo_current_image),
                ("Ctrl+V", self.paste_image),
            ]
            for sequence, handler in shortcuts:
                action = QAction(self)
                action.setShortcut(QKeySequence(sequence))
                action.triggered.connect(handler)
                self.addAction(action)

        def show_status(self, message, timeout_ms=5000):
            self.statusBar().showMessage(message, timeout_ms)

        def show_info(self, title, message):
            QMessageBox.information(self, title, message)

        def show_warning(self, title, message):
            QMessageBox.warning(self, title, message)

        def show_error(self, title, message):
            QMessageBox.critical(self, title, message)

        def choose_directory(self, title):
            start_dir = self.ui_preferences.last_folder or ""
            return QFileDialog.getExistingDirectory(self, title, start_dir)

        def choose_save_file(self, title, filter_text):
            start_dir = self.ui_preferences.last_folder or ""
            file_path, _ = QFileDialog.getSaveFileName(self, title, start_dir, filter_text)
            return file_path

        def run_task(self, task_id, title, task_fn, on_done, on_error=None, maximum=1):
            dialog = ProgressDialog(
                self,
                title=title,
                maximum=maximum,
                on_cancel=lambda: self.task_runner.cancel(task_id),
            )
            handle = self.task_runner.submit(task_id, task_fn)
            if handle is None:
                self.show_warning("Tarefa", "Já existe uma operação em andamento com esse identificador.")
                return None

            def close_dialog(*_args):
                dialog.close()

            handle.progress.connect(lambda current, total, text: dialog.update_progress(current, total, text))
            handle.done.connect(lambda result: (close_dialog(), on_done(result)))
            if on_error:
                handle.error.connect(lambda exc: (close_dialog(), on_error(exc)))
            else:
                handle.error.connect(lambda exc: (close_dialog(), self.show_error("Erro", str(exc))))
            handle.cancelled.connect(lambda: (close_dialog(), self.show_status("Operação cancelada.")))
            dialog.show()
            return handle

        @staticmethod
        def _format_count(label, value):
            return f"{label}: {int(value or 0)}"

        @staticmethod
        def _format_path(label, path):
            return f"{label}: {path}" if path else None

        def _show_result_summary(self, title, lines, details=None, warning=False):
            message = "\n".join(line for line in lines if line)
            if warning:
                self.show_warning(title, message)
            elif details:
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Information)
                box.setWindowTitle(title)
                box.setText(message)
                box.setDetailedText("\n".join(details))
                box.exec()
            else:
                self.show_info(title, message)

        def _close_current_original(self):
            if self.current_original_image is not None:
                try:
                    self.current_original_image.close()
                except Exception:
                    pass
                self.current_original_image = None

        @staticmethod
        def _estimate_image_bytes(image):
            if image is None:
                return 0
            try:
                channels = len(image.getbands())
            except Exception:
                channels = 4
            return max(1, image.width * image.height * channels)

        def _touch_preview_cache_entry(self, path):
            if path not in self._preview_cache:
                return
            image = self._preview_cache.pop(path)
            self._preview_cache[path] = image

        def _remember_preview_cache(self, path, image):
            if not path or image is None:
                return
            cached = image.copy()
            if path in self._preview_cache:
                existing = self._preview_cache.pop(path)
                self._preview_cache_current_bytes -= self._estimate_image_bytes(existing)
                try:
                    existing.close()
                except Exception:
                    pass
            self._preview_cache[path] = cached
            self._preview_cache_current_bytes += self._estimate_image_bytes(cached)

            while self._preview_cache_current_bytes > self._preview_cache_limit_bytes and self._preview_cache:
                evicted_path, evicted_image = self._preview_cache.popitem(last=False)
                self._preview_cache_current_bytes = max(
                    0,
                    self._preview_cache_current_bytes - self._estimate_image_bytes(evicted_image),
                )
                try:
                    evicted_image.close()
                except Exception:
                    pass

        def _clear_preview_cache(self):
            while self._preview_cache:
                _, image = self._preview_cache.popitem(last=False)
                try:
                    image.close()
                except Exception:
                    pass
            self._preview_cache_current_bytes = 0

        def _get_preview_cache_copy(self, path):
            cached = self._preview_cache.get(path)
            if cached is None:
                return None
            self._touch_preview_cache_entry(path)
            return cached.copy()

        @staticmethod
        def _dispose_images(images):
            for image in images:
                if image is None:
                    continue
                try:
                    image.close()
                except Exception:
                    pass

        @staticmethod
        def _pil_to_preview_qpixmap(image):
            from src.qt.widgets.image_canvas import _pil_to_qpixmap

            return _pil_to_qpixmap(image)

        @staticmethod
        def _dispose_image_load_result(result):
            for key in ("original", "preview"):
                image = result.get(key)
                if image is None:
                    continue
                try:
                    image.close()
                except Exception:
                    pass

        def _preview_max_dimension(self):
            viewport = self.image_canvas.viewport().size()
            base = max(viewport.width(), viewport.height(), 900)
            return max(1000, min(2400, base * 2))

        def _build_image_load_result(self, index, path, preview_max_dim, include_preview, cancel_event):
            if cancel_event and cancel_event.is_set():
                return {"cancelled": True, "index": index, "path": path}

            with Image.open(path) as source:
                original = source.convert("RGBA")

            preview = None
            if include_preview:
                preview = ImageProcessor.resize_image(original, preview_max_dim, preview_max_dim)
                if preview is original:
                    preview = original.copy()

            if cancel_event and cancel_event.is_set():
                result = {"original": original, "preview": preview}
                self._dispose_image_load_result(result)
                return {"cancelled": True, "index": index, "path": path}

            return {
                "cancelled": False,
                "index": index,
                "path": path,
                "original": original,
                "preview": preview,
            }

        def add_images(self, paths, replace=False, select_last=False):
            valid_paths = []
            for path in paths:
                if not path:
                    continue
                lower_path = path.lower()
                if os.path.isfile(path) and lower_path.endswith(SUPPORTED_EXTENSIONS):
                    valid_paths.append(path)

            if replace:
                self.editor_state.reset_images()
                self.stop_preview_animation()
                for image in self.edited_images.values():
                    try:
                        image.close()
                    except Exception:
                        pass
                self.edited_images.clear()
                for stack in self._undo_stacks.values():
                    for undo_image, *_rest in stack:
                        self._dispose_images([undo_image])
                self._undo_stacks.clear()
                self._clear_preview_cache()

            for path in valid_paths:
                if path not in self.editor_state.image_list:
                    self.editor_state.image_list.append(path)

            self.image_list_panel.set_paths(self.editor_state.image_list)

            if valid_paths:
                self.ui_preferences.last_folder = os.path.dirname(valid_paths[0])

            if not self.editor_state.image_list:
                self.current_path = None
                self.image_canvas.clear_image()
                return

            if select_last and valid_paths:
                target_index = self.editor_state.image_list.index(valid_paths[-1])
            elif self.editor_state.current_image_index is not None:
                target_index = self.editor_state.current_image_index
            else:
                target_index = 0
            self.load_image(target_index)

        def load_folder(self):
            folder = self.choose_directory("Selecione a pasta de imagens")
            if not folder:
                return
            paths = [
                os.path.join(folder, name)
                for name in sorted(os.listdir(folder))
                if os.path.isfile(os.path.join(folder, name)) and name.lower().endswith(SUPPORTED_EXTENSIONS)
            ]
            self.add_images(paths, replace=True)
            self.show_status(f"{len(paths)} imagem(ns) carregada(s).")

        def get_active_image_copy(self):
            if not self.current_path:
                return None
            image = self.edited_images.get(self.current_path) or self.current_original_image
            if image is None:
                image = self._get_preview_cache_copy(self.current_path)
                if image is None:
                    return None
                try:
                    return image.copy()
                finally:
                    image.close()
            if image is None:
                return None
            return image.copy()

        def set_edited_image_for_current(self, image):
            if not self.current_path:
                return
            self.edited_images[self.current_path] = image.copy()
            self._remember_preview_cache(self.current_path, self.edited_images[self.current_path])
            state = self.editor_state.image_states.get(self.current_path)
            self.image_canvas.set_image(
                self.edited_images[self.current_path],
                state=state,
                border_color=self.editor_state.resolve_border_hex(BORDA_HEX, self.current_path),
            )
            self._update_preview_animation()

        def save_state_for_undo(self):
            if not self.current_path:
                return
            image = self.get_active_image_copy()
            if image is None:
                return
            state = self.editor_state.image_states.get(self.current_path) or self._ensure_state_for_current(image)
            snapshot = (
                image,
                tuple(state.get("pos", self.editor_state.borda_pos)),
                tuple(state.get("size", image.size)),
            )
            stack = self._undo_stacks.setdefault(self.current_path, [])
            stack.append(snapshot)
            while len(stack) > 20:
                old_image, *_rest = stack.pop(0)
                self._dispose_images([old_image])

        def undo_current_image(self):
            if not self.current_path:
                return
            stack = self._undo_stacks.get(self.current_path) or []
            if not stack:
                self.show_status("Nada para desfazer.")
                return
            image, pos, size = stack.pop()
            previous = self.edited_images.get(self.current_path)
            if previous is not None:
                self._dispose_images([previous])
            self.edited_images[self.current_path] = image.copy()
            self._remember_preview_cache(self.current_path, self.edited_images[self.current_path])
            self.editor_state.set_image_state(self.current_path, pos, size)
            self.image_canvas.set_image(
                self.edited_images[self.current_path],
                state={"pos": pos, "size": size},
                border_color=self.editor_state.resolve_border_hex(BORDA_HEX, self.current_path),
            )
            self._dispose_images([image])
            self._update_preview_animation()
            self.show_status("Ultima alteracao desfeita.")

        def _ensure_state_for_current(self, image):
            if not self.current_path:
                return None
            state = self.editor_state.image_states.get(self.current_path)
            if state:
                return state
            fit = ImageProcessor.calculate_auto_fit_pos(image, self.editor_state.borda_pos)
            if fit:
                new_w, new_h, pos_x, pos_y = fit
                state = {"pos": (pos_x, pos_y), "size": (new_w, new_h)}
            else:
                state = {"pos": self.editor_state.borda_pos, "size": image.size}
            self.editor_state.image_states[self.current_path] = state
            return state

        def load_image(self, index):
            if index is None or index < 0 or index >= len(self.editor_state.image_list):
                return

            path = self.editor_state.image_list[index]
            self._close_current_original()
            self.current_path = path
            self.editor_state.current_image_index = index
            self.image_list_panel.set_current_index(index)
            self.editor_state.borda_pos = self.image_canvas.border_pos
            self.editor_tab.refresh_from_state()
            display_image = self.edited_images.get(path) or self._get_preview_cache_copy(path)
            if display_image is not None:
                state = self._ensure_state_for_current(display_image)
                self.image_canvas.set_image(
                    display_image,
                    state=state,
                    border_color=self.editor_state.resolve_border_hex(BORDA_HEX, path),
                )
            else:
                self.image_canvas.clear_image()
                self.refresh_current_canvas()

            if self._active_image_load_task_id and self.task_runner.is_running(self._active_image_load_task_id):
                self.task_runner.cancel(self._active_image_load_task_id)

            self._image_load_seq += 1
            task_id = f"qt_image_load_{self._image_load_seq}"
            self._active_image_load_task_id = task_id
            preview_max_dim = self._preview_max_dimension()
            include_preview = path not in self.edited_images and path not in self._preview_cache

            def task_fn(cancel_event, _on_progress):
                result = self._build_image_load_result(index, path, preview_max_dim, include_preview, cancel_event)
                result["task_id"] = task_id
                return result

            def on_done(result):
                if result.get("task_id") != self._active_image_load_task_id:
                    self._dispose_image_load_result(result)
                    return
                self._active_image_load_task_id = None
                if result.get("cancelled"):
                    return
                if result.get("index") != self.editor_state.current_image_index or result.get("path") != self.current_path:
                    self._dispose_image_load_result(result)
                    return

                self._close_current_original()
                self.current_original_image = result.get("original")

                preview = result.get("preview")
                if preview is not None:
                    self._remember_preview_cache(path, preview)
                    try:
                        preview.close()
                    except Exception:
                        pass

                refreshed_image = self.edited_images.get(path) or self._get_preview_cache_copy(path)
                if refreshed_image is None and self.current_original_image is not None:
                    refreshed_image = ImageProcessor.resize_image(self.current_original_image, preview_max_dim, preview_max_dim)
                    if refreshed_image is self.current_original_image:
                        refreshed_image = self.current_original_image.copy()
                    self._remember_preview_cache(path, refreshed_image)

                if refreshed_image is not None and path == self.current_path:
                    state = self._ensure_state_for_current(refreshed_image)
                    self.image_canvas.set_image(
                        refreshed_image,
                        state=state,
                        border_color=self.editor_state.resolve_border_hex(BORDA_HEX, path),
                    )
                    if refreshed_image is not self.edited_images.get(path):
                        try:
                            refreshed_image.close()
                        except Exception:
                            pass
                self._update_preview_animation()
                self.show_status(f"Imagem carregada: {os.path.basename(path)}")

            def on_error(exc):
                if task_id == self._active_image_load_task_id:
                    self._active_image_load_task_id = None
                self.show_error("Erro", f"Falha ao carregar imagem: {exc}")

            handle = self.task_runner.submit(task_id, task_fn)
            if handle is None:
                self._active_image_load_task_id = None
                self.show_warning("Carregamento", "Não foi possível iniciar o carregamento da imagem.")
                return
            handle.done.connect(on_done)
            handle.error.connect(on_error)
            self.show_status(f"Carregando: {os.path.basename(path)}")

        def refresh_current_canvas(self):
            if not self.current_path:
                return
            border_color = self.editor_state.resolve_border_hex(BORDA_HEX, self.current_path)
            self.image_canvas.set_border_color(border_color)
            self._update_preview_animation()

        def on_canvas_state_changed(self, pos, size):
            if not self.current_path:
                return
            self.editor_state.set_image_state(self.current_path, pos, size)

        def on_border_pos_changed(self, pos):
            self.editor_state.borda_pos = pos

        def apply_auto_fit(self, push_undo=True):
            image = self.get_active_image_copy()
            if image is None or not self.current_path:
                self.show_warning("Ajuste", "Carregue uma imagem primeiro.")
                return
            if push_undo:
                self.save_state_for_undo()
            result = ImageProcessor.calculate_auto_fit_pos(image, self.editor_state.borda_pos)
            if not result:
                self.show_warning("Ajuste", "Não foi possível calcular o ajuste.")
                return
            new_w, new_h, pos_x, pos_y = result
            self.editor_state.set_image_state(self.current_path, (pos_x, pos_y), (new_w, new_h))
            self.image_canvas.set_image_state((pos_x, pos_y), (new_w, new_h))
            self.show_status("Auto fit aplicado.")

        def apply_intelligent_fit(self, push_undo=True):
            image = self.get_active_image_copy()
            if image is None or not self.current_path:
                self.show_warning("Ajuste", "Carregue uma imagem primeiro.")
                return
            if push_undo:
                self.save_state_for_undo()
            face = ImageProcessor.detect_anime_face(image, self.face_cascade)
            if not face:
                self.show_warning("Ajuste", "Nenhum rosto detectado. Aplicando auto fit.")
                self.apply_auto_fit(push_undo=False)
                return
            result = ImageProcessor.calculate_intelligent_frame_pos(image, face, self.editor_state.borda_pos)
            if not result:
                self.show_warning("Ajuste", "Não foi possível aplicar o ajuste inteligente.")
                return
            new_w, new_h, pos_x, pos_y = result
            self.editor_state.set_image_state(self.current_path, (pos_x, pos_y), (new_w, new_h))
            self.image_canvas.set_image_state((pos_x, pos_y), (new_w, new_h))
            self.show_status("Ajuste inteligente aplicado.")

        def rotate_current_image(self, direction):
            image = self.get_active_image_copy()
            if image is None or not self.current_path:
                return
            self.save_state_for_undo()
            angle = 90 if direction == "left" else -90
            rotated = image.rotate(angle, expand=True)
            self.set_edited_image_for_current(rotated)
            self.apply_auto_fit(push_undo=False)
            self.show_status(f"Prévia rotacionada para {direction}.")

        def apply_preset(self, data):
            border_name = data.get("border_name", self.editor_state.selected_borda)
            if border_name in BORDA_HEX or border_name == "Cor Personalizada":
                self.editor_state.selected_borda = border_name
            custom_color = data.get("border_color")
            if isinstance(custom_color, str) and custom_color.startswith("#") and len(custom_color) == 7:
                self.editor_state.custom_borda_hex = custom_color
            animation_type = data.get("animation_type")
            if isinstance(animation_type, str):
                self.editor_state.animation_type = animation_type
            self.editor_tab.refresh_from_state()
            self.refresh_current_canvas()
            self.show_status("Preset aplicado.")

        def apply_adjustment_to_all(self, adjustment_name):
            if not self.editor_state.image_list:
                self.show_warning("Ajuste", "Nenhuma imagem carregada.")
                return

            def task_fn(cancel_event, on_progress):
                updated = 0
                total = len(self.editor_state.image_list)
                for index, path in enumerate(self.editor_state.image_list, start=1):
                    if cancel_event and cancel_event.is_set():
                        break

                    working = self.edited_images.get(path)
                    should_close = False
                    if working is None:
                        with Image.open(path) as source:
                            working = source.convert("RGBA")
                        should_close = True

                    try:
                        if adjustment_name == "auto_fit":
                            result = ImageProcessor.calculate_auto_fit_pos(working, self.editor_state.borda_pos)
                        else:
                            face = ImageProcessor.detect_anime_face(working, self.face_cascade)
                            if face:
                                result = ImageProcessor.calculate_intelligent_frame_pos(
                                    working,
                                    face,
                                    self.editor_state.borda_pos,
                                )
                            else:
                                result = ImageProcessor.calculate_auto_fit_pos(working, self.editor_state.borda_pos)
                        if result:
                            new_w, new_h, pos_x, pos_y = result
                            self.editor_state.set_image_state(path, (pos_x, pos_y), (new_w, new_h))
                            updated += 1
                    finally:
                        if should_close:
                            self._dispose_images([working])

                    if on_progress:
                        message = "Aplicando ajuste em lote..."
                        on_progress(index, total, message)

                return {"updated": updated}

            def on_done(result):
                if self.current_path:
                    state = self.editor_state.image_states.get(self.current_path)
                    if state:
                        self.image_canvas.set_image_state(state["pos"], state["size"])
                label = "Auto fit" if adjustment_name == "auto_fit" else "Ajuste inteligente"
                self.show_info("Ajuste", f"{label} aplicado em {result.get('updated', 0)} imagem(ns).")

            self.run_task(
                f"qt_adjust_all_{adjustment_name}",
                "Aplicando ajuste em lote",
                task_fn,
                on_done=on_done,
                maximum=max(1, len(self.editor_state.image_list)),
            )

        def remove_image_at(self, index):
            if index < 0 or index >= len(self.editor_state.image_list):
                return
            path = self.editor_state.image_list[index]
            self.editor_state.remove_image(path)
            cached_preview = self._preview_cache.pop(path, None)
            if cached_preview is not None:
                self._preview_cache_current_bytes = max(
                    0,
                    self._preview_cache_current_bytes - self._estimate_image_bytes(cached_preview),
                )
                try:
                    cached_preview.close()
                except Exception:
                    pass
            edited = self.edited_images.pop(path, None)
            if edited is not None:
                try:
                    edited.close()
                except Exception:
                    pass
            undo_stack = self._undo_stacks.pop(path, [])
            for undo_image, *_rest in undo_stack:
                self._dispose_images([undo_image])
            self.image_list_panel.set_paths(self.editor_state.image_list)
            if not self.editor_state.image_list:
                self.current_path = None
                self._close_current_original()
                self.image_canvas.clear_image()
                self.stop_preview_animation()
                self.show_status("Lista de imagens vazia.")
                return
            self.load_image(self.editor_state.current_image_index or 0)

        def toggle_individual_border(self, index):
            if index < 0 or index >= len(self.editor_state.image_list):
                return
            path = self.editor_state.image_list[index]
            if path in self.editor_state.individual_bordas:
                self.editor_state.individual_bordas.pop(path, None)
            else:
                self.editor_state.individual_bordas[path] = self.editor_state.selected_borda
            if path == self.current_path:
                self.refresh_current_canvas()
            self.show_status("Configuração individual de borda atualizada.")

        def toggle_color_picker(self):
            self._color_picker_enabled = not self._color_picker_enabled
            self.image_canvas.set_color_pick_enabled(self._color_picker_enabled)
            if self._color_picker_enabled:
                self.show_status("Modo Pick Color ativo. Clique sobre a imagem.")
            else:
                self.show_status("Modo Pick Color desativado.")

        def on_canvas_color_picked(self, color):
            self._color_picker_enabled = False
            self.image_canvas.set_color_pick_enabled(False)
            self.editor_state.selected_borda = "Cor Personalizada"
            self.editor_state.custom_borda_hex = color
            self.ui_preferences.last_global_borda = "Cor Personalizada"
            QApplication.clipboard().setText(color)
            self.editor_tab.refresh_from_state()
            self.refresh_current_canvas()
            self.show_info("Pick Color", f"Cor copiada: {color}")

        @staticmethod
        def _generate_preview_frames(animation_type, border_color, cancel_event):
            try:
                size = (BORDA_WIDTH, BORDA_HEIGHT)
                if cancel_event and cancel_event.is_set():
                    return {"cancelled": True, "frames": [], "duration": 50}
                if animation_type == "Rainbow":
                    frames, duration = AnimationProcessor.generate_rainbow_frames(size, total_frames=40, border_width=BORDER_THICKNESS, overlay_only=True)
                elif animation_type == "Neon Pulsante":
                    frames, duration = AnimationProcessor.generate_neon_frames(size, border_color, total_frames=40, border_width=BORDER_THICKNESS, overlay_only=True)
                elif animation_type == "Strobe (Pisca)":
                    frames, duration = AnimationProcessor.generate_strobe_frames(size, total_frames=10, border_width=BORDER_THICKNESS, overlay_only=True)
                elif animation_type == "Glitch":
                    frames, duration = AnimationProcessor.generate_glitch_frames(size, total_frames=20, border_width=BORDER_THICKNESS, overlay_only=True)
                elif animation_type == "Spin":
                    frames, duration = AnimationProcessor.generate_spin_frames(size, border_color, total_frames=30, border_width=BORDER_THICKNESS, overlay_only=True)
                elif animation_type == "Flow":
                    frames, duration = AnimationProcessor.generate_flow_frames(size, border_color, total_frames=30, border_width=BORDER_THICKNESS, overlay_only=True)
                else:
                    return {"cancelled": False, "frames": [], "duration": 50}
                if cancel_event and cancel_event.is_set():
                    return {"cancelled": True, "frames": [], "duration": duration}
                return {"cancelled": False, "frames": frames, "duration": duration}
            except Exception as exc:
                return {"cancelled": False, "frames": [], "duration": 50, "error": str(exc)}

        def _update_preview_animation(self):
            if not self.editor_state.has_animation or not self.current_path:
                self.stop_preview_animation()
                return
            self.start_preview_animation()

        def start_preview_animation(self):
            animation_type = self.editor_state.animation_type
            border_color = self.editor_state.resolve_border_hex(BORDA_HEX, self.current_path)
            self.stop_preview_animation(clear_frames=False)
            self._preview_index = 0
            self._preview_seq += 1
            task_id = f"qt_preview_frames_{self._preview_seq}"
            self._active_preview_task_id = task_id

            def task_fn(cancel_event, _on_progress):
                result = self._generate_preview_frames(animation_type, border_color, cancel_event)
                result["task_id"] = task_id
                return result

            def on_done(result):
                if result.get("task_id") != self._active_preview_task_id:
                    self._dispose_images(result.get("frames") or [])
                    return
                self._active_preview_task_id = None
                if result.get("cancelled"):
                    return
                if result.get("error"):
                    self.image_canvas.clear_preview_overlay()
                    self.show_warning("Preview", result["error"])
                    return
                pixmaps = []
                for frame in result.get("frames") or []:
                    pixmaps.append(self._pil_to_preview_qpixmap(frame))
                self._dispose_images(result.get("frames") or [])
                self._preview_frames = pixmaps
                self._preview_duration = max(30, int(result.get("duration") or 50))
                if not self._preview_frames:
                    self.image_canvas.clear_preview_overlay()
                    return
                self._advance_preview_frame()
                self._preview_timer.start(self._preview_duration)

            def on_error(exc):
                if task_id == self._active_preview_task_id:
                    self._active_preview_task_id = None
                self.image_canvas.clear_preview_overlay()
                self.show_warning("Preview", str(exc))

            handle = self.task_runner.submit(task_id, task_fn)
            if handle is None:
                self._active_preview_task_id = None
                return
            handle.done.connect(on_done)
            handle.error.connect(on_error)

        def _advance_preview_frame(self):
            if not self._preview_frames:
                return
            pixmap = self._preview_frames[self._preview_index % len(self._preview_frames)]
            self.image_canvas.set_preview_overlay(pixmap)
            self._preview_index = (self._preview_index + 1) % len(self._preview_frames)

        def stop_preview_animation(self, clear_frames=True):
            self._preview_timer.stop()
            if self._active_preview_task_id and self.task_runner.is_running(self._active_preview_task_id):
                self.task_runner.cancel(self._active_preview_task_id)
            self._active_preview_task_id = None
            self.image_canvas.clear_preview_overlay()
            if clear_frames:
                self._preview_frames = []
                self._preview_duration = 50
                self._preview_index = 0

        def paste_image(self):
            try:
                clipboard_content = ImageGrab.grabclipboard()
            except Exception as exc:
                self.show_error("Colar imagem", f"Falha ao acessar a área de transferência: {exc}")
                return

            if not isinstance(clipboard_content, Image.Image):
                self.show_warning("Colar imagem", "Nenhuma imagem encontrada na área de transferência.")
                return

            temp_dir = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp", "CustomMakerPaste")
            os.makedirs(temp_dir, exist_ok=True)
            filename = f"pasted_{self._image_load_seq + len(self.editor_state.image_list) + 1}.png"
            path = os.path.join(temp_dir, filename)
            clipboard_content.save(path)
            self.add_images([path], replace=False, select_last=True)
            self.show_status("Imagem colada da área de transferência.")

        def save_all_images(self):
            if not self.editor_state.image_list:
                self.show_warning("Salvar", "Nenhuma imagem carregada.")
                return
            target_dir = self.choose_directory("Selecione a pasta para salvar")
            if not target_dir:
                return

            def task_fn(cancel_event, on_progress):
                return self.batch_controller.save_all_images(
                    target_dir,
                    progress_callback=on_progress,
                    cancel_event=cancel_event,
                )

            def on_done(result):
                lines = [
                    "Exportação concluída.",
                    self._format_count("Processadas", result.get("processed")),
                    self._format_count("Erros", result.get("errors")),
                    self._format_path("Destino", result.get("target_dir") or target_dir),
                ]
                self._show_result_summary("Salvar", lines, warning=bool(result.get("errors")))

            self.run_task(
                "qt_save_all_images",
                "Salvando imagens",
                task_fn,
                on_done=on_done,
                maximum=max(1, len(self.editor_state.image_list)),
            )

        def save_zip(self):
            if not self.editor_state.image_list:
                self.show_warning("ZIP", "Nenhuma imagem carregada.")
                return
            file_path = self.choose_save_file("Salvar ZIP", "Arquivos ZIP (*.zip)")
            if not file_path:
                return

            def task_fn(cancel_event, on_progress):
                return self.batch_controller.save_zip(
                    file_path,
                    progress_callback=on_progress,
                    cancel_event=cancel_event,
                )

            def on_done(result):
                lines = [
                    "ZIP gerado com sucesso.",
                    self._format_count("Arquivos escritos", result.get("written")),
                    self._format_count("Processadas", result.get("processed")),
                    self._format_count("Erros", result.get("errors")),
                    self._format_path("Arquivo", result.get("zip_path") or file_path),
                ]
                self._show_result_summary("ZIP", lines, warning=bool(result.get("errors")))

            self.run_task(
                "qt_save_zip",
                "Gerando ZIP",
                task_fn,
                on_done=on_done,
                maximum=max(1, len(self.editor_state.image_list)),
            )

        def upload_to_imgchest(self):
            if not self.editor_state.image_list:
                self.show_warning("Upload", "Nenhuma imagem carregada.")
                return
            album_title, ok = QInputDialog.getText(self, "Upload ImgChest", "Título do álbum:")
            if not ok:
                return
            album_title = album_title.strip() or "CustomMaker"

            def task_fn(cancel_event, on_progress):
                return self.batch_controller.upload_to_imgchest(
                    album_title,
                    progress_callback=on_progress,
                    cancel_event=cancel_event,
                )

            def on_done(result):
                links = result.get("links") or []
                errors = result.get("errors") or []
                lines = [
                    "Upload finalizado.",
                    self._format_count("Processadas", result.get("processed")),
                    self._format_count("Arquivos enviados", result.get("uploaded")),
                    self._format_count("Links retornados", len(links)),
                    self._format_count("Erros", len(errors)),
                ]
                if errors:
                    self._show_result_summary("Upload", lines, details=errors[:20], warning=not links)
                if links:
                    self._show_links_dialog(album_title, links)
                    if not errors:
                        self._show_result_summary("Upload", lines)
                elif not errors:
                    self.show_warning("Upload", "Nenhum link retornado.")

            self.run_task(
                "qt_upload_imgchest",
                "Enviando para ImgChest",
                task_fn,
                on_done=on_done,
                maximum=max(1, len(self.editor_state.image_list)),
            )

        def _show_links_dialog(self, title, links):
            dialog = QWidget(self, Qt.Dialog)
            dialog.setWindowTitle("Links de Upload")
            dialog.resize(540, 420)
            layout = QVBoxLayout(dialog)
            text = QPlainTextEdit(dialog)
            text.setReadOnly(True)
            text.setPlainText("\n".join(links))
            copy_button = QPushButton("Copiar comando", dialog)

            def copy_links():
                command = f"$ai {title} $\n" + " $\n".join(links)
                QGuiApplication.clipboard().setText(command)
                self.show_status("Comando copiado para a área de transferência.")

            copy_button.clicked.connect(copy_links)
            layout.addWidget(text)
            layout.addWidget(copy_button)
            dialog.show()

        def dragEnterEvent(self, event):
            if event.mimeData().hasUrls():
                event.acceptProposedAction()

        def dropEvent(self, event):
            paths = [url.toLocalFile() for url in event.mimeData().urls()]
            folders = [path for path in paths if os.path.isdir(path)]
            files = [path for path in paths if os.path.isfile(path)]
            if folders:
                folder = folders[0]
                folder_paths = [
                    os.path.join(folder, name)
                    for name in sorted(os.listdir(folder))
                    if os.path.isfile(os.path.join(folder, name)) and name.lower().endswith(SUPPORTED_EXTENSIONS)
                ]
                self.add_images(folder_paths, replace=True)
            elif files:
                self.add_images(files, replace=False, select_last=True)
            event.acceptProposedAction()

        def closeEvent(self, event):
            self.ui_preferences.last_global_borda = self.editor_state.selected_borda
            if self.editor_state.image_list:
                self.ui_preferences.last_folder = os.path.dirname(self.editor_state.image_list[0])
            self.ui_preferences.save_to_app_config(self.app_config)
            self.app_config.save()
            self.stop_preview_animation()
            self.online_tab.close()
            self._close_current_original()
            self._clear_preview_cache()
            for image in self.edited_images.values():
                try:
                    image.close()
                except Exception:
                    pass
            self.edited_images.clear()
            for stack in self._undo_stacks.values():
                for image, *_rest in stack:
                    self._dispose_images([image])
            self._undo_stacks.clear()
            super().closeEvent(event)
else:
    class QtMainWindow:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
