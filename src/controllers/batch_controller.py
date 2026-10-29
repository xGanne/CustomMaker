import concurrent.futures
import copy
import logging
import os
import secrets
import shutil
import tempfile
import threading
import zipfile
from concurrent.futures.process import BrokenProcessPool
from typing import List

from PIL import Image

from src.core.batch_worker import measure_custom, process_image_task
from src.core.image_processor import ImageProcessor


logger = logging.getLogger(__name__)


def unique_output_names(paths, suffix):
    """Nome de saída por path, sem colisões dentro do lote.

    "pastaA/001.png" e "pastaB/001.png" (ou "a.jpg" e "a.png") gerariam o
    mesmo arquivo, e uma custom sobrescrevia a outra sem aviso. O Windows não
    diferencia maiúsculas, então a comparação também não diferencia.
    """
    names = {}
    used = set()
    for path in paths:
        stem = os.path.splitext(os.path.basename(path))[0]
        candidate = f"{stem}{suffix}"
        counter = 2
        while candidate.lower() in used:
            root, ext = os.path.splitext(suffix)
            candidate = f"{stem}{root}_{counter}{ext}"
            counter += 1
        used.add(candidate.lower())
        names[path] = candidate
    return names


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
        # M15: pool de processos preguiçoso e reutilizado entre exportações —
        # no Windows (spawn) criar um pool novo custa segundos a cada lote
        self._executor = None
        self._executor_workers = None
        self._executor_lock = threading.Lock()
        # cópias congeladas (frozen) usam o pool deste controlador
        self._pool_owner = self
        # M11: cascade próprio (carregado sob demanda) para o enquadramento
        # inteligente padrão — não compartilha o classificador da GUI entre threads
        self._face_cascade = None
        self._face_cascade_loaded = False

    def frozen(self):
        """Cópia com o estado do editor congelado, para um lote.

        Chamar na GUI thread ao iniciar uma exportação: o lote roda num worker
        e lia o estado aos poucos, enquanto a janela seguia viva — redimensionar
        (que desloca a borda e os enquadramentos) ou editar no meio misturava
        estados antigos e novos entre as customs do mesmo lote. A cópia
        compartilha o pool de processos deste controlador.
        """
        clone = copy.copy(self)
        if self.editor_state is not None:
            clone.editor_state = copy.deepcopy(self.editor_state)
        # cópias próprias: o editor fecha a imagem editada anterior ao rotacionar
        clone._edited_source_images = {
            path: image.copy() for path, image in (self._edited_source_images or {}).items()
        }
        return clone

    def _get_task_data(self, path, output_path=None, source_dir=None):
        state = self._image_states().get(path)
        generated_state = False
        if not state:
            state = self._default_state_for(path)
            if not state:
                return None
            generated_state = True

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
            "generated_state": generated_state,
        }
        source_image = self._edited_source_images.get(path)
        if source_image is not None:
            data["source_path"] = self._save_source_override(path, source_image, source_dir)
        return data

    @staticmethod
    def _generated_states(tasks):
        """Enquadramentos calculados no export para imagens sem estado — o
        editor adota os mesmos, para mostrar exatamente o que foi exportado."""
        return {task["path"]: task["state"] for task in tasks if task.get("generated_state")}

    def _default_framing(self):
        mode = _resolve_value(self._state_attr("default_framing", "auto_fit"), "auto_fit")
        return mode if mode in ("auto_fit", "intelligent") else "auto_fit"

    def _get_face_cascade(self):
        if not self._face_cascade_loaded:
            self._face_cascade = ImageProcessor.load_face_cascade()
            self._face_cascade_loaded = True
        return self._face_cascade

    def _default_state_for(self, path):
        """Enquadramento padrão para imagens nunca abertas no canvas — evita que
        a exportação as pule silenciosamente (F4). Segue o modo escolhido pelo
        usuário (auto fit ou inteligente) (M11)."""
        mode = self._default_framing()
        face_cascade = self._get_face_cascade() if mode == "intelligent" else None
        source_image = self._edited_source_images.get(path)
        try:
            if source_image is not None:
                fit = ImageProcessor.calculate_default_fit(
                    source_image, self._resolve_borda_pos(), mode, face_cascade
                )
            else:
                with Image.open(path) as image:
                    fit = ImageProcessor.calculate_default_fit(
                        image, self._resolve_borda_pos(), mode, face_cascade
                    )
        except Exception as exc:
            logger.warning("Sem estado e sem enquadramento possível para %s: %s", path, exc)
            return None
        if not fit:
            return None
        new_w, new_h, pos_x, pos_y = fit
        return {"pos": (pos_x, pos_y), "size": (new_w, new_h)}

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

    @staticmethod
    def _sort_results_by_task_order(results, tasks):
        """Resultados chegam na ordem de conclusão dos processos; reordena pela
        ordem da lista de tasks para manter links/arquivos na ordem da lista (F5)."""
        order = {task.get("path"): index for index, task in enumerate(tasks)}
        results.sort(key=lambda r: order.get(r.get("path"), len(order)))
        return results

    def _get_executor(self, max_workers):
        """M15: devolve o pool compartilhado, recriando-o só se o número de
        workers mudou ou se um processo filho morreu (pool quebrado)."""
        owner = self._pool_owner
        with owner._executor_lock:
            broken = owner._executor is not None and getattr(owner._executor, "_broken", False)
            if owner._executor is not None and (broken or owner._executor_workers != max_workers):
                owner._executor.shutdown(wait=False, cancel_futures=True)
                owner._executor = None
            if owner._executor is None:
                owner._executor = concurrent.futures.ProcessPoolExecutor(max_workers=max_workers)
                owner._executor_workers = max_workers
            return owner._executor

    def _discard_executor(self, executor):
        owner = self._pool_owner
        with owner._executor_lock:
            if owner._executor is executor:
                owner._executor = None
                owner._executor_workers = None
        executor.shutdown(wait=False, cancel_futures=True)

    def shutdown(self):
        """Encerra o pool compartilhado (chamado ao fechar a janela)."""
        owner = self._pool_owner
        with owner._executor_lock:
            executor, owner._executor = owner._executor, None
            owner._executor_workers = None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _saved_sizes(results):
        """{path de origem: bytes do arquivo gerado} dos resultados com sucesso."""
        sizes = {}
        for result in results:
            saved_to = result.get("saved_to")
            if result.get("status") == "success" and saved_to and os.path.isfile(saved_to):
                sizes[result.get("path")] = os.path.getsize(saved_to)
        return sizes

    def _run_batch(self, tasks, on_progress=None, cancel_event=None, worker=process_image_task, on_result=None):
        """Roda `worker` sobre as tasks no pool; `on_result` recebe cada
        resultado assim que fica pronto (para mostrar progresso por item)."""
        total = len(tasks)
        completed = 0
        results: List[dict] = []
        if total == 0:
            return {"results": results, "cancelled": False}

        max_workers = self._resolve_max_workers()
        logger.info("Iniciando processamento em lote com %s task(s), workers=%s", total, max_workers)
        executor = self._get_executor(max_workers)
        try:
            futures = {executor.submit(worker, task): task for task in tasks}
        except BrokenProcessPool:
            # um worker morreu desde o último lote: recria o pool e tenta de novo
            self._discard_executor(executor)
            executor = self._get_executor(max_workers)
            futures = {executor.submit(worker, task): task for task in tasks}
        pending = set(futures.keys())

        while pending:
            if cancel_event and cancel_event.is_set():
                # o pool é compartilhado: cancela só as tasks deste lote; as que
                # já estão rodando terminam em segundo plano e são ignoradas
                for future in pending:
                    future.cancel()
                return {"results": self._sort_results_by_task_order(results, tasks), "cancelled": True}

            done, pending = concurrent.futures.wait(
                pending,
                timeout=0.2,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                try:
                    res = future.result()
                except Exception as exc:
                    logger.exception("Erro no batch worker: %s", exc)
                    if isinstance(exc, BrokenProcessPool):
                        self._discard_executor(executor)
                    src_task = futures[future]
                    res = {"status": "error", "path": src_task.get("path"), "error": str(exc)}
                results.append(res)
                if on_result:
                    on_result(res)

                completed += 1
                if on_progress:
                    on_progress(completed, total, f"Processando {completed}/{total}")

        return {"results": self._sort_results_by_task_order(results, tasks), "cancelled": False}

    @staticmethod
    def _size_cache_key(task):
        """Chave do conteúdo que define o arquivo exportado, ou None se não dá
        para confiar nela (imagem com edição de pixels, arquivo inacessível).

        A posição entra relativa à borda: redimensionar a janela desloca borda e
        enquadramentos juntos sem mudar a custom.
        """
        if task.get("source_path"):
            return None
        try:
            stat = os.stat(task["path"])
        except OSError:
            return None
        (x, y), (bx, by) = task["state"]["pos"], task["borda_pos"]
        return (
            task["path"], stat.st_mtime_ns, stat.st_size,
            (int(x - bx), int(y - by)), tuple(int(v) for v in task["state"]["size"]),
            task["border_color"], task["anim_type"],
        )

    def measure_sizes(self, paths=None, progress_callback=None, cancel_event=None, on_result=None, cache=None):
        """Tamanho de cada custom como seria exportada, sem gravar arquivos.

        Mesmas tasks e mesmo formato do export (GIF com animação, PNG sem).
        Devolve {"results": [{"path", "status", "bytes", "format"}...],
        "cancelled", "skipped"} na ordem da lista. `cache` (dict) guarda as
        medições por conteúdo: customs que não mudaram não são recodificadas.
        """
        source_dir = tempfile.mkdtemp()
        try:
            tasks, skipped, cached = [], [], []
            for path in self._image_list() if paths is None else paths:
                data = self._get_task_data(path, None, source_dir=source_dir)
                if not data:
                    skipped.append(path)
                    continue
                key = self._size_cache_key(data) if cache is not None else None
                hit = cache.get(key) if key is not None else None
                if hit is not None:
                    cached.append(dict(hit, path=path))
                else:
                    data["size_cache_key"] = key
                    tasks.append(data)
            for result in cached:
                if on_result:
                    on_result(result)

            def remember(result):
                if cache is not None and result.get("status") == "success":
                    task = next((t for t in tasks if t["path"] == result.get("path")), None)
                    if task is not None and task.get("size_cache_key") is not None:
                        cache[task["size_cache_key"]] = {k: result[k] for k in ("status", "bytes", "format")}
                if on_result:
                    on_result(result)

            batch = self._run_batch(
                tasks, on_progress=progress_callback, cancel_event=cancel_event, worker=measure_custom, on_result=remember
            )
            order = {path: i for i, path in enumerate(self._image_list() if paths is None else paths)}
            results = sorted(cached + batch["results"], key=lambda r: order.get(r.get("path"), len(order)))
            return {"results": results, "cancelled": batch["cancelled"], "skipped": skipped}
        finally:
            shutil.rmtree(source_dir, ignore_errors=True)

    def save_single_image(self, path, output_path):
        """M12: exporta uma única imagem em processo, sem pool."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            data = self._get_task_data(path, output_path, source_dir=tmp_dir)
            if not data:
                return {"status": "error", "path": path, "error": "Sem enquadramento possível para a imagem."}
            return process_image_task(data)

    def save_all_images(self, target_dir, progress_callback=None, cancel_event=None, paths=None):
        source_dir = tempfile.mkdtemp()
        tasks = []
        skipped = []
        is_anim = self._animation_type() != "Nenhuma"
        ext = "_custom.gif" if is_anim else "_custom.png"

        try:
            batch_paths = self._image_list() if paths is None else paths
            names = unique_output_names(batch_paths, ext)
            for path in batch_paths:
                out = os.path.join(target_dir, names[path])
                data = self._get_task_data(path, out, source_dir=source_dir)
                if data:
                    tasks.append(data)
                else:
                    skipped.append(os.path.basename(path))

            batch = self._run_batch(tasks, on_progress=progress_callback, cancel_event=cancel_event)
            errors = [r for r in batch["results"] if r.get("status") != "success"]
            return {
                "cancelled": batch["cancelled"],
                "processed": len(batch["results"]),
                "errors": len(errors),
                "target_dir": target_dir,
                "total": len(tasks),
                "skipped": skipped,
                "generated_states": self._generated_states(tasks),
                "sizes": self._saved_sizes(batch["results"]),
            }
        finally:
            shutil.rmtree(source_dir, ignore_errors=True)

    def save_zip(self, target_file, progress_callback=None, cancel_event=None, paths=None):
        is_anim = self._animation_type() != "Nenhuma"
        ext = ".gif" if is_anim else ".png"

        with tempfile.TemporaryDirectory() as tmp_dir:
            source_dir = os.path.join(tmp_dir, "_sources")
            tasks = []
            skipped = []

            batch_paths = self._image_list() if paths is None else paths
            names = unique_output_names(batch_paths, f"_custom{ext}")
            for path in batch_paths:
                out = os.path.join(tmp_dir, names[path])
                data = self._get_task_data(path, out, source_dir=source_dir)
                if data:
                    tasks.append(data)
                else:
                    skipped.append(os.path.basename(path))

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
                    "skipped": skipped,
                    "generated_states": self._generated_states(tasks),
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
                "skipped": skipped,
                "generated_states": self._generated_states(tasks),
                "sizes": self._saved_sizes(batch["results"]),
            }

    def prepare_upload(self, progress_callback=None, cancel_event=None, paths=None):
        """Renderiza as customs do upload numa pasta temporária, sem enviar.

        Devolve os arquivos e o tamanho de cada um: quem chama pode conferir
        os tamanhos (e perguntar ao usuário) antes de `upload_prepared`, sem
        codificar tudo duas vezes. Chame `upload_prepared` ou
        `discard_prepared` para apagar a pasta.
        """
        ext = ".gif" if self._animation_type() != "Nenhuma" else ".png"
        tmp_dir = tempfile.mkdtemp(prefix="custommaker_upload_")
        try:
            source_dir = os.path.join(tmp_dir, "_sources")
            tasks, skipped = [], []
            batch_paths = self._image_list() if paths is None else paths
            names = unique_output_names(batch_paths, f"_custom{ext}")
            for path in batch_paths:
                data = self._get_task_data(path, os.path.join(tmp_dir, names[path]), source_dir=source_dir)
                if data:
                    tasks.append(data)
                else:
                    skipped.append(os.path.basename(path))
            batch = self._run_batch(tasks, on_progress=progress_callback, cancel_event=cancel_event)
        except BaseException:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
        prepared = {
            "tmp_dir": tmp_dir,
            "cancelled": batch["cancelled"],
            "results": batch["results"],
            "files": [
                {"path": r["saved_to"], "filename": os.path.basename(r["saved_to"]), "source": r.get("path")}
                for r in batch["results"] if r.get("status") == "success" and "saved_to" in r
            ],
            "sizes": self._saved_sizes(batch["results"]),
            "total": len(tasks),
            "skipped": skipped,
            "generated_states": self._generated_states(tasks),
        }
        if prepared["cancelled"]:
            self.discard_prepared(prepared)
        return prepared

    @staticmethod
    def discard_prepared(prepared):
        shutil.rmtree(prepared.get("tmp_dir") or "", ignore_errors=True)

    def upload_prepared(self, prepared, title, progress_callback=None, cancel_event=None):
        """Envia os arquivos de `prepare_upload` e apaga a pasta temporária."""
        try:
            process_errors = [r for r in prepared["results"] if r.get("status") != "success"]
            common = {
                "processed": len(prepared["results"]),
                "total": prepared["total"],
                "skipped": prepared["skipped"],
                "generated_states": prepared["generated_states"],
            }
            if prepared["cancelled"]:
                return dict(common, cancelled=True, links=[], errors=["Operação cancelada pelo usuário."], uploaded=0)
            files = [{"path": f["path"], "filename": f["filename"]} for f in prepared["files"]]
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
            return dict(
                common,
                cancelled=bool(cancel_event and cancel_event.is_set()),
                links=links,
                errors=all_errors,
                uploaded=len(files),
            )
        finally:
            self.discard_prepared(prepared)

    def upload_to_imgchest(self, title, progress_callback=None, cancel_event=None, paths=None):
        prepared = self.prepare_upload(progress_callback=progress_callback, cancel_event=cancel_event, paths=paths)
        return self.upload_prepared(prepared, title, progress_callback=progress_callback, cancel_event=cancel_event)
