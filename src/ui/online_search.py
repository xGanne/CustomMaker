import os
import logging
import customtkinter as ctk
from PIL import Image, UnidentifiedImageError
from io import BytesIO
from tkinter import messagebox, filedialog
import tkinter as tk

from src.core.danbooru import DanbooruClient
from src.core.task_runner import TaskRunner
from src.ui.theme import (
    ACCENT,
    ACCENT_HOVER,
    FONT_BODY,
    FONT_CAPTION,
    SURFACE_BG,
    SURFACE_ELEVATED,
    SURFACE_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from src.ui.widgets import ActionButtonPrimary, ActionButtonSecondary, InlineHint, ProgressBarPopup, SectionCard
from src.ui.autocomplete import DanbooruAutocomplete
from src.ui.danbooru_grid import DanbooruGridWidget

logger = logging.getLogger(__name__)


def _submit_download_task(
    *,
    app,
    ui_parent,
    task_id,
    selected_posts,
    final_path,
    client,
    on_success,
    running_message,
):
    if app.task_runner.is_running(task_id):
        messagebox.showwarning("Aviso", running_message)
        return

    popup = ProgressBarPopup(
        ui_parent,
        title="Baixando...",
        maximum=max(1, len(selected_posts)),
        on_cancel=lambda: app._cancel_background_task(task_id, "Download"),
    )

    def task_fn(cancel_event, on_progress):
        processed = 0
        downloaded = 0
        errors = []
        total = len(selected_posts)

        for post in selected_posts:
            if cancel_event and cancel_event.is_set():
                return {
                    "cancelled": True,
                    "processed": processed,
                    "downloaded": downloaded,
                    "errors": errors,
                    "path": final_path,
                }

            try:
                file_url = post.get("file_url") or post.get("large_file_url") or post.get("sample_url")
                if not file_url:
                    errors.append(f"Post {post.get('id')}: URL nao encontrada.")
                else:
                    fname = f"{post['id']}.{post.get('file_ext', 'png')}"
                    save_path = os.path.join(final_path, fname)
                    data = client.download_image(file_url)
                    if data:
                        with open(save_path, "wb") as f:
                            f.write(data)
                        downloaded += 1
                    else:
                        errors.append(f"Post {post.get('id')}: download vazio.")
            except Exception as exc:
                logger.warning("Erro ao baixar post %s: %s", post.get("id"), exc)
                errors.append(f"Post {post.get('id')}: {exc}")

            processed += 1
            if on_progress:
                on_progress(processed, total, f"Baixado {processed}/{total}")

        return {
            "cancelled": False,
            "processed": processed,
            "downloaded": downloaded,
            "errors": errors,
            "path": final_path,
        }

    def on_progress(current, total, msg):
        def _update():
            try:
                if not popup.window.winfo_exists():
                    return
                popup.maximum = max(1, total)
                popup.update_progress(current, msg)
            except tk.TclError:
                return

        ui_parent.after(0, _update)

    def on_done(result):
        def _finish():
            popup.close()
            if result.get("cancelled"):
                return

            errors = result.get("errors") or []
            if errors:
                messagebox.showwarning("Download com avisos", "\n".join(errors[:20]))

            on_success(result)

        ui_parent.after(0, _finish)

    def on_error(exc):
        ui_parent.after(0, lambda: (popup.close(), messagebox.showerror("Erro", str(exc))))

    started = app.task_runner.submit(
        task_id,
        task_fn,
        on_progress=on_progress,
        on_done=on_done,
        on_error=on_error,
    )
    if not started:
        popup.close()
        messagebox.showwarning("Aviso", "Nao foi possivel iniciar o download.")


class DanbooruSearchTab:
    def __init__(self, parent_frame, app_instance):
        self.parent = parent_frame
        self.app = app_instance
        self.client = DanbooruClient(config=self.app.app_config)
        self.current_page = 1
        self._search_seq = 0
        self._active_search_task_id = None
        
        self.setup_ui()
        self.autocomplete = DanbooruAutocomplete(self.entry_search, self.app.root, self.client)

    def close(self):
        if self._active_search_task_id and self.app.task_runner.is_running(self._active_search_task_id):
            self.app.task_runner.cancel(self._active_search_task_id)
        self.client.close()

    def setup_ui(self):
        controls_card = SectionCard(
            self.parent,
            title="Busca Online",
            subtitle="Pesquise e filtre imagens antes de importar para a edicao.",
        )
        controls_card.pack(fill="x", padx=10, pady=(10, 6))

        top_frame = ctk.CTkFrame(controls_card.body, fg_color="transparent")
        top_frame.pack(fill="x", pady=(0, 5))

        self.entry_search = ctk.CTkEntry(
            top_frame,
            placeholder_text="Tags (ex: hatsune_miku rating:safe)",
            fg_color=SURFACE_MUTED,
            border_color="#3A465D",
            text_color=TEXT_PRIMARY,
            font=FONT_BODY,
            height=34,
        )
        self.entry_search.pack(fill="x", expand=True)
        self.entry_search.bind("<Return>", lambda e: self.search(page=1, new_search=True))

        # Filters Row
        filters_frame = ctk.CTkFrame(controls_card.body, fg_color="transparent")
        filters_frame.pack(fill="x", pady=(0, 5))
        
        # Rating Filter
        self.opt_rating = ctk.CTkOptionMenu(
            filters_frame,
            values=[
                "Qualquer Classificacao",
                "Geral (General)",
                "Sensivel (Sensitive)",
                "Questionavel (Questionable)",
                "Explicito (Explicit)",
            ],
        )
        self._style_option_menu(self.opt_rating)
        self.opt_rating.pack(side="left", expand=True, fill="x", padx=(0, 5))
        
        # Sort Filter
        self.opt_sort = ctk.CTkOptionMenu(filters_frame, values=["Mais Recentes", "Melhor Avaliados", "Mais Favoritos"])
        self._style_option_menu(self.opt_sort)
        self.opt_sort.pack(side="left", expand=True, fill="x", padx=(5, 0))

        # Buttons row
        btn_frame = ctk.CTkFrame(controls_card.body, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 0))
        
        btn_search = ActionButtonPrimary(btn_frame, text="Buscar", width=120, command=lambda: self.search(page=1, new_search=True))
        btn_search.pack(side="left", padx=(0, 5), expand=True, fill="x")
        
        btn_expand = ActionButtonSecondary(btn_frame, text="Expandir", width=120, command=self.open_expanded_gallery)
        btn_expand.pack(side="left", padx=(5, 0), expand=True, fill="x")
        InlineHint(controls_card.body, text="Dica: clique direito em uma miniatura para abrir em tela cheia.").pack(fill="x", pady=(6, 0))

        result_card = SectionCard(self.parent, title="Resultados")
        result_card.pack(fill="both", expand=True, padx=10, pady=(6, 8))

        # Main Content: Grid of Images (using reusable widget)
        self.grid_widget = DanbooruGridWidget(
            result_card.body,
            self.app, 
            self.client, 
            on_selection_change=self.update_selection_label,
            columns=4
        )
        self.grid_widget.pack(fill="both", expand=True, pady=5)
        
        # Pagination / Footer
        footer_frame = ctk.CTkFrame(result_card.body, fg_color="transparent", height=40)
        footer_frame.pack(fill="x", pady=5)
        
        self.btn_prev = ActionButtonSecondary(footer_frame, text="<", width=40, command=lambda: self.change_page(-1))
        self.btn_prev.pack(side="left")
        
        self.lbl_page = ctk.CTkLabel(footer_frame, text="Pagina 1", width=100, anchor="center", font=ctk.CTkFont(weight="bold"), text_color=TEXT_PRIMARY)
        self.lbl_page.pack(side="left", padx=5)
        
        self.btn_next = ActionButtonSecondary(footer_frame, text=">", width=40, command=lambda: self.change_page(1))
        self.btn_next.pack(side="left")

        # Bottom Bar: Actions
        bottom_frame = ctk.CTkFrame(result_card.body, fg_color="transparent", height=40)
        bottom_frame.pack(fill="x", pady=(0, 6))

        self.selection_label = ctk.CTkLabel(bottom_frame, text="0 selecionados", text_color=TEXT_SECONDARY, font=FONT_CAPTION)
        self.selection_label.pack(side="left", padx=10)

        ActionButtonPrimary(bottom_frame, text="Criar Pasta com Selecionados", command=self.download_selected).pack(side="right")

    @staticmethod
    def _style_option_menu(widget):
        widget.configure(
            fg_color=SURFACE_MUTED,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            text_color=TEXT_PRIMARY,
            font=FONT_BODY,
            dropdown_fg_color=SURFACE_ELEVATED,
            dropdown_text_color=TEXT_PRIMARY,
            dropdown_hover_color=SURFACE_MUTED,
        )

    def search(self, page=1, new_search=False):
        tags = self.entry_search.get()
        if not tags: return

        # Apply Filters
        rating_map = {
            "Geral (General)": "rating:general",
            "Sensivel (Sensitive)": "rating:sensitive",
            "Questionavel (Questionable)": "rating:questionable",
            "Explicito (Explicit)": "rating:explicit"
        }
        sort_map = {
            "Melhor Avaliados": "order:score",
            "Mais Favoritos": "order:favcount",
            "Mais Recentes": "" # Default
        }
        
        rating_val = self.opt_rating.get()
        sort_val = self.opt_sort.get()
        
        if rating_val in rating_map:
            tags += f" {rating_map[rating_val]}"
        
        if sort_val in sort_map and sort_map[sort_val]:
            tags += f" {sort_map[sort_val]}"

        self.current_page = page
        self.lbl_page.configure(text=f"Pagina {self.current_page}")

        if new_search:
             self.grid_widget.clear_selection()
             self.update_selection_label(0)
        self.grid_widget.display_loading()

        if self._active_search_task_id and self.app.task_runner.is_running(self._active_search_task_id):
            self.app.task_runner.cancel(self._active_search_task_id)

        self._search_seq += 1
        task_id = f"online_search_main_{self._search_seq}"
        self._active_search_task_id = task_id

        def task_fn(cancel_event, _on_progress):
            if cancel_event and cancel_event.is_set():
                return {"cancelled": True, "posts": [], "task_id": task_id}

            posts = self.client.search_posts(tags, limit=20, page=page)
            if cancel_event and cancel_event.is_set():
                return {"cancelled": True, "posts": [], "task_id": task_id}

            return {"cancelled": False, "posts": posts, "task_id": task_id}

        def on_done(result):
            if result.get("task_id") != self._active_search_task_id:
                return
            self._active_search_task_id = None
            if result.get("cancelled"):
                return
            self.app.root.after(0, lambda: self.grid_widget.display_posts(result.get("posts") or []))

        def on_error(exc):
            if task_id != self._active_search_task_id:
                return
            self._active_search_task_id = None
            logger.exception("Search failed: %s", exc)
            self.app.root.after(0, lambda: messagebox.showerror("Erro", f"Falha na busca: {exc}"))

        self.app.task_runner.submit(
            task_id,
            task_fn,
            on_done=on_done,
            on_error=on_error,
        )

    def change_page(self, delta):
        new_page = self.current_page + delta
        if new_page < 1: return
        self.search(page=new_page, new_search=False)

    def update_selection_label(self, count):
        self.selection_label.configure(text=f"{count} selecionados")

    def download_selected(self):
        selected_posts = self.grid_widget.get_selected_items()
        if not selected_posts:
            messagebox.showwarning("Aviso", "Selecione pelo menos uma imagem.")
            return

        folder_original_dir = self.app.app_config.get('last_folder')
        if not folder_original_dir: folder_original_dir = os.path.expanduser("~")

        target_dir = filedialog.askdirectory(title="Escolha onde Criar a Pasta", initialdir=folder_original_dir)
        if not target_dir: return
        
        name_dialog = ctk.CTkInputDialog(text="Nome da Nova Pasta:", title="Criar Pasta")
        folder_name = name_dialog.get_input()
        if not folder_name: return
        
        final_path = os.path.join(target_dir, folder_name)
        if not os.path.exists(final_path):
            os.makedirs(final_path)

        def on_success(result):
            messagebox.showinfo("Sucesso", "Download concluido! Carregando pasta...")
            self.app.app_config.set("last_folder", result["path"])
            self.app.load_images_from_folder(result["path"])
            self.app.tabview.set("Edição")

        _submit_download_task(
            app=self.app,
            ui_parent=self.app.root,
            task_id="online_download_main",
            selected_posts=selected_posts,
            final_path=final_path,
            client=self.client,
            on_success=on_success,
            running_message="Ja existe um download em andamento.",
        )

    def open_expanded_gallery(self):
        tags = self.entry_search.get()
        if not tags:
            messagebox.showinfo("Info", "Faca uma busca primeiro.")
            return
        
        DanbooruGalleryWindow(self.app.root, self.grid_widget.posts, self.client, self.app, tags, self.current_page)


class DanbooruGalleryWindow(ctk.CTkToplevel):
    def __init__(self, parent, posts, client, app_instance, tags, current_page=1):
        super().__init__(parent)
        self.title(f"Galeria Expandida - {tags}")
        self.geometry("1100x850")
        self.minsize(980, 680)
        
        self.posts = posts
        self.client = client
        self.app = app_instance
        self.tags = tags
        self.current_page = current_page
        self._search_seq = 0
        self._active_search_task_id = None
        
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.setup_ui()
        self.after(100, self.display_results)

    def _on_close(self):
        if self._active_search_task_id and self.app.task_runner.is_running(self._active_search_task_id):
            self.app.task_runner.cancel(self._active_search_task_id)
        self.destroy()

    def setup_ui(self):
        self.configure(fg_color=SURFACE_BG)

        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.pack(fill="both", expand=True, padx=12, pady=12)

        header_card = SectionCard(
            shell,
            title="Galeria Expandida",
            subtitle=f"Resultados para: {self.tags}",
        )
        header_card.pack(fill="x", pady=(0, 8))

        header_meta = ctk.CTkFrame(header_card.body, fg_color="transparent")
        header_meta.pack(fill="x")
        ctk.CTkLabel(
            header_meta,
            text="Visualize mais resultados, selecione e baixe em lote.",
            text_color=TEXT_SECONDARY,
            font=FONT_CAPTION,
            anchor="w",
            justify="left",
        ).pack(fill="x")

        results_card = SectionCard(
            shell,
            title="Resultados",
            subtitle="Clique para selecionar. Clique direito em uma miniatura para abrir em tela cheia.",
        )
        results_card.pack(fill="both", expand=True)

        self.grid_widget = DanbooruGridWidget(
            results_card.body,
            self.app,
            self.client,
            on_selection_change=self.update_selection_label,
            columns=5,
        )
        self.grid_widget.pack(fill="both", expand=True, pady=(0, 8))

        footer = ctk.CTkFrame(results_card.body, fg_color="transparent")
        footer.pack(fill="x")

        nav_frame = ctk.CTkFrame(footer, fg_color="transparent")
        nav_frame.pack(side="left")

        self.btn_prev = ActionButtonSecondary(nav_frame, text="<", width=44, command=lambda: self.change_page(-1))
        self.btn_prev.pack(side="left")

        self.lbl_page = ctk.CTkLabel(
            nav_frame,
            text=f"Pagina {self.current_page}",
            width=110,
            height=36,
            corner_radius=8,
            fg_color=SURFACE_MUTED,
            text_color=TEXT_PRIMARY,
            font=FONT_BODY,
        )
        self.lbl_page.pack(side="left", padx=6)

        self.btn_next = ActionButtonSecondary(nav_frame, text=">", width=44, command=lambda: self.change_page(1))
        self.btn_next.pack(side="left")

        actions_frame = ctk.CTkFrame(footer, fg_color="transparent")
        actions_frame.pack(side="right")

        self.selection_label = ctk.CTkLabel(
            actions_frame,
            text="0 selecionados",
            text_color=TEXT_SECONDARY,
            font=FONT_CAPTION,
            anchor="e",
        )
        self.selection_label.pack(side="left", padx=(0, 12))

        self.btn_download_selected = ActionButtonPrimary(
            actions_frame,
            text="Criar Pasta com Selecionados",
            command=self.download_selected,
        )
        self.btn_download_selected.pack(side="left")

        self._update_page_controls()

    def display_results(self):
        if self.posts:
            self.grid_widget.display_posts(self.posts)
        # else: maybe fetch?

    def change_page(self, delta):
        new_page = self.current_page + delta
        if new_page < 1: return
        self.current_page = new_page
        self._update_page_controls()
        
        self.grid_widget.display_loading()

        if self._active_search_task_id and self.app.task_runner.is_running(self._active_search_task_id):
            self.app.task_runner.cancel(self._active_search_task_id)

        self._search_seq += 1
        task_id = f"online_search_gallery_{id(self)}_{self._search_seq}"
        self._active_search_task_id = task_id

        def task_fn(cancel_event, _on_progress):
            if cancel_event and cancel_event.is_set():
                return {"cancelled": True, "posts": [], "task_id": task_id}

            logger.debug("Fetching page %s for tags '%s'", self.current_page, self.tags)
            posts = self.client.search_posts(self.tags, limit=20, page=self.current_page)
            if cancel_event and cancel_event.is_set():
                return {"cancelled": True, "posts": [], "task_id": task_id}

            return {"cancelled": False, "posts": posts, "task_id": task_id}

        def on_done(result):
            if result.get("task_id") != self._active_search_task_id:
                return
            self._active_search_task_id = None
            if result.get("cancelled"):
                return
            self.posts = result.get("posts") or []
            self.after(0, lambda: self.grid_widget.display_posts(self.posts))

        def on_error(exc):
            if task_id != self._active_search_task_id:
                return
            self._active_search_task_id = None
            logger.exception("Failed to fetch posts: %s", exc)
            self.after(0, lambda: tk.messagebox.showerror("Erro", f"Erro ao buscar imagens: {exc}"))

        self.app.task_runner.submit(
            task_id,
            task_fn,
            on_done=on_done,
            on_error=on_error,
        )

    def update_selection_label(self, count):
        noun = "selecionado" if count == 1 else "selecionados"
        self.selection_label.configure(text=f"{count} {noun}")

    def _update_page_controls(self):
        if hasattr(self, "lbl_page"):
            self.lbl_page.configure(text=f"Pagina {self.current_page}")
        if hasattr(self, "btn_prev"):
            state = "disabled" if self.current_page <= 1 else "normal"
            self.btn_prev.configure(state=state)

    def download_selected(self):
        selected_posts = self.grid_widget.get_selected_items()
        if not selected_posts:
            messagebox.showwarning("Aviso", "Selecione pelo menos uma imagem.")
            return

        folder_original_dir = self.app.app_config.get('last_folder')
        if not folder_original_dir: folder_original_dir = os.path.expanduser("~")

        target_dir = filedialog.askdirectory(title="Escolha onde Criar a Pasta", initialdir=folder_original_dir)
        if not target_dir: return
        
        name_dialog = ctk.CTkInputDialog(text="Nome da Nova Pasta:", title="Criar Pasta")
        folder_name = name_dialog.get_input()
        if not folder_name: return
        
        final_path = os.path.join(target_dir, folder_name)
        if not os.path.exists(final_path):
            os.makedirs(final_path)

        def on_success(result):
            messagebox.showinfo("Sucesso", "Download concluido! Carregando pasta...")
            self.app.app_config.set("last_folder", result["path"])
            self.app.load_images_from_folder(result["path"])
            self.app.tabview.set("Edição")
            self.destroy()

        _submit_download_task(
            app=self.app,
            ui_parent=self,
            task_id=f"online_download_gallery_{id(self)}",
            selected_posts=selected_posts,
            final_path=final_path,
            client=self.client,
            on_success=on_success,
            running_message="Ja existe um download em andamento nesta galeria.",
        )

    def open_image_viewer(self, post):
        DanbooruImageViewer(self, post, self.client, app_instance=self.app)



class DanbooruImageViewer(ctk.CTkToplevel):
    SUPPORTED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "bmp"}

    def __init__(self, parent, post, client, app_instance=None):
        super().__init__(parent)
        self.post = post
        self.client = client
        self.app = app_instance
        self.task_runner = app_instance.task_runner if app_instance else TaskRunner()
        self.rotation = 0
        self.original_image = None
        self._load_task_id = f"online_viewer_load_{id(self)}"

        self.title(f"Visualizador - {post.get('tag_string_character', 'Imagem')}")
        self.geometry("1200x900")
        try:
            self.state('zoomed')
        except Exception as exc:
            logger.debug("Nao foi possivel maximizar o visualizador: %s", exc)

        self.label_loading = ctk.CTkLabel(self, text="Carregando imagem em alta resolucao...", font=ctk.CTkFont(size=20))
        self.label_loading.pack(expand=True)

        self.image_label = ctk.CTkLabel(self, text="")
        self.image_label.pack(fill="both", expand=True)

        # Controls
        self.bind("<Escape>", lambda e: self._on_close())
        self.bind("<Control-q>", lambda e: self.rotate_left())
        self.bind("<Control-e>", lambda e: self.rotate_right())
        self.bind("<Control-Q>", lambda e: self.rotate_left())
        self.bind("<Control-E>", lambda e: self.rotate_right())

        self.image_label.bind("<Button-3>", self.show_context_menu)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._start_load_image()

    def _on_close(self):
        if self._load_task_id and self.task_runner.is_running(self._load_task_id):
            self.task_runner.cancel(self._load_task_id)
        if self.original_image:
            try:
                self.original_image.close()
            except Exception:
                pass
            self.original_image = None
        self.destroy()

    def _start_load_image(self):
        task_id = self._load_task_id
        if self.task_runner.is_running(task_id):
            return

        def task_fn(cancel_event, _on_progress):
            url = self.post.get("large_file_url") or self.post.get("file_url") or self.post.get("sample_url")
            if not url:
                return {"error": "URL da imagem nao encontrada."}

            file_ext = str(self.post.get("file_ext") or "").lower()
            if file_ext and file_ext not in self.SUPPORTED_IMAGE_EXTENSIONS:
                return {"error": f"Formato nao suportado no visualizador: .{file_ext}"}

            if cancel_event and cancel_event.is_set():
                return {"cancelled": True}

            data = self.client.download_image(url)
            if cancel_event and cancel_event.is_set():
                return {"cancelled": True}
            if not data:
                return {"error": "Falha ao baixar imagem."}

            try:
                with Image.open(BytesIO(data)) as img:
                    loaded = img.convert("RGBA").copy()
                return {"cancelled": False, "image": loaded}
            except (UnidentifiedImageError, OSError):
                return {"error": "Arquivo recebido nao e uma imagem valida para visualizacao."}

        def on_done(result):
            self.after(0, lambda: self._on_image_loaded(result))

        def on_error(exc):
            self.after(0, lambda: self._set_loading_error(f"Erro ao carregar: {exc}"))

        started = self.task_runner.submit(
            task_id,
            task_fn,
            on_done=on_done,
            on_error=on_error,
        )
        if not started:
            self._set_loading_error("Falha ao iniciar carregamento.")

    def _set_loading_error(self, text):
        if not self.winfo_exists():
            return
        if self.label_loading.winfo_exists():
            self.label_loading.configure(text=text)

    def _on_image_loaded(self, result):
        if not self.winfo_exists():
            return
        if result.get("cancelled"):
            return
        if result.get("error"):
            self._set_loading_error(result["error"])
            return
        img = result.get("image")
        if img is None:
            self._set_loading_error("Falha ao carregar imagem.")
            return
        self.display_image(img)

    def rotate_left(self):
        self.rotation = (self.rotation + 90) % 360
        self.display_image()

    def rotate_right(self):
        self.rotation = (self.rotation - 90) % 360
        self.display_image()

    def show_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Rotacionar 90 Esquerda (Ctrl+Q)", command=self.rotate_left)
        menu.add_command(label="Rotacionar 90 Direita (Ctrl+E)", command=self.rotate_right)
        menu.post(event.x_root, event.y_root)

    def display_image(self, img_pil=None):
        if self.label_loading.winfo_exists():
            self.label_loading.destroy()
            
        if img_pil:
            if self.original_image and self.original_image is not img_pil:
                try:
                    self.original_image.close()
                except Exception:
                    pass
            self.original_image = img_pil
            
        if not self.original_image:
            return

        # Apply rotation
        # Expand=True ensures the full image is kept (dimensions swap at 90/270)
        img_rotated = self.original_image.rotate(self.rotation, expand=True)
        
        # Calculate fit size
        win_w = self.winfo_width()
        win_h = self.winfo_height()
        if win_w < 100: win_w = 1200
        if win_h < 100: win_h = 900
        
        # Fit logic
        ratio = min(win_w / img_rotated.width, win_h / img_rotated.height)
        new_w = int(img_rotated.width * ratio)
        new_h = int(img_rotated.height * ratio)
        
        if new_w <= 0: new_w = 1
        if new_h <= 0: new_h = 1
        
        resized = img_rotated.resize((new_w, new_h), Image.LANCZOS)
        
        ctk_img = ctk.CTkImage(light_image=resized, dark_image=resized, size=(new_w, new_h))
        self.image_label.configure(image=ctk_img)
        self.image_label.image = ctk_img # keep ref

