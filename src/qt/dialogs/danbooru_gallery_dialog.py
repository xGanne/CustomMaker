from src.core.danbooru import filter_blacklisted
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error
from src.qt.theme import tokens
from src.qt.task_runner import QtTaskRunner
from src.qt.widgets.danbooru_grid import DanbooruResultsGrid

if QT_AVAILABLE:
    from src.qt.compat import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, Qt


if QT_AVAILABLE:
    class DanbooruGalleryDialog(QDialog):
        def __init__(
            self,
            posts,
            app_config,
            client,
            tags="",
            current_page=1,
            exclude_tags=None,
            has_next_page=None,
            selection_state=None,
            parent=None,
            title="Galeria Expandida",
        ):
            super().__init__(parent)
            self.setWindowTitle(title)
            self.resize(1280, 860)
            self.setModal(False)
            self.setWindowFlags(
                self.windowFlags()
                | Qt.WindowMinimizeButtonHint
                | Qt.WindowMaximizeButtonHint
                | Qt.WindowCloseButtonHint
            )

            self.client = client
            self.tags = tags or ""
            self.posts = posts or []
            self.current_page = max(1, int(current_page or 1))
            self._page_size = 20
            self._exclude_tags = list(exclude_tags or [])
            # os posts recebidos já vêm filtrados pela blacklist, então o
            # tamanho deles não diz se há próxima página — a aba informa
            self._has_next_page = (
                has_next_page if has_next_page is not None else len(self.posts) >= self._page_size
            )
            self._search_seq = 0
            self._active_search_task_id = None
            self._task_runner = QtTaskRunner(self)

            layout = QVBoxLayout(self)
            layout.setSpacing(6)

            self.grid = DanbooruResultsGrid(app_config, client, self, selection_state=selection_state)
            # Tamanhos absolutos: a janela expandida é larga, então não deve
            # herdar os cards compactos do painel lateral.
            from src.qt.compat import QSize
            self.grid.setIconSize(QSize(190, 190))
            self.grid.setGridSize(QSize(212, 250))
            self.grid.selection_count_changed.connect(self._update_selection_label)
            layout.addWidget(self.grid, 1)

            # Status + pagination row
            status_row = QHBoxLayout()
            self.results_label = QLabel()
            self.results_label.setWordWrap(True)
            self.results_label.setStyleSheet(f"color: {tokens()['text_muted']}; font-size: 11px;")
            status_row.addWidget(self.results_label, 1)

            self.selection_label = QLabel("0 selecionados")
            self.selection_label.setStyleSheet(f"color: {tokens()['text_muted']}; font-size: 11px;")
            status_row.addWidget(self.selection_label)

            self.prev_button = QPushButton("←")
            self.prev_button.setFixedWidth(36)
            self.prev_button.clicked.connect(lambda: self.change_page(-1))
            self.page_label = QLabel()
            self.page_label.setStyleSheet("font-size: 11px; padding: 0 4px;")
            self.next_button = QPushButton("→")
            self.next_button.setFixedWidth(36)
            self.next_button.clicked.connect(lambda: self.change_page(1))
            status_row.addWidget(self.prev_button)
            status_row.addWidget(self.page_label)
            status_row.addWidget(self.next_button)
            layout.addLayout(status_row)

            # Action buttons
            buttons_row = QHBoxLayout()
            self.import_button = QPushButton("Importar para Lista")
            self.import_button.clicked.connect(self._import_selected)
            self.download_button = QPushButton("Baixar Selecionados")
            self.download_button.setProperty("class", "secondary")
            self.download_button.clicked.connect(self._download_selected)
            close_button = QPushButton("Fechar")
            close_button.setProperty("class", "secondary")
            close_button.clicked.connect(self.close)
            buttons_row.addWidget(self.import_button)
            buttons_row.addWidget(self.download_button)
            buttons_row.addStretch(1)
            buttons_row.addWidget(close_button)
            layout.addLayout(buttons_row)

            self.grid.display_posts(self.posts)
            self._set_results_summary()
            self._update_page_controls()
            self._update_action_buttons()

        def _set_results_summary(self):
            if self.posts:
                self.results_label.setText(
                    f"{len(self.posts)} resultado(s) · pág. {self.current_page}"
                )
            elif self.tags:
                self.results_label.setText(f"Nenhum resultado · pág. {self.current_page}")
            else:
                self.results_label.setText("Nenhum resultado para exibir.")

        def _update_selection_label(self, count):
            noun = "selecionado" if count == 1 else "selecionados"
            self.selection_label.setText(f"{count} {noun}")
            self._update_action_buttons()

        def _selected_count(self):
            return len(self.grid.get_selected_items())

        def _update_action_buttons(self):
            has_selection = self._selected_count() > 0
            self.download_button.setEnabled(has_selection)
            self.import_button.setEnabled(has_selection)

        def _download_selected(self):
            parent = self.parent()
            if parent is not None and hasattr(parent, "download_selected"):
                parent.download_selected()

        def _import_selected(self):
            parent = self.parent()
            if parent is not None and hasattr(parent, "import_selected"):
                parent.import_selected()

        def _update_page_controls(self):
            self.page_label.setText(f"Pág. {self.current_page}")
            has_search = bool(self.tags)
            self.prev_button.setEnabled(has_search and self.current_page > 1)
            self.next_button.setEnabled(has_search and self._has_next_page)

        def change_page(self, delta):
            if not self.tags:
                return
            new_page = self.current_page + delta
            if new_page < 1:
                return
            self._load_page(new_page)

        def _load_page(self, page):
            if not self.tags:
                return

            if self._active_search_task_id and self._task_runner.is_running(self._active_search_task_id):
                self._task_runner.cancel(self._active_search_task_id)

            self.current_page = max(1, int(page or 1))
            self._has_next_page = False
            self._update_page_controls()
            self.grid.display_loading()
            self.results_label.setText(f"Buscando pág. {self.current_page}...")

            self._search_seq += 1
            task_id = f"qt_gallery_search_{id(self)}_{self._search_seq}"
            self._active_search_task_id = task_id
            active_page = self.current_page
            active_tags = self.tags

            exclude_tags = list(self._exclude_tags)

            def task_fn(_cancel_event, _on_progress):
                raw_posts = self.client.search_posts(active_tags, limit=self._page_size, page=active_page)
                return {
                    "task_id": task_id,
                    "page": active_page,
                    "posts": filter_blacklisted(raw_posts, exclude_tags),
                    "raw_count": len(raw_posts),
                }

            def on_done(result):
                if result.get("task_id") != self._active_search_task_id:
                    return
                self._active_search_task_id = None
                self.current_page = result.get("page") or self.current_page
                self.posts = result.get("posts") or []
                self._has_next_page = result.get("raw_count", len(self.posts)) >= self._page_size
                self.grid.display_posts(self.posts)
                self._set_results_summary()
                self._update_page_controls()

            def on_error(_exc):
                if task_id != self._active_search_task_id:
                    return
                self._active_search_task_id = None
                self.grid.display_posts(self.posts)
                self._set_results_summary()
                self._update_page_controls()

            handle = self._task_runner.submit(task_id, task_fn)
            if handle is None:
                return
            handle.done.connect(on_done)
            handle.error.connect(on_error)

        def closeEvent(self, event):
            if self._active_search_task_id and self._task_runner.is_running(self._active_search_task_id):
                self._task_runner.cancel(self._active_search_task_id)
            self.grid.close()
            super().closeEvent(event)

else:
    class DanbooruGalleryDialog:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
