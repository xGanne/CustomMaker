from src.qt.compat import QT_AVAILABLE, qt_unavailable_error

if QT_AVAILABLE:
    from src.qt.compat import QDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout


if QT_AVAILABLE:
    class ProgressDialog(QDialog):
        def __init__(self, parent=None, title="Processando...", maximum=1, on_cancel=None):
            super().__init__(parent)
            self.setWindowTitle(title)
            self.setModal(True)
            self.setMinimumWidth(360)
            self.maximum = max(1, maximum)
            self._on_cancel = on_cancel
            self._task_running = True

            layout = QVBoxLayout(self)
            self.label = QLabel("Iniciando...", self)
            self.progress_bar = QProgressBar(self)
            self.progress_bar.setRange(0, self.maximum)
            self.progress_bar.setValue(0)
            layout.addWidget(self.label)
            layout.addWidget(self.progress_bar)

            if on_cancel:
                self.cancel_button = QPushButton("Cancelar", self)
                self.cancel_button.clicked.connect(self._handle_cancel)
                layout.addWidget(self.cancel_button)
            else:
                self.cancel_button = None

        def _handle_cancel(self):
            if self._on_cancel:
                self._on_cancel()

        def mark_done(self):
            self._task_running = False

        def closeEvent(self, event):
            if self._task_running and self._on_cancel:
                self._on_cancel()
            self._task_running = False
            super().closeEvent(event)

        def update_progress(self, current, total=None, text=None):
            if total is not None:
                self.maximum = max(1, total)
                self.progress_bar.setRange(0, self.maximum)
            self.progress_bar.setValue(max(0, min(self.maximum, current)))
            if text:
                self.label.setText(text)
else:
    class ProgressDialog:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
