from src.qt.compat import QT_AVAILABLE, qt_unavailable_error

if QT_AVAILABLE:
    from src.qt.compat import QLabel, QListWidget, QListWidgetItem, QMenu, QVBoxLayout, QWidget, Qt, Signal


if QT_AVAILABLE:
    class ImageListPanel(QWidget):
        selection_changed = Signal(int)
        remove_requested = Signal(int)
        toggle_individual_requested = Signal(int)

        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 6, 10, 10)
            layout.setSpacing(8)
            self.title = QLabel("Lista de Imagens", self)
            self.list_widget = QListWidget(self)
            self.list_widget.setMinimumHeight(180)
            self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
            self.list_widget.currentRowChanged.connect(self.selection_changed.emit)
            self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
            layout.addWidget(self.title)
            layout.addWidget(self.list_widget)

        def set_paths(self, paths):
            self.list_widget.clear()
            for path in paths:
                self.list_widget.addItem(QListWidgetItem(path))
            self.title.setText(f"Lista de Imagens ({len(paths)})")

        def set_current_index(self, index):
            self.list_widget.blockSignals(True)
            self.list_widget.setCurrentRow(index if index is not None else -1)
            self.list_widget.blockSignals(False)

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
else:
    class ImageListPanel:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
