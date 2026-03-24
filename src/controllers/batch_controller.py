import concurrent.futures
import logging
import os
import shutil
import tempfile
import zipfile
from typing import List

from src.core.batch_worker import process_image_task


logger = logging.getLogger(__name__)


class BatchController:
    def __init__(self, app_context):
        self.app = app_context

    def _get_task_data(self, path, output_path=None):
        state = self.app.image_states.get(path)
        if not state:
            return None

        anim_type = self.app.animation_type.get()
        b_name = self.app.individual_bordas.get(path, self.app.selected_borda.get())
        if b_name == "Cor Personalizada":
            b_hex = self.app.custom_borda_hex_individual.get(path, self.app.custom_borda_hex)
        else:
            b_hex = self.app.borda_hex.get(b_name, "#FFFFFF")

        return {
            "path": path,
            "state": state,
            "borda_pos": self.app.borda_pos,
            "anim_type": anim_type,
            "border_color": b_hex,
            "output_path": output_path,
        }

    def _resolve_max_workers(self):
        configured = self.app.app_config.get("max_workers")
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
        tasks = []
        is_anim = self.app.animation_type.get() != "Nenhuma"
        ext = "_custom.gif" if is_anim else "_custom.png"

        for path in self.app.image_list:
            out = os.path.join(target_dir, os.path.splitext(os.path.basename(path))[0] + ext)
            data = self._get_task_data(path, out)
            if data:
                tasks.append(data)

        batch = self._run_batch(tasks, on_progress=progress_callback, cancel_event=cancel_event)
        return {
            "cancelled": batch["cancelled"],
            "processed": len(batch["results"]),
            "errors": len([r for r in batch["results"] if r.get("status") != "success"]),
        }

    def save_zip(self, target_file, progress_callback=None, cancel_event=None):
        tmp_dir = tempfile.mkdtemp()
        tasks = []
        is_anim = self.app.animation_type.get() != "Nenhuma"
        ext = ".gif" if is_anim else ".png"

        for path in self.app.image_list:
            fname = os.path.splitext(os.path.basename(path))[0] + f"_custom{ext}"
            out = os.path.join(tmp_dir, fname)
            data = self._get_task_data(path, out)
            if data:
                tasks.append(data)

        try:
            batch = self._run_batch(tasks, on_progress=progress_callback, cancel_event=cancel_event)
            if batch["cancelled"]:
                return {"cancelled": True, "zip_path": target_file, "written": 0}

            written = 0
            with zipfile.ZipFile(target_file, "w") as z:
                for result in batch["results"]:
                    if result.get("status") == "success" and "saved_to" in result:
                        z.write(result["saved_to"], os.path.basename(result["saved_to"]))
                        written += 1
            return {"cancelled": False, "zip_path": target_file, "written": written}
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def upload_to_imgchest(self, title, progress_callback=None, cancel_event=None):
        tmp_dir = tempfile.mkdtemp()
        tasks = []
        is_anim = self.app.animation_type.get() != "Nenhuma"
        ext = ".gif" if is_anim else ".png"

        for path in self.app.image_list:
            fname = os.path.splitext(os.path.basename(path))[0] + f"_custom{ext}"
            out = os.path.join(tmp_dir, fname)
            data = self._get_task_data(path, out)
            if data:
                tasks.append(data)

        try:
            batch = self._run_batch(tasks, on_progress=progress_callback, cancel_event=cancel_event)
            if batch["cancelled"]:
                return {"cancelled": True, "links": [], "errors": ["Operacao cancelada pelo usuario."]}

            files = []
            for result in batch["results"]:
                if result.get("status") == "success" and "saved_to" in result:
                    file_path = result["saved_to"]
                    files.append({"path": file_path, "filename": os.path.basename(file_path)})

            if progress_callback:
                progress_callback(0, len(files), "Enviando...")

            links, errors = self.app.uploader.upload_images(
                files,
                title,
                progress_callback=progress_callback,
                cancel_event=cancel_event,
            )
            return {"cancelled": bool(cancel_event and cancel_event.is_set()), "links": links, "errors": errors}
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
