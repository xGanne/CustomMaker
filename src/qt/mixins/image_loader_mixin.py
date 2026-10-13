"""
ImageLoaderMixin — cache de imagens, pipeline de carregamento e pilha de undo.

Responsabilidades:
  • LRU cache de previews em memória
  • Dispose seguro de objetos PIL
  • Carregamento assíncrono de imagens do disco
  • Adição/substituição de imagens na lista de trabalho
  • Pilha de undo por imagem (até 20 snapshots)
"""
import os

from PIL import Image

from src.config.settings import BORDA_HEX, SUPPORTED_EXTENSIONS
from src.core.image_processor import ImageProcessor


class ImageLoaderMixin:

    # ── Cache de preview ───────────────────────────────────────────────────

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

    # ── Gerenciamento de recursos PIL ──────────────────────────────────────

    def _close_current_original(self):
        if self.current_original_image is not None:
            try:
                self.current_original_image.close()
            except Exception:
                pass
            self.current_original_image = None

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

    # ── Pipeline de carregamento ───────────────────────────────────────────

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
            for stack in self._redo_stack_map().values():
                for redo_image, *_rest in stack:
                    self._dispose_images([redo_image])
            self._redo_stack_map().clear()
            self._clear_preview_cache()

        for path in valid_paths:
            if path not in self.editor_state.image_list:
                self.editor_state.image_list.append(path)

        self.image_list_panel.set_paths(self.editor_state.image_list)

        if valid_paths:
            self.ui_preferences.last_folder = os.path.dirname(valid_paths[0])

        if not self.editor_state.image_list:
            self.current_path = None
            self.image_canvas.set_loading(False)
            self.image_canvas.clear_image()
            return

        if select_last and valid_paths:
            target_index = self.editor_state.image_list.index(valid_paths[-1])
        elif self.editor_state.current_image_index is not None:
            target_index = self.editor_state.current_image_index
        else:
            target_index = 0
        self.load_image(target_index)

    def load_folder(self, folder=None):
        if not folder:
            folder = self.choose_directory("Selecione a pasta de imagens")
        if not folder:
            return
        paths = [
            os.path.join(folder, name)
            for name in sorted(os.listdir(folder))
            if os.path.isfile(os.path.join(folder, name)) and name.lower().endswith(SUPPORTED_EXTENSIONS)
        ]
        self.add_images(paths, replace=True)
        self._push_recent_folder(folder)
        self.show_status(f"{len(paths)} imagem(ns) carregada(s).")

    def _push_recent_folder(self, folder):
        recent = list(self.app_config.get("recent_folders") or [])
        if folder in recent:
            recent.remove(folder)
        recent.insert(0, folder)
        self.app_config.set("recent_folders", recent[:8])
        self.app_config.save()

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

    def _natural_size_for(self, path):
        """M8: tamanho em pixels da fonte da exportação (referência do zoom 100%).

        Edição de pixels vira a nova fonte; senão vale o arquivo original — lido
        só do cabeçalho e memorizado, sem decodificar a imagem."""
        edited = self.edited_images.get(path)
        if edited is not None:
            return edited.size
        cache = self.__dict__.setdefault("_natural_size_cache", {})
        if path not in cache:
            try:
                with Image.open(path) as source:
                    cache[path] = source.size
            except Exception:
                return None
        return cache[path]

    def set_edited_image_for_current(self, image):
        if not self.current_path:
            return
        previous = self.edited_images.get(self.current_path)
        self.edited_images[self.current_path] = image.copy()
        if previous is not None and previous is not image:
            self._dispose_images([previous])
        self.editor_state.mark_pixels_edited(self.current_path)
        self._remember_preview_cache(self.current_path, self.edited_images[self.current_path])
        state = self.editor_state.image_states.get(self.current_path)
        self.image_canvas.set_image(
            self.edited_images[self.current_path],
            state=state,
            border_color=self.editor_state.resolve_border_hex(BORDA_HEX, self.current_path),
            natural_size=self._natural_size_for(self.current_path),
        )
        self._update_preview_animation()
        if hasattr(self, "refresh_list_indicators"):
            self.refresh_list_indicators()

    def load_image(self, index):
        if index is None or index < 0 or index >= len(self.editor_state.image_list):
            return

        path = self.editor_state.image_list[index]
        self._close_current_original()
        self.current_path = path
        self.editor_state.current_image_index = index
        self.image_list_panel.set_current_index(index)
        self._update_image_counter()
        self.editor_state.borda_pos = self.image_canvas.border_pos
        self.editor_tab.refresh_from_state()
        display_image = self.edited_images.get(path) or self._get_preview_cache_copy(path)
        # M4: sem nada em cache o canvas fica vazio até o disco responder —
        # indicar o carregamento em vez de exibir a orientação de canvas vazio
        self.image_canvas.set_loading(display_image is None)
        if display_image is not None:
            state = self._ensure_state_for_current(display_image)
            self.image_canvas.set_image(
                display_image,
                state=state,
                border_color=self.editor_state.resolve_border_hex(BORDA_HEX, path),
                natural_size=self._natural_size_for(path),
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
        # M11: o enquadramento padrão de uma imagem nova é calculado no worker —
        # o modo inteligente roda detecção de rosto, cara demais para a GUI thread
        needs_default_fit = path not in self.editor_state.image_states
        framing_mode = self.editor_state.default_framing
        borda_pos = tuple(self.editor_state.borda_pos)
        face_cascade = self.face_cascade

        def task_fn(cancel_event, _on_progress):
            result = self._build_image_load_result(index, path, preview_max_dim, include_preview, cancel_event)
            result["task_id"] = task_id
            if needs_default_fit and not result.get("cancelled"):
                fit_source = result.get("preview") or result.get("original")
                if fit_source is not None:
                    result["default_fit"] = ImageProcessor.calculate_default_fit(
                        fit_source, borda_pos, framing_mode, face_cascade
                    )
            return result

        def on_done(result):
            if result.get("task_id") != self._active_image_load_task_id:
                self._dispose_image_load_result(result)
                return
            self._active_image_load_task_id = None
            self.image_canvas.set_loading(False)
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
                state = self._ensure_state_for_current(refreshed_image, default_fit=result.get("default_fit"))
                self.image_canvas.set_image(
                    refreshed_image,
                    state=state,
                    border_color=self.editor_state.resolve_border_hex(BORDA_HEX, path),
                    natural_size=self._natural_size_for(path),
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
                self.image_canvas.set_loading(False)
            self.show_error("Erro", f"Falha ao carregar imagem: {exc}")

        handle = self.task_runner.submit(task_id, task_fn)
        if handle is None:
            self._active_image_load_task_id = None
            self.image_canvas.set_loading(False)
            self.show_warning("Carregamento", "Não foi possível iniciar o carregamento da imagem.")
            return
        handle.done.connect(on_done)
        handle.error.connect(on_error)
        self.show_status(f"Carregando: {os.path.basename(path)}")

    # ── Pilhas de undo/redo ───────────────────────────────────────────────

    def _redo_stack_map(self):
        if not hasattr(self, "_redo_stacks"):
            self._redo_stacks = {}
        return self._redo_stacks

    def _capture_current_snapshot(self):
        """Snapshot (imagem, pos, size, tinha_pixels_editados) do estado atual."""
        if not self.current_path:
            return None
        image = self.get_active_image_copy()
        if image is None:
            return None
        state = self.editor_state.image_states.get(self.current_path) or self._ensure_state_for_current(image)
        return (
            image,
            tuple(state.get("pos", self.editor_state.borda_pos)),
            tuple(state.get("size", image.size)),
            self.current_path in self.edited_images,
        )

    def _drop_redo_stack(self, path):
        for image, *_rest in self._redo_stack_map().pop(path, []):
            self._dispose_images([image])

    def save_state_for_undo(self):
        if not self.current_path:
            return
        snapshot = self._capture_current_snapshot()
        if snapshot is None:
            return
        stack = self._undo_stacks.setdefault(self.current_path, [])
        stack.append(snapshot)
        while len(stack) > 20:
            old_image, *_rest = stack.pop(0)
            self._dispose_images([old_image])
        # F15: uma nova ação do usuário invalida o redo
        self._drop_redo_stack(self.current_path)

    def _apply_snapshot(self, snapshot):
        image, pos, size, was_pixel_edited = snapshot
        path = self.current_path
        previous = self.edited_images.pop(path, None)
        if previous is not None:
            self._dispose_images([previous])
        if was_pixel_edited:
            # F15: só volta para edited_images se o estado restaurado tinha
            # edição de pixels — senão o indicador "editada" ficava para sempre
            self.edited_images[path] = image.copy()
        self._remember_preview_cache(path, image)
        self.editor_state.set_image_state(path, pos, size)
        self.image_canvas.set_image(
            image,
            state={"pos": pos, "size": size},
            border_color=self.editor_state.resolve_border_hex(BORDA_HEX, path),
            natural_size=self._natural_size_for(path),
        )
        self._dispose_images([image])
        self._update_preview_animation()
        if hasattr(self, "refresh_list_indicators"):
            self.refresh_list_indicators()

    def undo_current_image(self):
        if not self.current_path:
            return
        stack = self._undo_stacks.get(self.current_path) or []
        if not stack:
            self.show_status("Nada para desfazer.")
            return
        current = self._capture_current_snapshot()
        if current is not None:
            self._redo_stack_map().setdefault(self.current_path, []).append(current)
        self._apply_snapshot(stack.pop())
        self.show_status("Última alteração desfeita.")

    def redo_current_image(self):
        if not self.current_path:
            return
        stack = self._redo_stack_map().get(self.current_path) or []
        if not stack:
            self.show_status("Nada para refazer.")
            return
        current = self._capture_current_snapshot()
        if current is not None:
            self._undo_stacks.setdefault(self.current_path, []).append(current)
        self._apply_snapshot(stack.pop())
        self.show_status("Alteração refeita.")

    def _ensure_state_for_current(self, image, default_fit=None):
        if not self.current_path:
            return None
        state = self.editor_state.image_states.get(self.current_path)
        if state:
            return state
        # default_fit vem do worker de carregamento (M11); sem ele, o fallback
        # síncrono é sempre o auto fit, barato o bastante para a GUI thread
        fit = default_fit or ImageProcessor.calculate_auto_fit_pos(image, self.editor_state.borda_pos)
        if fit:
            new_w, new_h, pos_x, pos_y = fit
            state = {"pos": (pos_x, pos_y), "size": (new_w, new_h)}
        else:
            state = {"pos": self.editor_state.borda_pos, "size": image.size}
        self.editor_state.image_states[self.current_path] = state
        return state
