from io import BytesIO

from PIL import Image

from src.core.cache_manager import CacheManager
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error
from src.qt.task_runner import QtTaskRunner

if QT_AVAILABLE:
    from src.qt.compat import (
        QAction,
        QDialog,
        QEvent,
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
            self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
            self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setContextMenuPolicy(Qt.CustomContextMenu)

            self.scene = QGraphicsScene(self)
            self.setScene(self.scene)
            self.pixmap_item = QGraphicsPixmapItem()
            self.pixmap_item.setTransformationMode(Qt.SmoothTransformation)
            self.scene.addItem(self.pixmap_item)

            self._auto_fit = True
            self._zoom_level = 1.0

        def set_pixmap(self, pixmap):
            self.pixmap_item.setPixmap(pixmap)
            self.pixmap_item.setOffset(-pixmap.width() / 2, -pixmap.height() / 2)
            self.scene.setSceneRect(self.pixmap_item.sceneBoundingRect())
            if self._auto_fit:
                self.refit()

        def refit(self):
            if self.pixmap_item.pixmap().isNull():
                return
            self.resetTransform()
            self._zoom_level = 1.0
            self._auto_fit = True
            self.centerOn(self.pixmap_item)
            self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

        def zoom_by(self, factor):
            if self.pixmap_item.pixmap().isNull():
                return
            next_zoom = self._zoom_level * factor
            if next_zoom < 0.08 or next_zoom > 20:
                return
            self._auto_fit = False
            self._zoom_level = next_zoom
            self.scale(factor, factor)

        def zoom_in(self):
            self.zoom_by(1.2)

        def zoom_out(self):
            self.zoom_by(1 / 1.2)

        def wheelEvent(self, event):
            delta = event.angleDelta().y()
            if delta:
                self.zoom_by(1.2 if delta > 0 else 1 / 1.2)
                event.accept()
                return
            super().wheelEvent(event)

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if self._auto_fit and not self.pixmap_item.pixmap().isNull():
                self.refit()


    class DanbooruImageViewer(QDialog):
        def __init__(self, post, client, parent=None):
            super().__init__(parent)
            self.post = post
            self.client = client
            self.rotation = 0
            self.original_image = None
            self._task_runner = QtTaskRunner(self)
            self._active_load_task_id = None
            self._load_seq = 0
            self._disk_cache = CacheManager(cache_dir=".cache/danbooru_viewer", max_disk_size_mb=768)

            self.setWindowTitle(f"Imagem #{post.get('id')}")
            self.resize(1280, 900)
            self.setWindowFlags(
                self.windowFlags()
                | Qt.WindowMinimizeButtonHint
                | Qt.WindowMaximizeButtonHint
                | Qt.WindowCloseButtonHint
            )

            layout = QVBoxLayout(self)
            self.info_label = QLabel("Carregando imagem...")
            self.info_label.setWordWrap(True)
            self.canvas = _ImageViewerCanvas(self)
            self.canvas.customContextMenuRequested.connect(self._show_context_menu)

            controls = QHBoxLayout()
            self.copy_url_button = QPushButton("Mostrar URL da Imagem")
            self.copy_url_button.clicked.connect(self._copy_image_url)
            zoom_out_button = QPushButton("Zoom -")
            zoom_out_button.clicked.connect(self.canvas.zoom_out)
            fit_button = QPushButton("Ajustar")
            fit_button.clicked.connect(self.canvas.refit)
            zoom_in_button = QPushButton("Zoom +")
            zoom_in_button.clicked.connect(self.canvas.zoom_in)
            minimize_button = QPushButton("Minimizar")
            minimize_button.clicked.connect(self.showMinimized)
            self.maximize_button = QPushButton("Maximizar")
            self.maximize_button.clicked.connect(self._toggle_maximized)

            controls.addWidget(self.copy_url_button)
            controls.addWidget(zoom_out_button)
            controls.addWidget(fit_button)
            controls.addWidget(zoom_in_button)
            controls.addStretch(1)
            controls.addWidget(minimize_button)
            controls.addWidget(self.maximize_button)

            layout.addWidget(self.info_label)
            layout.addWidget(self.canvas, 1)
            layout.addLayout(controls)

            self._register_shortcuts()
            self._fit_to_current_screen()
            self._update_window_button_text()
            QTimer.singleShot(0, self._load_image)

        def _register_shortcuts(self):
            shortcuts = [
                ("Escape", self.close),
                ("Ctrl+Q", self.rotate_left),
                ("Ctrl+E", self.rotate_right),
                ("Ctrl++", self.canvas.zoom_in),
                ("Ctrl+=", self.canvas.zoom_in),
                ("Ctrl+-", self.canvas.zoom_out),
                ("Ctrl+0", self.canvas.refit),
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
            zoom_in_action = menu.addAction("Zoom +")
            zoom_out_action = menu.addAction("Zoom -")
            fit_action = menu.addAction("Ajustar")
            menu.addSeparator()
            left_action = menu.addAction("Rotacionar 90 Esquerda (Ctrl+Q)")
            right_action = menu.addAction("Rotacionar 90 Direita (Ctrl+E)")
            chosen = menu.exec(self.canvas.mapToGlobal(pos))
            if chosen == zoom_in_action:
                self.canvas.zoom_in()
            elif chosen == zoom_out_action:
                self.canvas.zoom_out()
            elif chosen == fit_action:
                self.canvas.refit()
            elif chosen == left_action:
                self.rotate_left()
            elif chosen == right_action:
                self.rotate_right()

        def _copy_image_url(self):
            file_url = self.post.get("file_url") or self.post.get("large_file_url") or self.post.get("preview_file_url")
            if file_url:
                self.info_label.setText(file_url)
                QGuiApplication.clipboard().setText(file_url)

        def _image_urls(self):
            full_url = self.post.get("file_url") or self.post.get("large_file_url")
            preview_url = (
                self.post.get("sample_url")
                or self.post.get("large_file_url")
                or self.post.get("preview_file_url")
                or full_url
            )
            urls = []
            if preview_url:
                urls.append(("preview", preview_url))
            if full_url and full_url != preview_url:
                urls.append(("full", full_url))
            return urls

        def _download_cached(self, url):
            data = self._disk_cache.get(url)
            if data:
                return data
            data = self.client.download_image(url)
            if data:
                self._disk_cache.set(url, data)
            return data

        def _load_image(self):
            urls = self._image_urls()
            if not urls:
                QMessageBox.warning(self, "Danbooru", "URL da imagem nao encontrada.")
                return
            self._load_next_image(urls, has_displayed_image=False)

        def _load_next_image(self, urls, has_displayed_image):
            if not urls:
                if has_displayed_image:
                    self.info_label.setText((self.post.get("tag_string", "") or "").replace(" ", ", "))
                else:
                    QMessageBox.warning(self, "Danbooru", "Nao foi possivel carregar a imagem.")
                return

            quality, url = urls[0]
            remaining_urls = urls[1:]
            self._load_seq += 1
            task_id = f"qt_danbooru_viewer_{id(self)}_{self._load_seq}"
            self._active_load_task_id = task_id

            def task_fn(cancel_event, on_progress):
                if cancel_event.is_set():
                    return {"task_id": task_id, "quality": quality, "image": None}
                if on_progress:
                    label = "previsualizacao" if quality == "preview" else "imagem completa"
                    on_progress(0, 1, f"Carregando {label}...")
                data = self._download_cached(url)
                if not data:
                    return {"task_id": task_id, "quality": quality, "image": None}
                with Image.open(BytesIO(data)) as image:
                    loaded_image = image.convert("RGBA").copy()
                if on_progress:
                    on_progress(1, 1, "Imagem carregada.")
                return {"task_id": task_id, "quality": quality, "image": loaded_image}

            def on_progress(_value, _maximum, message):
                self.info_label.setText(message)

            def on_done(result):
                if result.get("task_id") != self._active_load_task_id:
                    return
                self._active_load_task_id = None
                image = result.get("image")
                if image is None:
                    self._load_next_image(remaining_urls, has_displayed_image)
                    return
                self._set_original_image(image)
                self._render_current_image(keep_view=has_displayed_image and quality == "full")
                self._load_next_image(remaining_urls, has_displayed_image=True)

            def on_error(_exc):
                if task_id != self._active_load_task_id:
                    return
                self._active_load_task_id = None
                self._load_next_image(remaining_urls, has_displayed_image)

            handle = self._task_runner.submit(task_id, task_fn)
            if handle is None:
                return
            handle.progress.connect(on_progress)
            handle.done.connect(on_done)
            handle.error.connect(on_error)

        def _set_original_image(self, image):
            if self.original_image is not None:
                try:
                    self.original_image.close()
                except Exception:
                    pass
            self.original_image = image

        def _render_current_image(self, keep_view=False):
            if self.original_image is None:
                return
            if not keep_view:
                self.canvas._auto_fit = True
            rendered = self.original_image.rotate(self.rotation, expand=True)
            try:
                self.canvas.set_pixmap(_pil_to_pixmap(rendered))
            finally:
                rendered.close()
            if not keep_view:
                QTimer.singleShot(0, self.canvas.refit)

        def rotate_left(self):
            self.rotation = (self.rotation + 90) % 360
            self._render_current_image()

        def rotate_right(self):
            self.rotation = (self.rotation - 90) % 360
            self._render_current_image()

        def _update_window_button_text(self):
            if self.isMaximized():
                self.maximize_button.setText("Restaurar")
            else:
                self.maximize_button.setText("Maximizar")

        def _toggle_maximized(self):
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
            self._update_window_button_text()

        def changeEvent(self, event):
            super().changeEvent(event)
            if event.type() == QEvent.WindowStateChange:
                self._update_window_button_text()

        def closeEvent(self, event):
            if self._active_load_task_id and self._task_runner.is_running(self._active_load_task_id):
                self._task_runner.cancel(self._active_load_task_id)
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
