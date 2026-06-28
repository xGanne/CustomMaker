import concurrent.futures
import logging
import os

from src.core.danbooru import DanbooruClient
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error
from src.qt.dialogs.danbooru_gallery_dialog import DanbooruGalleryDialog
from src.qt.dialogs.danbooru_image_viewer import DanbooruImageViewer
from src.qt.widgets.danbooru_autocomplete import DanbooruAutocomplete
from src.qt.widgets.danbooru_grid import DanbooruResultsGrid, DanbooruSelectionState

if QT_AVAILABLE:
    from src.qt.compat import (
        QComboBox,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )


logger = logging.getLogger(__name__)


RATING_TAGS = {
    "Qualquer classificacao": "",
    "Geral": "rating:g",
    "Sensivel": "rating:s",
    "Questionavel": "rating:q",
    "Explicito": "rating:e",
}

SORT_TAGS = {
    "Mais recentes": "order:id_desc",
    "Melhor avaliados": "order:score",
    "Mais favoritos": "order:favcount",
}


if QT_AVAILABLE:
    class OnlineTab(QWidget):
        def __init__(self, main_window, parent=None):
            super().__init__(parent)
            self.main_window = main_window
            self.client = DanbooruClient(config=self.main_window.app_config)
            self.posts = []
            self.current_page = 1
            self._page_size = 20
            self._has_next_page = False
            self._search_seq = 0
            self._active_search_task_id = None
            self._active_search_tags = ""
            self._active_query_label = ""
            self._expanded_dialog = None
            self._image_viewer = None
            self.selection_state = DanbooruSelectionState()

            layout = QVBoxLayout(self)

            search_group = QGroupBox("Busca Online")
            search_layout = QVBoxLayout(search_group)
            self.search_edit = QLineEdit()
            self.search_edit.setPlaceholderText("Tags (ex: hatsune_miku)")
            self.search_edit.returnPressed.connect(self.search)

            filter_row = QHBoxLayout()
            self.rating_combo = QComboBox()
            self.rating_combo.addItems(list(RATING_TAGS.keys()))
            self.sort_combo = QComboBox()
            self.sort_combo.addItems(list(SORT_TAGS.keys()))
            self.search_button = QPushButton("Buscar")
            self.search_button.clicked.connect(self.search)
            filter_row.addWidget(self.rating_combo)
            filter_row.addWidget(self.sort_combo)
            filter_row.addWidget(self.search_button)
            search_layout.addWidget(self.search_edit)
            search_layout.addLayout(filter_row)

            result_group = QGroupBox("Resultados")
            result_layout = QVBoxLayout(result_group)
            self.results_grid = DanbooruResultsGrid(
                self.main_window.app_config,
                self.client,
                result_group,
                selection_state=self.selection_state,
            )
            self.results_grid.selection_count_changed.connect(self._update_selection_summary)
            self.results_grid.image_open_requested.connect(self.open_image_viewer)

            self.summary_label = QLabel("Nenhuma busca executada.")
            self.summary_label.setWordWrap(True)

            pagination_row = QHBoxLayout()
            pagination_row.addWidget(self.summary_label, 1)
            self.prev_button = QPushButton("Anterior")
            self.prev_button.clicked.connect(lambda: self.change_page(-1))
            self.page_label = QLabel("Pagina 1")
            self.next_button = QPushButton("Proxima")
            self.next_button.clicked.connect(lambda: self.change_page(1))
            pagination_row.addWidget(self.prev_button)
            pagination_row.addWidget(self.page_label)
            pagination_row.addWidget(self.next_button)

            actions_row = QHBoxLayout()
            self.download_button = QPushButton("Baixar Selecionados")
            self.download_button.clicked.connect(self.download_selected)
            self.import_button = QPushButton("Importar para Lista")
            self.import_button.clicked.connect(self.import_selected)
            self.expand_button = QPushButton("Expandir")
            self.expand_button.clicked.connect(self.open_expanded_gallery)
            actions_row.addWidget(self.download_button)
            actions_row.addWidget(self.import_button)
            actions_row.addWidget(self.expand_button)

            result_layout.addWidget(self.results_grid)
            result_layout.addLayout(pagination_row)
            result_layout.addLayout(actions_row)

            layout.addWidget(search_group)
            layout.addWidget(result_group)

            self.autocomplete = DanbooruAutocomplete(self.search_edit, self.client)
            self._update_page_controls()

        def close(self):
            if self._active_search_task_id and self.main_window.task_runner.is_running(self._active_search_task_id):
                self.main_window.task_runner.cancel(self._active_search_task_id)
            if self._expanded_dialog is not None:
                self._expanded_dialog.close()
            if self._image_viewer is not None:
                self._image_viewer.close()
            self.autocomplete.close()
            self.results_grid.close()
            self.client.close()

        def _build_tags(self):
            parts = [self.search_edit.text().strip()]
            rating_tag = RATING_TAGS.get(self.rating_combo.currentText(), "")
            sort_tag = SORT_TAGS.get(self.sort_combo.currentText(), "")
            if rating_tag:
                parts.append(rating_tag)
            if sort_tag:
                parts.append(sort_tag)
            return " ".join(part for part in parts if part).strip()

        def _set_results_summary(self):
            if self.posts:
                self.summary_label.setText(
                    f"{len(self.posts)} resultado(s) encontrados na pagina {self.current_page}."
                )
            elif self._active_search_tags:
                self.summary_label.setText(f"Nenhum resultado encontrado na pagina {self.current_page}.")
            else:
                self.summary_label.setText("Nenhuma busca executada.")

        def _update_page_controls(self):
            self.page_label.setText(f"Pagina {self.current_page}")
            has_search = bool(self._active_search_tags)
            self.prev_button.setEnabled(has_search and self.current_page > 1)
            self.next_button.setEnabled(has_search and self._has_next_page)

        def _posts_with_selected_thumbnails(self, posts):
            selected_posts = list(self.selection_state.selected_posts_details.values())
            selected_ids = {post.get("id") for post in selected_posts}
            merged = list(selected_posts)
            for post in posts or []:
                if post.get("id") not in selected_ids:
                    merged.append(post)
            return merged

        def search(self, page=1, use_active_tags=False):
            tags = self._active_search_tags if use_active_tags else self._build_tags()
            if not tags:
                self.main_window.show_warning("Busca", "Informe ao menos uma tag.")
                return

            if self._active_search_task_id and self.main_window.task_runner.is_running(self._active_search_task_id):
                self.main_window.task_runner.cancel(self._active_search_task_id)

            self.current_page = max(1, int(page or 1))
            if not use_active_tags:
                self._active_search_tags = tags
                self._active_query_label = self.search_edit.text().strip() or tags
                self.results_grid.clear_selection()

            self._has_next_page = False
            self.search_button.setEnabled(False)
            self._update_page_controls()
            self.results_grid.display_loading()
            self.summary_label.setText(f"Buscando pagina {self.current_page}...")

            self._search_seq += 1
            task_id = f"qt_online_search_{self._search_seq}"
            self._active_search_task_id = task_id
            active_page = self.current_page
            active_tags = self._active_search_tags

            def task_fn(_cancel_event, on_progress):
                if on_progress:
                    on_progress(0, 1, "Buscando no Danbooru...")
                posts = self.client.search_posts(active_tags, limit=self._page_size, page=active_page)
                if on_progress:
                    on_progress(1, 1, f"{len(posts)} resultado(s) carregado(s).")
                return {"task_id": task_id, "page": active_page, "posts": posts}

            def on_done(result):
                self.search_button.setEnabled(True)
                if result.get("task_id") != self._active_search_task_id:
                    return
                self._active_search_task_id = None
                self.current_page = result.get("page") or self.current_page
                self.posts = result.get("posts") or []
                self._has_next_page = len(self.posts) >= self._page_size
                self.results_grid.display_posts(self._posts_with_selected_thumbnails(self.posts))
                self._set_results_summary()
                self._update_page_controls()
                self.main_window.show_status(
                    f"Busca concluida: pagina {self.current_page} com {len(self.posts)} resultado(s)."
                )

            def on_error(exc):
                self.search_button.setEnabled(True)
                if task_id != self._active_search_task_id:
                    return
                self._active_search_task_id = None
                self.posts = []
                self._has_next_page = False
                self.results_grid.display_posts(self._posts_with_selected_thumbnails([]))
                self.summary_label.setText(f"Erro na página {self.current_page}: {exc}")
                self._update_page_controls()
                logger.exception("Erro na busca Danbooru Qt: %s", exc)
                self.main_window.show_warning("Danbooru", str(exc))

            handle = self.main_window.task_runner.submit(task_id, task_fn)
            if handle is None:
                return
            handle.done.connect(on_done)
            handle.error.connect(on_error)

        def change_page(self, delta):
            if not self._active_search_tags:
                self.main_window.show_info("Paginacao", "Faca uma busca primeiro.")
                return
            new_page = self.current_page + delta
            if new_page < 1:
                return
            self.search(page=new_page, use_active_tags=True)

        def _selected_posts(self):
            return list(self.selection_state.selected_posts_details.values())

        def _resolve_import_directory(self):
            image_paths = list(self.main_window.editor_state.image_list or [])
            if image_paths:
                folders = {os.path.dirname(path) for path in image_paths if path}
                if len(folders) == 1:
                    folder = next(iter(folders))
                    if folder and os.path.isdir(folder):
                        return folder
            fallback = self.main_window.ui_preferences.last_folder
            if fallback and os.path.isdir(fallback):
                return fallback
            return None

        def _resolve_download_workers(self):
            configured = self.main_window.app_config.get("max_workers")
            try:
                value = int(configured) if configured is not None else 4
            except (TypeError, ValueError):
                value = 4
            return max(2, min(8, value))

        def _update_selection_summary(self, count=None):
            if self._active_search_task_id:
                return
            posts = self._selected_posts()
            if not posts:
                self._set_results_summary()
                return
            sample = posts[0]
            self.summary_label.setText(
                f"{count or len(posts)} selecionado(s). Primeiro item: #{sample.get('id')} com rating {sample.get('rating', '?')}."
            )

        def _handle_expanded_selection_changed(self, count):
            self.results_grid.display_posts(self._posts_with_selected_thumbnails(self.posts))
            self._update_selection_summary(count)

        def _download_posts(self, target_dir, import_after=False):
            selected_posts = self._selected_posts()
            if not selected_posts:
                self.main_window.show_warning("Danbooru", "Selecione ao menos um resultado.")
                return

            def task_fn(cancel_event, on_progress):
                downloaded_paths = []
                errors = []
                total = len(selected_posts)
                max_workers = min(total, self._resolve_download_workers())

                def download_one(post):
                    if cancel_event.is_set():
                        return {"cancelled": True, "post_id": post.get("id")}

                    file_url = post.get("file_url") or post.get("large_file_url") or post.get("sample_url")
                    if not file_url:
                        return {"error": f"Post {post.get('id')}: URL nao encontrada."}

                    filename = f"{post.get('id')}.{post.get('file_ext', 'png')}"
                    target_path = os.path.join(target_dir, filename)
                    data = self.client.download_image(file_url)
                    if not data:
                        return {"error": f"Post {post.get('id')}: download vazio."}

                    with open(target_path, "wb") as file_obj:
                        file_obj.write(data)
                    return {"path": target_path}

                processed = 0
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=max_workers,
                    thread_name_prefix="danbooru_dl",
                ) as executor:
                    futures = [executor.submit(download_one, post) for post in selected_posts]
                    for future in concurrent.futures.as_completed(futures):
                        processed += 1
                        try:
                            result = future.result()
                        except Exception as exc:
                            errors.append(str(exc))
                            result = {}

                        if result.get("path"):
                            downloaded_paths.append(result["path"])
                        elif result.get("error"):
                            errors.append(result["error"])

                        if on_progress:
                            on_progress(processed, total, f"Baixado {processed}/{total}")

                        if cancel_event.is_set():
                            return {"cancelled": True, "paths": downloaded_paths, "errors": errors}

                return {"cancelled": False, "paths": downloaded_paths, "errors": errors}

            def on_done(result):
                errors = result.get("errors") or []
                if errors:
                    self.main_window.show_warning("Danbooru", "\n".join(errors[:10]))
                if import_after and result.get("paths"):
                    self.main_window.add_images(result["paths"], replace=False, select_last=True)
                self.main_window.show_status(f"Download concluido: {len(result.get('paths') or [])} arquivo(s).")

            self.main_window.run_task(
                "qt_online_download",
                "Baixando",
                task_fn,
                on_done=on_done,
                maximum=max(1, len(selected_posts)),
            )

        def download_selected(self):
            target_dir = self.main_window.choose_directory("Selecione a pasta de destino")
            if not target_dir:
                return
            self._download_posts(target_dir, import_after=False)

        def import_selected(self):
            target_dir = self._resolve_import_directory()
            if not target_dir:
                self.main_window.show_warning("Importar", "Abra uma pasta na edicao antes de importar imagens.")
                return
            self._download_posts(target_dir, import_after=True)

        def open_expanded_gallery(self):
            if not self.posts:
                self.main_window.show_info("Galeria", "Faca uma busca primeiro.")
                return
            dialog = DanbooruGalleryDialog(
                self.posts,
                self.main_window.app_config,
                self.client,
                tags=self._active_search_tags,
                current_page=self.current_page,
                selection_state=self.selection_state,
                parent=self,
                title=f"Galeria Expandida - {self._active_query_label or 'Danbooru'}",
            )
            dialog.grid.image_open_requested.connect(self.open_image_viewer)
            dialog.grid.selection_count_changed.connect(self._handle_expanded_selection_changed)
            dialog.destroyed.connect(lambda *_args: setattr(self, "_expanded_dialog", None))
            dialog.showMaximized()
            dialog.show()
            self._expanded_dialog = dialog

        def open_image_viewer(self, post):
            viewer = DanbooruImageViewer(post, self.client, parent=self)
            viewer.showMaximized()
            viewer.show()
            self._image_viewer = viewer
else:
    class OnlineTab:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
