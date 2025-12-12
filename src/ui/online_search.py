import os
import threading
import customtkinter as ctk
from PIL import Image, ImageTk
from io import BytesIO
from tkinter import messagebox, filedialog
import tkinter as tk

from src.core.danbooru import DanbooruClient
from src.ui.widgets import ProgressBarPopup
from src.ui.autocomplete import DanbooruAutocomplete
from src.ui.danbooru_grid import DanbooruGridWidget

class DanbooruSearchTab:
    def __init__(self, parent_frame, app_instance):
        self.parent = parent_frame
        self.app = app_instance
        self.client = DanbooruClient()
        self.current_page = 1
        
        self.setup_ui()
        self.autocomplete = DanbooruAutocomplete(self.entry_search, self.app.root, self.client)

    def setup_ui(self):
        # Top Bar: Search
        top_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        top_frame.pack(fill="x", padx=10, pady=(10, 5))

        self.entry_search = ctk.CTkEntry(top_frame, placeholder_text="Tags (ex: hatsune_miku rating:safe)")
        self.entry_search.pack(fill="x", expand=True)
        self.entry_search.bind("<Return>", lambda e: self.search(page=1, new_search=True))

        # Filters Row
        filters_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        filters_frame.pack(fill="x", padx=10, pady=(0, 5))
        
        # Rating Filter
        self.opt_rating = ctk.CTkOptionMenu(filters_frame, values=["Qualquer Classificação", "Geral (General)", "Sensível (Sensitive)", "Questionável (Questionable)", "Explícito (Explicit)"])
        self.opt_rating.pack(side="left", expand=True, fill="x", padx=(0, 5))
        
        # Sort Filter
        self.opt_sort = ctk.CTkOptionMenu(filters_frame, values=["Mais Recentes", "Melhor Avaliados", "Mais Favoritos"])
        self.opt_sort.pack(side="left", expand=True, fill="x", padx=(5, 0))

        # Buttons row
        btn_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        btn_search = ctk.CTkButton(btn_frame, text="🔍 Buscar", width=120, command=lambda: self.search(page=1, new_search=True))
        btn_search.pack(side="left", padx=(0, 5), expand=True, fill="x")
        
        btn_expand = ctk.CTkButton(btn_frame, text="⤢ Expandir", width=120, fg_color="#3a3a3a", hover_color="#4a4a4a", command=self.open_expanded_gallery)
        btn_expand.pack(side="left", padx=(5, 0), expand=True, fill="x")

        # Main Content: Grid of Images (using reusable widget)
        self.grid_widget = DanbooruGridWidget(
            self.parent, 
            self.app, 
            self.client, 
            on_selection_change=self.update_selection_label,
            columns=4
        )
        self.grid_widget.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Pagination / Footer
        footer_frame = ctk.CTkFrame(self.parent, fg_color="transparent", height=40)
        footer_frame.pack(fill="x", padx=10, pady=5)
        
        self.btn_prev = ctk.CTkButton(footer_frame, text="❮", width=40, command=lambda: self.change_page(-1))
        self.btn_prev.pack(side="left")
        
        self.lbl_page = ctk.CTkLabel(footer_frame, text="Página 1", width=100, anchor="center", font=ctk.CTkFont(weight="bold"))
        self.lbl_page.pack(side="left", padx=5)
        
        self.btn_next = ctk.CTkButton(footer_frame, text="❯", width=40, command=lambda: self.change_page(1))
        self.btn_next.pack(side="left")

        # Bottom Bar: Actions
        bottom_frame = ctk.CTkFrame(self.parent, fg_color="transparent", height=40)
        bottom_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.selection_label = ctk.CTkLabel(bottom_frame, text="0 selecionados")
        self.selection_label.pack(side="left", padx=10)

        ctk.CTkButton(bottom_frame, text="Criar Pasta com Selecionados", fg_color="green", hover_color="darkgreen", command=self.download_selected).pack(side="right")

    def search(self, page=1, new_search=False):
        tags = self.entry_search.get()
        if not tags: return

        # Apply Filters
        rating_map = {
            "Geral (General)": "rating:general",
            "Sensível (Sensitive)": "rating:sensitive",
            "Questionável (Questionable)": "rating:questionable",
            "Explícito (Explicit)": "rating:explicit"
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
        self.lbl_page.configure(text=f"Página {self.current_page}")

        if new_search:
             self.grid_widget.clear_selection()
             self.update_selection_label(0)
        
        self.app.root.update()

        def fetch():
            try:
                posts = self.client.search_posts(tags, limit=20, page=self.current_page)
                self.app.root.after(0, lambda: self.grid_widget.display_posts(posts))
            except Exception as e:
                print(f"ERROR: Search failed: {e}")

        threading.Thread(target=fetch, daemon=True).start()

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

        popup = ProgressBarPopup(self.app.root, title="Baixando...", maximum=len(selected_posts))
        
        def download_task():
            try:
                count = 0
                for post in selected_posts:
                    try:
                        file_url = post.get('file_url') or post.get('large_file_url') or post.get('source')
                        if not file_url: continue
                        
                        fname = f"{post['id']}.{post.get('file_ext', 'png')}"
                        save_path = os.path.join(final_path, fname)
                        
                        data = self.client.download_image(file_url)
                        if data:
                            with open(save_path, 'wb') as f:
                                f.write(data)
                        
                        count += 1
                        self.app.root.after(0, lambda c=count: popup.update_progress(c, f"Baixado {c}/{len(selected_posts)}"))
                    except Exception as e:
                        print(f"ERRO ao baixar post {post.get('id')}: {e}")

                self.app.root.after(0, lambda: finish(final_path))
            except Exception as e:
                print(f"ERRO CRÍTICO no download (Main Tab): {e}")
                self.app.root.after(0, popup.close)

        def finish(path):
            popup.close()
            messagebox.showinfo("Sucesso", "Download concluído! Carregando pasta...")
            self.app.app_config.set('last_folder', path)
            self.app.load_images_from_folder(path)
            self.app.tabview.set("Edição")

        threading.Thread(target=download_task, daemon=True).start()

    def open_expanded_gallery(self):
        tags = self.entry_search.get()
        if not tags:
            messagebox.showinfo("Info", "Faça uma busca primeiro.")
            return
        
        DanbooruGalleryWindow(self.app.root, self.grid_widget.posts, self.client, self.app, tags, self.current_page)


class DanbooruGalleryWindow(ctk.CTkToplevel):
    def __init__(self, parent, posts, client, app_instance, tags, current_page=1):
        super().__init__(parent)
        self.title(f"Galeria Expandida - {tags}")
        self.geometry("1100x850")
        
        self.posts = posts
        self.client = client
        self.app = app_instance
        self.tags = tags
        self.current_page = current_page
        
        self.setup_ui()
        self.after(100, self.display_results)

    def setup_ui(self):
        # Top Bar
        top_frame = ctk.CTkFrame(self, height=50)
        top_frame.pack(fill="x", padx=10, pady=10)
        
        self.btn_prev = ctk.CTkButton(top_frame, text="<", width=40, command=lambda: self.change_page(-1))
        self.btn_prev.pack(side="left", padx=(10, 5))
        
        self.lbl_page = ctk.CTkLabel(top_frame, text=f"Pág. {self.current_page}", width=60)
        self.lbl_page.pack(side="left", padx=5)

        self.btn_next = ctk.CTkButton(top_frame, text=">", width=40, command=lambda: self.change_page(1))
        self.btn_next.pack(side="left", padx=(5, 20))
        
        self.selection_label = ctk.CTkLabel(top_frame, text="0 selecionados")
        self.selection_label.pack(side="left", padx=20)
        
        ctk.CTkButton(top_frame, text="Criar Pasta com Selecionados", fg_color="green", hover_color="darkgreen", command=self.download_selected).pack(side="right", padx=10)

        # Reusable Grid Widget
        self.grid_widget = DanbooruGridWidget(
            self, 
            self.app, 
            self.client, 
            on_selection_change=self.update_selection_label,
            columns=5 # More columns for expanded view
        )
        self.grid_widget.pack(fill="both", expand=True, padx=10, pady=5)

    def display_results(self):
        if self.posts:
            self.grid_widget.display_posts(self.posts)
        # else: maybe fetch?

    def change_page(self, delta):
        new_page = self.current_page + delta
        if new_page < 1: return
        self.current_page = new_page
        self.lbl_page.configure(text=f"Pág. {self.current_page}")
        
        self.grid_widget.display_loading()
        
        def fetch():
            try:
                print(f"DEBUG: Fetching page {self.current_page} for tags '{self.tags}'")
                posts = self.client.search_posts(self.tags, limit=20, page=self.current_page)
                self.posts = posts
                self.after(0, lambda: self.grid_widget.display_posts(posts))
            except Exception as e:
                print(f"ERROR: Failed to fetch posts: {e}")
                def show_error():
                    tk.messagebox.showerror("Erro", f"Erro ao buscar imagens: {e}")
                self.after(0, show_error)
        
        threading.Thread(target=fetch, daemon=True).start()

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

        popup = ProgressBarPopup(self, title="Baixando...", maximum=len(selected_posts))
        
        def download_task():
            try:
                count = 0
                for post in selected_posts:
                    try:
                        print(f"DEBUG: Processing post {post.get('id')}")
                        file_url = post.get('file_url') or post.get('large_file_url') or post.get('source')
                        if not file_url: 
                            print(f"AVISO: URL não encontrada para post {post.get('id')}")
                            continue
                        
                        fname = f"{post['id']}.{post.get('file_ext', 'png')}"
                        save_path = os.path.join(final_path, fname)
                        
                        # Try to use cache if available (or just download)
                        data = self.client.download_image(file_url)
                        
                        if data:
                            with open(save_path, 'wb') as f:
                                f.write(data)
                        
                        count += 1
                        self.after(0, lambda c=count: popup.update_progress(c, f"Baixado {c}/{len(selected_posts)}"))
                    except Exception as e:
                        print(f"ERRO ao baixar imagem {post.get('id')}: {e}")
                
                self.after(0, lambda: finish(final_path))
            except Exception as e:
                print(f"ERRO CRÍTICO no download: {e}")
                self.after(0, popup.close)

        def finish(path):
            popup.close()
            messagebox.showinfo("Sucesso", "Download concluído! Carregando pasta...")
            self.app.app_config.set('last_folder', path)
            self.app.load_images_from_folder(path)
            self.app.tabview.set("Edição")
            self.destroy()

        threading.Thread(target=download_task, daemon=True).start()

    def open_image_viewer(self, post):
        DanbooruImageViewer(self, post, self.client)



class DanbooruImageViewer(ctk.CTkToplevel):
    def __init__(self, parent, post, client):
        super().__init__(parent)
        self.post = post
        self.client = client
        self.rotation = 0
        self.original_image = None
        
        self.title(f"Visualizador - {post.get('tag_string_character', 'Imagem')}")
        self.geometry("1200x900")
        try:
            self.state('zoomed')
        except: pass
        
        self.label_loading = ctk.CTkLabel(self, text="Carregando imagem em alta resolução...", font=ctk.CTkFont(size=20))
        self.label_loading.pack(expand=True)
        
        self.image_label = ctk.CTkLabel(self, text="")
        self.image_label.pack(fill="both", expand=True)
        
        # Controls
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Control-q>", lambda e: self.rotate_left())
        self.bind("<Control-e>", lambda e: self.rotate_right())
        self.bind("<Control-Q>", lambda e: self.rotate_left())
        self.bind("<Control-E>", lambda e: self.rotate_right())
        
        self.image_label.bind("<Button-3>", self.show_context_menu)
        
        threading.Thread(target=self.load_image, daemon=True).start()

    def load_image(self):
        url = self.post.get('large_file_url') or self.post.get('file_url') or self.post.get('sample_url')
        if not url:
            self.label_loading.configure(text="URL da imagem não encontrada.")
            return

        data = self.client.download_image(url)
        if data:
            try:
                img = Image.open(BytesIO(data))
                
                # Resize to fit screen (approx 90% of screen size if possible, or just fit to window)
                # Since we are in a thread, we can't query window size accurately if it's maximizing.
                # Use a safe default logic: 
                # On UI main thread: get window size -> resize img -> show.
                
                self.after(0, lambda: self.display_image(img))
            except Exception as e:
                self.after(0, lambda: self.label_loading.configure(text=f"Erro ao carregar: {e}"))

    def rotate_left(self):
        self.rotation = (self.rotation + 90) % 360
        self.display_image()

    def rotate_right(self):
        self.rotation = (self.rotation - 90) % 360
        self.display_image()

    def show_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="⟲ Rotacionar 90° Esquerda (Ctrl+Q)", command=self.rotate_left)
        menu.add_command(label="⟳ Rotacionar 90° Direita (Ctrl+E)", command=self.rotate_right)
        menu.post(event.x_root, event.y_root)

    def display_image(self, img_pil=None):
        if self.label_loading.winfo_exists():
            self.label_loading.destroy()
            
        if img_pil:
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
