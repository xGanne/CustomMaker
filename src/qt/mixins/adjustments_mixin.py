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
                    cached = self._get_preview_cache_copy(path)
                    if cached is not None:
                        working = cached
                        should_close = True
                    else:
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
                    on_progress(index, total, "Aplicando ajuste em lote...")

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
        self.show_status(f"Borda '{state.selected_borda}' aplicada a {len(image_list)} imagem(ns).")
