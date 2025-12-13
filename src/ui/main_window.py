import os
import sys
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox, Menu # standard menu is still better for context menus usually, unless CTkOptionMenu replaces it totally
from PIL import Image, ImageTk, ImageOps, ImageGrab
import cssutils
import numpy as np
import zipfile
import tempfile
import threading
import shutil

# Internal imports
from src.config.settings import COLORS, BORDA_WIDTH, BORDA_HEIGHT, BORDA_HEX, BORDA_NAMES, SUPPORTED_EXTENSIONS, CSS_FILE, BORDER_THICKNESS
from src.utils.resource_loader import resource_path
# from src.ui.styles import configure_styles # Removed
from src.ui.widgets import Tooltip, ProgressBarPopup
from src.core.image_processor import ImageProcessor
from src.core.uploader import ImgChestUploader
from src.core.app_config import AppConfig
from src.ui.online_search import DanbooruSearchTab
from src.ui.online_search import DanbooruSearchTab
from src.core.animation_processor import AnimationProcessor
from src.controllers.batch_controller import BatchController
from src.core.preset_manager import PresetManager
from src.ui.toast import show_toast

class CustomMakerApp:
    def __init__(self, root, app_config):
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
        # Delay maximization to ensure it applies correctly after window mapping
        self.root.after(200, lambda: self.root.state('zoomed'))
        
        # Internal Logic
        self.app_config = app_config
        self.uploader = ImgChestUploader()
        self.face_cascade = ImageProcessor.load_face_cascade()
        self.batch_controller = BatchController(self)
        self.preset_manager = PresetManager()
        
        # Drag & Drop Registration
        try:
            self.root.drop_target_register('DND_Files')
            self.root.dnd_bind('<<Drop>>', self.on_drop_files)
        except Exception as e:
            print(f"DnD Init Warn: {e}")
        
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
        # Mode and Theme are already applied in main.py before window creation
        # to prevent startup flicker.

        self.after_id_init_canvas = self.root.after(100, self.update_canvas_if_ready)
        
        self.root.bind('<Control-z>', self.undo)
        self.root.bind('<Control-s>', lambda event: self.show_save_menu())
        self.root.bind('<Control-o>', lambda event: self.select_folder())
        self.root.bind('<Control-v>', self.paste_image)
        self.root.bind('<Alt-f>', lambda event: self.intelligent_auto_frame())
        self.root.bind('<Alt-b>', lambda event: self.auto_fit_image())
        
        # Rotation Shortcuts
        self.root.bind('<Control-q>', lambda event: self.rotate_image("left"))
        self.root.bind('<Control-e>', lambda event: self.rotate_image("right"))
        self.root.bind('<Control-Q>', lambda event: self.rotate_image("left"))
        self.root.bind('<Control-E>', lambda event: self.rotate_image("right"))

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
        self.hover_tooltip = None
        self.drag_data = {"item": None, "index": None}
        self.is_picking_color = False
        
        
        # Animation State
        self.animation_type = ctk.StringVar(value="Nenhuma")
        self.animation_running = False
        self.animation_hue = 0.0
        self.animation_pulse = 0.0 # For Neon
        self.animation_index = 0   # For Strobe
        self.animation_job = None

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
        self.right_frame.pack_propagate(False)

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
        self.canvas.bind("<Button-3>", self.show_canvas_context_menu)
        # Linux
        self.canvas.bind("<Button-4>", self.zoom_image)
        self.canvas.bind("<Button-5>", self.zoom_image)

    def create_right_panel(self):
        # self.right_frame uses pack, so no grid config needed here
        
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
        ctk.CTkFrame(self.tab_edit, height=2, fg_color="gray30").pack(fill="x", pady=10, padx=5)
        self.create_presets_section(self.tab_edit)
        
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

    def create_presets_section(self, parent):
        ctk.CTkLabel(parent, text="Presets:", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(fill="x", padx=10, pady=(10,5))
        
        # Save
        frame_save = ctk.CTkFrame(parent, fg_color="transparent")
        frame_save.pack(fill="x", padx=10, pady=5)
        
        self.preset_name_var = tk.StringVar()
        entry = ctk.CTkEntry(frame_save, textvariable=self.preset_name_var, placeholder_text="Nome do Preset", width=120)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        btn_save = ctk.CTkButton(frame_save, text="💾", width=30, command=self.save_current_preset, fg_color=COLORS['success'])
        btn_save.pack(side="right")
        Tooltip(btn_save, "Salvar Preset Atual")

        # Load/Delete
        frame_load = ctk.CTkFrame(parent, fg_color="transparent")
        frame_load.pack(fill="x", padx=10, pady=5)
        
        self.preset_menu_var = tk.StringVar(value="Selecione...")
        self.preset_menu = ctk.CTkOptionMenu(frame_load, variable=self.preset_menu_var, values=[], command=self.load_selected_preset)
        self.preset_menu.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        btn_del = ctk.CTkButton(frame_load, text="❌", width=30, command=self.delete_current_preset, fg_color=COLORS['danger'])
        btn_del.pack(side="right")
        Tooltip(btn_del, "Excluir Preset Selecionado")
        
        self.update_presets_menu()

    def update_presets_menu(self):
        presets = self.preset_manager.list_presets()
        if not presets:
            self.preset_menu.configure(values=["Vazio"])
            self.preset_menu_var.set("Vazio")
            self.preset_menu.configure(state="disabled")
        else:
            self.preset_menu.configure(state="normal")
            self.preset_menu.configure(values=presets)
            if self.preset_menu_var.get() not in presets:
                self.preset_menu_var.set("Selecione...")

    def save_current_preset(self):
        name = self.preset_name_var.get().strip()
        if not name:
            messagebox.showwarning("Aviso", "Digite um nome para o preset.")
            return
            
        data = {
            "border_name": self.selected_borda.get(),
            "border_color": self.custom_borda_hex, 
            "animation_type": self.animation_type.get(),
        }
        
        self.preset_manager.add_preset(name, data)
        self.update_presets_menu()
        self.preset_menu_var.set(name)
        show_toast(self.root, "Preset Salvo", f"Preset '{name}' salvo com sucesso!", "success")

    def load_selected_preset(self, name):
        data = self.preset_manager.get_preset(name)
        if not data: return
        
        if 'border_name' in data:
            self.selected_borda.set(data['border_name'])
            # Trigger handler to update UI (toggle entry, etc)
            self.on_borda_global_selected(None)
        
        if 'border_color' in data:
            h = data['border_color']
            self.custom_borda_hex = h
            # Update UI elements
            # self.btn_borda_color.configure(fg_color=h, text=h) # Button not present in this version
            self.custom_color_entry.delete(0, tk.END)
            self.custom_color_entry.insert(0, h)
            
            # If custom, ensure canvas updates with new color
            if self.selected_borda.get() == "Cor Personalizada":
                 self.update_canvas()

        if 'animation_type' in data:
            anim = data['animation_type']
            self.animation_type.set(anim)
            # Trigger handler to start/restart animation
            self.on_animation_change(anim)

    def delete_current_preset(self):
        name = self.preset_menu_var.get()
        if name and name != "Selecione..." and name != "Vazio":
            if messagebox.askyesno("Confirmar", f"Excluir preset '{name}'?"):
                self.preset_manager.delete_preset(name)
                self.update_presets_menu()
                self.preset_menu_var.set("Selecione...")

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
        
        self.btn_pick_color = ctk.CTkButton(parent, text="🎨 Pick Color", width=100, fg_color="#555555", hover_color="#666666", command=self.toggle_color_picker)
        self.btn_pick_color.pack(fill="x", padx=10, pady=(0, 5))

        ctk.CTkLabel(parent, text="Animação:", anchor="w").pack(fill="x", padx=10, pady=(5,0))
        self.anim_combo = ctk.CTkOptionMenu(parent, variable=self.animation_type, 
                                            values=["Nenhuma", "Rainbow", "Neon Pulsante", "Strobe (Pisca)", "Glitch", "Spin", "Flow"], 
                                            command=self.on_animation_change)
        self.anim_combo.pack(fill="x", padx=10, pady=5)

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

    def on_drop_files(self, event):
        files = event.data
        if not files: return
        
        # TkinterDnD returns a Tcl list string. root.tk.splitlist handles it correctly.
        try:
            paths = self.root.tk.splitlist(files)
        except Exception as e:
            print(f"DnD Parse Error: {e}")
            paths = [files]

        valid_images = []
        for p in paths:
            if os.path.isdir(p):
                 self.load_images_from_folder(p)
                 return # If folder, just load folder and stop
            elif os.path.isfile(p) and p.lower().endswith(SUPPORTED_EXTENSIONS):
                 valid_images.append(p)
        
        if valid_images:
            # Append or Replace? Let's Append if list exists, or Replace if user wants?
            # Current behavior is load folder replaces list. Let's make Drop replace list to match folder behavior roughly,
            # OR append if it's just files. Let's Append.
            # Actually, let's just add them.
            if not self.image_list: 
                self.image_list = []
                self.images.clear()
            
            for p in valid_images:
                if p not in self.image_list:
                    self.image_list.append(p)
                    self.image_listbox.insert(tk.END, os.path.basename(p))
            
            if len(valid_images) > 0 and self.current_image_index is None:
                self.load_image(0)
            
            self.status_var.set(f"Adicionadas {len(valid_images)} imagens via Drag & Drop.")

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
        self.preserve_undo_flag = preserve_undo
        
        # UI Feedback immediately
        self.canvas.delete("all")
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw > 1 and ch > 1:
            self.canvas.create_text(cw/2, ch/2, text="Carregando...", fill="white", font=("Arial", 16))
        
        self.image_listbox.selection_clear(0, tk.END)
        self.image_listbox.selection_set(index)
        self.image_listbox.see(index)
        
        threading.Thread(target=self._load_image_background, args=(index, self.image_path), daemon=True).start()

    def _load_image_background(self, index, path):
        try:
            # Heavy lifting here
            original = Image.open(path).convert("RGBA")
            
            # Prepare result dictionary
            result = {
                'index': index,
                'path': path,
                'original': original,
                'user_image': None,
                'pos': None,
                'size': None,
                'error': None
            }

            # Logic moved from synchronous load
            if path in self.images:
                 # Reuse cached
                 result['user_image'] = self.images[path].copy()
                 # Access order update should handle in main thread
                 
                 if path in self.image_states:
                     state = self.image_states[path]
                     result['pos'] = state['pos']
                     result['size'] = state['size']
                 else:
                     # Default center
                     # We might need canvas size here. 
                     # Ideally we pass canvas size to thread or just calc pos in main thread.
                     # Let's calc pos in main thread to assume safety, 
                     # OR pass dimensions.
                     result['calc_center'] = True # Signal to main thread to center
            
            elif path in self.image_states:
                state = self.image_states[path]
                result['size'] = state['size']
                result['pos'] = state['pos']
                result['user_image'] = original.resize(state['size'], Image.LANCZOS)
                result['add_to_cache'] = True
                
            else:
                 # Default new
                 # Resize logic
                 resized = ImageProcessor.resize_image(original, 400, 300)
                 result['user_image'] = resized
                 result['size'] = resized.size
                 result['calc_center'] = True
                 result['add_to_cache'] = True

            self.root.after(0, lambda: self._on_image_loaded(result))

        except Exception as e:
            self.root.after(0, lambda: self._on_image_loaded({'index': index, 'error': str(e)}))

    def paste_image(self, event=None):
        try:
            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image):
                # Save to temp
                temp_dir = os.path.join(tempfile.gettempdir(), "CustomMakerPaste")
                os.makedirs(temp_dir, exist_ok=True)
                
                # Unique name
                import time
                filename = f"pasted_{int(time.time())}.png"
                path = os.path.join(temp_dir, filename)
                img.save(path)
                
                # Load
                if not self.image_list: self.image_list = []
                # Check if already exists? Unlikely with timestamp
                self.image_list.append(path)
                self.image_listbox.insert(tk.END, filename)
                
                # Select it
                idx = len(self.image_list) - 1
                self.load_image(idx)
                
                self.status_var.set("Imagem colada da área de transferência.")
            else:
                self.status_var.set("Nenhuma imagem na área de transferência.")
        except Exception as e:
            print(f"Paste error: {e}")
            self.status_var.set("Erro ao colar imagem.")

    def _on_image_loaded(self, result):
        if result.get('error'):
             messagebox.showerror("Erro", f"Falha ao carregar: {result['error']}")
             return
             
        # Race condition check: did user switch image again?
        if result['index'] != self.current_image_index:
             # Discard this result, close images if opened
             if result.get('original'): result['original'].close()
             if result.get('user_image'): result['user_image'].close()
             return

        # Apply State
        if self.original_image: self.original_image.close()
        self.original_image = result['original']
        
        if self.user_image and self.user_image != result['user_image']: 
            self.user_image.close()
            
        self.user_image = result['user_image']
        
        if result.get('pos'): self.user_image_pos = result['pos']
        if result.get('size'): self.user_image_size = result['size']
        
        if result.get('calc_center'):
             cw = self.canvas.winfo_width() if self.canvas.winfo_width() > 1 else 800
             ch = self.canvas.winfo_height() if self.canvas.winfo_height() > 1 else 600
             if self.user_image:
                 self.user_image_pos = ((cw - self.user_image.width)//2, (ch - self.user_image.height)//2)
                 if result.get('pos') is None: self.user_image_pos = ((cw - self.user_image.width)//2, (ch - self.user_image.height)//2)

        if result.get('add_to_cache'):
             self._add_to_cache(result['path'], self.user_image.copy())
             
        # Update LRU
        if result['path'] in self.images:
             if result['path'] in self.image_access_order: self.image_access_order.remove(result['path'])
             self.image_access_order.append(result['path'])

        self.update_canvas()
        self.status_var.set(f"Visualizando: {os.path.basename(result['path'])}")
        
        if not self.preserve_undo_flag: self.undo_stack = []
        self.save_state_for_undo()

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

        self.canvas.create_rectangle(bx, by, bx+BORDA_WIDTH, by+BORDA_HEIGHT, outline=b_hex, width=BORDER_THICKNESS, tags="border_rect")

    def on_animation_change(self, choice):
        if choice == "Nenhuma":
            self.stop_preview_animation()
            self.update_canvas()
        else:
            self.stop_preview_animation() # Force restart to regen frames
            self.start_preview_animation()

    def start_preview_animation(self):
        if self.animation_running: return
        self.animation_running = True
        self.animation_hue = 0.0
        self.animation_pulse = 0.0
        self.animation_index = 0
        self.preview_frames = []
        self.preview_overlay_item = None
        
        # Start generation in background
        threading.Thread(target=self._generate_preview_frames_thread, daemon=True).start()
        
        self.animate_loop()

    def _generate_preview_frames_thread(self):
        try:
            anim_type = self.animation_type.get()
            
            # Determine color
            b_name = self.individual_bordas.get(self.image_path, self.selected_borda.get()) if self.image_path else self.selected_borda.get()
            if b_name == "Cor Personalizada":
                b_hex = self.custom_borda_hex_individual.get(self.image_path, self.custom_borda_hex) if self.image_path else self.custom_borda_hex
            else:
                b_hex = self.borda_hex.get(b_name, '#FFFFFF')
            
            # Generate frames with overlay_only=True
            # Size is fixed layout size
            size = (BORDA_WIDTH, BORDA_HEIGHT)
            
            frames, duration = [], 50
            if anim_type == "Rainbow":
                frames, duration = AnimationProcessor.generate_rainbow_frames(size, total_frames=40, border_width=BORDER_THICKNESS, overlay_only=True)
            elif anim_type == "Neon Pulsante":
                frames, duration = AnimationProcessor.generate_neon_frames(size, b_hex, total_frames=40, border_width=BORDER_THICKNESS, overlay_only=True)
            elif anim_type == "Strobe (Pisca)":
                frames, duration = AnimationProcessor.generate_strobe_frames(size, total_frames=10, border_width=BORDER_THICKNESS, overlay_only=True)
            elif anim_type == "Glitch":
                frames, duration = AnimationProcessor.generate_glitch_frames(size, total_frames=20, border_width=BORDER_THICKNESS, overlay_only=True)
            elif anim_type == "Spin":
                frames, duration = AnimationProcessor.generate_spin_frames(size, b_hex, total_frames=30, border_width=BORDER_THICKNESS, overlay_only=True)
            elif anim_type == "Flow":
                frames, duration = AnimationProcessor.generate_flow_frames(size, b_hex, total_frames=30, border_width=BORDER_THICKNESS, overlay_only=True)
            
            # Convert to ImageTk in thread? No, Tkinter objects must be created in main thread usually.
            # But ImageTk.PhotoImage can sometimes work if passed carefully, OR better: convert in loop.
            # Storing PIL images is safer.
            self.preview_frames = frames
            self.preview_duration = duration
            
        except Exception as e:
            print(f"Preview Gen Error: {e}")

    def stop_preview_animation(self):
        self.animation_running = False
        if self.animation_job:
            self.root.after_cancel(self.animation_job)
            self.animation_job = None
        self.canvas.delete("preview_overlay")
        # Ensure border rect is visible again if needed
        self.canvas.itemconfig("border_rect", state="normal")

    def animate_loop(self):
        if not self.animation_running: return
        
        delay = 50
        
        # If we have high-fi frames, use them
        if hasattr(self, 'preview_frames') and self.preview_frames:
            idx = self.animation_index % len(self.preview_frames)
            pil_frame = self.preview_frames[idx]
            
            # Convert to TK
            self.current_preview_tk = ImageTk.PhotoImage(pil_frame) # Keep ref
            
            bx, by = self.borda_pos
            
            # Update or create overlay
            self.canvas.delete("preview_overlay") # naive redraw
            self.canvas.create_image(bx, by, anchor=tk.NW, image=self.current_preview_tk, tags="preview_overlay")
            
            # Hide default border rect to avoid clash
            self.canvas.itemconfig("border_rect", state="hidden")
            
            self.animation_index += 1
            if hasattr(self, 'preview_duration'): delay = self.preview_duration

        else:
            # Fallback to simple simulation while loading
            anim_type = self.animation_type.get()
            hex_color = None
            
            # reuse simulated logic for loading state... or just simple pulse
            # ... (Simplified logic from before, truncated for brevity/cleanliness)
            # Actually, let's just do a simple "Loading" pulse using Neon logic
            self.animation_pulse += 0.2
            import math
            val = int(128 + 127 * math.sin(self.animation_pulse))
            hex_color = '#{:02x}{:02x}{:02x}'.format(val, val, val)
            self.canvas.itemconfig("border_rect", outline=hex_color, state="normal")
            
        self.animation_job = self.root.after(delay, self.animate_loop)
        # I'll modify update_canvas in another chunk to add tags.
        
        pass # Placeholder, see next chunk logic adjustments
        
    def select_image(self, event):
        if self.is_picking_color:
            self.pick_color_from_event(event)
            return

        if self.user_image:
            x, y = self.user_image_pos
            w, h = self.user_image_size
            if x <= event.x <= x+w and y <= event.y <= y+h:
                self.selected_image = True
                self.start_x = event.x - x
                self.start_y = event.y - y
                self.save_state_for_undo()

    def toggle_color_picker(self):
        self.is_picking_color = not self.is_picking_color
        if self.is_picking_color:
            self.canvas.configure(cursor="crosshair")
            self.btn_pick_color.configure(fg_color="#1f538d", text="Cancelar Pick")
            self.status_var.set("Modo Pick Color: Clique na imagem para copiar a cor.")
        else:
            self.canvas.configure(cursor="")
            self.btn_pick_color.configure(fg_color="#555555", text="🎨 Pick Color")
            self.status_var.set("Modo Pick Color desativado.")

    def pick_color_from_event(self, event):
        # Allow picking from anywhere on canvas, but let's prioritize image if user clicks it
        # Tkinter canvas doesn't easily give pixel color directly without taking a screenshot or knowing the source.
        # We rely on our known 'self.user_image' and 'self.user_image_pos'.
        
        color = None
        
        # Check against user image
        if self.user_image:
            ix, iy = self.user_image_pos
            iw, ih = self.user_image_size
            if ix <= event.x < ix + iw and iy <= event.y < iy + ih:
                # Inside image
                # Map to image coordinates
                rel_x = event.x - ix
                rel_y = event.y - iy
                
                # Careful with bounds
                rel_x = max(0, min(rel_x, iw-1))
                rel_y = max(0, min(rel_y, ih-1))
                
                try:
                    # Get pixel from the resized user_image currently displayed
                    # This matches what the user sees
                    rgb = self.user_image.getpixel((rel_x, rel_y))
                    if isinstance(rgb, int): # Grayscale?
                        color = '#{:02x}{:02x}{:02x}'.format(rgb, rgb, rgb)
                    else:
                        # Handle RGBA
                        if len(rgb) == 4:
                             r, g, b, a = rgb
                             # If transparent, maybe mix with bg? Or just ignore alpha?
                             # Let's just take RGB for now.
                             color = '#{:02x}{:02x}{:02x}'.format(r, g, b)
                        else:
                             r, g, b = rgb
                             color = '#{:02x}{:02x}{:02x}'.format(r, g, b)
                except: pass
        
        # If not on image, or failed, maybe we want to allow picking background?
        # For this requirement, user likely wants image colors.
        
        if color:
             self.root.clipboard_clear()
             self.root.clipboard_append(color)
             self.root.update()
             messagebox.showinfo("Pick Color", f"Cor copiada: {color}")
             self.toggle_color_picker() # Turn off
        else:
             self.status_var.set("Nenhuma cor detectada (Clique na imagem).")

    def move_image(self, event):
        if self.selected_image:
            self.user_image_pos = (event.x - self.start_x, event.y - self.start_y)
            self.update_canvas()

    def release_image(self, _):
        if self.selected_image:
            self.selected_image = False
            
            # Re-apply resize with High Quality (LANCZOS) on release
            if self.user_image and self.original_image:
                 w, h = self.user_image_size
                 # Only if size differs significantly or just always to be safe/consistent
                 # Since drag used NEAREST, we must re-do it.
                 self.user_image = self.original_image.resize((w, h), Image.LANCZOS)
                 self.update_canvas()

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
                
            self.user_image = self.original_image.resize((fw, fh), Image.NEAREST)
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

    def rotate_image(self, direction):
        if not self.original_image or not self.user_image: return
        
        angle = 90 if direction == "left" else -90
        
        self.save_state_for_undo()
        
        # Rotate original to maintain source of truth for subsequent resizes
        self.original_image = self.original_image.rotate(angle, expand=True)
        
        # Rotate user_image to match
        self.user_image = self.user_image.rotate(angle, expand=True)
        self.user_image_size = self.user_image.size
        
        # Adjust position slightly to center? Optional.
        # For now, let's keep the top-left corner or center logic?
        # A simple rotation around center of image is what `rotate` does, but `expand=True` changes dimensions.
        # Let's just update canvas. User can move it if needed.
        
        self.update_canvas()
        self.save_current_image_state()

    def show_canvas_context_menu(self, event):
        if not self.user_image: return
        menu = Menu(self.root, tearoff=0)
        menu.add_command(label="⟲ Rotacionar 90° Esquerda (Ctrl+Q)", command=lambda: self.rotate_image("left"))
        menu.add_command(label="⟳ Rotacionar 90° Direita (Ctrl+E)", command=lambda: self.rotate_image("right"))
        menu.post(event.x_root, event.y_root)

    # --- Automated Features (Threaded) ---
    def intelligent_auto_frame(self):
        if not self.original_image: return
        face = ImageProcessor.detect_anime_face(self.original_image, self.face_cascade)
        if face is None:
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
             show_toast(self.root, "Concluído", "Processamento em lote finalizado.", "success")

         threading.Thread(target=batch_task, daemon=True).start()

    # --- Save & Upload ---


    def show_save_menu(self):
        m = Menu(self.root, tearoff=0)
        m.add_command(label="Salvar PNGs", command=self.save_all_images)
        m.add_command(label="Salvar ZIP", command=self.save_zip)
        m.add_command(label="Upload ImgChest", command=self.open_upload_window)
        m.post(self.root.winfo_pointerx(), self.root.winfo_pointery())



    def save_all_images(self):
        d = filedialog.askdirectory()
        if not d: return
        
        popup = ProgressBarPopup(self.root, title="Salvando...", maximum=len(self.image_list))
        
        def on_progress(current, total, msg):
             popup.update_progress(current, msg)
             
        def on_finish():
             popup.close()
             show_toast(self.root, "Salvo", "Imagens salvas com sucesso.", "success")
             
        self.batch_controller.save_all_images(d, on_progress, on_finish)

    def save_zip(self):
        f = filedialog.asksaveasfilename(defaultextension=".zip")
        if not f: return
        
        popup = ProgressBarPopup(self.root, title="Salvando ZIP...", maximum=len(self.image_list))
        
        def on_progress(current, total, msg):
             popup.update_progress(current, msg)
             
        def on_finish():
             popup.close()
             show_toast(self.root, "Salvo", "ZIP salvo com sucesso.", "success")
        
        self.batch_controller.save_zip(f, on_progress, on_finish)

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
            
            def on_progress(current, total, msg):
                popup.update_progress(0, msg)
            
            def on_error(msg):
                popup.close()
                messagebox.showerror("Erro", f"{msg}")

            def on_finish(links):
                popup.close()
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
                    self.root.update() 
                    btn_copy.configure(text="Copiado!", fg_color="green")
                    w.after(2000, lambda: btn_copy.configure(text="Copiar Comando", fg_color=["#3a7ebf", "#1f538d"]))
                
                btn_copy = ctk.CTkButton(w, text="Copiar Comando", command=copy_command)
                btn_copy.pack(pady=5)
            
            self.batch_controller.upload_to_imgchest(title, on_progress, on_finish, on_error)

        ctk.CTkButton(top, text="Upload", command=do_upload).pack(pady=10)

    # --- Utils ---
    def update_canvas_if_ready(self):
        if self.root.winfo_exists(): self.update_canvas()

    def on_custom_color_change(self, event=None):
        h = self.custom_color_entry.get()
        if len(h) == 7 and h.startswith("#"):
            self.custom_borda_hex = h
            if self.selected_borda.get() == "Cor Personalizada": 
                self.update_canvas()
                if self.animation_running: 
                    self.stop_preview_animation()
                    self.start_preview_animation()

    def _toggle_custom_color_entry(self):
        if self.selected_borda.get() == "Cor Personalizada":
            self.custom_color_entry.pack(fill="x", padx=15, pady=5)
        else:
            self.custom_color_entry.pack_forget()

    def on_borda_global_selected(self, event):
        self._toggle_custom_color_entry()
        self.update_canvas()
        if self.animation_running: 
            self.stop_preview_animation()
            self.start_preview_animation()
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
