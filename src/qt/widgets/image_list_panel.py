import concurrent.futures
import os

from PIL import Image

from src.qt.compat import QT_AVAILABLE, qt_unavailable_error
from src.qt.theme import tokens
from src.qt.worker_signal import WorkerSignal
from src.utils.file_reveal import reveal_in_file_manager

if QT_AVAILABLE:
    from src.qt.compat import (
        QAbstractItemView,
        QColor,
        QIcon,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMenu,
        QPainter,
        QPen,
        QPixmap,
        QSize,
        QStyledItemDelegate,
        QVBoxLayout,
        QWidget,
        Qt,
        Signal,
    )

_THUMB_W = 60
_THUMB_H = 75

if QT_AVAILABLE:
    # M9: cor da borda individual do item (None = segue a borda global)
    BORDER_BADGE_ROLE = Qt.UserRole + 1


if QT_AVAILABLE:
    class _EmptyStateListWidget(QListWidget):
        """Lista que desenha uma orientação centralizada enquanto está vazia."""

        placeholder_text = "Nenhuma imagem carregada\n\nAbra uma pasta ou cole uma imagem"
        delete_pressed = Signal()

        def paintEvent(self, event):
            super().paintEvent(event)
            if self.count() > 0:
                return
            painter = QPainter(self.viewport())
            painter.setPen(QColor(tokens()["text_muted"]))
            painter.drawText(self.viewport().rect(), Qt.AlignCenter, self.placeholder_text)
            painter.end()

        def keyPressEvent(self, event):
            # M9: Delete remove as imagens selecionadas da lista
            if event.key() == Qt.Key_Delete and event.modifiers() == Qt.NoModifier:
                self.delete_pressed.emit()
                event.accept()
                return
            super().keyPressEvent(event)


    class _BorderBadgeDelegate(QStyledItemDelegate):
        """M9: bolinha com a cor da borda individual à direita do item — o
        toggle de borda individual era invisível na lista."""

        BADGE_DIAMETER = 12
        BADGE_MARGIN = 10

        def paint(self, painter, option, index):
            super().paint(painter, option, index)
            color = index.data(BORDER_BADGE_ROLE)
            if not color:
                return
            rect = option.rect
            diameter = self.BADGE_DIAMETER
            x = rect.right() - self.BADGE_MARGIN - diameter
            y = rect.center().y() - diameter // 2
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor(tokens()["border_strong"]), 1.5))
            painter.setBrush(QColor(color))
            painter.drawEllipse(x, y, diameter, diameter)
            painter.restore()


    class ImageListPanel(QWidget):
        selection_changed = Signal(int)
        remove_requested = Signal(list)  # M9: índices a remover (uma ou várias)
        toggle_individual_requested = Signal(int)
        order_changed = Signal(list)  # C1: emitted after drag-reorder

        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 6, 10, 10)
            layout.setSpacing(8)
            self.title = QLabel("Lista de Imagens", self)
            self.title.setStyleSheet(
                f"font-size: 10px; font-weight: 500; letter-spacing: 0.8px; color: {tokens()['text_muted']};"
            )
            self.list_widget = _EmptyStateListWidget(self)
            self.list_widget.setMinimumHeight(180)
            self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
            self.list_widget.setIconSize(QSize(_THUMB_W, _THUMB_H))  # B3
            # M9: Shift/Ctrl+clique selecionam várias imagens
            self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
            self.list_widget.setItemDelegate(_BorderBadgeDelegate(self.list_widget))
            # C1: enable internal drag-to-reorder
            self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)
            self.list_widget.setDefaultDropAction(Qt.MoveAction)
            self.list_widget.model().rowsMoved.connect(self._on_rows_moved)

            self.list_widget.currentRowChanged.connect(self.selection_changed.emit)
            self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
            self.list_widget.delete_pressed.connect(self._remove_selected)
            layout.addWidget(self.title)
            layout.addWidget(self.list_widget)

            self._paths = []
            self._border_badges = {}  # path -> (nome da borda, hex)
            self._edited_set = set()
            self._adjusted_set = set()
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="list_thumb"
            )
            self._generation = 0
            # as threads de miniatura emitem numa ponte que sobrevive ao painel
            self._thumbnail_signal = WorkerSignal()
            self._thumbnail_signal.ready.connect(self._on_thumbnail_ready)

        def set_paths(self, paths, edited_set=None, adjusted_set=None):
            self._generation += 1
            generation = self._generation
            self._paths = list(paths)
            self.list_widget.clear()
            placeholder = self._placeholder_icon()
            for path in paths:
                item = QListWidgetItem(placeholder, os.path.basename(path))
                item.setData(Qt.UserRole, path)
                self.list_widget.addItem(item)
                self._load_thumb_async(item, path, generation)
            self.title.setText(f"Lista de Imagens ({len(paths)})")
            if edited_set is not None or adjusted_set is not None:
                self._edited_set = set(edited_set or ())
                self._adjusted_set = set(adjusted_set or ())
            self._refresh_item_decorations()

        def update_indicators(self, edited_set, adjusted_set):
            self._edited_set = set(edited_set)
            self._adjusted_set = set(adjusted_set)
            self._refresh_item_decorations()

        def update_border_badges(self, badges):
            """M9: `badges` mapeia path → (nome da borda, hex) das imagens com
            borda individual; as demais seguem a borda global e ficam sem badge."""
            self._border_badges = dict(badges)
            self._refresh_item_decorations()

        def _refresh_item_decorations(self):
            theme = tokens()
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item is None:
                    continue
                path = item.data(Qt.UserRole)
                tooltip = [path]
                if path in self._edited_set:
                    item.setForeground(QColor(theme["success"]))
                    tooltip.append("● Pixels editados")
                elif path in self._adjusted_set:
                    item.setForeground(QColor(theme["warning"]))
                    tooltip.append("◉ Enquadramento ajustado")
                else:
                    item.setForeground(QColor(theme["text_primary"]))
                badge = self._border_badges.get(path)
                item.setData(BORDER_BADGE_ROLE, badge[1] if badge else None)
                if badge:
                    tooltip.append(f"◆ Borda individual: {badge[0]}")
                item.setToolTip("\n".join(tooltip))

        def set_current_index(self, index):
            self.list_widget.blockSignals(True)
            self.list_widget.setCurrentRow(index if index is not None else -1)
            self.list_widget.blockSignals(False)

        def selected_rows(self):
            return sorted(self.list_widget.row(item) for item in self.list_widget.selectedItems())

        def _remove_selected(self):
            rows = self.selected_rows()
            if not rows and self.list_widget.currentRow() >= 0:
                rows = [self.list_widget.currentRow()]
            if rows:
                self.remove_requested.emit(rows)

        # ── B3: thumbnail loading ──────────────────────────────────────────

        @staticmethod
        def _placeholder_icon():
            pixmap = QPixmap(_THUMB_W, _THUMB_H)
            pixmap.fill(Qt.darkGray)
            return QIcon(pixmap)

        def _load_thumb_async(self, item, path, generation):
            future = self._executor.submit(self._generate_thumb, path)
            signal = self._thumbnail_signal

            def on_done(f):
                # runs on the executor thread — only emit the signal here so the
                # QPixmap/QIcon work happens on the GUI thread (queued connection)
                try:
                    thumb = f.result()
                except Exception:
                    return
                signal.ready.emit((generation, item, thumb))

            future.add_done_callback(on_done)

        def _on_thumbnail_ready(self, payload):
            self._apply_thumbnail(*payload)

        def _apply_thumbnail(self, generation, item, thumb):
            if thumb is None:
                return
            if generation != self._generation:
                return
            from src.qt.pixmap_utils import pil_to_qpixmap
            item.setIcon(QIcon(pil_to_qpixmap(thumb)))

        @staticmethod
        def _generate_thumb(path):
            try:
                with Image.open(path) as img:
                    thumb = img.convert("RGBA")
                    thumb.thumbnail((_THUMB_W, _THUMB_H), Image.LANCZOS)
                    return thumb
            except Exception:
                return None

        # ── C1: drag-to-reorder ────────────────────────────────────────────

        def _on_rows_moved(self, _parent, start, _end, _dest, dest_row):
            new_paths = []
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                new_paths.append(item.data(Qt.UserRole))
            self._paths = new_paths
            self.title.setText(f"Lista de Imagens ({len(new_paths)})")
            self.order_changed.emit(new_paths)

        def _show_context_menu(self, pos):
            item = self.list_widget.itemAt(pos)
            if not item:
                return
            index = self.list_widget.row(item)
            # clicar fora da seleção atual age só sobre o item clicado
            selected = self.selected_rows()
            if index not in selected:
                selected = [index]
            menu = QMenu(self)
            if len(selected) > 1:
                remove_action = menu.addAction(f"Remover selecionadas ({len(selected)})\tDel")
            else:
                remove_action = menu.addAction("Remover\tDel")
            individual_action = menu.addAction("Alternar borda individual")
            menu.addSeparator()
            reveal_action = menu.addAction("Revelar no Explorer")
            chosen = menu.exec(self.list_widget.mapToGlobal(pos))
            if chosen == remove_action:
                self.remove_requested.emit(selected)
            elif chosen == individual_action:
                self.toggle_individual_requested.emit(index)
            elif chosen == reveal_action:
                reveal_in_file_manager(item.data(Qt.UserRole))

        def close(self):
            self._executor.shutdown(wait=False, cancel_futures=True)
            super().close()

else:
    class ImageListPanel:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
