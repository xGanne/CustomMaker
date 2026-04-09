import concurrent.futures
import logging
from collections import OrderedDict
from io import BytesIO

from PIL import Image

from src.core.cache_manager import CacheManager
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error

if QT_AVAILABLE:
    from src.qt.compat import QAbstractItemView, QIcon, QImage, QListView, QListWidget, QListWidgetItem, QMenu, QPixmap, QSize, Qt, Signal


logger = logging.getLogger(__name__)


class DanbooruSelectionState:
    def __init__(self):
        self.selected_post_ids = set()
        self.selected_posts_details = {}

    def clear(self):
        self.selected_post_ids.clear()
        self.selected_posts_details.clear()


if QT_AVAILABLE:
    class DanbooruResultsGrid(QListWidget):
        selection_count_changed = Signal(int)
        thumbnail_ready = Signal(int, object, object)
        image_open_requested = Signal(object)

        def __init__(self, app_config, client, parent=None, selection_state=None):
            super().__init__(parent)
            self.app_config = app_config
            self.client = client
            self.selection_state = selection_state or DanbooruSelectionState()
            self.posts = []
            self._generation = 0
            self._syncing_selection = False
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=self._resolve_config_int("max_workers", 4, minimum=2, maximum=8),
                thread_name_prefix="qt_thumb",
            )
            self._memory_limit_bytes = (
                self._resolve_config_int("thumbnail_memory_cache_mb", 64, minimum=8, maximum=2048) * 1024 * 1024
            )
            self._memory_cache = OrderedDict()
            self._memory_cache_bytes = 0
            self._disk_cache = CacheManager(max_disk_size_mb=self._resolve_config_int("thumbnail_disk_cache_mb", 512))

            self.setViewMode(QListView.IconMode)
            self.setResizeMode(QListView.Adjust)
            self.setMovement(QListView.Static)
            self.setSpacing(10)
            self.setIconSize(QSize(180, 180))
            self.setGridSize(QSize(196, 236))
            self.setSelectionMode(QAbstractItemView.MultiSelection)
            self.itemSelectionChanged.connect(self._sync_selection_state)
            self.itemDoubleClicked.connect(self._open_item)
            self.setContextMenuPolicy(Qt.CustomContextMenu)
            self.customContextMenuRequested.connect(self._show_context_menu)
            self.thumbnail_ready.connect(self._apply_thumbnail)

        def close(self):
            self._executor.shutdown(wait=False, cancel_futures=True)
            while self._memory_cache:
                _, image = self._memory_cache.popitem(last=False)
                try:
                    image.close()
                except Exception:
                    pass

        def _sync_selection_state(self):
            if self._syncing_selection:
                return
            for index in range(self.count()):
                item = self.item(index)
                post = item.data(Qt.UserRole)
                if not post:
                    continue
                post_id = post.get("id")
                if post_id is None:
                    continue
                if item.isSelected():
                    self.selection_state.selected_post_ids.add(post_id)
                    self.selection_state.selected_posts_details[post_id] = post
                else:
                    self.selection_state.selected_post_ids.discard(post_id)
                    self.selection_state.selected_posts_details.pop(post_id, None)
            self.selection_count_changed.emit(len(self.selection_state.selected_post_ids))

        def _resolve_config_int(self, key, default, minimum=None, maximum=None):
            value = self.app_config.get(key, default) if self.app_config else default
            try:
                value = int(value)
            except (TypeError, ValueError):
                value = default
            if minimum is not None:
                value = max(minimum, value)
            if maximum is not None:
                value = min(maximum, value)
            return value

        @staticmethod
        def _estimate_bytes(image):
            try:
                channels = len(image.getbands())
            except Exception:
                channels = 4
            return max(1, image.width * image.height * channels)

        def _remember_memory(self, url, image):
            if url in self._memory_cache:
                existing = self._memory_cache.pop(url)
                self._memory_cache_bytes -= self._estimate_bytes(existing)
                try:
                    existing.close()
                except Exception:
                    pass
            cached = image.copy()
            self._memory_cache[url] = cached
            self._memory_cache_bytes += self._estimate_bytes(cached)
            while self._memory_cache_bytes > self._memory_limit_bytes and self._memory_cache:
                _, evicted = self._memory_cache.popitem(last=False)
                self._memory_cache_bytes = max(0, self._memory_cache_bytes - self._estimate_bytes(evicted))
                try:
                    evicted.close()
                except Exception:
                    pass

        def _get_memory_copy(self, url):
            cached = self._memory_cache.get(url)
            if cached is None:
                return None
            image = self._memory_cache.pop(url)
            self._memory_cache[url] = image
            return image.copy()

        @staticmethod
        def _placeholder_pixmap():
            pixmap = QPixmap(180, 180)
            pixmap.fill(Qt.transparent)
            return pixmap

        def display_loading(self):
            self._generation += 1
            self._syncing_selection = True
            self.clear()
            self._syncing_selection = False
            item = QListWidgetItem("Carregando resultados...")
            item.setFlags(Qt.NoItemFlags)
            self.addItem(item)

        def display_posts(self, posts):
            self._generation += 1
            generation = self._generation
            self.posts = posts or []
            self._syncing_selection = True
            self.clear()

            if not self.posts:
                item = QListWidgetItem("Nenhum resultado encontrado.")
                item.setFlags(Qt.NoItemFlags)
                self.addItem(item)
                self._syncing_selection = False
                self.selection_count_changed.emit(len(self.selection_state.selected_post_ids))
                return

            for post in self.posts:
                preview_url = (
                    post.get("preview_file_url")
                    or post.get("preview_url")
                    or post.get("file_url")
                    or post.get("large_file_url")
                )
                rating = post.get("rating", "?")
                item = QListWidgetItem(QIcon(self._placeholder_pixmap()), f"#{post.get('id')}\n{rating}")
                item.setData(Qt.UserRole, post)
                item.setToolTip((post.get("tag_string", "") or "").replace(" ", ", "))
                self.addItem(item)
                if post.get("id") in self.selection_state.selected_post_ids:
                    item.setSelected(True)
                if preview_url:
                    self._queue_thumbnail_load(item, preview_url, generation)
            self._syncing_selection = False
            self._sync_selection_state()

        def _load_thumbnail_image(self, url):
            memory = self._get_memory_copy(url)
            if memory is not None:
                return memory

            data = self._disk_cache.get(url)
            if not data:
                data = self.client.download_image(url)
                if data:
                    self._disk_cache.set(url, data)
            if not data:
                return None

            with Image.open(BytesIO(data)) as img:
                thumb = img.convert("RGBA")
                thumb.thumbnail((180, 180), Image.LANCZOS)
                prepared = thumb.copy()

            self._remember_memory(url, prepared)
            return prepared

        def _queue_thumbnail_load(self, item, url, generation):
            future = self._executor.submit(self._load_thumbnail_image, url)

            def on_done(done_future):
                try:
                    thumb = done_future.result()
                except Exception as exc:
                    logger.debug("Falha ao carregar thumbnail %s: %s", url, exc)
                    thumb = None
                self.thumbnail_ready.emit(generation, item, thumb)

            future.add_done_callback(on_done)

        def _apply_thumbnail(self, generation, item, thumb):
            if generation != self._generation or thumb is None:
                if thumb is not None:
                    try:
                        thumb.close()
                    except Exception:
                        pass
                return
            qimage = thumb.convert("RGBA")
            data = qimage.tobytes("raw", "RGBA")
            image = QImage(
                data,
                qimage.width,
                qimage.height,
                qimage.width * 4,
                QImage.Format_RGBA8888,
            ).copy()
            pixmap = QPixmap.fromImage(image)
            item.setIcon(QIcon(pixmap))
            try:
                thumb.close()
            except Exception:
                pass

        def get_selected_items(self):
            return list(self.selection_state.selected_posts_details.values())

        def clear_selection(self):
            self.selection_state.clear()
            self._syncing_selection = True
            super().clearSelection()
            self._syncing_selection = False
            self.selection_count_changed.emit(0)

        def _open_item(self, item):
            post = item.data(Qt.UserRole)
            if post:
                self.image_open_requested.emit(post)

        def _show_context_menu(self, pos):
            item = self.itemAt(pos)
            if item is None:
                return
            post = item.data(Qt.UserRole)
            if not post:
                return
            menu = QMenu(self)
            open_action = menu.addAction("Abrir em Tela Cheia")
            chosen = menu.exec(self.mapToGlobal(pos))
            if chosen == open_action:
                self.image_open_requested.emit(post)
else:
    class DanbooruResultsGrid:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
