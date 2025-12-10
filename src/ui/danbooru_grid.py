import threading
import customtkinter as ctk
from PIL import Image
from io import BytesIO
import tkinter as tk
from src.core.cache_manager import CacheManager

class DanbooruGridWidget(ctk.CTkScrollableFrame):
    def __init__(self, parent, app_instance, client, on_selection_change=None, columns=4, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.app = app_instance
        self.client = client
        self.on_selection_change = on_selection_change
        self.columns = columns
        
        self.cache = CacheManager() # Initialize cache
        
        self.posts = []
        self.selected_posts = set()
        self.selected_posts_details = {}
        self.thumbnails = {}
        
        # Grid configuration
        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_frame.pack(fill="both", expand=True)
        
        for i in range(self.columns):
            self.grid_frame.grid_columnconfigure(i, weight=1)

    def display_loading(self):
        # Clear previous widgets
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
        self.posts = posts
        
        # Clear previous widgets
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        self.thumbnails.clear()

        if not posts:
            ctk.CTkLabel(self.grid_frame, text="Nenhum resultado encontrado.").pack(pady=20)
            return
            
        row = 0
        col = 0
        
        for post in posts:
            # Try multiple keys for preview
            preview_url = post.get('preview_file_url') or post.get('preview_url') or post.get('file_url') or post.get('large_file_url') or post.get('source')
            
            if not preview_url: continue
            
            # Container for image
            card = ctk.CTkFrame(self.grid_frame, corner_radius=5, fg_color="#2b2b2b")
            card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

            if post['id'] in self.selected_posts:
                card.configure(border_width=2, border_color="#3B8ED0")
            
            # Placeholder Label
            lbl = ctk.CTkLabel(card, text="...", width=150, height=150)
            lbl.pack(padx=2, pady=2)
            
            # Bind events
            card.bind("<Button-1>", lambda e, p=post, w=card: self.toggle_selection(p, w))
            lbl.bind("<Button-1>", lambda e, p=post, w=card: self.toggle_selection(p, w))
            
            # Context Menu (Right Click)
            card.bind("<Button-3>", lambda e, p=post: self.show_context_menu(e, p))
            lbl.bind("<Button-3>", lambda e, p=post: self.show_context_menu(e, p))
            
            self.load_thumbnail(preview_url, lbl)

            col += 1
            if col >= self.columns:
                col = 0
                row += 1

    def load_thumbnail(self, url, label_widget):
        def task():
            try:
                # Check cache first
                data = self.cache.get(url)
                if not data:
                    data = self.client.download_image(url)
                    if data:
                        self.cache.set(url, data)
                
                if data:
                    img = Image.open(BytesIO(data))
                    # Resize for thumbnail
                    img.thumbnail((200, 200))
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                    
                    def update_ui():
                        if label_widget.winfo_exists():
                            label_widget.configure(image=ctk_img, text="")
                            self.thumbnails[label_widget] = ctk_img
                    
                    self.app.root.after(0, update_ui)
            except: pass
        
        threading.Thread(target=task, daemon=True).start()

    def toggle_selection(self, post, card_widget):
        post_id = post['id']
        if post_id in self.selected_posts:
            self.selected_posts.remove(post_id)
            if post_id in self.selected_posts_details:
                del self.selected_posts_details[post_id]
            card_widget.configure(border_width=0)
        else:
            self.selected_posts.add(post_id)
            self.selected_posts_details[post_id] = post
            card_widget.configure(border_width=2, border_color="#3B8ED0")
            
        if self.on_selection_change:
            self.on_selection_change(len(self.selected_posts))

    def get_selected_items(self):
        return list(self.selected_posts_details.values())

    def clear_selection(self):
        self.selected_posts.clear()
        self.selected_posts_details.clear()
        if self.on_selection_change:
            self.on_selection_change(0)
        # Note: Visual update would require re-displaying or tracking widgets. 
        # For now, usually used when changing search/page so re-display happens anyway.

    def show_context_menu(self, event, post):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="👁 Abrir em Tela Cheia", command=lambda: self.open_image_viewer(post))
        menu.post(event.x_root, event.y_root)

    def open_image_viewer(self, post):
        # We need to import DanbooruImageViewer here or pass a factory
        # To avoid circular imports, maybe we can ask the parent to open it, 
        # or import inside method. 
        # Importing inside method is safer for refactoring for now.
        from src.ui.online_search import DanbooruImageViewer
        DanbooruImageViewer(self.winfo_toplevel(), post, self.client)
