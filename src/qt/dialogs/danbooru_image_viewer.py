from io import BytesIO

from PIL import Image

from src.qt.compat import QT_AVAILABLE, qt_unavailable_error

if QT_AVAILABLE:
    from src.qt.compat import (
        QAction,
        QDialog,
        QGraphicsPixmapItem,
        QGraphicsScene,
        QGraphicsView,
        QGuiApplication,
        QImage,
        QLabel,
        QKeySequence,
        QMenu,
        QMessageBox,
        QPainter,
        QPixmap,
        QPushButton,
        Qt,
        QTimer,
        QVBoxLayout,
        QHBoxLayout,
    )


def _pil_to_pixmap(image):
    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimage = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimage.copy())


if QT_AVAILABLE:
    class _ImageViewerCanvas(QGraphicsView):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setRenderHint(QPainter.Antialiasing)
            self.setRenderHint(QPainter.SmoothPixmapTransform)
            self.setAlignment(Qt.AlignCenter)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
            self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
            self.setContextMenuPolicy(Qt.CustomContextMenu)
            self.scene = QGraphicsScene(self)
            self.setScene(self.scene)
            self.pixmap_item = QGraphicsPixmapItem()
            self.pixmap_item.setTransformationMode(Qt.SmoothTransformation)
            self.scene.addItem(self.pixmap_item)

        def set_pixmap(self, pixmap):
            self.pixmap_item.setPixmap(pixmap)
            self.pixmap_item.setOffset(-pixmap.width() / 2, -pixmap.height() / 2)
            self.scene.setSceneRect(self.pixmap_item.boundingRect())
            self.refit()

        def refit(self):
            if self.pixmap_item.pixmap().isNull():
                return
            self.resetTransform()
            self.centerOn(self.pixmap_item)
            self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if not self.pixmap_item.pixmap().isNull():
                self.refit()


    class DanbooruImageViewer(QDialog):
        def __init__(self, post, client, parent=None):
            super().__init__(parent)
            self.post = post
            self.client = client
            self.rotation = 0
            self.original_image = None
            self.setWindowTitle(f"Imagem #{post.get('id')}")
            self.resize(1280, 900)

            layout = QVBoxLayout(self)
            self.info_label = QLabel("Carregando imagem...")
            self.info_label.setWordWrap(True)
            self.canvas = _ImageViewerCanvas(self)
            self.canvas.customContextMenuRequested.connect(self._show_context_menu)
            controls = QHBoxLayout()
            self.copy_url_button = QPushButton("Mostrar URL da Imagem")
            self.copy_url_button.clicked.connect(self._copy_image_url)
            controls.addWidget(self.copy_url_button)
            controls.addStretch(1)

            layout.addWidget(self.info_label)
            layout.addWidget(self.canvas, 1)
            layout.addLayout(controls)

            self._register_shortcuts()
            self._fit_to_current_screen()
            QTimer.singleShot(0, self._load_image)

        def _register_shortcuts(self):
            shortcuts = [
                ("Escape", self.close),
                ("Ctrl+Q", self.rotate_left),
                ("Ctrl+E", self.rotate_right),
            ]
            for sequence, handler in shortcuts:
                action = QAction(self)
                action.setShortcut(QKeySequence(sequence))
                action.triggered.connect(handler)
                self.addAction(action)

        def _fit_to_current_screen(self):
            screen = None
            if self.windowHandle() is not None:
                screen = self.windowHandle().screen()
            if screen is None and self.parent() is not None and getattr(self.parent(), "windowHandle", None):
                parent_handle = self.parent().windowHandle()
                if parent_handle is not None:
                    screen = parent_handle.screen()
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            if screen is None:
                return
            self.setGeometry(screen.availableGeometry())

        def _show_context_menu(self, pos):
            menu = QMenu(self)
            left_action = menu.addAction("Rotacionar 90 Esquerda (Ctrl+Q)")
            right_action = menu.addAction("Rotacionar 90 Direita (Ctrl+E)")
            chosen = menu.exec(self.canvas.mapToGlobal(pos))
            if chosen == left_action:
                self.rotate_left()
            elif chosen == right_action:
                self.rotate_right()

        def _copy_image_url(self):
            file_url = self.post.get("file_url") or self.post.get("large_file_url") or self.post.get("preview_file_url")
            if file_url:
                self.info_label.setText(file_url)
                QGuiApplication.clipboard().setText(file_url)

        def _load_image(self):
            file_url = self.post.get("file_url") or self.post.get("large_file_url") or self.post.get("preview_file_url")
            if not file_url:
                QMessageBox.warning(self, "Danbooru", "URL da imagem nao encontrada.")
                return
            data = self.client.download_image(file_url)
            if not data:
                QMessageBox.warning(self, "Danbooru", "Nao foi possivel carregar a imagem.")
                return
            with Image.open(BytesIO(data)) as image:
                self.original_image = image.convert("RGBA").copy()
            self._render_current_image()
            self.info_label.setText((self.post.get("tag_string", "") or "").replace(" ", ", "))

        def _render_current_image(self):
            if self.original_image is None:
                return
            rendered = self.original_image.rotate(self.rotation, expand=True)
            try:
                self.canvas.set_pixmap(_pil_to_pixmap(rendered))
            finally:
                rendered.close()
            QTimer.singleShot(0, self.canvas.refit)

        def rotate_left(self):
            self.rotation = (self.rotation + 90) % 360
            self._render_current_image()

        def rotate_right(self):
            self.rotation = (self.rotation - 90) % 360
            self._render_current_image()

        def closeEvent(self, event):
            if self.original_image is not None:
                try:
                    self.original_image.close()
                except Exception:
                    pass
                self.original_image = None
            super().closeEvent(event)
else:
    class DanbooruImageViewer:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
