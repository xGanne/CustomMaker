import concurrent.futures
import logging
import time
import tkinter as tk
from collections import deque
from io import BytesIO

import customtkinter as ctk
from PIL import Image

from src.core.cache_manager import CacheManager
from src.ui.theme import ACCENT, SURFACE_ELEVATED, SURFACE_MUTED


logger = logging.getLogger(__name__)


class DanbooruGridWidget(ctk.CTkScrollableFrame):
    def __init__(self, parent, app_instance, client, on_selection_change=None, columns=4, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.app = app_instance
        self.client = client
        self.on_selection_change = on_selection_change
        self.columns = columns

        self._thumbnail_batch_size = self._resolve_config_int("thumbnail_batch_size", 4, minimum=1, maximum=32)
        self._thumbnail_batch_interval_ms = self._resolve_config_int(
            "thumbnail_batch_interval_ms",
            40,
            minimum=1,
            maximum=1000,
        )
        memory_cache_mb = self._resolve_config_int("thumbnail_memory_cache_mb", 64, minimum=8, maximum=2048)
        self._thumbnail_memory_limit_bytes = memory_cache_mb * 1024 * 1024

        self.cache = CacheManager(max_disk_size_mb=self._resolve_config_int("thumbnail_disk_cache_mb", 512))

        self.posts = []
        self.selected_posts = set()
        self.selected_posts_details = {}
        self.thumbnails = {}
        self._thumb_generation = 0
        self._pending_thumbnails = deque()
        self._thumb_after_id = None
        self._thumbnail_futures = set()
        self._thumb_memory_cache = {}
        self._thumb_memory_access_order = deque()
        self._thumb_memory_current_bytes = 0

        self._thumb_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self._resolve_thumbnail_workers(),
            thread_name_prefix="thumb",
        )
        self.bind("<Destroy>", self._on_destroy, add="+")

        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_frame.pack(fill="both", expand=True)
        for i in range(self.columns):
            self.grid_frame.grid_columnconfigure(i, weight=1)

    def _resolve_config_int(self, key, default, minimum=None, maximum=None):
        value = default
        if getattr(self.app, "app_config", None):
            value = self.app.app_config.get(key, default)
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = default
        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value

    def _resolve_thumbnail_workers(self):
        configured = None
        if getattr(self.app, "app_config", None):
            configured = self.app.app_config.get("max_workers")
        try:
            value = int(configured) if configured is not None else 4
        except (TypeError, ValueError):
            value = 4
        return max(2, min(8, value))

    def _next_thumbnail_generation(self):
        self._thumb_generation += 1
        self._pending_thumbnails.clear()
        self._cancel_thumbnail_scheduler()
        self._cancel_pending_futures()
        return self._thumb_generation

    def _cancel_thumbnail_scheduler(self):
        if self._thumb_after_id is None:
            return
        try:
            self.app.root.after_cancel(self._thumb_after_id)
        except Exception:
            pass
        self._thumb_after_id = None

    def _cancel_pending_futures(self):
        for future in list(self._thumbnail_futures):
            if not future.done():
                future.cancel()

    def _estimate_thumb_bytes(self, image):
        try:
            channels = len(image.getbands())
        except Exception:
            channels = 4
        return max(1, image.width * image.height * channels)

    def _touch_thumb_memory_entry(self, url):
        try:
            self._thumb_memory_access_order.remove(url)
        except ValueError:
            pass
        self._thumb_memory_access_order.append(url)

    def _remember_thumb_memory(self, url, image):
        if not url or image is None:
            return

        if url in self._thumb_memory_cache:
            existing = self._thumb_memory_cache.pop(url)
            self._thumb_memory_current_bytes -= self._estimate_thumb_bytes(existing)
            try:
                existing.close()
            except Exception:
                pass
            try:
                self._thumb_memory_access_order.remove(url)
            except ValueError:
                pass

        cached = image.copy()
        self._thumb_memory_cache[url] = cached
        self._thumb_memory_current_bytes += self._estimate_thumb_bytes(cached)
        self._thumb_memory_access_order.append(url)

        while (
            self._thumb_memory_current_bytes > self._thumbnail_memory_limit_bytes
            and self._thumb_memory_access_order
        ):
            oldest_url = self._thumb_memory_access_order.popleft()
            oldest_image = self._thumb_memory_cache.pop(oldest_url, None)
            if oldest_image is None:
                continue
            evicted_size = self._estimate_thumb_bytes(oldest_image)
            self._thumb_memory_current_bytes = max(0, self._thumb_memory_current_bytes - evicted_size)
            try:
                oldest_image.close()
            except Exception:
                pass
            logger.debug("Thumbnail cache memory eviction: %s (%s bytes)", oldest_url, evicted_size)

    def _get_thumb_from_memory(self, url):
        cached = self._thumb_memory_cache.get(url)
        if cached is None:
            return None
        self._touch_thumb_memory_entry(url)
        logger.debug("Thumbnail cache hit (memory): %s", url)
        return cached.copy()

    def display_loading(self):
        self._next_thumbnail_generation()
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        self.thumbnails.clear()

        loading_label = ctk.CTkLabel(self.grid_frame, text="Carregando...", font=ctk.CTkFont(size=16))
        loading_label.grid(row=0, column=0, columnspan=self.columns, pady=50)

    def set_columns(self, count):
        self.columns = count
        for i in range(count):
            self.grid_frame.grid_columnconfigure(i, weight=1)

    def display_posts(self, posts):
        generation = self._next_thumbnail_generation()
        self.posts = posts

        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        self.thumbnails.clear()

        if not posts:
            ctk.CTkLabel(self.grid_frame, text="Nenhum resultado encontrado.").pack(pady=20)
            return

        row = 0
        col = 0
        for post in posts:
            preview_url = (
                post.get("preview_file_url")
                or post.get("preview_url")
                or post.get("file_url")
                or post.get("large_file_url")
            )
            if not preview_url:
                continue

            card = ctk.CTkFrame(self.grid_frame, corner_radius=10, fg_color=SURFACE_ELEVATED)
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")

            if post["id"] in self.selected_posts:
                card.configure(border_width=2, border_color=ACCENT)

            lbl = ctk.CTkLabel(card, text="...", width=150, height=150)
            lbl.pack(padx=2, pady=2, fill="both", expand=True)

            card.bind("<Button-1>", lambda e, p=post, w=card: self.toggle_selection(p, w))
            lbl.bind("<Button-1>", lambda e, p=post, w=card: self.toggle_selection(p, w))

            card.bind("<Enter>", lambda e, w=card: self._on_enter(w))
            card.bind("<Leave>", lambda e, w=card: self._on_leave(w))
            lbl.bind("<Enter>", lambda e, w=card: self._on_enter(w))
            lbl.bind("<Leave>", lambda e, w=card: self._on_leave(w))

            card.bind("<Button-3>", lambda e, p=post: self.show_context_menu(e, p))
            lbl.bind("<Button-3>", lambda e, p=post: self.show_context_menu(e, p))

            self._pending_thumbnails.append((preview_url, lbl, generation))

            col += 1
            if col >= self.columns:
                col = 0
                row += 1

        self._schedule_next_batch(generation, delay_ms=0)

    def _schedule_next_batch(self, generation, delay_ms=None):
        if generation != self._thumb_generation:
            return
        if not self.winfo_exists():
            return

        self._cancel_thumbnail_scheduler()
        interval = self._thumbnail_batch_interval_ms if delay_ms is None else delay_ms
        try:
            self._thumb_after_id = self.app.root.after(interval, lambda: self._process_thumbnail_batch(generation))
        except tk.TclError:
            self._thumb_after_id = None

    def _process_thumbnail_batch(self, generation):
        self._thumb_after_id = None
        if generation != self._thumb_generation:
            return
        if not self.winfo_exists():
            return

        processed = 0
        while self._pending_thumbnails and processed < self._thumbnail_batch_size:
            url, label_widget, thumb_generation = self._pending_thumbnails.popleft()
            if thumb_generation != self._thumb_generation:
                continue
            if not label_widget.winfo_exists():
                continue
            self.load_thumbnail(url, label_widget, thumb_generation)
            processed += 1

        if self._pending_thumbnails:
            self._schedule_next_batch(generation)

    def _fetch_thumbnail_image(self, url):
        start = time.perf_counter()
        try:
            memory_hit = self._get_thumb_from_memory(url)
            if memory_hit is not None:
                return memory_hit

            data = self.cache.get(url)
            if data:
                logger.debug("Thumbnail cache hit (disk): %s", url)
            else:
                logger.debug("Thumbnail cache miss (disk): %s", url)
                data = self.client.download_image(url)
                if data:
                    self.cache.set(url, data)
            if not data:
                return None

            with Image.open(BytesIO(data)) as img:
                thumb = img.convert("RGBA")
                thumb.thumbnail((200, 200), Image.LANCZOS)
                prepared = thumb.copy()

            self._remember_thumb_memory(url, prepared)
            return prepared
        except Exception as exc:
            logger.warning("Falha ao carregar thumbnail %s: %s", url, exc)
            return None
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.debug("Thumbnail load latency: %.1fms url='%s'", elapsed_ms, url)

    def load_thumbnail(self, url, label_widget, generation):
        future = self._thumb_executor.submit(self._fetch_thumbnail_image, url)
        self._thumbnail_futures.add(future)

        def on_done(done_future):
            self._thumbnail_futures.discard(done_future)
            try:
                thumb = done_future.result()
            except concurrent.futures.CancelledError:
                return
            except Exception as exc:
                logger.warning("Erro na future de thumbnail %s: %s", url, exc)
                return

            if thumb is None:
                return

            def update_ui():
                if generation != self._thumb_generation:
                    return
                if not self.winfo_exists() or not label_widget.winfo_exists():
                    return
                ctk_img = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=thumb.size)
                label_widget.configure(image=ctk_img, text="")
                self.thumbnails[label_widget] = ctk_img

            try:
                self.app.root.after(0, update_ui)
            except tk.TclError:
                return

        future.add_done_callback(on_done)

    def toggle_selection(self, post, card_widget):
        post_id = post["id"]
        if post_id in self.selected_posts:
            self.selected_posts.remove(post_id)
            if post_id in self.selected_posts_details:
                del self.selected_posts_details[post_id]
            card_widget.configure(border_width=0)
        else:
            self.selected_posts.add(post_id)
            self.selected_posts_details[post_id] = post
            card_widget.configure(border_width=2, border_color=ACCENT)

        if self.on_selection_change:
            self.on_selection_change(len(self.selected_posts))

    def get_selected_items(self):
        return list(self.selected_posts_details.values())

    def clear_selection(self):
        self.selected_posts.clear()
        self.selected_posts_details.clear()
        if self.on_selection_change:
            self.on_selection_change(0)

    def _on_enter(self, card_widget):
        if card_widget.cget("border_width") == 0:
            pass
        card_widget.configure(fg_color=SURFACE_MUTED)

    def _on_leave(self, card_widget):
        card_widget.configure(fg_color=SURFACE_ELEVATED)

    def show_context_menu(self, event, post):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Abrir em Tela Cheia", command=lambda: self.open_image_viewer(post))
        menu.post(event.x_root, event.y_root)

    def open_image_viewer(self, post):
        from src.ui.online_search import DanbooruImageViewer

        DanbooruImageViewer(self.winfo_toplevel(), post, self.client, app_instance=self.app)

    def _clear_thumbnail_memory(self):
        for image in self._thumb_memory_cache.values():
            try:
                image.close()
            except Exception:
                pass
        self._thumb_memory_cache.clear()
        self._thumb_memory_access_order.clear()
        self._thumb_memory_current_bytes = 0

    def _on_destroy(self, event):
        if event.widget is not self:
            return
        self._next_thumbnail_generation()
        self._clear_thumbnail_memory()
        try:
            self._thumb_executor.shutdown(wait=False, cancel_futures=True)
        except Exception as exc:
            logger.debug("Falha ao encerrar executor de thumbnails: %s", exc)
