"""Revisão em grade: todas as customs lado a lado, como serão exportadas.

Depois de um "Gerar customs" (ou a qualquer momento, pela aba Edição), mostra
as customs prontas para achar as que ficaram ruins sem navegar uma a uma.
Duplo clique abre a imagem no editor; "Atualizar" redesenha após ajustes.
"""
import os
import shutil
import tempfile

from src.config.settings import BORDA_HEIGHT, BORDA_WIDTH
from src.core.batch_worker import render_custom_preview
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error
from src.qt.theme import tokens

if QT_AVAILABLE:
    from src.qt.compat import (
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
        def __init__(self, main_window, paths=None, title="Revisar customs", summary=None):
            super().__init__(main_window)
            self.main_window = main_window
            self._paths = list(paths) if paths is not None else None
            self._render_seq = 0
            self._active_task_id = None
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
            refresh = QPushButton("Atualizar")
            refresh.setProperty("class", "secondary")
            refresh.clicked.connect(self.render)
            close = QPushButton("Fechar")
            close.clicked.connect(self.close)
            buttons.addWidget(self.status, 1)
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
            errors = 0
            for path, image, error in previews:
                item = QListWidgetItem(os.path.basename(path))
                item.setData(Qt.UserRole, path)
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

        def closeEvent(self, event):
            # a renderização em andamento não deve chegar a um diálogo destruído
            self._render_seq += 1
            if self._active_task_id:
                self.main_window.task_runner.cancel(self._active_task_id)
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
