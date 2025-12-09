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

class DanbooruSearchTab:
    def __init__(self, parent_frame, app_instance):
        self.parent = parent_frame
        self.app = app_instance
        self.client = DanbooruClient()
        self.results = []
        self.selected_posts = set()
        self.selected_posts_details = {}
        self.thumbnails = {}
        self.current_page = 1
        
        self.setup_ui()
        self.autocomplete = DanbooruAutocomplete(self.entry_search, self.app.root, self.client)

    def setup_ui(self):
        # Top Bar: Search
        top_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        top_frame.pack(fill="x", padx=10, pady=10)

        self.entry_search = ctk.CTkEntry(top_frame, placeholder_text="Tags (ex: hatsune_miku rating:safe)")
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry_search.bind("<Return>", lambda e: self.search(page=1, new_search=True))

        btn_search = ctk.CTkButton(top_frame, text="Buscar", width=100, command=lambda: self.search(page=1, new_search=True))
        btn_search.pack(side="right")
        
        btn_expand = ctk.CTkButton(top_frame, text="🗖 Expandir", width=100, fg_color="#3a3a3a", hover_color="#4a4a4a", command=self.open_expanded_gallery)
        btn_expand.pack(side="right", padx=10)

        # Main Content: Grid of Images
        self.scroll_frame = ctk.CTkScrollableFrame(self.parent, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.msg_label = ctk.CTkLabel(self.scroll_frame, text="Digite as tags acima para buscar.")
        self.msg_label.pack(pady=20)

        self.msg_label.pack(pady=20)

        # Pagination / Footer
        footer_frame = ctk.CTkFrame(self.parent, fg_color="transparent", height=40)
        footer_frame.pack(fill="x", padx=10, pady=5)
        
        self.btn_prev = ctk.CTkButton(footer_frame, text="< Anterior", width=80, command=lambda: self.change_page(-1))
        self.btn_prev.pack(side="left")
        
        self.lbl_page = ctk.CTkLabel(footer_frame, text="Página 1", width=80, anchor="center")
        self.lbl_page.pack(side="left", padx=5)
        
        self.btn_next = ctk.CTkButton(footer_frame, text="Próximo >", width=80, command=lambda: self.change_page(1))
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

        self.current_page = page
        self.lbl_page.configure(text=f"Página {self.current_page}")

        # Clear previous
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        # Keep selections? Maybe not between searches, but between pages? 
        # Usually clearing selection on new search is better.
        if new_search:

             self.selected_posts.clear()
             self.selected_posts_details.clear()
             self.update_selection_label()
        
        self.thumbnails.clear()

        self.msg_label = ctk.CTkLabel(self.scroll_frame, text="Buscando...")
        self.msg_label.pack(pady=20)
        self.app.root.update()

        def fetch():
            posts = self.client.search_posts(tags, limit=20, page=self.current_page)
            self.app.root.after(0, lambda: self.display_results(posts))

        threading.Thread(target=fetch, daemon=True).start()

    def change_page(self, delta):
        new_page = self.current_page + delta
        if new_page < 1: return
        self.search(page=new_page, new_search=False)

    def display_results(self, posts):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        if not posts:
            ctk.CTkLabel(self.scroll_frame, text="Nenhum resultado encontrado.").pack(pady=20)
            return
        
        self.results = posts
        
        # Grid Configuration
        columns = 4
        # Configure columns weights if possible, or just pack in frames
        # Creating a grid of frames
        
        row = 0
        col = 0
        
        grid_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        grid_frame.pack(fill="both", expand=True)

        for i in range(columns):
            grid_frame.grid_columnconfigure(i, weight=1)

        for post in posts:
            # Try multiple keys for preview
            preview_url = post.get('preview_file_url') or post.get('preview_url') or post.get('file_url') or post.get('large_file_url')
            
            if not preview_url: continue
            
            # Container for image
            card = ctk.CTkFrame(grid_frame, corner_radius=5, fg_color="#2b2b2b")
            card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

            if post['id'] in self.selected_posts:
                card.configure(border_width=2, border_color="#3B8ED0")
            
            # Placeholder Label while loading
            lbl = ctk.CTkLabel(card, text="...", width=150, height=150)
            lbl.pack(padx=2, pady=2)
            
            # Store data on widget for click handler
            # Store data on widget for click handler
            card.bind("<Button-1>", lambda e, p=post, w=card: self.toggle_selection(p, w))
            lbl.bind("<Button-1>", lambda e, p=post, w=card: self.toggle_selection(p, w))
            
            # Async thumbnail load
            self.load_thumbnail(preview_url, lbl)

            col += 1
            if col >= columns:
                col = 0
                row += 1

    def load_thumbnail(self, url, label_widget):
        if not url.startswith("http"):
             # Sometimes Danbooru returns relative paths?
             # But normally API returns absolute if not specified otherwise.
             pass 

        def task():
            try:
                data = self.client.download_image(url)
                if data:
                    img = Image.open(BytesIO(data))
                    img.thumbnail((150, 150))
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                    
                    def update_ui():
                        label_widget.configure(image=ctk_img, text="")
                        self.thumbnails[label_widget] = ctk_img # Keep ref
                    
                    self.app.root.after(0, update_ui)
            except: pass
        
        threading.Thread(target=task, daemon=True).start()

    def toggle_selection(self, post, card_widget):
        post_id = post['id']
        if post_id in self.selected_posts:
            self.selected_posts.remove(post_id)
            if post_id in self.selected_posts_details: del self.selected_posts_details[post_id]
            card_widget.configure(border_width=0)
        else:
            self.selected_posts.add(post_id)
            self.selected_posts_details[post_id] = post
            card_widget.configure(border_width=2, border_color="#3B8ED0")
        self.update_selection_label()

    def update_selection_label(self):
        self.selection_label.configure(text=f"{len(self.selected_posts)} selecionados")

    def download_selected(self):
        if not self.selected_posts:
            messagebox.showwarning("Aviso", "Selecione pelo menos uma imagem.")
            return

        folder_original_dir = self.app.app_config.get('last_folder')
        if not folder_original_dir: folder_original_dir = os.path.expanduser("~")

        # Ask for folder name 
        # (Using a simple dialogue or input)
        # Using filedialog to pick a parent folder, then we create a subfolder?
        # Or just ask user where to save.
        
        target_dir = filedialog.askdirectory(title="Escolha onde Criar a Pasta", initialdir=folder_original_dir)
        if not target_dir: return
        
        # Ask for new folder name
        name_dialog = ctk.CTkInputDialog(text="Nome da Nova Pasta:", title="Criar Pasta")
        folder_name = name_dialog.get_input()
        if not folder_name: return
        
        final_path = os.path.join(target_dir, folder_name)
        if not os.path.exists(final_path):
            os.makedirs(final_path)

        # Download Process
        popup = ProgressBarPopup(self.app.root, title="Baixando...", maximum=len(self.selected_posts))
        
        def download_task():
            count = 0
            for post in self.selected_posts_details.values():
                file_url = post.get('file_url') or post.get('large_file_url') or post.get('source')
                if not file_url: continue
                
                fname = f"{post['id']}.{post.get('file_ext', 'png')}"
                save_path = os.path.join(final_path, fname)
                
                data = self.client.download_image(file_url)
                if data:
                    with open(save_path, 'wb') as f:
                        f.write(data)
                
                count += 1
                self.app.root.after(0, lambda c=count: popup.update_progress(c, f"Baixado {c}/{len(self.selected_posts)}"))
            
            self.app.root.after(0, lambda: finish(final_path))

        def finish(path):
            popup.close()
            messagebox.showinfo("Sucesso", "Download concluído! Carregando pasta...")
            self.app.app_config.set('last_folder', path)
            self.app.load_images_from_folder(path)
            # Switch back to editor tab
            self.app.tabview.set("Edição") # Assuming we put tabs in main window or we navigate somehow
            # If search is a tab in the main layout, we might need to expose tabview or method to switch.

        threading.Thread(target=download_task, daemon=True).start()

    def open_expanded_gallery(self):
        tags = self.entry_search.get()
        if not tags:
            messagebox.showinfo("Info", "Faça uma busca primeiro.")
            return
        
        # We pass self.results (current page) but also tags and current page number so gallery can paginate
        DanbooruGalleryWindow(self.app.root, self.results, self.client, self.app, tags, self.current_page)


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
        
        self.selected_posts = set()
        self.selected_posts_details = {}
        self.thumbnails = {}
        
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

        # Scroll Area
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)

    def display_results(self):
        # Clear previous
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        # Grid Configuration (Larger grid)
        columns = 5
        row = 0
        col = 0
        
        grid_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        grid_frame.pack(fill="both", expand=True)

        for i in range(columns):
            grid_frame.grid_columnconfigure(i, weight=1)

        for post in self.posts:
            # Try multiple keys for preview
            preview_url = post.get('preview_file_url') or post.get('preview_url') or post.get('file_url') or post.get('large_file_url') or post.get('source')
            
            if not preview_url: continue
            
            # Container for image (Larger cards)
            card = ctk.CTkFrame(grid_frame, corner_radius=5, fg_color="#2b2b2b")
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            
            if post['id'] in self.selected_posts:
                card.configure(border_width=3, border_color="#3B8ED0")
            
            # Placeholder Label
            lbl = ctk.CTkLabel(card, text="...", width=200, height=200) # Bigger placeholder
            lbl.pack(padx=2, pady=2)
            
            # Store data on widget for click handler
            # Store data on widget for click handler
            card.bind("<Button-1>", lambda e, p=post, w=card: self.toggle_selection(p, w))
            lbl.bind("<Button-1>", lambda e, p=post, w=card: self.toggle_selection(p, w))
            
            # Use DanbooruSearchTab static logic or duplicated logic? 
            # Ideally minimal duplication. But for now local load method is fine.
            self.load_thumbnail(preview_url, lbl)

            col += 1
            if col >= columns:
                col = 0
                row += 1

    def load_thumbnail(self, url, label_widget):
        def task():
            try:
                data = self.client.download_image(url)
                if data:
                    img = Image.open(BytesIO(data))
                    img.thumbnail((200, 200)) # Bigger size
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                    
                    def update_ui():
                        if label_widget.winfo_exists():
                            label_widget.configure(image=ctk_img, text="")
                            self.thumbnails[label_widget] = ctk_img
                    
                    self.after(0, update_ui)
            except: pass
        
        threading.Thread(target=task, daemon=True).start()

    def toggle_selection(self, post, card_widget):
        post_id = post['id']
        if post_id in self.selected_posts:
            self.selected_posts.remove(post_id)
            if post_id in self.selected_posts_details: del self.selected_posts_details[post_id]
            card_widget.configure(border_width=0)
        else:
            self.selected_posts.add(post_id)
            self.selected_posts_details[post_id] = post
            card_widget.configure(border_width=3, border_color="#3B8ED0")
        self.selection_label.configure(text=f"{len(self.selected_posts)} selecionados")

    def download_selected(self):
        # Reuse logic from DanbooruSearchTab? Or duplicate for independence?
        # Duplicating small download logic to avoid tighter coupling or complex passing.
        if not self.selected_posts:
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

        popup = ProgressBarPopup(self, title="Baixando...", maximum=len(self.selected_posts))
        
        def download_task():
            count = 0
            for post in self.selected_posts_details.values():
                file_url = post.get('file_url') or post.get('large_file_url') or post.get('source')
                if not file_url: continue
                
                fname = f"{post['id']}.{post.get('file_ext', 'png')}"
                save_path = os.path.join(final_path, fname)
                
                data = self.client.download_image(file_url)
                if data:
                    with open(save_path, 'wb') as f:
                        f.write(data)
                
                count += 1
                self.after(0, lambda c=count: popup.update_progress(c, f"Baixado {c}/{len(self.selected_posts)}"))
            
            self.after(0, lambda: finish(final_path))

        def finish(path):
            popup.close()
            messagebox.showinfo("Sucesso", "Download concluído! Carregando pasta...")
            self.app.app_config.set('last_folder', path)
            self.app.load_images_from_folder(path)
            self.app.tabview.set("Edição")
            self.destroy() # Close gallery after done?

        threading.Thread(target=download_task, daemon=True).start()

    def change_page(self, delta):
        new_page = self.current_page + delta
        if new_page < 1: return
        self.current_page = new_page
        self.lbl_page.configure(text=f"Pág. {self.current_page}")
        
        # Fetch new data
        # We need a loading indicator
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.scroll_frame, text="Carregando...").pack(pady=20)
        
        def fetch():
            try:
                posts = self.client.search_posts(self.tags, limit=20, page=self.current_page)
                self.posts = posts
                self.after(0, self.display_results)
            except: pass
        
        threading.Thread(target=fetch, daemon=True).start()
