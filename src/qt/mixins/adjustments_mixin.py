"""
AdjustmentsMixin — ajustes visuais de imagem: fit, rotação, presets e estilos.

Responsabilidades:
  • Auto fit e ajuste inteligente (detecção de rosto) por imagem individual
  • Aplicação em lote de ajustes de enquadramento
  • Rotação de imagem com refit automático
  • Aplicação de presets de borda/animação
  • Propagação de borda/animação para todas as imagens da lista
"""
from PIL import Image

from src.config.settings import BORDA_HEX
from src.core.image_processor import ImageProcessor


class AdjustmentsMixin:

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
        if self.face_cascade is None:
            # M17: o atalho Alt+F continua ativo mesmo com o botão desabilitado
            self.show_status("Detecção de rosto indisponível — aplicando auto fit.")
            self.apply_auto_fit(push_undo=push_undo)
            return
        if push_undo:
            self.save_state_for_undo()
        faces = ImageProcessor.detect_faces_ranked(image, self.face_cascade)
        if not faces:
            self.show_warning("Ajuste", "Nenhum rosto detectado. Aplicando auto fit.")
            self.apply_auto_fit(push_undo=False)
            return
        # repetir o ajuste na mesma imagem passa para o próximo rosto (do maior
        # para o menor): em imagens com várias pessoas, a personagem da custom
        # nem sempre é o maior rosto
        cycle = self.__dict__.setdefault("_face_cycle", {})
        index = cycle.get(self.current_path, -1) + 1
        if index >= len(faces):
            index = 0
        cycle[self.current_path] = index
        result = ImageProcessor.calculate_intelligent_frame_pos(image, faces[index], self.editor_state.borda_pos)
        if not result:
            self.show_warning("Ajuste", "Não foi possível aplicar o ajuste inteligente.")
            return
        new_w, new_h, pos_x, pos_y = result
        self.editor_state.set_image_state(self.current_path, (pos_x, pos_y), (new_w, new_h))
        self.image_canvas.set_image_state((pos_x, pos_y), (new_w, new_h))
        if len(faces) > 1:
            self.show_status(f"Rosto {index + 1} de {len(faces)} — Alt+F de novo para o próximo.", timeout_ms=8000)
        else:
            self.show_status("Ajuste inteligente aplicado.")

    def rotate_current_image(self, direction):
        if not self.current_path:
            return
        # F10: sem edição de pixels, rotacionar o original em resolução plena
        # para não fixar a preview reduzida como fonte da exportação
        image = self.edited_images.get(self.current_path)
        if image is None:
            image = self.current_original_image
        if image is None:
            image = self.get_active_image_copy()
        if image is None:
            return
        self.save_state_for_undo()
        angle = 90 if direction == "left" else -90
        rotated = image.rotate(angle, expand=True)
        self.set_edited_image_for_current(rotated)
        rotated.close()
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
        # M11: partes opcionais — só existem se o preset foi salvo com elas
        framing = data.get("default_framing")
        if framing in ("auto_fit", "intelligent"):
            self.set_default_framing(framing, announce=False)
        blacklist = data.get("danbooru_blacklist")
        if isinstance(blacklist, str):
            self.app_config.set("danbooru_tag_blacklist", blacklist.strip())
            self.app_config.save()
            if hasattr(self, "online_tab"):
                self.online_tab.refresh_from_config()
        self.editor_tab.refresh_from_state()
        self.refresh_current_canvas()
        self.show_status("Preset aplicado.")

    def set_default_framing(self, mode, announce=True):
        """M11: modo de enquadramento das imagens ainda não enquadradas."""
        if mode not in ("auto_fit", "intelligent"):
            return
        changed = mode != self.editor_state.default_framing
        self.editor_state.default_framing = mode
        self.app_config.set("default_framing", mode)
        self.app_config.save()
        if changed:
            self._reframe_auto_framed_images()
        if hasattr(self, "editor_tab"):
            self.editor_tab.sync_default_framing_combo()
        if announce:
            label = "inteligente (rosto)" if mode == "intelligent" else "auto fit"
            self.show_status(f"Imagens ainda não ajustadas usarão {label}.")

    def _reframe_auto_framed_images(self):
        """Recalcula no modo novo as imagens com enquadramento automático.

        O enquadramento padrão é calculado ao importar; sem isto, trocar o modo
        depois não tinha efeito nenhum nas imagens ainda não ajustadas. Ajustes
        do usuário não são tocados.
        """
        self._framing_generation = getattr(self, "_framing_generation", 0) + 1
        state = self.editor_state
        stale = [path for path in state.image_list if path in state.auto_framed]
        for path in stale:
            state.image_states.pop(path, None)
            state.auto_framed.discard(path)
        if stale and hasattr(self, "_precompute_default_framing"):
            self._precompute_default_framing(stale)

    def apply_adjustment_to_all(self, adjustment_name):
        if not self.editor_state.image_list:
            self.show_warning("Ajuste", "Nenhuma imagem carregada.")
            return

        # F9: a task roda em worker thread — capturar aqui (GUI thread) cópias
        # imutáveis de tudo que ela precisa; nada compartilhado é tocado depois.
        borda_pos = tuple(self.editor_state.borda_pos)
        snapshots = []
        for path in list(self.editor_state.image_list):
            source = self.edited_images.get(path)
            if source is not None:
                snapshots.append((path, source.copy()))
            else:
                snapshots.append((path, self._get_preview_cache_copy(path)))

        def task_fn(cancel_event, on_progress):
            updated = {}
            total = len(snapshots)
            try:
                for index, (path, working) in enumerate(snapshots, start=1):
                    if cancel_event and cancel_event.is_set():
                        break

                    if working is None:
                        with Image.open(path) as source:
                            working = source.convert("RGBA")

                    try:
                        if adjustment_name == "auto_fit":
                            result = ImageProcessor.calculate_auto_fit_pos(working, borda_pos)
                        else:
                            face = ImageProcessor.detect_anime_face(working, self.face_cascade)
                            if face:
                                result = ImageProcessor.calculate_intelligent_frame_pos(
                                    working,
                                    face,
                                    borda_pos,
                                )
                            else:
                                result = ImageProcessor.calculate_auto_fit_pos(working, borda_pos)
                        if result:
                            updated[path] = result
                    finally:
                        self._dispose_images([working])
                        snapshots[index - 1] = (path, None)

                    if on_progress:
                        on_progress(index, total, "Aplicando ajuste em lote...")
            finally:
                self._dispose_images([image for _path, image in snapshots])

            return {"updated": updated}

        def on_done(result):
            updated = result.get("updated") or {}
            # aplicar no editor_state apenas aqui, na GUI thread (F9)
            for path, (new_w, new_h, pos_x, pos_y) in updated.items():
                if path in self.editor_state.image_list:
                    self.editor_state.set_image_state(path, (pos_x, pos_y), (new_w, new_h))
            if self.current_path:
                state = self.editor_state.image_states.get(self.current_path)
                if state:
                    self.image_canvas.set_image_state(state["pos"], state["size"])
            if hasattr(self, "refresh_list_indicators"):
                self.refresh_list_indicators()
            label = "Auto fit" if adjustment_name == "auto_fit" else "Ajuste inteligente"
            # M1: confirmação não crítica vai para a status bar, sem modal
            self.show_status(f"{label} aplicado em {len(updated)} imagem(ns).", timeout_ms=6000)

        self.run_task(
            f"qt_adjust_all_{adjustment_name}",
            "Aplicando ajuste em lote",
            task_fn,
            on_done=on_done,
            maximum=max(1, len(snapshots)),
        )

    def copy_framing_to_all(self):
        if not self.current_path:
            self.show_warning("Enquadramento", "Nenhuma imagem selecionada.")
            return
        state = self.editor_state.image_states.get(self.current_path)
        if not state:
            self.show_warning("Enquadramento", "A imagem atual não tem enquadramento definido.")
            return
        image_list = self.editor_state.image_list or []
        if len(image_list) <= 1:
            self.show_warning("Enquadramento", "Não há outras imagens na lista.")
            return
        pos = state["pos"]
        size = state["size"]
        for path in image_list:
            if path != self.current_path:
                self.editor_state.set_image_state(path, pos, size)
        self.show_status(f"Enquadramento copiado para {len(image_list) - 1} imagem(ns).")

    def apply_auto_border(self, all_images=False):
        """Borda automática: cor que combina com o que aparece em cada custom.

        Calculada sobre o recorte enquadrado (o que a borda envolve), não sobre
        a imagem inteira, e aplicada como borda individual personalizada — o
        export já sabe lidar, e dá para trocar à mão depois.
        """
        import shutil
        import tempfile

        from src.core.batch_worker import render_custom_crop

        state = self.editor_state
        paths = list(state.image_list) if all_images else ([self.current_path] if self.current_path else [])
        if not paths:
            self.show_warning("Cor automática", "Carregue uma imagem primeiro.")
            return
        batch = self.batch_controller.frozen()  # retrato do estado (GUI thread)

        def task_fn(cancel_event, on_progress):
            colors = {}
            source_dir = tempfile.mkdtemp(prefix="custommaker_autoborder_")
            try:
                for index, path in enumerate(paths, start=1):
                    if cancel_event and cancel_event.is_set():
                        break
                    try:
                        data = batch._get_task_data(path, None, source_dir=source_dir)
                        if data:
                            crop = render_custom_crop(data)
                            try:
                                colors[path] = ImageProcessor.suggest_border_color(crop)
                            finally:
                                crop.close()
                    except Exception:
                        continue  # arquivo ilegível: mantém a borda atual
                    if on_progress:
                        on_progress(index, len(paths), f"Escolhendo cores... {index}/{len(paths)}")
            finally:
                shutil.rmtree(source_dir, ignore_errors=True)
            return colors

        def on_done(colors):
            for path, color in colors.items():
                if path in state.image_list:
                    state.individual_bordas[path] = "Cor Personalizada"
                    state.custom_borda_hex_individual[path] = color
            self.refresh_current_canvas()
            if hasattr(self, "refresh_list_indicators"):
                self.refresh_list_indicators()
            if len(paths) == 1 and colors:
                self.show_status(f"Cor automática aplicada: {next(iter(colors.values()))}")
            else:
                self.show_status(f"Cor automática aplicada em {len(colors)} imagem(ns).")

        self.run_task(
            "qt_auto_border",
            "Escolhendo cores de borda",
            task_fn,
            on_done=on_done,
            maximum=max(1, len(paths)),
        )

    def apply_style_to_all(self):
        image_list = self.editor_state.image_list or []
        if not image_list:
            self.show_warning("Aplicar a Todas", "Nenhuma imagem na lista.")
            return
        state = self.editor_state
        for path in image_list:
            state.individual_bordas[path] = state.selected_borda
            if state.selected_borda == "Cor Personalizada":
                state.custom_borda_hex_individual[path] = state.custom_borda_hex
        self.refresh_current_canvas()
        if hasattr(self, "refresh_list_indicators"):
            self.refresh_list_indicators()
        self.show_status(f"Borda '{state.selected_borda}' aplicada a {len(image_list)} imagem(ns).")
