"""Paleta de comandos (Ctrl+K): digite e execute qualquer ação do app."""
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error
from src.qt.theme import tokens

if QT_AVAILABLE:
    from src.qt.compat import (
        QDialog,
        QEvent,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        Qt,
        QTimer,
        QVBoxLayout,
    )


if QT_AVAILABLE:
    class CommandPalette(QDialog):
        def __init__(self, main_window, registry, recent_ids=(), on_run=None):
            super().__init__(main_window, Qt.Popup | Qt.FramelessWindowHint)
            self.main_window = main_window
            self.registry = registry
            self.recent_ids = list(recent_ids)
            self.on_run = on_run
            self.setObjectName("CommandPalette")
            self.setAttribute(Qt.WA_DeleteOnClose, True)
            self.resize(560, 380)
            t = tokens()
            self.setStyleSheet(
                f"#CommandPalette {{ background: {t['surface_elevated']}; border: 1px solid {t['border_strong']};"
                f" border-radius: {t['radius_md']}px; }}"
            )

            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            self.input = QLineEdit(self)
            self.input.setPlaceholderText("Digite um comando…  (Enter executa · Esc fecha)")
            self.input.textChanged.connect(self._refresh)
            self.input.installEventFilter(self)
            self.list = QListWidget(self)
            self.list.itemActivated.connect(self._run_item)
            self.list.itemClicked.connect(self._run_item)
            layout.addWidget(self.input)
            layout.addWidget(self.list, 1)
            self._refresh()

        def show_centered(self):
            parent = self.main_window
            geo = parent.geometry()
            self.move(geo.x() + (geo.width() - self.width()) // 2, geo.y() + 80)
            self.show()
            self.input.setFocus()

        def _refresh(self, *_args):
            self.list.clear()
            muted = tokens()["text_muted"]
            for command in self.registry.search(self.input.text(), self.recent_ids):
                parts = [command.title]
                if command.category:
                    parts.append(f"— {command.category}")
                if command.shortcut:
                    parts.append(f"  [{command.shortcut}]")
                item = QListWidgetItem("  ".join(parts))
                item.setData(Qt.UserRole, command.id)
                if not command.enabled():
                    item.setForeground(Qt.gray)
                    item.setToolTip("Indisponível agora")
                self.list.addItem(item)
            if self.list.count():
                self.list.setCurrentRow(0)
            self.list.setStyleSheet(f"QListWidget {{ border: none; }} QListWidget::item {{ padding: 6px; }}"
                                    f" QToolTip {{ color: {muted}; }}")

        def eventFilter(self, obj, event):
            # ↑/↓ movem a seleção sem tirar o foco do campo de busca
            if obj is self.input and event.type() == QEvent.KeyPress:
                key = event.key()
                step = {Qt.Key_Down: 1, Qt.Key_Up: -1, Qt.Key_PageDown: 8, Qt.Key_PageUp: -8}.get(key)
                if step and self.list.count():
                    row = max(0, min(self.list.count() - 1, self.list.currentRow() + step))
                    self.list.setCurrentRow(row)
                    return True
                if key in (Qt.Key_Return, Qt.Key_Enter):
                    item = self.list.currentItem()
                    if item is not None:
                        self._run_item(item)
                    return True
                if key == Qt.Key_Escape:
                    self.close()
                    return True
            return super().eventFilter(obj, event)

        def _run_item(self, item):
            command = self.registry.get(item.data(Qt.UserRole))
            if command is None:
                return
            if not command.enabled():
                self.main_window.show_status(f"“{command.title}” não está disponível agora.")
                return
            on_run = self.on_run
            self.close()
            # fecha antes: handlers que abrem diálogos modais não podem rodar com a paleta aberta
            QTimer.singleShot(0, lambda: on_run(command) if on_run else command.handler())
else:
    class CommandPalette:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
