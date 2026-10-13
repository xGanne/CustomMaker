"""
AnimationMixin — loop de animação de prévia de borda.

Responsabilidades:
  • Geração assíncrona de frames PIL para cada tipo de animação
  • Timer de reprodução quadro a quadro sobre o canvas
  • Parada e limpeza segura do loop
"""
from src.config.settings import BORDA_HEIGHT, BORDA_HEX, BORDA_WIDTH, BORDER_THICKNESS
from src.core.animation_processor import AnimationProcessor


class AnimationMixin:

    _PREVIEW_CACHE_MAX_ENTRIES = 8

    def _preview_frames_cache(self):
        """M13: cache de pixmaps por (tipo, cor) — os frames não dependem da imagem."""
        if not hasattr(self, "_preview_frames_cache_map"):
            from collections import OrderedDict
            self._preview_frames_cache_map = OrderedDict()
        return self._preview_frames_cache_map

    @staticmethod
    def _generate_preview_frames(animation_type, border_color, cancel_event):
        try:
            size = (BORDA_WIDTH, BORDA_HEIGHT)
            if cancel_event and cancel_event.is_set():
                return {"cancelled": True, "frames": [], "duration": 50}
            if animation_type == "Rainbow":
                frames, duration = AnimationProcessor.generate_rainbow_frames(
                    size, total_frames=40, border_width=BORDER_THICKNESS, overlay_only=True
                )
            elif animation_type == "Neon Pulsante":
                frames, duration = AnimationProcessor.generate_neon_frames(
                    size, border_color, total_frames=40, border_width=BORDER_THICKNESS, overlay_only=True
                )
            elif animation_type == "Strobe (Pisca)":
                frames, duration = AnimationProcessor.generate_strobe_frames(
                    size, total_frames=10, border_width=BORDER_THICKNESS, overlay_only=True
                )
            elif animation_type == "Glitch":
                frames, duration = AnimationProcessor.generate_glitch_frames(
                    size, total_frames=20, border_width=BORDER_THICKNESS, overlay_only=True
                )
            elif animation_type == "Spin":
                frames, duration = AnimationProcessor.generate_spin_frames(
                    size, border_color, total_frames=30, border_width=BORDER_THICKNESS, overlay_only=True
                )
            elif animation_type == "Flow":
                frames, duration = AnimationProcessor.generate_flow_frames(
                    size, border_color, total_frames=30, border_width=BORDER_THICKNESS, overlay_only=True
                )
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

        # M13: reutiliza frames já gerados para o mesmo (tipo, cor)
        cache = self._preview_frames_cache()
        cache_key = (animation_type, border_color)
        cached = cache.get(cache_key)
        if cached is not None:
            cache.move_to_end(cache_key)
            self._preview_frames, self._preview_duration = cached
            if self._preview_frames:
                self._advance_preview_frame()
                self._preview_timer.start(self._preview_duration)
            return
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
                if not self._window_alive():
                    return
                self.image_canvas.clear_preview_overlay()
                self.show_status(f"Prévia da animação indisponível: {result['error']}", timeout_ms=8000)
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
            # M13: guarda no cache com evicção LRU simples
            cache[cache_key] = (pixmaps, self._preview_duration)
            cache.move_to_end(cache_key)
            while len(cache) > self._PREVIEW_CACHE_MAX_ENTRIES:
                cache.popitem(last=False)
            self._advance_preview_frame()
            self._preview_timer.start(self._preview_duration)

        def on_error(exc):
            if not self._window_alive():
                return
            if task_id == self._active_preview_task_id:
                self._active_preview_task_id = None
            self.image_canvas.clear_preview_overlay()
            self.show_status(f"Prévia da animação indisponível: {exc}", timeout_ms=8000)

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
