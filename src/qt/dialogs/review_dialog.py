"""Revisão em grade: todas as customs lado a lado, como serão exportadas.

Depois de um "Gerar customs" (ou a qualquer momento, pela aba Edição), mostra
as customs prontas para achar as que ficaram ruins sem navegar uma a uma.
Duplo clique abre a imagem no editor; "Atualizar" redesenha após ajustes.
"Calcular tamanhos" mede cada custom como será exportada (GIF animado pesa).
"""
import os
import shutil
import tempfile
import threading

from src.config.settings import BORDA_HEIGHT, BORDA_WIDTH
from src.core.batch_worker import render_custom_preview
from src.core.file_sizes import format_bytes, size_summary, warn_limit_bytes
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error
from src.qt.theme import tokens

if QT_AVAILABLE:
    from PySide6.QtGui import QBrush

    from src.qt.compat import (
        QColor,
        QDialog,
        QHBoxLayout,
        QIcon,
        QLabel,
        QListView,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QSize,
        Qt,
        QVBoxLayout,
    )

# cards na metade do tamanho real da custom
CARD_W, CARD_H = BORDA_WIDTH * 2 // 3, BORDA_HEIGHT * 2 // 3


if QT_AVAILABLE:
    class ReviewDialog(QDialog):
        def __init__(self, main_window, paths=None, title="Revisar customs", summary=None, measure=False):
            super().__init__(main_window)
            self.main_window = main_window
            self._paths = list(paths) if paths is not None else None
            self._render_seq = 0
            self._active_task_id = None
            self._measure_seq = 0
            self._measure_task_id = None
            self._items = {}  # path -> card
            self._sizes = {}  # path -> resultado da medição
            self._measure_after_render = measure
            self.setWindowTitle(title)
            self.setAttribute(Qt.WA_DeleteOnClose, True)
            self.resize(980, 720)

            layout = QVBoxLayout(self)
            if summary:
                headline = QLabel(summary)
                headline.setWordWrap(True)
                layout.addWidget(headline)
            self.hint = QLabel(
                "Prévia das customs como serão exportadas (animações aparecem com a borda "
                "estática). Duplo clique abre a imagem no editor para ajustar; depois, "
                "clique em Atualizar e exporte de novo."
            )
            self.hint.setWordWrap(True)
            self.hint.setStyleSheet(f"color: {tokens()['text_muted']}; font-size: 11px;")
            layout.addWidget(self.hint)

            self.grid = QListWidget(self)
            self.grid.setViewMode(QListView.IconMode)
            self.grid.setResizeMode(QListView.Adjust)
            self.grid.setMovement(QListView.Static)
            self.grid.setSpacing(8)
            self.grid.setIconSize(QSize(CARD_W, CARD_H))
            self.grid.setGridSize(QSize(CARD_W + 24, CARD_H + 44))
            self.grid.setWordWrap(True)
            self.grid.itemDoubleClicked.connect(self._open_in_editor)
            layout.addWidget(self.grid, 1)

            buttons = QHBoxLayout()
            self.status = QLabel("")
            self.status.setStyleSheet(f"color: {tokens()['text_muted']}; font-size: 11px;")
            self.measure_button = QPushButton("Calcular tamanhos")
            self.measure_button.setProperty("class", "secondary")
            self.measure_button.setToolTip(
                "Mede quanto cada custom vai pesar, no formato da exportação (GIF com animação)"
            )
            self.measure_button.clicked.connect(self.measure_sizes)
            refresh = QPushButton("Atualizar")
            refresh.setProperty("class", "secondary")
            refresh.clicked.connect(self.render)
            close = QPushButton("Fechar")
            close.clicked.connect(self.close)
            buttons.addWidget(self.status, 1)
            buttons.addWidget(self.measure_button)
            buttons.addWidget(refresh)
            buttons.addWidget(close)
            layout.addLayout(buttons)

            self.render()

        def _current_paths(self):
            image_list = self.main_window.editor_state.image_list
            if self._paths is None:
                return list(image_list)
            # imagens removidas da lista saem da revisão
            return [p for p in self._paths if p in image_list]

        def render(self):
            """Renderiza as prévias em segundo plano, sobre um retrato do estado."""
            paths = self._current_paths()
            self._cancel_measure()
            self._sizes.clear()  # a borda/animação pode ter mudado: tamanhos velhos
            self._items.clear()
            self.grid.clear()
            if not paths:
                self.status.setText("Nenhuma imagem para revisar.")
                return
            self.status.setText(f"Renderizando {len(paths)} custom(s)...")
            batch = self.main_window.batch_controller.frozen()  # GUI thread
            self._render_seq += 1
            seq = self._render_seq
            task_id = f"qt_review_render_{id(self)}_{seq}"
            self._active_task_id = task_id

            def task_fn(cancel_event, _on_progress):
                source_dir = tempfile.mkdtemp(prefix="custommaker_review_")
                previews = []
                try:
                    for path in paths:
                        if cancel_event.is_set():
                            break
                        try:
                            data = batch._get_task_data(path, None, source_dir=source_dir)
                            image = render_custom_preview(data) if data else None
                            error = None if data else "sem enquadramento possível"
                        except Exception as exc:  # arquivo sumiu/ilegível: card de erro
                            image, error = None, str(exc)
                        if image is not None:
                            image.thumbnail((CARD_W, CARD_H))
                        previews.append((path, image, error))
                finally:
                    shutil.rmtree(source_dir, ignore_errors=True)
                return {"seq": seq, "previews": previews}

            def on_done(result):
                try:
                    if result.get("seq") != self._render_seq:
                        return
                    self._show_previews(result.get("previews") or [])
                except RuntimeError:
                    pass  # diálogo fechado enquanto renderizava

            handle = self.main_window.task_runner.submit(task_id, task_fn)
            if handle is not None:
                handle.done.connect(on_done)

        def _show_previews(self, previews):
            from src.qt.pixmap_utils import pil_to_qpixmap
            self.grid.clear()
            self._items.clear()
            errors = 0
            for path, image, error in previews:
                item = QListWidgetItem(os.path.basename(path))
                item.setData(Qt.UserRole, path)
                self._items[path] = item
                if image is not None:
                    item.setIcon(QIcon(pil_to_qpixmap(image)))
                    image.close()
                    item.setToolTip(f"{path}\nDuplo clique: abrir no editor")
                else:
                    errors += 1
                    item.setText(f"{os.path.basename(path)}\n⚠ {error}")
                    item.setToolTip(f"{path}\nNão foi possível gerar a prévia: {error}")
                self.grid.addItem(item)
            summary = f"{len(previews)} custom(s)"
            if errors:
                summary += f" · {errors} com problema"
            self.status.setText(summary)
            if self._measure_after_render:
                self._measure_after_render = False
                self.measure_sizes()

        # ── Tamanho das customs ───────────────────────────────────────────

        def measure_sizes(self):
            """Mede, no pool de exportação, quanto cada custom vai pesar."""
            paths = [p for p in self._current_paths() if p in self._items]
            if not paths:
                return
            self._cancel_measure()
            batch = self.main_window.batch_controller.frozen()  # GUI thread
            cache = self.main_window.__dict__.setdefault("_size_cache", {})
            if len(cache) > 2000:
                cache.clear()
            arrived = {}
            lock = threading.Lock()
            self._measure_seq += 1
            seq = self._measure_seq
            task_id = f"qt_review_measure_{id(self)}_{seq}"
            self._measure_task_id = task_id
            self.measure_button.setEnabled(False)
            self.status.setText(f"Medindo 0/{len(paths)}...")

            def task_fn(cancel_event, on_progress):
                def on_result(result):
                    with lock:
                        arrived[result.get("path")] = result
                        count = len(arrived)
                    if on_progress:
                        on_progress(count, len(paths), "")

                return {"seq": seq, **batch.measure_sizes(paths, cancel_event=cancel_event, on_result=on_result, cache=cache)}

            def on_progress(done_count, total, _message):
                try:
                    if seq != self._measure_seq:
                        return
                    with lock:
                        self._sizes.update(arrived)
                    self._apply_sizes()
                    self.status.setText(f"Medindo {done_count}/{total}...")
                except RuntimeError:
                    pass  # diálogo fechado enquanto media

            def on_done(result):
                try:
                    if result.get("seq") != self._measure_seq:
                        return
                    self._measure_task_id = None
                    for item in result.get("results") or []:
                        self._sizes[item.get("path")] = item
                    self._apply_sizes()
                    self._show_size_summary()
                    self.measure_button.setEnabled(True)
                except RuntimeError:
                    pass

            def on_error(exc):
                try:
                    if seq != self._measure_seq:
                        return
                    self._measure_task_id = None
                    self.measure_button.setEnabled(True)
                    self.status.setText(f"Não foi possível medir: {exc}")
                except RuntimeError:
                    pass

            handle = self.main_window.task_runner.submit(task_id, task_fn)
            if handle is None:
                self.measure_button.setEnabled(True)
                return
            handle.progress.connect(on_progress)
            handle.done.connect(on_done)
            handle.error.connect(on_error)

        def _cancel_measure(self):
            self._measure_seq += 1
            if self._measure_task_id:
                self.main_window.task_runner.cancel(self._measure_task_id)
                self._measure_task_id = None
            if hasattr(self, "measure_button"):
                self.measure_button.setEnabled(True)

        def _over_limit(self, size):
            limit = warn_limit_bytes(self.main_window.app_config)
            return limit is not None and size > limit

        def _apply_sizes(self):
            for path, result in self._sizes.items():
                item = self._items.get(path)
                if item is None or result.get("status") != "success":
                    continue
                name = os.path.basename(path)
                label = f"{result['format'].upper()} · {format_bytes(result['bytes'])}"
                if self._over_limit(result["bytes"]):
                    item.setText(f"{name}\n⚠ {label}")
                    item.setForeground(QBrush(QColor(tokens()["warning"])))
                else:
                    item.setText(f"{name}\n{label}")
                    item.setData(Qt.ForegroundRole, None)  # limite aumentou: tira o destaque

        def _show_size_summary(self):
            sizes = {p: r["bytes"] for p, r in self._sizes.items() if r.get("status") == "success"}
            total, largest = size_summary(sizes)
            if not largest:
                self.status.setText("Não foi possível medir as customs.")
                return
            text = (
                f"{len(sizes)} custom(s) · total {format_bytes(total)} · maior "
                f"{format_bytes(largest[1])} ({os.path.basename(largest[0])})"
            )
            over = sum(1 for size in sizes.values() if self._over_limit(size))
            if over:
                text += f" · ⚠ {over} acima de {format_bytes(warn_limit_bytes(self.main_window.app_config))}"
            self.status.setText(text)

        def closeEvent(self, event):
            # a renderização/medição em andamento não deve chegar a um diálogo destruído
            self._render_seq += 1
            if self._active_task_id:
                self.main_window.task_runner.cancel(self._active_task_id)
            self._cancel_measure()
            super().closeEvent(event)

        def _open_in_editor(self, item):
            path = item.data(Qt.UserRole)
            image_list = self.main_window.editor_state.image_list
            if path not in image_list:
                self.status.setText("Essa imagem não está mais na lista do editor.")
                return
            self.main_window.load_image(image_list.index(path))
            self.main_window.raise_()
            self.main_window.activateWindow()
            self.status.setText(f"Aberta no editor: {os.path.basename(path)} — ajuste e clique em Atualizar.")
else:
    class ReviewDialog:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
