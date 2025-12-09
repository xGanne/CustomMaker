import os
import sys
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox, Menu # standard menu is still better for context menus usually, unless CTkOptionMenu replaces it totally
from PIL import Image, ImageTk, ImageOps
import cssutils
import numpy as np
import zipfile
import tempfile
import threading
import shutil

# Internal imports
from src.config.settings import COLORS, BORDA_WIDTH, BORDA_HEIGHT, BORDA_HEX, BORDA_NAMES, SUPPORTED_EXTENSIONS, CSS_FILE
from src.utils.resource_loader import resource_path
# from src.ui.styles import configure_styles # Removed
from src.ui.widgets import Tooltip, ProgressBarPopup
from src.core.image_processor import ImageProcessor
from src.core.uploader import ImgChestUploader
from src.core.app_config import AppConfig
from src.ui.online_search import DanbooruSearchTab

class CustomMakerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Custom Maker Pro")

        # Icon setup
        try:
            icon_path = resource_path("icon.ico")
            if not os.path.exists(icon_path): icon_path = resource_path("icon.png")
            if os.path.exists(icon_path):
                if icon_path.endswith(".ico"): self.root.iconbitmap(icon_path)
                elif icon_path.endswith(".png"):
                    img = tk.PhotoImage(file=icon_path)
                    self.root.tk.call('wm', 'iconphoto', self.root._w, img)
        except Exception: pass

        self.root.geometry("1400x900")
        try:
            self.root.state('zoomed')
        except: pass
        
        # Internal Logic
        self.app_config = AppConfig()
        self.uploader = ImgChestUploader()
        self.face_cascade = ImageProcessor.load_face_cascade()
        
        self.initialize_state_variables()
        self.load_resources()
        
        # configure_styles() # Not needed
        self.create_widgets()

        # Load properties
        last_borda = self.app_config.get('last_global_borda', 'White')
        if last_borda in self.borda_hex:
            self.selected_borda.set(last_borda)
        else:
            self.selected_borda.set('White')
            
        # Initialize default appearance
        default_mode = self.app_config.get('appearance_mode', 'Dark')
        ctk.set_appearance_mode(default_mode)
        
        default_theme = self.app_config.get('color_theme', 'blue')
        ctk.set_default_color_theme(default_theme) # This only affects new widgets mostly, but good for restart

        self.after_id_init_canvas = self.root.after(100, self.update_canvas_if_ready)
        
        self.root.bind('<Control-z>', self.undo)
        self.root.bind('<Control-s>', lambda event: self.show_save_menu())
        self.root.bind('<Control-o>', lambda event: self.select_folder())
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def initialize_state_variables(self):
        self.image_path = None
        self.original_image = None
        self.user_image = None
        self.user_image_pos = (50, 50)
        self.user_image_size = None
        self.selected_image = False
        self.start_x = 0
        self.start_y = 0
        self.status_var = ctk.StringVar(value="Pronto. Selecione uma pasta para começar.")
        self.selected_borda = ctk.StringVar(value="White")
        
        # Memory Optimization
        self.MAX_CACHE_SIZE = 20
        self.images = {}
        self.image_access_order = []
        self.image_states = {}
        
        self.image_list = []
        self.current_image_index = None
        self.undo_stack = []
        self.individual_bordas = {}
        self.uploaded_links = []
        self.custom_borda_hex = "#FFFFFF"
        self.custom_borda_hex_individual = {}
        self.current_hover_item_index = -1
        self.hover_tooltip = None
        self.drag_data = {"item": None, "index": None}

    def load_resources(self):
        self.bordas = self.load_bordas_from_css()
        self.borda_names = BORDA_NAMES
        self.borda_hex = BORDA_HEX

    def load_bordas_from_css(self):
        if not os.path.exists(CSS_FILE): return []
        try:
            p = cssutils.CSSParser()
            s = p.parseFile(CSS_FILE)
            return [r.selectorText for r in s.cssRules if r.type == r.STYLE_RULE]
        except: return []

    def on_closing(self):
        self.app_config.set('last_global_borda', self.selected_borda.get())
        if self.image_list and os.path.dirname(self.image_list[0]):
             self.app_config.set('last_folder', os.path.dirname(self.image_list[0]))
        
        # Save appearance settings
        self.app_config.set('appearance_mode', ctk.get_appearance_mode())
        # self.app_config.set('color_theme', ...) # We don't have a simple getter for current theme name from CTk
        
        self.app_config.save()
        
        if messagebox.askokcancel("Sair", "Deseja sair?"):
            self.close_resources()
            self.root.destroy()
            sys.exit(0)

    def close_resources(self):
        if self.original_image: self.original_image.close()
        if self.user_image: self.user_image.close()
        for img in self.images.values():
            if img: img.close()
        self.undo_stack.clear()

    # --- UI Creation ---
    def create_widgets(self):
        self.create_layout_frames()
        self.setup_canvas_events()
        
        # Status Bar
        self.status_bar = ctk.CTkLabel(self.left_frame, textvariable=self.status_var, anchor="w", height=25)
        self.status_bar.pack(side=tk.BOTTOM, fill="x", pady=(5, 5), padx=5)
        
        self.create_right_panel()

    def create_layout_frames(self):
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=0)
        self.root.grid_rowconfigure(0, weight=1)

        self.left_frame = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        self.right_frame = ctk.CTkFrame(self.root, width=320, corner_radius=10)
        self.right_frame.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.right_frame.grid_propagate(False)

        # Canvas Frame
        self.canvas_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.canvas_frame.pack(fill="both", expand=True)
        
        # Canvas (Standard TKinter Canvas is best for drawing)
        self.canvas = tk.Canvas(self.canvas_frame, bg="#1a1a1a", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

    def setup_canvas_events(self):
        self.canvas.bind("<Button-1>", self.select_image)
        self.canvas.bind("<B1-Motion>", self.move_image)
        self.canvas.bind("<ButtonRelease-1>", self.release_image)
        self.canvas.bind("<Shift-B1-Motion>", self.resize_image_proportional)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self.zoom_image)
        # Linux
        self.canvas.bind("<Button-4>", self.zoom_image)
        self.canvas.bind("<Button-5>", self.zoom_image)

    def create_right_panel(self):
        self.right_frame.grid_rowconfigure(0, weight=0)
        self.right_frame.grid_rowconfigure(1, weight=1) # Tabview expands
        self.right_frame.grid_rowconfigure(2, weight=0)
        
        ctk.CTkLabel(self.right_frame, text="CustomMaker Pro", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(20, 10))

        # Use Tabview for better organization
        self.tabview = ctk.CTkTabview(self.right_frame, width=280)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.tab_edit = self.tabview.add("Edição")
        self.tab_settings = self.tabview.add("Ajustes")
        self.tab_online = self.tabview.add("Online")
        
        # --- Tab Edição ---
        self.create_file_section(self.tab_edit)
        ctk.CTkFrame(self.tab_edit, height=2, fg_color="gray30").pack(fill="x", pady=10, padx=5)
        self.create_border_section(self.tab_edit)
        
        # --- Tab Ajustes ---
        self.create_settings_section(self.tab_settings)

        # --- Tab Online ---
        self.danbooru_tab = DanbooruSearchTab(self.tab_online, self)

        # Image List (Outside tabs, always visible or inside Edit?)
        # Let's put Image List below Tabs or inside "Edição" but it might be cramped.
        # Actually, Image List is core. Let's put it back in the main right frame, BELOW the tabview? 
        # Or make "Lista" a 3rd tab? "Lista" tab is good.
        self.tab_list = self.tabview.add("Lista de Imagens")
        self.create_image_list_section(self.tab_list)
        
        self.create_tips_section(self.right_frame)
        self.create_context_menu_image_list()

    def create_settings_section(self, parent):
        ctk.CTkLabel(parent, text="Aparência:", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(fill="x", padx=10, pady=(10,5))
        
        ctk.CTkLabel(parent, text="Tema (Claro/Escuro):", anchor="w").pack(fill="x", padx=10, pady=2)
        self.appearance_mode_optionemenu = ctk.CTkOptionMenu(parent, values=["Light", "Dark", "System"],
                                                               command=self.change_appearance_mode_event)
        self.appearance_mode_optionemenu.pack(fill="x", padx=10, pady=5)
        self.appearance_mode_optionemenu.set(self.app_config.get('appearance_mode', 'Dark'))

        ctk.CTkLabel(parent, text="Cor de Destaque (Reiniciar):", anchor="w").pack(fill="x", padx=10, pady=2)
        self.color_theme_optionemenu = ctk.CTkOptionMenu(parent, values=["blue", "green", "dark-blue"],
                                                           command=self.change_color_theme_event)
        self.color_theme_optionemenu.pack(fill="x", padx=10, pady=5)
        self.color_theme_optionemenu.set(self.app_config.get('color_theme', 'blue'))

    def change_appearance_mode_event(self, new_appearance_mode: str):
        ctk.set_appearance_mode(new_appearance_mode)
        
    def change_color_theme_event(self, new_color_theme: str):
        # Theme change usually requires restart or manual widget update for complex apps
        self.app_config.set('color_theme', new_color_theme)
        self.app_config.save()
        messagebox.showinfo("Tema", "A alteração da cor de destaque será aplicada na próxima reinicialização.")

    def create_file_section(self, parent):
        btn_open = ctk.CTkButton(parent, text="📂 Selecionar Pasta (Ctrl+O)", command=self.select_folder)
        btn_open.pack(fill="x", padx=10, pady=5)
        
        btn_int = ctk.CTkButton(parent, text="✨ Ajuste Inteligente", command=self.intelligent_auto_frame)
        btn_int.pack(fill="x", padx=10, pady=5)

        m_int = Menu(self.root, tearoff=0)
        m_int.add_command(label="Aplicar à Imagem Atual", command=self.intelligent_auto_frame)
        m_int.add_command(label="Aplicar a Todas", command=lambda: self.apply_adjustment_to_all(self.intelligent_auto_frame, "Ajuste Inteligente"))
        btn_int.bind("<Button-3>", lambda e: m_int.post(e.x_root, e.y_root))

        btn_fit = ctk.CTkButton(parent, text="🖼️ Preencher Borda", command=self.auto_fit_image)
        btn_fit.pack(fill="x", padx=10, pady=5)
        
        m_fit = Menu(self.root, tearoff=0)
        m_fit.add_command(label="Aplicar à Imagem Atual", command=self.auto_fit_image)
        m_fit.add_command(label="Aplicar a Todas", command=lambda: self.apply_adjustment_to_all(self.auto_fit_image, "Preenchimento"))
        btn_fit.bind("<Button-3>", lambda e: m_fit.post(e.x_root, e.y_root))

        ctk.CTkButton(parent, text="💾 Exportar/Upload (Ctrl+S)", fg_color="green", hover_color="darkgreen", command=self.show_save_menu).pack(fill="x", padx=10, pady=(15, 5))

    def create_border_section(self, parent):
        ctk.CTkLabel(parent, text="Borda:", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(fill="x", padx=10, pady=(5,5))

        display_names = [self.borda_names.get(b, b) for b in self.bordas]
        display_names.append("Cor Personalizada")
        if not display_names: display_names = ["Padrão"]

        self.border_combo = ctk.CTkOptionMenu(parent, variable=self.selected_borda, values=display_names, command=self.on_borda_global_selected)
        self.border_combo.pack(fill="x", padx=10, pady=5)
        
        self.custom_color_entry = ctk.CTkEntry(parent, placeholder_text="#FFFFFF")
        self.custom_color_entry.bind("<KeyRelease>", self.on_custom_color_change)
        
        self._toggle_custom_color_entry()

    def create_image_list_section(self, parent):
        # parent is now a tab frame, so we expand
        # list_frame = ctk.CTkFrame(parent, fg_color="transparent") # Not needed if parent is tab
        # list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        sb = tk.Scrollbar(parent, orient=tk.VERTICAL)
        
        # Use a contrasting bg for listbox based on probable theme? 
        # Hard to know theme color dynamically easily without private access.
        # Just stick to neutral gray.
        self.image_listbox = tk.Listbox(parent, bg="#252525", fg="#eeeeee", selectbackground="#1f538d",
                                        borderwidth=0, highlightthickness=0, yscrollcommand=sb.set,
                                        font=("Segoe UI", 11))
        sb.config(command=self.image_listbox.yview)
        
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.image_listbox.pack(side=tk.LEFT, fill="both", expand=True)

        self.image_listbox.bind("<<ListboxSelect>>", self.on_image_select)
        self.image_listbox.bind("<Button-3>", self.show_context_menu_image_list)
        self.image_listbox.bind("<Button-1>", self.start_drag)

    def create_tips_section(self, parent):
        t = "Dica: Shift+Arrastar para redimensionar.\nClique direito para mais opções."
        ctk.CTkLabel(parent, text=t, text_color="gray", wraplength=250, font=("Arial", 10)).pack(side=tk.BOTTOM, pady=10)

    # --- Logic ---

    def select_folder(self):
        last_dir = self.app_config.get('last_folder')
        start_dir = last_dir if last_dir and os.path.isdir(last_dir) else None
        folder = filedialog.askdirectory(initialdir=start_dir)
        if folder:
            self.app_config.set('last_folder', folder)
            self.app_config.save()
            self.load_images_from_folder(folder)

    def load_images_from_folder(self, folder):
        self.status_var.set("Carregando imagens...")
        self.root.update_idletasks()
        self.image_list = []
        self.image_listbox.delete(0, tk.END)
        self.images.clear()
        self.image_states.clear()
        self.individual_bordas.clear()
        self.image_access_order.clear()
        self.undo_stack.clear()

        paths = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(SUPPORTED_EXTENSIONS)]
        for p in paths:
            self.image_list.append(p)
            self.image_listbox.insert(tk.END, os.path.basename(p))

        if self.image_list:
            self.status_var.set(f"Carregadas {len(self.image_list)} imagens")
            self.load_image(0)
        else:
            self.original_image = None
            self.user_image = None
            self.update_canvas()
            self.status_var.set("Nenhuma imagem encontrada.")

    def _add_to_cache(self, path, image):
        if path in self.images:
            if path in self.image_access_order: self.image_access_order.remove(path)
            self.image_access_order.append(path)
            self.images[path] = image 
        else:
            if len(self.images) >= self.MAX_CACHE_SIZE:
                oldest = self.image_access_order.pop(0)
                if oldest in self.images:
                    self.images[oldest].close()
                    del self.images[oldest]
            self.images[path] = image
            self.image_access_order.append(path)

    def load_image(self, index, preserve_undo=False):
        if self.current_image_index is not None and self.current_image_index < len(self.image_list) and self.image_path:
            self.save_current_image_state()
            
        self.current_image_index = index
        self.image_path = self.image_list[index]
        
        try:
            if self.original_image: self.original_image.close()
            self.original_image = Image.open(self.image_path).convert("RGBA")
            
            if self.image_path in self.images:
                self.user_image = self.images[self.image_path].copy()
                if self.image_path in self.image_access_order: self.image_access_order.remove(self.image_path)
                self.image_access_order.append(self.image_path)
                
                if self.image_path in self.image_states:
                    state = self.image_states[self.image_path]
                    self.user_image_pos = state['pos']
                    self.user_image_size = state['size']
                else: 
                     cw = self.canvas.winfo_width() if self.canvas.winfo_width() > 1 else 800
                     ch = self.canvas.winfo_height() if self.canvas.winfo_height() > 1 else 600
                     self.user_image_pos = ((cw - self.user_image.width)//2, (ch - self.user_image.height)//2)
                     self.user_image_size = self.user_image.size

            elif self.image_path in self.image_states:
                state = self.image_states[self.image_path]
                self.user_image_size = state['size']
                self.user_image_pos = state['pos']
                self.user_image = self.original_image.resize(self.user_image_size, Image.LANCZOS)
                self._add_to_cache(self.image_path, self.user_image.copy())
                
            else:
                if self.user_image: self.user_image.close()
                self.user_image = ImageProcessor.resize_image(self.original_image, 400, 300)
                self.user_image_size = self.user_image.size
                cw = self.canvas.winfo_width() if self.canvas.winfo_width() > 1 else 800
                ch = self.canvas.winfo_height() if self.canvas.winfo_height() > 1 else 600
                self.user_image_pos = ((cw - self.user_image_size[0]) // 2, (ch - self.user_image_size[1]) // 2)
                self._add_to_cache(self.image_path, self.user_image.copy())

            self.update_canvas()
            self.image_listbox.selection_clear(0, tk.END)
            self.image_listbox.selection_set(index)
            self.image_listbox.see(index)
            self.status_var.set(f"Visualizando: {os.path.basename(self.image_path)}")
            
            if not preserve_undo: self.undo_stack = []
            self.save_state_for_undo()
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao carregar imagem: {e}")

    def save_current_image_state(self):
        if self.image_path and self.user_image:
             self._add_to_cache(self.image_path, self.user_image.copy())
             self.image_states[self.image_path] = {'pos': self.user_image_pos, 'size': self.user_image_size}

    def update_canvas(self, *_):
        self.canvas.delete("all")
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw <= 1 or ch <= 1: return
        
        # Match canvas bg with theme
        # bg_color = "#2b2b2b" # dark
        # self.canvas.config(bg=bg_color) 
        
        bx, by = (cw - BORDA_WIDTH)//2, (ch - BORDA_HEIGHT)//2
        self.borda_pos = (bx, by)
        
        b_name = self.individual_bordas.get(self.image_path, self.selected_borda.get())
        if b_name == "Cor Personalizada":
            b_hex = self.custom_borda_hex_individual.get(self.image_path, self.custom_borda_hex)
        else:
            b_hex = self.borda_hex.get(b_name, '#FFFFFF')

        self.canvas.create_rectangle(bx-5, by-5, bx+BORDA_WIDTH+5, by+BORDA_HEIGHT+5, outline="gray", dash=(4,4))
        
        if self.user_image:
            self.user_tk = ImageTk.PhotoImage(self.user_image)
            self.canvas.create_image(self.user_image_pos[0], self.user_image_pos[1], anchor=tk.NW, image=self.user_tk)

        self.canvas.create_rectangle(bx, by, bx+BORDA_WIDTH, by+BORDA_HEIGHT, outline=b_hex, width=3)


    def select_image(self, event):
        if self.user_image:
            x, y = self.user_image_pos
            w, h = self.user_image_size
            if x <= event.x <= x+w and y <= event.y <= y+h:
                self.selected_image = True
                self.start_x = event.x - x
                self.start_y = event.y - y
                self.save_state_for_undo()

    def move_image(self, event):
        if self.selected_image:
            self.user_image_pos = (event.x - self.start_x, event.y - self.start_y)
            self.update_canvas()

    def release_image(self, _):
        if self.selected_image:
            self.selected_image = False
            self.save_current_image_state()

    def resize_image_proportional(self, event):
        if self.selected_image and self.original_image:
            x, y = self.user_image_pos
            nw = event.x - x
            nh = event.y - y
            if nw < 10 or nh < 10: return
            
            ow, oh = self.original_image.size
            ratio = ow/oh
            
            if nw/ratio > nh:
                fh = max(20, int(nh))
                fw = max(int(fh*ratio), 20)
            else:
                fw = max(20, int(nw))
                fh = max(int(fw/ratio), 20)
                
            self.user_image = self.original_image.resize((fw, fh), Image.LANCZOS)
            self.user_image_size = (fw, fh)
            self.update_canvas()

    def zoom_image(self, event):
        if not self.user_image: return
        self.save_state_for_undo()
        factor = 1.1 if (event.num == 5 or event.delta < 0) else 1/1.1
        if event.num == 5 or event.delta < 0: factor = 1/1.1 
        else: factor = 1.1

        cw, ch = self.user_image_size
        nw, nh = int(cw*factor), int(ch*factor)
        if nw < 20 or nh < 20: return
        
        self.user_image = ImageProcessor.resize_image(self.user_image, nw, nh)
        scale = nw / self.original_image.width # Approximate
        self.user_image = self.original_image.resize((nw, nh), Image.LANCZOS)
        self.user_image_size = (nw, nh)
        
        cx = event.x - self.user_image_pos[0]
        cy = event.y - self.user_image_pos[1]
        ncx, ncy = cx*factor, cy*factor
        self.user_image_pos = (event.x - ncx, event.y - ncy)
        
        self.update_canvas()
        self.save_current_image_state()

    def save_state_for_undo(self):
        if self.user_image:
            self.undo_stack.append((self.user_image.copy(), self.user_image_pos, self.user_image_size))
            if len(self.undo_stack) > 20:
                old = self.undo_stack.pop(0)
                old[0].close()

    def undo(self, _=None):
        if self.undo_stack:
            # Pop the last state
            prev_img, prev_pos, prev_size = self.undo_stack.pop()
            
            # Close current user_image to free memory (if it exists and is distinct)
            # We don't close self.original_image here, just the modified user instance
            if self.user_image and self.user_image != prev_img:
                self.user_image.close()

            # Restore state
            self.user_image = prev_img
            self.user_image_pos = prev_pos
            self.user_image_size = prev_size
            
            # Update state cache and canvas
            self.save_current_image_state() # Updates the 'current' persistent state
            self.update_canvas()

    # --- Automated Features (Threaded) ---
    def intelligent_auto_frame(self):
        if not self.original_image: return
        face = ImageProcessor.detect_anime_face(self.original_image, self.face_cascade)
        if not face:
            self.auto_fit_image()
            return
            
        result = ImageProcessor.calculate_intelligent_frame_pos(self.original_image, face, self.borda_pos)
        if result:
            nw, nh, px, py = result
            self.user_image = self.original_image.resize((nw, nh), Image.LANCZOS)
            self.user_image_size = (nw, nh)
            self.user_image_pos = (px, py)
            self.update_canvas()
            self.save_current_image_state()

    def auto_fit_image(self):
        if not self.original_image: return
        result = ImageProcessor.calculate_auto_fit_pos(self.original_image, self.borda_pos)
        if result:
            nw, nh, px, py = result
            self.user_image = self.original_image.resize((nw, nh), Image.LANCZOS)
            self.user_image_size = (nw, nh)
            self.user_image_pos = (px, py)
            self.update_canvas()
            self.save_current_image_state()

    def apply_adjustment_to_all(self, func, name):
         if not self.image_list: return
         if not messagebox.askyesno("Confirmar", f"Aplicar '{name}' a todas as imagens?"): return
         
         popup = ProgressBarPopup(self.root, title=f"Processando {name}", maximum=len(self.image_list))
         
         def batch_task():
             for i, path in enumerate(self.image_list):
                 try:
                     temp_img = Image.open(path).convert("RGBA")
                     nw, nh, px, py = None, None, None, None
                     
                     if name == "Ajuste Inteligente":
                         face = ImageProcessor.detect_anime_face(temp_img, self.face_cascade)
                         if face:
                             res = ImageProcessor.calculate_intelligent_frame_pos(temp_img, face, self.borda_pos)
                             if res: nw, nh, px, py = res
                     
                     if not nw: 
                         res = ImageProcessor.calculate_auto_fit_pos(temp_img, self.borda_pos)
                         if res: nw, nh, px, py = res
                     
                     if nw and nh:
                         self.image_states[path] = {'pos': (px, py), 'size': (nw, nh)}
                     
                     temp_img.close()
                     self.root.after(0, lambda v=i+1, n=os.path.basename(path): popup.update_progress(v, f"Processando: {n}"))
                     
                 except Exception as e: print(e)
             
             self.root.after(0, finish_batch)

         def finish_batch():
             popup.close()
             self.load_image(self.current_image_index)
             messagebox.showinfo("Concluído", "Processamento em lote finalizado.")

         threading.Thread(target=batch_task, daemon=True).start()

    # --- Save & Upload ---
    def show_save_menu(self):
        m = Menu(self.root, tearoff=0)
        m.add_command(label="Salvar PNGs", command=self.save_all_images)
        m.add_command(label="Salvar ZIP", command=self.save_zip)
        m.add_command(label="Upload ImgChest", command=self.open_upload_window)
        m.post(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def _prepare_final_image(self, path):
        state = self.image_states.get(path)
        if not state: return None
        try:
             orig = Image.open(path).convert("RGBA")
             resized = orig.resize(state['size'], Image.LANCZOS)
             cropped = ImageProcessor.crop_image_to_borda(resized, state['pos'], state['size'], self.borda_pos)
             b_name = self.individual_bordas.get(path, self.selected_borda.get())
             if b_name == "Cor Personalizada":
                 b_hex = self.custom_borda_hex_individual.get(path, self.custom_borda_hex)
             else:
                 b_hex = self.borda_hex.get(b_name, '#FFFFFF')
             final = ImageProcessor.add_borda_to_image(cropped, b_hex)
             orig.close()
             return final
        except Exception: return None

    def save_all_images(self):
        d = filedialog.askdirectory()
        if not d: return
        for path in self.image_list:
            img = self._prepare_final_image(path)
            if img:
                out = os.path.join(d, os.path.splitext(os.path.basename(path))[0] + "_custom.png")
                img.save(out)
        messagebox.showinfo("Salvo", "Imagens salvas.")

    def save_zip(self):
        f = filedialog.asksaveasfilename(defaultextension=".zip")
        if not f: return
        with zipfile.ZipFile(f, 'w') as z:
            for path in self.image_list:
                img = self._prepare_final_image(path)
                if img:
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        img.save(tmp.name)
                        tmp_name = tmp.name
                    z.write(tmp_name, os.path.splitext(os.path.basename(path))[0] + "_custom.png")
                    os.unlink(tmp_name)
        messagebox.showinfo("Salvo", "ZIP salvo.")

    def open_upload_window(self):
        top = ctk.CTkToplevel(self.root)
        top.title("Upload ImgChest")
        top.attributes('-topmost', True)
        
        ctk.CTkLabel(top, text="Título do Álbum:").pack(pady=5, padx=10)
        e_title = ctk.CTkEntry(top)
        e_title.pack(pady=5, padx=10)
        
        def do_upload():
            title = e_title.get() or "CustomMaker"
            top.destroy()
            popup = ProgressBarPopup(self.root, title="Fiscalizando...", maximum=100)
            popup.progress.configure(mode='indeterminate')
            popup.progress.start()
            
            def upload_task():
                files = []
                tmp_dir = tempfile.mkdtemp()
                try:
                    for i, path in enumerate(self.image_list):
                        self.root.after(0, lambda v=i: popup.update_progress(0, f"Preparando {os.path.basename(path)}..."))
                        img = self._prepare_final_image(path)
                        if img:
                            fname = os.path.splitext(os.path.basename(path))[0] + "_custom.png"
                            fpath = os.path.join(tmp_dir, fname)
                            img.save(fpath)
                            files.append({'path': fpath, 'filename': fname})
                    
                    self.root.after(0, lambda: popup.update_progress(0, "Enviando..."))
                    links = self.uploader.upload_images(files, title)
                    self.root.after(0, lambda: finish(links, None))
                except Exception as e:
                    self.root.after(0, lambda: finish(None, str(e)))
                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)

            def finish(links, error):
                popup.close()
                if error: messagebox.showerror("Erro", f"{error}")
                elif links:
                    w = ctk.CTkToplevel(self.root)
                    w.title("Resultado Upload")
                    w.geometry("500x400")
                    
                    textbox = ctk.CTkTextbox(w, width=480, height=300)
                    textbox.pack(pady=10, padx=10)
                    textbox.insert("1.0", "\n".join(links))
                    
                    def copy_command():
                        cmd = f"$ai {title} $\n" + " $\n".join(links)
                        self.root.clipboard_clear()
                        self.root.clipboard_append(cmd)
                        self.root.update() # Required for clipboard
                        btn_copy.configure(text="Copiado!", fg_color="green")
                        w.after(2000, lambda: btn_copy.configure(text="Copiar Comando", fg_color=["#3a7ebf", "#1f538d"]))
                    
                    btn_copy = ctk.CTkButton(w, text="Copiar Comando", command=copy_command)
                    btn_copy.pack(pady=5)
            
            threading.Thread(target=upload_task, daemon=True).start()

        ctk.CTkButton(top, text="Upload", command=do_upload).pack(pady=10)

    # --- Utils ---
    def update_canvas_if_ready(self):
        if self.root.winfo_exists(): self.update_canvas()

    def on_custom_color_change(self, event=None):
        h = self.custom_color_entry.get()
        if len(h) == 7 and h.startswith("#"):
            self.custom_borda_hex = h
            if self.selected_borda.get() == "Cor Personalizada": self.update_canvas()

    def _toggle_custom_color_entry(self):
        if self.selected_borda.get() == "Cor Personalizada":
            self.custom_color_entry.pack(fill="x", padx=15, pady=5)
        else:
            self.custom_color_entry.pack_forget()

    def on_borda_global_selected(self, event):
        self._toggle_custom_color_entry()
        self.update_canvas()
        if self.image_path in self.individual_bordas:
            if messagebox.askyesno("Remover Individual", "Remover borda individual?"):
                del self.individual_bordas[self.image_path]
                self.update_canvas()
    
    def on_image_select(self, event):
        sel = self.image_listbox.curselection()
        if sel:
            idx = sel[0]
            if idx != self.current_image_index: self.load_image(idx)

    def create_context_menu_image_list(self):
        self.image_list_context_menu = Menu(self.root, tearoff=0)
        self.image_list_context_menu.add_command(label="Remover", command=self.remove_from_list)
        self.image_list_context_menu.add_command(label="Borda Individual", command=self.toggle_individual_borda)

    def show_context_menu_image_list(self, event):
        try:
            clicked_idx = self.image_listbox.nearest(event.y)
            self.image_listbox.selection_clear(0, tk.END)
            self.image_listbox.selection_set(clicked_idx)
            self.image_listbox.activate(clicked_idx)
            self.image_list_context_menu.post(event.x_root, event.y_root)
        except: pass
    
    def remove_from_list(self):
        sel = self.image_listbox.curselection()
        if not sel: return
        idx = sel[0]
        path = self.image_list.pop(idx)
        self.image_listbox.delete(idx)
        if path in self.images: del self.images[path]
        if path in self.image_states: del self.image_states[path]
        self.update_canvas()

    def toggle_individual_borda(self):
        sel = self.image_listbox.curselection()
        if not sel: return
        path = self.image_list[sel[0]]
        if path in self.individual_bordas: del self.individual_bordas[path]
        else: self.individual_bordas[path] = self.selected_borda.get()
        self.update_canvas()

    def start_drag(self, event): pass

    def on_canvas_configure(self, event):
        self.update_canvas_if_ready()
