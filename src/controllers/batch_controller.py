import concurrent.futures
import logging
import os
import secrets
import shutil
import tempfile
import zipfile
from typing import List

from PIL import Image

from src.core.batch_worker import process_image_task


logger = logging.getLogger(__name__)


def _resolve_value(value, default=None):
    if value is None:
        return default
    getter = getattr(value, "get", None)
    if callable(getter):
        try:
            return getter()
        except TypeError:
            return value
    return value


class BatchController:
    def __init__(
        self,
        app_context=None,
        *,
        editor_state=None,
        app_config=None,
        uploader=None,
        borda_hex=None,
        borda_pos=None,
        edited_source_images=None,
    ):
        self.app = app_context
        self.editor_state = editor_state
        self.app_config = app_config or getattr(app_context, "app_config", None)
        self.uploader = uploader or getattr(app_context, "uploader", None)
        self._borda_hex = borda_hex or getattr(app_context, "borda_hex", {})
        self._borda_pos = borda_pos
        if edited_source_images is None:
            edited_source_images = getattr(app_context, "edited_source_images", {})
        self._edited_source_images = edited_source_images

    def _get_task_data(self, path, output_path=None, source_dir=None):
        state = self._image_states().get(path)
        if not state:
            return None

        anim_type = self._animation_type()
        b_name = self._individual_bordas().get(path, self._selected_borda())
        if b_name == "Cor Personalizada":
            b_hex = self._custom_borda_hex_individual().get(path, self._custom_borda_hex())
        else:
            b_hex = self._borda_hex.get(b_name, "#FFFFFF")

        data = {
            "path": path,
            "state": state,
            "borda_pos": self._resolve_borda_pos(),
            "anim_type": anim_type,
            "border_color": b_hex,
            "output_path": output_path,
        }
        source_image = self._edited_source_images.get(path)
        if source_image is not None:
            data["source_path"] = self._save_source_override(path, source_image, source_dir)
        return data

    @staticmethod
    def _save_source_override(path, image, source_dir):
        if source_dir is None:
            raise ValueError("source_dir is required when exporting edited source images.")
        if not isinstance(image, Image.Image):
            raise TypeError("Edited source image must be a PIL image.")
        os.makedirs(source_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(path))[0]
        source_path = os.path.join(source_dir, f"{stem}_{secrets.token_hex(4)}.png")
        image.save(source_path, format="PNG")
        return source_path

    def _config_get(self, key, default=None):
        if not self.app_config:
            return default
        try:
            return self.app_config.get(key, default)
        except TypeError:
            try:
                value = self.app_config.get(key)
            except Exception:
                return default
            return default if value is None else value

    def _state_attr(self, name, default=None):
        if self.editor_state is not None:
            return getattr(self.editor_state, name, default)
        if self.app is None:
            return default
        return getattr(self.app, name, default)

    def _image_states(self):
        return self._state_attr("image_states", {}) or {}

    def _image_list(self):
        return self._state_attr("image_list", []) or []

    def _individual_bordas(self):
        return self._state_attr("individual_bordas", {}) or {}

    def _custom_borda_hex_individual(self):
        return self._state_attr("custom_borda_hex_individual", {}) or {}

    def _custom_borda_hex(self):
        return _resolve_value(self._state_attr("custom_borda_hex", "#FFFFFF"), "#FFFFFF")

    def _selected_borda(self):
        return _resolve_value(self._state_attr("selected_borda", "White"), "White")

    def _animation_type(self):
        return _resolve_value(self._state_attr("animation_type", "Nenhuma"), "Nenhuma")

    def _resolve_borda_pos(self):
        if self._borda_pos is not None:
            return self._borda_pos
        resolved = self._state_attr("borda_pos", (0, 0))
        return _resolve_value(resolved, (0, 0))

    def _resolve_max_workers(self):
        configured = self._config_get("max_workers")
        cpu_count = os.cpu_count() or 1
        cpu_default = max(1, min(4, cpu_count))
        max_allowed = max(1, min(8, cpu_count))
        if configured is None:
            return cpu_default
        try:
            value = int(configured)
            return max(1, min(value, max_allowed))
        except (TypeError, ValueError):
            return cpu_default

    def _run_batch(self, tasks, on_progress=None, cancel_event=None):
        total = len(tasks)
        completed = 0
        results: List[dict] = []
        if total == 0:
            return {"results": results, "cancelled": False}

        max_workers = self._resolve_max_workers()
        logger.info("Iniciando processamento em lote com %s task(s), workers=%s", total, max_workers)
        executor = concurrent.futures.ProcessPoolExecutor(max_workers=max_workers)
        try:
            futures = {executor.submit(process_image_task, task): task for task in tasks}
            pending = set(futures.keys())

            while pending:
                if cancel_event and cancel_event.is_set():
                    for future in pending:
                        future.cancel()
                    executor.shutdown(wait=False, cancel_futures=True)
                    return {"results": results, "cancelled": True}

                done, pending = concurrent.futures.wait(
                    pending,
                    timeout=0.2,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                for future in done:
                    try:
                        res = future.result()
                        results.append(res)
                    except Exception as exc:
                        logger.exception("Erro no batch worker: %s", exc)
                        src_task = futures[future]
                        results.append({"status": "error", "path": src_task.get("path"), "error": str(exc)})

                    completed += 1
                    if on_progress:
                        on_progress(completed, total, f"Processando {completed}/{total}")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        return {"results": results, "cancelled": False}

    def save_all_images(self, target_dir, progress_callback=None, cancel_event=None):
        source_dir = tempfile.mkdtemp()
        tasks = []
        is_anim = self._animation_type() != "Nenhuma"
        ext = "_custom.gif" if is_anim else "_custom.png"

        try:
            for path in self._image_list():
                out = os.path.join(target_dir, os.path.splitext(os.path.basename(path))[0] + ext)
                data = self._get_task_data(path, out, source_dir=source_dir)
                if data:
                    tasks.append(data)

            batch = self._run_batch(tasks, on_progress=progress_callback, cancel_event=cancel_event)
            errors = [r for r in batch["results"] if r.get("status") != "success"]
            return {
                "cancelled": batch["cancelled"],
                "processed": len(batch["results"]),
                "errors": len(errors),
                "target_dir": target_dir,
                "total": len(tasks),
            }
        finally:
            shutil.rmtree(source_dir, ignore_errors=True)

    def save_zip(self, target_file, progress_callback=None, cancel_event=None):
        is_anim = self._animation_type() != "Nenhuma"
        ext = ".gif" if is_anim else ".png"

        with tempfile.TemporaryDirectory() as tmp_dir:
            source_dir = os.path.join(tmp_dir, "_sources")
            tasks = []

            for path in self._image_list():
                fname = os.path.splitext(os.path.basename(path))[0] + f"_custom{ext}"
                out = os.path.join(tmp_dir, fname)
                data = self._get_task_data(path, out, source_dir=source_dir)
                if data:
                    tasks.append(data)

            batch = self._run_batch(tasks, on_progress=progress_callback, cancel_event=cancel_event)
            errors = [r for r in batch["results"] if r.get("status") != "success"]
            if batch["cancelled"]:
                return {
                    "cancelled": True,
                    "zip_path": target_file,
                    "written": 0,
                    "processed": len(batch["results"]),
                    "errors": len(errors),
                    "total": len(tasks),
                }

            written = 0
            with zipfile.ZipFile(target_file, "w") as z:
                for result in batch["results"]:
                    if result.get("status") == "success" and "saved_to" in result:
                        z.write(result["saved_to"], os.path.basename(result["saved_to"]))
                        written += 1
            return {
                "cancelled": False,
                "zip_path": target_file,
                "written": written,
                "processed": len(batch["results"]),
                "errors": len(errors),
                "total": len(tasks),
            }

    def upload_to_imgchest(self, title, progress_callback=None, cancel_event=None):
        is_anim = self._animation_type() != "Nenhuma"
        ext = ".gif" if is_anim else ".png"

        with tempfile.TemporaryDirectory() as tmp_dir:
            source_dir = os.path.join(tmp_dir, "_sources")
            tasks = []

            for path in self._image_list():
                fname = os.path.splitext(os.path.basename(path))[0] + f"_custom{ext}"
                out = os.path.join(tmp_dir, fname)
                data = self._get_task_data(path, out, source_dir=source_dir)
                if data:
                    tasks.append(data)

            batch = self._run_batch(tasks, on_progress=progress_callback, cancel_event=cancel_event)
            process_errors = [r for r in batch["results"] if r.get("status") != "success"]
            if batch["cancelled"]:
                return {
                    "cancelled": True,
                    "links": [],
                    "errors": ["Operação cancelada pelo usuário."],
                    "processed": len(batch["results"]),
                    "uploaded": 0,
                    "total": len(tasks),
                }

            files = []
            for result in batch["results"]:
                if result.get("status") == "success" and "saved_to" in result:
                    file_path = result["saved_to"]
                    files.append({"path": file_path, "filename": os.path.basename(file_path)})

            if progress_callback:
                progress_callback(0, len(files), "Enviando...")

            if not self.uploader:
                raise ValueError("Uploader não configurado.")
            links, errors = self.uploader.upload_images(
                files,
                title,
                progress_callback=progress_callback,
                cancel_event=cancel_event,
            )
            all_errors = [r.get("error") or r.get("path") or "Erro ao processar imagem." for r in process_errors]
            all_errors.extend(errors)
            return {
                "cancelled": bool(cancel_event and cancel_event.is_set()),
                "links": links,
                "errors": all_errors,
                "processed": len(batch["results"]),
                "uploaded": len(files),
                "total": len(tasks),
            }
