import concurrent.futures
import os
from io import BytesIO

from PIL import Image

from src.qt.compat import QT_AVAILABLE, qt_unavailable_error

if QT_AVAILABLE:
    from src.qt.compat import (
        QIcon,
        QImage,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMenu,
        QPixmap,
        QSize,
        QVBoxLayout,
        QWidget,
        Qt,
        Signal,
    )

_THUMB_W = 60
_THUMB_H = 75


if QT_AVAILABLE:
    class ImageListPanel(QWidget):
        selection_changed = Signal(int)
        remove_requested = Signal(int)
        toggle_individual_requested = Signal(int)
        order_changed = Signal(list)  # C1: emitted after drag-reorder

        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 6, 10, 10)
            layout.setSpacing(8)
            self.title = QLabel("Lista de Imagens", self)
            self.list_widget = QListWidget(self)
            self.list_widget.setMinimumHeight(180)
            self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
            self.list_widget.setIconSize(QSize(_THUMB_W, _THUMB_H))  # B3
            # C1: enable internal drag-to-reorder
            from src.qt.compat import QAbstractItemView
            self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)
            self.list_widget.setDefaultDropAction(Qt.MoveAction)
            self.list_widget.model().rowsMoved.connect(self._on_rows_moved)

            self.list_widget.currentRowChanged.connect(self.selection_changed.emit)
            self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
            layout.addWidget(self.title)
            layout.addWidget(self.list_widget)

            self._paths = []
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="list_thumb"
            )
            self._generation = 0

        def set_paths(self, paths):
            self._generation += 1
            generation = self._generation
            self._paths = list(paths)
            self.list_widget.clear()
            placeholder = self._placeholder_icon()
            for path in paths:
                item = QListWidgetItem(placeholder, os.path.basename(path))
                item.setData(Qt.UserRole, path)
                item.setToolTip(path)
                self.list_widget.addItem(item)
                self._load_thumb_async(item, path, generation)
            self.title.setText(f"Lista de Imagens ({len(paths)})")

        def set_current_index(self, index):
            self.list_widget.blockSignals(True)
            self.list_widget.setCurrentRow(index if index is not None else -1)
            self.list_widget.blockSignals(False)

        # ── B3: thumbnail loading ──────────────────────────────────────────

        @staticmethod
        def _placeholder_icon():
            pixmap = QPixmap(_THUMB_W, _THUMB_H)
            pixmap.fill(Qt.darkGray)
            return QIcon(pixmap)

        def _load_thumb_async(self, item, path, generation):
            future = self._executor.submit(self._generate_thumb, path)

            def on_done(f):
                try:
                    pixmap = f.result()
                except Exception:
                    return
                if pixmap and generation == self._generation:
                    # must set icon from main thread via a queued call
                    item.setIcon(QIcon(pixmap))

            future.add_done_callback(on_done)

        @staticmethod
        def _generate_thumb(path):
            try:
                with Image.open(path) as img:
                    thumb = img.convert("RGBA")
                    thumb.thumbnail((_THUMB_W, _THUMB_H), Image.LANCZOS)
                    data = thumb.tobytes("raw", "RGBA")
                    qimage = QImage(data, thumb.width, thumb.height, thumb.width * 4, QImage.Format_RGBA8888)
                    return QPixmap.fromImage(qimage.copy())
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
            menu = QMenu(self)
            remove_action = menu.addAction("Remover")
            individual_action = menu.addAction("Alternar borda individual")
            chosen = menu.exec(self.list_widget.mapToGlobal(pos))
            if chosen == remove_action:
                self.remove_requested.emit(index)
            elif chosen == individual_action:
                self.toggle_individual_requested.emit(index)

        def close(self):
            self._executor.shutdown(wait=False, cancel_futures=True)
            super().close()

else:
    class ImageListPanel:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
