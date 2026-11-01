"""
ImageLoaderMixin — cache de imagens, pipeline de carregamento e pilha de undo.

Responsabilidades:
  • LRU cache de previews em memória
  • Dispose seguro de objetos PIL
  • Carregamento assíncrono de imagens do disco
  • Adição/substituição de imagens na lista de trabalho
  • Pilha de undo por imagem (até 20 snapshots)
"""
import logging
import os

from PIL import Image

from src.config.settings import BORDA_HEX, SUPPORTED_EXTENSIONS
from src.core.history import Snapshot
from src.core.image_processor import ImageProcessor


logger = logging.getLogger(__name__)


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

    def _drop_preview_cache(self, path):
        image = self._preview_cache.pop(path, None)
        if image is not None:
            self._preview_cache_current_bytes = max(
                0, self._preview_cache_current_bytes - self._estimate_image_bytes(image)
            )
            self._dispose_images([image])

    def _display_image_for(self, path):
        """Imagem para a tela (sempre uma prévia reduzida, dona do chamador).

        Imagem editada (rotação, IA) também: a cópia em resolução cheia fica só
        em edited_images, para o export. Antes o canvas e o cache de prévias
        guardavam a imagem editada inteira — ~290 MB para exibir uma foto de
        24 MP rotacionada, e o cache empurrava as outras imagens para fora.
        """
        cached = self._get_preview_cache_copy(path)
        if cached is not None:
            return cached
        edited = self.edited_images.get(path)
        if edited is None:
            return None
        max_dim = self._preview_max_dimension()
        preview = ImageProcessor.resize_image(edited, max_dim, max_dim)
        if preview is edited:
            preview = edited.copy()
        self._remember_preview_cache(path, preview)
        return preview

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

    def _window_alive(self):
        """False se a janela já fechou (ou o objeto C++ foi destruído) — tasks em
        segundo plano não devem mais mexer na interface."""
        try:
            return bool(self.isVisible()) or not getattr(self, "_closing", False)
        except RuntimeError:
            return False

    # ── Pipeline de carregamento ───────────────────────────────────────────

    def _preview_max_dimension(self):
        viewport = self.image_canvas.viewport().size()
        base = max(viewport.width(), viewport.height(), 900)
        return max(1000, min(2400, base * 2))

    @staticmethod
    def _decode_preview(path, max_dim):
        """Prévia para a tela, sem decodificar o original inteiro.

        O JPEG é decodificado já reduzido (draft: 1/2, 1/4, 1/8, sempre >= o
        tamanho pedido) e então redimensionado: numa foto de 24 MP isso evita
        decodificar 96 MB a cada troca de imagem. O original em resolução cheia
        só é carregado quando preciso (rotação, IA) — ver _full_original.
        """
        with Image.open(path) as source:
            source.draft(source.mode, (max_dim, max_dim))
            decoded = source.convert("RGBA")
        preview = ImageProcessor.resize_image(decoded, max_dim, max_dim)
        if preview is not decoded:
            decoded.close()
        return preview

    def _build_image_load_result(self, index, path, preview_max_dim, include_preview, cancel_event):
        if cancel_event and cancel_event.is_set():
            return {"cancelled": True, "index": index, "path": path}

        preview = self._decode_preview(path, preview_max_dim) if include_preview else None

        if cancel_event and cancel_event.is_set():
            self._dispose_image_load_result({"preview": preview})
            return {"cancelled": True, "index": index, "path": path}

        return {
            "cancelled": False,
            "index": index,
            "path": path,
            "preview": preview,
        }

    def _full_original(self):
        """Original da imagem atual em resolução cheia, decodificado só agora."""
        if self.current_original_image is None and self.current_path:
            try:
                with Image.open(self.current_path) as source:
                    self.current_original_image = source.convert("RGBA")
            except Exception as exc:
                logger.warning("Não foi possível abrir %s: %s", self.current_path, exc)
                return None
        return self.current_original_image

    def add_images(self, paths, replace=False, select_last=False):
        valid_paths = []
        for path in paths:
            if not path:
                continue
            lower_path = path.lower()
            if os.path.isfile(path) and lower_path.endswith(SUPPORTED_EXTENSIONS):
                valid_paths.append(path)

        if replace:
            self._reset_workspace()

        new_paths = []
        for path in valid_paths:
            if path not in self.editor_state.image_list:
                self.editor_state.image_list.append(path)
                new_paths.append(path)

        self.image_list_panel.set_paths(self.editor_state.image_list)

        if valid_paths:
            self.ui_preferences.last_folder = os.path.dirname(valid_paths[0])

        if not self.editor_state.image_list:
            self.current_path = None
            self.image_canvas.set_loading(False)
            self.image_canvas.clear_image()
            return

        self._precompute_default_framing(new_paths)

        if select_last and valid_paths:
            target_index = self.editor_state.image_list.index(valid_paths[-1])
        elif self.editor_state.current_image_index is not None:
            target_index = self.editor_state.current_image_index
        else:
            target_index = 0
        self.load_image(target_index)

    # ── Enquadramento padrão calculado ao importar ─────────────────────────

    _precompute_seq = 0

    def _precompute_default_framing(self, paths):
        """Calcula em segundo plano o enquadramento padrão das imagens novas.

        Navegar e exportar passam a usar o mesmo enquadramento, já pronto. O
        resultado é guardado relativo à borda (a janela pode ser redimensionada
        durante o cálculo) e nunca sobrescreve um ajuste do usuário.
        """
        pending = [p for p in paths if p not in self.editor_state.image_states]
        if not pending:
            return
        mode = self.editor_state.default_framing
        face_cascade = self.face_cascade if mode == "intelligent" else None
        reference = tuple(self.editor_state.borda_pos)
        # troca de modo no meio do cálculo invalida o resultado deste lote
        generation = getattr(self, "_framing_generation", 0)
        type(self)._precompute_seq += 1
        task_id = f"qt_precompute_framing_{self._precompute_seq}"

        def task_fn(cancel_event, _on_progress):
            fits = {}
            for path in pending:
                if cancel_event and cancel_event.is_set():
                    break
                try:
                    with Image.open(path) as source:
                        # só a proporção e a posição do rosto importam aqui:
                        # decodificar reduzido basta (JPEG) e é bem mais rápido
                        source.draft(source.mode, (1000, 1000))
                        image = source.convert("RGB")
                    fit = ImageProcessor.calculate_default_fit(image, reference, mode, face_cascade)
                    image.close()
                except Exception as exc:  # arquivo ilegível: o editor tenta de novo ao abrir
                    logger.debug("Enquadramento prévio falhou para %s: %s", path, exc)
                    continue
                if fit:
                    new_w, new_h, pos_x, pos_y = fit
                    fits[path] = ((pos_x - reference[0], pos_y - reference[1]), (new_w, new_h))
            return fits

        def on_done(fits):
            if generation != getattr(self, "_framing_generation", 0):
                return  # calculado no modo anterior
            bx, by = self.editor_state.borda_pos
            changed = False
            for path, ((rel_x, rel_y), size) in fits.items():
                if path not in self.editor_state.image_list:
                    continue
                pos = (bx + rel_x, by + rel_y)
                if self.editor_state.set_auto_state(path, pos, size):
                    changed = True
                    if path == self.current_path and self.image_canvas.image_item is not None:
                        # imagem na tela sem ajuste do usuário: mostra o novo enquadramento
                        self.image_canvas.set_image_state(pos, size)
            if changed and hasattr(self, "refresh_list_indicators"):
                self.refresh_list_indicators()

        handle = self.task_runner.submit(task_id, task_fn)
        if handle is not None:
            handle.done.connect(on_done)

    def _reset_workspace(self):
        """Esvazia a lista e libera tudo que estava em memória para ela."""
        self.editor_state.reset_images()
        self.stop_preview_animation()
        for image in self.edited_images.values():
            try:
                image.close()
            except Exception:
                pass
        self.edited_images.clear()
        for stack in self._undo_stacks.values():
            self._dispose_images([snapshot.image for snapshot in stack])
        self._undo_stacks.clear()
        self._history_ops().clear()
        for stack in self._redo_stack_map().values():
            self._dispose_images([snapshot.image for snapshot in stack])
        self._redo_stack_map().clear()
        self._clear_preview_cache()
        if getattr(self, "render_cache", None) is not None:
            self.render_cache.clear()
        self.__dict__.pop("_edit_versions", None)
        self.__dict__.pop("_edit_rotation", None)

    def load_folder(self, folder=None):
        if not folder:
            folder = self.choose_directory("Selecione a pasta de imagens")
        if not folder:
            return
        from src.core.image_files import list_folder_images
        paths = list_folder_images(folder)
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
        """Cópia em resolução cheia da imagem atual (edição de IA): carrega o
        original sob demanda."""
        if not self.current_path:
            return None
        image = self.edited_images.get(self.current_path) or self._full_original()
        if image is None:
            return self._get_preview_cache_copy(self.current_path)
        return image.copy()

    def get_framing_image(self):
        """Imagem para calcular enquadramento (auto fit, rosto): a prévia basta —
        o cálculo depende só das proporções e da posição do rosto, não da
        resolução — e a detecção de rosto fica bem mais rápida que no original."""
        if not self.current_path:
            return None
        return self._get_preview_cache_copy(self.current_path) or self.get_active_image_copy()

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

    def _bump_edit_version(self, path):
        """Edição de pixels mudou a fonte da imagem sem mudar o caminho (cache da Revisão)."""
        versions = self.__dict__.setdefault("_edit_versions", {})
        versions[path] = versions.get(path, 0) + 1

    def _drop_pixel_edit_for_current(self):
        """A imagem atual volta a ser o próprio arquivo (sem edição de pixels)."""
        path = self.current_path
        if not path:
            return
        self._dispose_images([self.edited_images.pop(path, None)])
        self._edit_rotations().pop(path, None)
        self._bump_edit_version(path)
        self.editor_state.mark_pixels_edited(path)  # mudou desde o último export
        self._drop_preview_cache(path)
        display = self._original_display_image(path)
        if display is not None:
            self.image_canvas.set_image(
                display,
                state=self.editor_state.image_states.get(path),
                border_color=self.editor_state.resolve_border_hex(BORDA_HEX, path),
                natural_size=self._natural_size_for(path),
            )
            self._dispose_images([display])
        self._update_preview_animation()
        if hasattr(self, "refresh_list_indicators"):
            self.refresh_list_indicators()

    def set_edited_image_for_current(self, image, rotation=None):
        """Imagem editada (rotação, IA). `rotation`: graus em relação ao original
        quando a edição é só rotação — o desfazer refaz a imagem sem guardar cópia."""
        if not self.current_path:
            return
        if rotation is not None:
            self._edit_rotations()[self.current_path] = rotation % 360
        else:
            self._edit_rotations().pop(self.current_path, None)
        previous = self.edited_images.get(self.current_path)
        self.edited_images[self.current_path] = image.copy()
        self._bump_edit_version(self.current_path)
        if previous is not None and previous is not image:
            self._dispose_images([previous])
        self.editor_state.mark_pixels_edited(self.current_path)
        self._drop_preview_cache(self.current_path)  # a prévia antiga é de antes da edição
        display = self._display_image_for(self.current_path)
        state = self.editor_state.image_states.get(self.current_path)
        self.image_canvas.set_image(
            display,
            state=state,
            border_color=self.editor_state.resolve_border_hex(BORDA_HEX, self.current_path),
            natural_size=self._natural_size_for(self.current_path),
        )
        self._dispose_images([display])
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
        # passa pelo mesmo ajuste do resize: se a borda tiver mudado, os
        # enquadramentos salvos acompanham o deslocamento
        self.on_border_pos_changed(self.image_canvas.border_pos)
        self.editor_tab.refresh_from_state()
        display_image = self._display_image_for(path)
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
            self._dispose_images([display_image])  # o canvas guarda a própria cópia
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
        # prévia em cache: o enquadramento padrão (se faltar) usa uma cópia dela
        fit_copy = None if include_preview or path in self.editor_state.image_states else self._get_preview_cache_copy(path)
        # M11: o enquadramento padrão de uma imagem nova é calculado no worker —
        # o modo inteligente roda detecção de rosto, cara demais para a GUI thread
        needs_default_fit = path not in self.editor_state.image_states
        framing_mode = self.editor_state.default_framing
        borda_pos = tuple(self.editor_state.borda_pos)
        face_cascade = self.face_cascade

        def task_fn(cancel_event, _on_progress):
            result = self._build_image_load_result(index, path, preview_max_dim, include_preview, cancel_event)
            result["task_id"] = task_id
            try:
                if needs_default_fit and not result.get("cancelled"):
                    fit_source = result.get("preview") or fit_copy
                    if fit_source is not None:
                        result["default_fit"] = ImageProcessor.calculate_default_fit(
                            fit_source, borda_pos, framing_mode, face_cascade
                        )
            finally:
                if fit_copy is not None:
                    fit_copy.close()
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

            # o original em resolução cheia não é carregado aqui (só sob demanda)
            preview = result.get("preview")
            if preview is not None:
                self._remember_preview_cache(path, preview)
                try:
                    preview.close()
                except Exception:
                    pass

            refreshed_image = self._display_image_for(path)

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
            # carregamento em segundo plano: a janela pode já ter fechado, e um
            # diálogo modal sobre uma janela destruída corrompia o heap. Erro de
            # navegação vai para a status bar (M1), sem interromper o fluxo.
            if not self._window_alive():
                return
            if task_id == self._active_image_load_task_id:
                self._active_image_load_task_id = None
                self.image_canvas.set_loading(False)
            self.show_status(f"Falha ao carregar {os.path.basename(path)}: {exc}", timeout_ms=10000)

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

    def _capture_current_snapshot(self, label=""):
        """Snapshot do estado atual da imagem.

        A imagem só é guardada quando há edição de pixels (rotação, IA): gestos
        de enquadramento não mudam os pixels, e copiar o original a cada arrasto
        custava ~97 MB por gesto numa imagem de 24 MP. None = arquivo original.
        """
        if not self.current_path:
            return None
        edited = self.edited_images.get(self.current_path)
        state = self.editor_state.image_states.get(self.current_path)
        if state is None:
            reference = edited or self.current_original_image or self._preview_cache.get(self.current_path)
            if reference is None:
                return None
            state = self._ensure_state_for_current(reference)
        rotation = self._edit_rotations().get(self.current_path) if edited is not None else None
        return Snapshot(
            # só rotação: os graus refazem a imagem; edição de IA: precisa da cópia
            image=edited.copy() if edited is not None and rotation is None else None,
            pos=tuple(state["pos"]),
            size=tuple(state["size"]),
            pixel_edited=edited is not None,
            label=label,
            adjustments=dict(self.editor_state.image_adjustments.get(self.current_path, {})),
            rotation=rotation,
        )

    def _edit_rotations(self):
        """Graus aplicados ao original nas imagens cuja edição é só rotação."""
        return self.__dict__.setdefault("_edit_rotation", {})

    def _original_display_image(self, path):
        """Preview do arquivo original (para desfazer até antes de uma edição de pixels)."""
        preview_max_dim = self._preview_max_dimension()
        try:
            preview = self._decode_preview(path, preview_max_dim)
        except Exception as exc:
            logger.warning("Não foi possível recarregar o original de %s: %s", path, exc)
            return None
        self._remember_preview_cache(path, preview)
        return preview

    def _drop_redo_stack(self, path):
        self._dispose_images([snapshot.image for snapshot in self._redo_stack_map().pop(path, [])])

    def save_state_for_undo(self, label=""):
        if not self.current_path:
            return
        self._push_undo(self.current_path, self._capture_current_snapshot(label))

    def save_state_for_undo_of(self, path, label=""):
        """Passo de desfazer para uma imagem que não está na tela (ações em
        lote, como "Aplicar a todas"). Sem ele, desfazer um passo antigo dessa
        imagem desfazia junto, e calado, a ação em lote."""
        if path == self.current_path:
            self.save_state_for_undo(label)
            return
        state = self.editor_state.image_states.get(path)
        if not state:
            return  # nunca enquadrada: não há estado anterior a guardar
        edited = self.edited_images.get(path)
        rotation = self._edit_rotations().get(path) if edited is not None else None
        self._push_undo(path, Snapshot(
            image=edited.copy() if edited is not None and rotation is None else None,
            pos=tuple(state["pos"]),
            size=tuple(state["size"]),
            pixel_edited=edited is not None,
            label=label,
            adjustments=dict(self.editor_state.image_adjustments.get(path, {})),
            rotation=rotation,
        ))

    def _push_undo(self, path, snapshot):
        if snapshot is None:
            return
        stack = self._undo_stacks.setdefault(path, [])
        if stack and self._same_state(stack[-1], snapshot):
            # a ação anterior não mudou nada (ex.: clique na imagem sem arrastar):
            # o passo vazio dá lugar a este, em vez de virar um "Mover" fantasma
            self._dispose_images([stack.pop().image])
        stack.append(snapshot)
        while len(stack) > 20:
            self._dispose_images([stack.pop(0).image])
        self._enforce_undo_budget()
        # F15: uma nova ação do usuário invalida o redo
        self._drop_redo_stack(path)
        self._history_ops()[path] = "edit"

    UNDO_IMAGE_BUDGET_BYTES = 512 * 1024 * 1024

    def _enforce_undo_budget(self):
        """Cópias de imagem no histórico (edições de IA) somam no máximo
        UNDO_IMAGE_BUDGET_BYTES: acima disso, saem os passos mais antigos."""
        stacks = [self._undo_stacks, self._redo_stack_map()]

        def total():
            return sum(
                self._estimate_image_bytes(s.image)
                for group in stacks for stack in group.values() for s in stack if s.image is not None
            )

        used = total()
        while used > self.UNDO_IMAGE_BUDGET_BYTES:
            candidates = [st for st in self._undo_stacks.values() if any(s.image is not None for s in st)]
            if not candidates:
                break
            # a pilha com a cópia mais antiga perde passos do fundo até liberar uma cópia
            stack = min(candidates, key=lambda st: next(s.timestamp for s in st if s.image is not None))
            while stack:
                dropped = stack.pop(0)
                if dropped.image is not None:
                    used -= self._estimate_image_bytes(dropped.image)
                    self._dispose_images([dropped.image])
                    break

    @staticmethod
    def _same_state(a, b):
        """Mesmo enquadramento e sem edição de pixels nos dois (imagem original)."""
        return (
            not a.pixel_edited and not b.pixel_edited
            and tuple(a.pos) == tuple(b.pos) and tuple(a.size) == tuple(b.size)
            and a.adjustments == b.adjustments
        )

    def _drop_noop_undo_steps(self, path):
        """Descarta do topo do undo os passos iguais ao estado atual (a última
        "ação" não mudou nada): desfazer/alternar sempre mostram uma diferença."""
        stack = self._undo_stacks.get(path)
        state = self.editor_state.image_states.get(path)
        if not stack or not state:
            return
        # compara sem capturar (capturar copiaria a imagem editada à toa)
        current = Snapshot(
            None, tuple(state["pos"]), tuple(state["size"]), path in self.edited_images,
            adjustments=dict(self.editor_state.image_adjustments.get(path, {})),
        )
        while stack and self._same_state(stack[-1], current):
            self._dispose_images([stack.pop().image])

    def _history_ops(self):
        """Última operação de histórico por imagem: "edit", "undo" ou "redo"."""
        return self.__dict__.setdefault("_last_history_op", {})

    def _rename_last_undo_step(self, label):
        """Renomeia o passo recém-empilhado (o nome final só se sabe depois da ação)."""
        stack = self._undo_stacks.get(self.current_path) if self.current_path else None
        if stack:
            stack[-1].label = label

    def _apply_snapshot(self, snapshot):
        image, pos, size, was_pixel_edited = snapshot.image, snapshot.pos, snapshot.size, snapshot.pixel_edited
        path = self.current_path
        self.editor_state.set_image_adjustments(path, snapshot.adjustments)
        currently_edited = path in self.edited_images
        if not was_pixel_edited and not currently_edited:
            # só o enquadramento muda: a imagem na tela continua a mesma
            self.editor_state.set_image_state(path, pos, size)
            self.image_canvas.set_image_state(pos, size)
            if hasattr(self, "refresh_list_indicators"):
                self.refresh_list_indicators()
            if hasattr(self, "_on_adjustments_restored"):
                self._on_adjustments_restored()
            return

        previous = self.edited_images.pop(path, None)
        if previous is not None:
            self._dispose_images([previous])
        owned_display = None
        rebuilt = None
        if was_pixel_edited and image is None and snapshot.rotation is not None:
            original = self._full_original()
            if original is not None:
                rebuilt = original.rotate(snapshot.rotation, expand=True) if snapshot.rotation else original.copy()
        if was_pixel_edited and (image is not None or rebuilt is not None):
            # F15: só volta para edited_images se o estado restaurado tinha
            # edição de pixels — senão o indicador "editada" ficava para sempre
            self.edited_images[path] = rebuilt if rebuilt is not None else image.copy()
            if snapshot.rotation is not None:
                self._edit_rotations()[path] = snapshot.rotation
            else:
                self._edit_rotations().pop(path, None)
            self._bump_edit_version(path)
            self._drop_preview_cache(path)
            display = owned_display = self._display_image_for(path)
        else:
            self._edit_rotations().pop(path, None)  # voltou ao arquivo original
            display = owned_display = self._original_display_image(path)
        self._dispose_images([image])
        self.editor_state.set_image_state(path, pos, size)
        if display is not None:
            self.image_canvas.set_image(
                display,
                state={"pos": pos, "size": size},
                border_color=self.editor_state.resolve_border_hex(BORDA_HEX, path),
                natural_size=self._natural_size_for(path),
            )
        self._dispose_images([owned_display])
        self._update_preview_animation()
        if hasattr(self, "refresh_list_indicators"):
            self.refresh_list_indicators()
        if hasattr(self, "_on_adjustments_restored"):
            self._on_adjustments_restored()

    def undo_current_image(self):
        if not self.current_path:
            return
        self._drop_noop_undo_steps(self.current_path)
        stack = self._undo_stacks.get(self.current_path) or []
        if not stack:
            self.show_status("Nada para desfazer.")
            return False
        target = stack.pop()
        # o estado atual vai para o redo com o nome (e o horário) da mesma ação, agora refazível
        current = self._capture_current_snapshot(target.label)
        if current is not None:
            current.timestamp = target.timestamp
            self._redo_stack_map().setdefault(self.current_path, []).append(current)
        self._apply_snapshot(target)
        self._history_ops()[self.current_path] = "undo"
        self.show_status(f"Desfeito: {target.label}" if target.label else "Última alteração desfeita.")
        return True

    def redo_current_image(self):
        if not self.current_path:
            return
        stack = self._redo_stack_map().get(self.current_path) or []
        if not stack:
            self.show_status("Nada para refazer.")
            return False
        target = stack.pop()
        current = self._capture_current_snapshot(target.label)
        if current is not None:
            current.timestamp = target.timestamp
            self._undo_stacks.setdefault(self.current_path, []).append(current)
        self._apply_snapshot(target)
        self._history_ops()[self.current_path] = "redo"
        self.show_status(f"Refeito: {target.label}" if target.label else "Alteração refeita.")
        return True

    def _comparing_original(self):
        """Antes/depois (B) ativo: o canvas mostra o original por cima do estado."""
        return bool(getattr(self.image_canvas, "_before_after_active", False))

    def toggle_last_state(self):
        """Ctrl+Alt+Z: alterna entre o estado atual e o anterior (Toggle Last State).

        Depois de uma edição, desfaz; depois de um desfazer, refaz — apertar de
        novo volta, para comparar "como estava" e "como ficou".
        """
        path = self.current_path
        if not path or self._comparing_original():
            return
        self._drop_noop_undo_steps(path)
        can_redo = bool(self._redo_stack_map().get(path))
        if self._history_ops().get(path) == "undo" and can_redo:
            done = self.redo_current_image()
        elif self._undo_stacks.get(path):
            done = self.undo_current_image()
        else:
            self.show_status("Nada para comparar.")
            return
        if done:
            self.show_status("Comparando com o passo anterior — Ctrl+Alt+Z de novo para voltar.", timeout_ms=6000)

    def jump_history(self, steps):
        """Volta (steps < 0) ou avança (steps > 0) vários passos de uma vez.

        Equivale a |steps| desfazer/refazer seguidos, mas só o estado final é
        aplicado no canvas: pular 15 passos custa o mesmo que 1, e nenhuma
        imagem intermediária é copiada.
        """
        path = self.current_path
        if not path or not steps or self._comparing_original():
            return
        if steps < 0:
            self._drop_noop_undo_steps(path)
        undo = self._undo_stacks.setdefault(path, [])
        redo = self._redo_stack_map().setdefault(path, [])
        source, target_stack = (undo, redo) if steps < 0 else (redo, undo)
        count = min(abs(steps), len(source))
        if not count:
            return
        current = self._capture_current_snapshot(source[-1].label)
        if current is not None:
            current.timestamp = source[-1].timestamp
            target_stack.append(current)
        for _ in range(count - 1):
            moved = source.pop()
            # como num desfazer/refazer avulso: o estado que muda de pilha leva o
            # nome (e o horário) da ação que fica entre ele e o próximo alvo
            moved.label, moved.timestamp = source[-1].label, source[-1].timestamp
            target_stack.append(moved)
        target = source.pop()
        self._apply_snapshot(target)
        self._history_ops()[path] = "undo" if steps < 0 else "redo"
        verb = "Voltou" if steps < 0 else "Avançou"
        self.show_status(f"{verb} {count} passo(s) no histórico.")

    def clear_history(self):
        """Descarta desfazer/refazer da imagem atual (libera as cópias guardadas)."""
        path = self.current_path
        if not path:
            return
        self._dispose_images([s.image for s in self._undo_stacks.pop(path, [])])
        self._drop_redo_stack(path)
        self._history_ops().pop(path, None)
        self.show_status("Histórico desta imagem limpo.")

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
            pos, size = (pos_x, pos_y), (new_w, new_h)
        else:
            pos, size = self.editor_state.borda_pos, image.size
        self.editor_state.set_auto_state(self.current_path, pos, size)
        return self.editor_state.image_states[self.current_path]
