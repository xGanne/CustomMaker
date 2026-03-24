import os
import sys
import logging
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox, Menu # standard menu is still better for context menus usually, unless CTkOptionMenu replaces it totally
from PIL import Image, ImageTk, ImageGrab
import cssutils
import tempfile

# Internal imports
from src.config.settings import BORDA_WIDTH, BORDA_HEIGHT, BORDA_HEX, BORDA_NAMES, SUPPORTED_EXTENSIONS, CSS_FILE, BORDER_THICKNESS
from src.utils.resource_loader import resource_path
# from src.ui.styles import configure_styles # Removed
from src.ui.widgets import (
    ActionButtonPrimary,
    ActionButtonSecondary,
    InlineHint,
    ProgressBarPopup,
    SectionCard,
    Tooltip,
)
from src.ui.theme import (
    ACCENT,
    ACCENT_HOVER,
    FONT_BODY,
    FONT_CAPTION,
    FONT_TITLE,
    SURFACE_BG,
    SURFACE_ELEVATED,
    SURFACE_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    button_style,
    card_style,
    input_style,
)
from src.core.image_processor import ImageProcessor
from src.core.uploader import ImgChestUploader
from src.ui.online_search import DanbooruSearchTab
from src.core.animation_processor import AnimationProcessor
from src.controllers.batch_controller import BatchController
from src.core.preset_manager import PresetManager
from src.core.task_runner import TaskRunner
from src.ui.toast import show_toast
from src.ui.ai_tab import AITab


logger = logging.getLogger(__name__)


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
        except Exception as exc:
            logger.warning("Falha ao configurar ícone da aplicação: %s", exc)

        self.root.geometry("1400x900")
        # Delay maximization to ensure it applies correctly after window mapping
        self.root.after(200, self._apply_initial_window_layout)
        
        # Internal Logic
        self.app_config = app_config
        self.uploader = ImgChestUploader()
        self.face_cascade = ImageProcessor.load_face_cascade()
        self.batch_controller = BatchController(self)
        self.task_runner = TaskRunner()
        self.preset_manager = PresetManager()
        
        # Drag & Drop Registration
        try:
            self.root.drop_target_register('DND_Files')
            self.root.dnd_bind('<<Drop>>', self.on_drop_files)
        except Exception as exc:
            logger.warning("Drag & Drop desativado: %s", exc)
        
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

    def _apply_initial_window_layout(self):
        try:
            self.root.state("zoomed")
        except Exception as exc:
            logger.debug("Falha ao aplicar estado inicial maximizado: %s", exc)
        self._schedule_edit_tab_layout_refresh()

    def initialize_state_variables(self):
        self.image_path = None
        self.original_image = None
        self.user_image = None
        self.user_image_pos = (50, 50)
        self.user_image_size = None
        self.selected_image = False
        self.start_x = 0
        self.start_y = 0
        self.status_var = ctk.StringVar(value="Sem imagens. Selecione uma pasta para começar.")
        self.selected_borda = ctk.StringVar(value="White")
        
        # Memory Optimization (cache por MB)
        self.image_cache_limit_bytes = self._resolve_image_cache_limit_bytes()
        self.image_cache_current_bytes = 0
        self.images = {}
        self.image_cache_sizes = {}
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
        self.preview_frames = []
        self.preview_duration = 50
        self.current_preview_tk = None
        self._image_load_seq = 0
        self._active_image_load_task_id = None
        self._preview_seq = 0
        self._active_preview_task_id = None

    def _resolve_image_cache_limit_bytes(self):
        configured_mb = self.app_config.get("image_cache_max_mb", 256)
        try:
            cache_mb = float(configured_mb)
        except (TypeError, ValueError):
            cache_mb = 256
        cache_mb = max(32.0, min(8192.0, cache_mb))
        return int(cache_mb * 1024 * 1024)

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
        except Exception as exc:
            logger.warning("Falha ao carregar bordas de %s: %s", CSS_FILE, exc)
            return []

    def on_closing(self):
        self.app_config.set('last_global_borda', self.selected_borda.get())
        if self.image_list and os.path.dirname(self.image_list[0]):
             self.app_config.set('last_folder', os.path.dirname(self.image_list[0]))
        
        # Save appearance settings
        self.app_config.set('appearance_mode', ctk.get_appearance_mode())
        # self.app_config.set('color_theme', ...) # We don't have a simple getter for current theme name from CTk
        
        self.app_config.save()
        
        if messagebox.askokcancel("Sair", "Deseja sair?"):
            self.stop_preview_animation()
            if self._active_image_load_task_id and self.task_runner.is_running(self._active_image_load_task_id):
                self.task_runner.cancel(self._active_image_load_task_id)
            self.close_resources()
            self.root.destroy()
            sys.exit(0)

    def close_resources(self):
        if self.original_image:
            self.original_image.close()
        if self.user_image:
            self.user_image.close()
        self._clear_image_cache()
        if hasattr(self, "danbooru_tab"):
            try:
                self.danbooru_tab.close()
            except Exception as exc:
                logger.debug("Falha ao encerrar recursos da aba Online: %s", exc)
        self.undo_stack.clear()

    # --- UI Creation ---
    def create_widgets(self):
        self.create_layout_frames()
        self.setup_canvas_events()
        
        # Status Bar
        self.status_bar = ctk.CTkLabel(
            self.left_frame,
            textvariable=self.status_var,
            anchor="w",
            height=30,
            text_color=TEXT_SECONDARY,
            fg_color=SURFACE_ELEVATED,
            corner_radius=8,
            font=FONT_BODY,
        )
        self.status_bar.pack(side=tk.BOTTOM, fill="x", pady=(8, 5), padx=5)
        
        self.create_right_panel()

    def create_layout_frames(self):
        self.root.configure(fg_color=SURFACE_BG)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=0)
        self.root.grid_rowconfigure(0, weight=1)

        self.left_frame = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        self.right_frame = ctk.CTkFrame(self.root, width=360, **card_style("root"))
        self.right_frame.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.right_frame.pack_propagate(False)

        # Canvas Frame
        self.canvas_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.canvas_frame.pack(fill="both", expand=True)
        
        # Canvas (Standard TKinter Canvas is best for drawing)
        self.canvas = tk.Canvas(self.canvas_frame, bg=SURFACE_BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

    @staticmethod
    def _style_entry(widget):
        widget.configure(**input_style())

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
        
        ctk.CTkLabel(self.right_frame, text="CustomMaker Pro", font=FONT_TITLE, text_color=TEXT_PRIMARY).pack(pady=(16, 4))
        InlineHint(self.right_frame, text="Fluxo rapido: Selecionar Pasta -> Ajustar -> Exportar/Upload", justify="center").pack(
            fill="x", padx=14, pady=(0, 8)
        )

        # Use Tabview for better organization
        self.tabview = ctk.CTkTabview(self.right_frame, width=280)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        self.tabview.configure(
            fg_color="transparent",
            segmented_button_fg_color=SURFACE_MUTED,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_HOVER,
            segmented_button_unselected_hover_color="#364059",
            text_color=TEXT_PRIMARY,
        )
        
        self.tab_edit = self.tabview.add("Edição")
        self.tab_settings = self.tabview.add("Ajustes")
        self.tab_online = self.tabview.add("Online")
        self.tab_ai = self.tabview.add("AI")
        self.tab_edit_scroll = ctk.CTkScrollableFrame(self.tab_edit, fg_color="transparent")
        self.tab_edit_scroll.pack(fill="both", expand=True)
        self.tab_edit.bind("<Visibility>", lambda _e: self._schedule_edit_tab_layout_refresh())
        
        # --- Tab Edicao ---
        self.create_file_section(self.tab_edit_scroll)
        self.create_border_section(self.tab_edit_scroll)
        self.create_presets_section(self.tab_edit_scroll)
        
        # --- Tab Ajustes ---
        self.create_settings_section(self.tab_settings)

        # --- Tab Online ---
        self.danbooru_tab = DanbooruSearchTab(self.tab_online, self)

        # --- Tab AI ---
        self.ai_tab = AITab(self.tab_ai, self)

        # Image List (Outside tabs, always visible or inside Edit?)
        # Let's put Image List below Tabs or inside "Edição" but it might be cramped.
        # Actually, Image List is core. Let's put it back in the main right frame, BELOW the tabview? 
        # "Lista" is shorter than "Lista de Imagens"
        self.tab_list = self.tabview.add("Lista")
        self.create_image_list_section(self.tab_list)
        
        self.create_tips_section(self.right_frame)
        self.create_context_menu_image_list()
        self._schedule_edit_tab_layout_refresh()

    def _schedule_edit_tab_layout_refresh(self):
        if not hasattr(self, "tab_edit_scroll"):
            return
        for delay in (0, 80, 220):
            self.root.after(delay, self._refresh_edit_tab_layout)

    def _refresh_edit_tab_layout(self):
        if not hasattr(self, "tab_edit_scroll"):
            return
        try:
            self.tab_edit_scroll.update_idletasks()
            self.tab_edit_scroll._fit_frame_dimensions_to_canvas(None)
            canvas = self.tab_edit_scroll._parent_canvas
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.xview_moveto(0.0)
        except Exception as exc:
            logger.debug("Nao foi possivel atualizar layout da aba Edicao: %s", exc)

    def create_presets_section(self, parent):
        card = SectionCard(parent, title="Presets", subtitle="Salve e reutilize combinacoes de borda/animacao.")
        card.pack(fill="x", padx=10, pady=(8, 6))
        
        # Save
        frame_save = ctk.CTkFrame(card.body, fg_color="transparent")
        frame_save.pack(fill="x", pady=5)
        
        self.preset_name_var = tk.StringVar()
        entry = ctk.CTkEntry(frame_save, textvariable=self.preset_name_var, placeholder_text="Nome do Preset", width=120)
        self._style_entry(entry)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        btn_save = ActionButtonSecondary(frame_save, text="Salvar", width=78, command=self.save_current_preset, kind="success")
        btn_save.pack(side="right")
        Tooltip(btn_save, "Salvar Preset Atual")

        # Load/Delete
        frame_load = ctk.CTkFrame(card.body, fg_color="transparent")
        frame_load.pack(fill="x", pady=5)
        
        self.preset_menu_var = tk.StringVar(value="Selecione...")
        self.preset_menu = ctk.CTkOptionMenu(frame_load, variable=self.preset_menu_var, values=[], command=self.load_selected_preset)
        self._style_option_menu(self.preset_menu)
        self.preset_menu.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        btn_del = ActionButtonSecondary(frame_load, text="Excluir", width=78, command=self.delete_current_preset, kind="danger")
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
        card = SectionCard(parent, title="Aparencia", subtitle="Preferencias visuais do aplicativo.")
        card.pack(fill="x", padx=10, pady=(10, 6))
        
        ctk.CTkLabel(card.body, text="Tema (Claro/Escuro):", anchor="w", text_color=TEXT_PRIMARY, font=FONT_BODY).pack(fill="x", pady=2)
        self.appearance_mode_optionemenu = ctk.CTkOptionMenu(card.body, values=["Light", "Dark", "System"],
                                                               command=self.change_appearance_mode_event)
        self._style_option_menu(self.appearance_mode_optionemenu)
        self.appearance_mode_optionemenu.pack(fill="x", pady=5)
        self.appearance_mode_optionemenu.set(self.app_config.get('appearance_mode', 'Dark'))

        ctk.CTkLabel(card.body, text="Cor de Destaque (Reiniciar):", anchor="w", text_color=TEXT_PRIMARY, font=FONT_BODY).pack(fill="x", pady=2)
        self.color_theme_optionemenu = ctk.CTkOptionMenu(card.body, values=["blue", "green", "dark-blue"],
                                                            command=self.change_color_theme_event)
        self._style_option_menu(self.color_theme_optionemenu)
        self.color_theme_optionemenu.pack(fill="x", pady=5)
        self.color_theme_optionemenu.set(self.app_config.get('color_theme', 'blue'))

    def change_appearance_mode_event(self, new_appearance_mode: str):
        ctk.set_appearance_mode(new_appearance_mode)
        
    def change_color_theme_event(self, new_color_theme: str):
        # Theme change usually requires restart or manual widget update for complex apps
        self.app_config.set('color_theme', new_color_theme)
        self.app_config.save()
        messagebox.showinfo("Tema", "A alteração da cor de destaque será aplicada na próxima reinicialização.")

    def create_file_section(self, parent):
        card = SectionCard(
            parent,
            title="Arquivo e Fluxo",
            subtitle="1) Importe as imagens  2) Ajuste enquadramento\n3) Exporte/Upload",
        )
        card.pack(fill="x", padx=10, pady=(10, 6))

        btn_open = ActionButtonSecondary(card.body, text="Selecionar Pasta (Ctrl+O)", command=self.select_folder)
        btn_open.pack(fill="x", pady=4)
        
        btn_int = ActionButtonSecondary(card.body, text="Ajuste Inteligente", command=self.intelligent_auto_frame)
        btn_int.pack(fill="x", pady=4)

        m_int = Menu(self.root, tearoff=0)
        m_int.add_command(label="Aplicar à Imagem Atual", command=self.intelligent_auto_frame)
        m_int.add_command(label="Aplicar a Todas", command=lambda: self.apply_adjustment_to_all(self.intelligent_auto_frame, "Ajuste Inteligente"))
        btn_int.bind("<Button-3>", lambda e: m_int.post(e.x_root, e.y_root))

        btn_fit = ActionButtonSecondary(card.body, text="Ajustar/Preencher Borda", command=self.auto_fit_image)
        btn_fit.pack(fill="x", pady=4)
        
        m_fit = Menu(self.root, tearoff=0)
        m_fit.add_command(label="Aplicar à Imagem Atual", command=self.auto_fit_image)
        m_fit.add_command(label="Aplicar a Todas", command=lambda: self.apply_adjustment_to_all(self.auto_fit_image, "Preenchimento"))
        btn_fit.bind("<Button-3>", lambda e: m_fit.post(e.x_root, e.y_root))

        ActionButtonPrimary(card.body, text="Exportar/Upload (Ctrl+S)", command=self.show_save_menu).pack(fill="x", pady=(10, 2))

    def create_border_section(self, parent):
        card = SectionCard(parent, title="Borda e Animacao", subtitle="Defina a cor da borda e os efeitos visuais.")
        card.pack(fill="x", padx=10, pady=(6, 6))

        ctk.CTkLabel(card.body, text="Cor da Borda:", font=FONT_BODY, text_color=TEXT_PRIMARY, anchor="w").pack(fill="x", pady=(0, 4))

        display_names = [self.borda_names.get(b, b) for b in self.bordas]
        display_names.append("Cor Personalizada")
        if not display_names: display_names = ["Padrão"]

        self.border_combo = ctk.CTkOptionMenu(card.body, variable=self.selected_borda, values=display_names, command=self.on_borda_global_selected)
        self._style_option_menu(self.border_combo)
        self.border_combo.pack(fill="x", pady=(0, 6))
        
        self.custom_color_entry = ctk.CTkEntry(card.body, placeholder_text="#FFFFFF")
        self._style_entry(self.custom_color_entry)
        self.custom_color_entry.bind("<KeyRelease>", self.on_custom_color_change)
        
        self.btn_pick_color = ActionButtonSecondary(card.body, text="Pick Color", command=self.toggle_color_picker)
        self.btn_pick_color.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(card.body, text="Animacao:", anchor="w", text_color=TEXT_PRIMARY, font=FONT_BODY).pack(fill="x", pady=(0, 4))
        self.anim_combo = ctk.CTkOptionMenu(card.body, variable=self.animation_type, 
                                            values=["Nenhuma", "Rainbow", "Neon Pulsante", "Strobe (Pisca)", "Glitch", "Spin", "Flow"], 
                                            command=self.on_animation_change)
        self._style_option_menu(self.anim_combo)
        self.anim_combo.pack(fill="x")

        self._toggle_custom_color_entry()

    def create_image_list_section(self, parent):
        card = SectionCard(parent, title="Lista de Imagens", subtitle="Gerencie as imagens carregadas para edicao.")
        card.pack(fill="both", expand=True, padx=10, pady=(10, 6))

        toolbar = ctk.CTkFrame(card.body, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 8))

        actions = ctk.CTkFrame(toolbar, fg_color="transparent")
        actions.pack(fill="x")
        actions.grid_columnconfigure((0, 1), weight=1)

        ActionButtonSecondary(actions, text="Carregar Pasta", command=self.select_folder).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ActionButtonSecondary(actions, text="Remover Selecao", command=self.remove_from_list).grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ActionButtonSecondary(actions, text="Limpar Lista", command=self.clear_image_list, kind="danger").grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=(0, 0), pady=(6, 0)
        )

        self.list_count_label = ctk.CTkLabel(toolbar, text="0 imagens", font=FONT_CAPTION, text_color=TEXT_SECONDARY)
        self.list_count_label.pack(fill="x", pady=(6, 0), anchor="e")

        list_wrap = ctk.CTkFrame(card.body, fg_color=SURFACE_MUTED, corner_radius=8, border_width=1, border_color="#3A465D")
        list_wrap.pack(fill="both", expand=True)

        sb = tk.Scrollbar(list_wrap, orient=tk.VERTICAL)
        self.image_listbox = tk.Listbox(list_wrap, bg="#252b38", fg="#e8edf7", selectbackground="#2F8CFF",
                                        borderwidth=0, highlightthickness=0, yscrollcommand=sb.set,
                                        font=("Segoe UI", 11))
        sb.config(command=self.image_listbox.yview)
        
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.image_listbox.pack(side=tk.LEFT, fill="both", expand=True)

        self.image_listbox.bind("<<ListboxSelect>>", self.on_image_select)
        self.image_listbox.bind("<Button-3>", self.show_context_menu_image_list)
        self.image_listbox.bind("<Button-1>", self.start_drag)

        self.list_empty_hint = InlineHint(
            list_wrap,
            text="Sem imagens carregadas.\nUse 'Carregar Pasta' ou arraste arquivos para o app.",
            justify="center",
            wraplength=220,
            text_color=TEXT_SECONDARY,
        )
        self.list_empty_hint.place(relx=0.5, rely=0.5, anchor="center")
        self.list_empty_hint.lift()
        self.refresh_list_empty_state()
        self.update_list_counter()

    def create_tips_section(self, parent):
        if not self.app_config.get("ui_show_tips", True):
            return
        t = "Dica: Shift+Arrastar para redimensionar.\nClique direito para mais opções."
        InlineHint(parent, text=t, justify="center", wraplength=290).pack(side=tk.BOTTOM, pady=10, padx=10)

    # --- Logic ---
    def update_list_counter(self):
        if hasattr(self, "list_count_label"):
            total = len(self.image_list)
            label = "imagem" if total == 1 else "imagens"
            self.list_count_label.configure(text=f"{total} {label}")

    def refresh_list_empty_state(self):
        if hasattr(self, "list_empty_hint"):
            if self.image_list:
                self.list_empty_hint.place_forget()
            else:
                self.list_empty_hint.place(relx=0.5, rely=0.5, anchor="center")

    def _reset_loaded_images_state(self):
        if self._active_image_load_task_id and self.task_runner.is_running(self._active_image_load_task_id):
            self.task_runner.cancel(self._active_image_load_task_id)
        self._active_image_load_task_id = None
        self.current_image_index = None
        self.image_path = None
        self.image_list = []
        if hasattr(self, "image_listbox"):
            self.image_listbox.delete(0, tk.END)
        self._clear_image_cache()
        self.image_states.clear()
        self.individual_bordas.clear()
        self.custom_borda_hex_individual.clear()
        self.undo_stack.clear()
        if self.original_image:
            self.original_image.close()
            self.original_image = None
        if self.user_image:
            self.user_image.close()
            self.user_image = None
        self.update_canvas()
        self.refresh_list_empty_state()
        self.update_list_counter()

    def clear_image_list(self):
        if not self.image_list:
            self.status_var.set("Sem imagens carregadas.")
            return
        if not messagebox.askyesno("Limpar Lista", "Remover todas as imagens da lista atual?"):
            return
        self._reset_loaded_images_state()
        self.status_var.set("Lista limpa. Selecione uma pasta para continuar.")

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
        except Exception as exc:
            logger.warning("Falha ao interpretar dados de drag & drop: %s", exc)
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
                self._clear_image_cache()
            
            for p in valid_images:
                if p not in self.image_list:
                    self.image_list.append(p)
                    self.image_listbox.insert(tk.END, os.path.basename(p))
            
            if len(valid_images) > 0 and self.current_image_index is None:
                self.load_image(0)
            
            self.refresh_list_empty_state()
            self.update_list_counter()
            self.status_var.set(f"{len(valid_images)} imagem(ns) adicionada(s) via arrastar e soltar.")

    def load_images_from_folder(self, folder):
        self.status_var.set("Carregando imagens...")
        self.root.update_idletasks()
        self._reset_loaded_images_state()

        paths = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(SUPPORTED_EXTENSIONS)]
        for p in paths:
            self.image_list.append(p)
            self.image_listbox.insert(tk.END, os.path.basename(p))

        self.refresh_list_empty_state()
        self.update_list_counter()

        if self.image_list:
            self.status_var.set(f"{len(self.image_list)} imagem(ns) carregada(s).")
            self.load_image(0)
        else:
            self.original_image = None
            self.user_image = None
            self.update_canvas()
            self.status_var.set("Sem imagens nesta pasta.")

    @staticmethod
    def _estimate_image_bytes(image):
        if image is None:
            return 0
        try:
            channels = len(image.getbands())
        except Exception:
            channels = 4
        return max(1, image.width * image.height * channels)

    def _touch_image_cache_entry(self, path):
        if path in self.image_access_order:
            self.image_access_order.remove(path)
        self.image_access_order.append(path)

    def _remove_from_cache(self, path, close_image=True, reason="manual"):
        img = self.images.pop(path, None)
        size = self.image_cache_sizes.pop(path, 0)
        self.image_cache_current_bytes = max(0, self.image_cache_current_bytes - size)
        if path in self.image_access_order:
            self.image_access_order.remove(path)
        if close_image and img:
            try:
                img.close()
            except Exception as exc:
                logger.debug("Falha ao fechar imagem removida do cache (%s): %s", path, exc)
        if size:
            logger.debug("Evicted image cache entry (%s): %s bytes reason=%s", path, size, reason)
        return img

    def _evict_cache_to_limit(self):
        while self.image_cache_current_bytes > self.image_cache_limit_bytes and self.image_access_order:
            oldest = self.image_access_order[0]
            self._remove_from_cache(oldest, close_image=True, reason="memory_limit")

    def _clear_image_cache(self):
        for path in list(self.images.keys()):
            self._remove_from_cache(path, close_image=True, reason="clear")
        self.images.clear()
        self.image_cache_sizes.clear()
        self.image_access_order.clear()
        self.image_cache_current_bytes = 0

    def _add_to_cache(self, path, image):
        if not path or image is None:
            return

        if path in self.images:
            self._remove_from_cache(path, close_image=True, reason="replace")

        self.images[path] = image
        entry_size = self._estimate_image_bytes(image)
        self.image_cache_sizes[path] = entry_size
        self.image_cache_current_bytes += entry_size
        self._touch_image_cache_entry(path)
        self._evict_cache_to_limit()

    def load_image(self, index, preserve_undo=False):
        if not self.image_list:
            return
        if index < 0 or index >= len(self.image_list):
            logger.warning("Indice de imagem invalido: %s (total=%s)", index, len(self.image_list))
            return

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
        
        self._start_image_load_task(index, self.image_path)

    def _start_image_load_task(self, index, path):
        if self._active_image_load_task_id and self.task_runner.is_running(self._active_image_load_task_id):
            self.task_runner.cancel(self._active_image_load_task_id)

        self._image_load_seq += 1
        task_id = f"load_image_{self._image_load_seq}"
        self._active_image_load_task_id = task_id

        def task_fn(cancel_event, _on_progress):
            result = self._build_image_load_result(index, path, cancel_event)
            result["task_id"] = task_id
            return result

        def on_done(result):
            def apply_result():
                if result.get("task_id") != self._active_image_load_task_id:
                    self._dispose_loaded_result(result)
                    return
                self._active_image_load_task_id = None
                self._on_image_loaded(result)

            self.root.after(0, apply_result)

        def on_error(exc):
            self.root.after(
                0,
                lambda: self._on_image_loaded(
                    {"index": index, "path": path, "task_id": task_id, "error": str(exc)}
                ),
            )

        started = self.task_runner.submit(task_id, task_fn, on_done=on_done, on_error=on_error)
        if not started:
            self._active_image_load_task_id = None
            self._on_image_loaded({"index": index, "path": path, "error": "Falha ao iniciar carregamento."})

    def _build_image_load_result(self, index, path, cancel_event):
        original = None
        result = None
        try:
            if cancel_event and cancel_event.is_set():
                return {"cancelled": True, "index": index, "path": path}

            original = Image.open(path).convert("RGBA")
            result = {
                "index": index,
                "path": path,
                "original": original,
                "user_image": None,
                "pos": None,
                "size": None,
                "error": None,
                "calc_center": False,
                "add_to_cache": False,
            }

            if cancel_event and cancel_event.is_set():
                self._dispose_loaded_result(result)
                return {"cancelled": True, "index": index, "path": path}

            if path in self.images:
                result["user_image"] = self.images[path].copy()
                if path in self.image_states:
                    state = self.image_states[path]
                    result["pos"] = state["pos"]
                    result["size"] = state["size"]
                else:
                    result["calc_center"] = True
            elif path in self.image_states:
                state = self.image_states[path]
                result["size"] = state["size"]
                result["pos"] = state["pos"]
                result["user_image"] = original.resize(state["size"], Image.LANCZOS)
                result["add_to_cache"] = True
            else:
                resized = ImageProcessor.resize_image(original, 400, 300)
                result["user_image"] = resized
                result["size"] = resized.size
                result["calc_center"] = True
                result["add_to_cache"] = True

            if cancel_event and cancel_event.is_set():
                self._dispose_loaded_result(result)
                return {"cancelled": True, "index": index, "path": path}

            return result
        except Exception as exc:
            if result:
                self._dispose_loaded_result(result)
            elif original:
                try:
                    original.close()
                except Exception:
                    pass
            logger.exception("Falha ao carregar imagem em background (%s): %s", path, exc)
            return {"index": index, "path": path, "error": str(exc)}

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
                self.refresh_list_empty_state()
                self.update_list_counter()
                
                # Select it
                idx = len(self.image_list) - 1
                self.load_image(idx)
                
                self.status_var.set("Imagem colada da área de transferência.")
            else:
                self.status_var.set("Nenhuma imagem na área de transferência.")
        except Exception as exc:
            logger.exception("Erro ao colar imagem da área de transferência: %s", exc)
            self.status_var.set("Erro ao colar imagem.")

    def _on_image_loaded(self, result):
        if result.get("cancelled"):
            return
        if result.get("error"):
            messagebox.showerror("Erro", f"Falha ao carregar: {result['error']}")
            return
              
        # Race condition check: did user switch image again?
        if result.get("index") != self.current_image_index or result.get("path") != self.image_path:
            self._dispose_loaded_result(result)
            return

        # Apply State
        if self.original_image:
            self.original_image.close()
        self.original_image = result["original"]
        
        if self.user_image and self.user_image != result["user_image"]:
            self.user_image.close()
             
        self.user_image = result["user_image"]
        
        if result.get("pos"):
            self.user_image_pos = result["pos"]
        if result.get("size"):
            self.user_image_size = result["size"]
        
        if result.get("calc_center"):
             cw = self.canvas.winfo_width() if self.canvas.winfo_width() > 1 else 800
             ch = self.canvas.winfo_height() if self.canvas.winfo_height() > 1 else 600
             if self.user_image:
                  self.user_image_pos = ((cw - self.user_image.width)//2, (ch - self.user_image.height)//2)
                  if result.get("pos") is None:
                      self.user_image_pos = ((cw - self.user_image.width)//2, (ch - self.user_image.height)//2)

        if result.get("add_to_cache"):
             self._add_to_cache(result["path"], self.user_image.copy())
              
        # Update LRU
        if result["path"] in self.images:
             self._touch_image_cache_entry(result["path"])

        self.update_canvas()
        self.status_var.set(f"Visualizando: {os.path.basename(result['path'])}")
        
        if not self.preserve_undo_flag:
            self.undo_stack = []
        self.save_state_for_undo()

    @staticmethod
    def _dispose_loaded_result(result):
        original = result.get("original")
        user_image = result.get("user_image")
        if original:
            try:
                original.close()
            except Exception:
                pass
        if user_image and user_image is not original:
            try:
                user_image.close()
            except Exception:
                pass

    def save_current_image_state(self):
        if self.image_path and self.user_image:
             self._add_to_cache(self.image_path, self.user_image.copy())
             self.image_states[self.image_path] = {'pos': self.user_image_pos, 'size': self.user_image_size}

    def update_canvas(self, *_):
        self.canvas.delete("all")
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw <= 1 or ch <= 1: return
        self.canvas.configure(bg=SURFACE_BG)
        
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

        self.canvas.create_rectangle(
            bx - 5,
            by - 5,
            bx + BORDA_WIDTH + 5,
            by + BORDA_HEIGHT + 5,
            outline="#5D6C86",
            dash=(4, 4),
        )
        
        if self.user_image:
            self.user_tk = ImageTk.PhotoImage(self.user_image)
            self.canvas.create_image(self.user_image_pos[0], self.user_image_pos[1], anchor=tk.NW, image=self.user_tk)

        self.canvas.create_rectangle(bx, by, bx+BORDA_WIDTH, by+BORDA_HEIGHT, outline=b_hex, width=BORDER_THICKNESS, tags="border_rect")

        if not self.image_list:
            self.canvas.create_text(
                cw / 2,
                max(30, by - 72),
                text="Sem imagens carregadas",
                fill=TEXT_PRIMARY,
                font=("Segoe UI", 18, "bold"),
                anchor="center",
            )
            self.canvas.create_text(
                cw / 2,
                max(50, by - 44),
                text="Arraste imagens para a janela ou clique em 'Selecionar Pasta'",
                fill=TEXT_SECONDARY,
                font=("Segoe UI", 12),
                anchor="center",
            )
        elif not self.user_image:
            self.canvas.create_text(
                cw / 2,
                max(50, by - 44),
                text="Selecione uma imagem da lista para editar.",
                fill=TEXT_SECONDARY,
                font=("Segoe UI", 12),
                anchor="center",
            )

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
        self.preview_duration = 50
        self.current_preview_tk = None
        self._start_preview_generation_task()
        
        self.animate_loop()

    def _start_preview_generation_task(self):
        if self._active_preview_task_id and self.task_runner.is_running(self._active_preview_task_id):
            self.task_runner.cancel(self._active_preview_task_id)

        self._preview_seq += 1
        task_id = f"preview_frames_{self._preview_seq}"
        self._active_preview_task_id = task_id

        anim_type = self.animation_type.get()
        b_name = self.individual_bordas.get(self.image_path, self.selected_borda.get()) if self.image_path else self.selected_borda.get()
        if b_name == "Cor Personalizada":
            b_hex = self.custom_borda_hex_individual.get(self.image_path, self.custom_borda_hex) if self.image_path else self.custom_borda_hex
        else:
            b_hex = self.borda_hex.get(b_name, "#FFFFFF")

        def task_fn(cancel_event, _on_progress):
            result = self._generate_preview_frames(anim_type, b_hex, cancel_event)
            result["task_id"] = task_id
            return result

        def on_done(result):
            def apply_result():
                if result.get("task_id") != self._active_preview_task_id:
                    return
                self._active_preview_task_id = None
                if result.get("cancelled"):
                    return
                if result.get("error"):
                    logger.warning("Falha ao gerar preview: %s", result["error"])
                    return
                self.preview_frames = result.get("frames", [])
                self.preview_duration = result.get("duration", 50)

            self.root.after(0, apply_result)

        def on_error(exc):
            logger.exception("Erro ao gerar frames de preview: %s", exc)

        self.task_runner.submit(task_id, task_fn, on_done=on_done, on_error=on_error)

    @staticmethod
    def _generate_preview_frames(anim_type, b_hex, cancel_event):
        try:
            size = (BORDA_WIDTH, BORDA_HEIGHT)

            if cancel_event and cancel_event.is_set():
                return {"cancelled": True, "frames": [], "duration": 50}

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

            if cancel_event and cancel_event.is_set():
                return {"cancelled": True, "frames": [], "duration": duration}

            return {"cancelled": False, "frames": frames, "duration": duration}
        except Exception as exc:
            return {"cancelled": False, "frames": [], "duration": 50, "error": str(exc)}

    def stop_preview_animation(self):
        self.animation_running = False
        if self._active_preview_task_id and self.task_runner.is_running(self._active_preview_task_id):
            self.task_runner.cancel(self._active_preview_task_id)
        self._active_preview_task_id = None
        if self.animation_job:
            self.root.after_cancel(self.animation_job)
            self.animation_job = None
        self.preview_frames = []
        self.current_preview_tk = None
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
            secondary = button_style("secondary")
            self.btn_pick_color.configure(
                fg_color=secondary["fg_color"],
                hover_color=secondary["hover_color"],
                text="Pick Color",
            )
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
                except Exception as exc:
                    logger.warning("Falha ao ler pixel para pick color: %s", exc)
        
        # If not on image, or failed, maybe we want to allow picking background?
        # For this requirement, user likely wants image colors.
        
        if color:
             self.root.clipboard_clear()
             self.root.clipboard_append(color)
             self.root.update_idletasks()
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
        menu.add_command(label="Rotacionar 90° Esquerda (Ctrl+Q)", command=lambda: self.rotate_image("left"))
        menu.add_command(label="Rotacionar 90° Direita (Ctrl+E)", command=lambda: self.rotate_image("right"))
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
        if not self.image_list:
            return
        if not messagebox.askyesno("Confirmar", f"Aplicar '{name}' a todas as imagens?"):
            return

        task_id = "apply_adjustment_all"
        if self.task_runner.is_running(task_id):
            messagebox.showwarning("Aviso", "Ja existe um ajuste em lote em andamento.")
            return

        popup = ProgressBarPopup(
            self.root,
            title=f"Processando {name}",
            maximum=max(1, len(self.image_list)),
            on_cancel=lambda: self._cancel_background_task(task_id, f"Ajuste em lote ({name})"),
        )

        def task_fn(cancel_event, on_progress):
            error_count = 0
            processed = 0
            for path in self.image_list:
                if cancel_event and cancel_event.is_set():
                    return {"cancelled": True, "processed": processed, "errors": error_count}

                temp_img = None
                try:
                    temp_img = Image.open(path).convert("RGBA")
                    nw, nh, px, py = None, None, None, None

                    if name == "Ajuste Inteligente":
                        face = ImageProcessor.detect_anime_face(temp_img, self.face_cascade)
                        if face:
                            res = ImageProcessor.calculate_intelligent_frame_pos(temp_img, face, self.borda_pos)
                            if res:
                                nw, nh, px, py = res

                    if not nw:
                        res = ImageProcessor.calculate_auto_fit_pos(temp_img, self.borda_pos)
                        if res:
                            nw, nh, px, py = res

                    if nw and nh:
                        self.image_states[path] = {"pos": (px, py), "size": (nw, nh)}
                    else:
                        error_count += 1
                except Exception as exc:
                    error_count += 1
                    logger.exception("Erro ao aplicar ajuste em lote para %s: %s", path, exc)
                finally:
                    if temp_img:
                        temp_img.close()

                processed += 1
                if on_progress:
                    on_progress(processed, len(self.image_list), f"Processando: {os.path.basename(path)}")

            return {"cancelled": False, "processed": processed, "errors": error_count}

        def on_progress(current, total, msg):
            self.root.after(0, lambda c=current, t=total, m=msg: self._task_popup_update(popup, c, t, m))

        def on_done(result):
            def finish():
                popup.close()
                if result.get("cancelled"):
                    show_toast(self.root, "Cancelado", "Ajuste em lote cancelado.", "info")
                    return
                if self.current_image_index is not None:
                    self.load_image(self.current_image_index)

                err_count = int(result.get("errors", 0))
                if err_count:
                    show_toast(self.root, "Concluido", f"Ajuste finalizado com {err_count} erro(s).", "error")
                else:
                    show_toast(self.root, "Concluido", "Processamento em lote finalizado.", "success")

            self.root.after(0, finish)

        def on_error(exc):
            self.root.after(0, lambda: (popup.close(), messagebox.showerror("Erro", str(exc))))

        started = self.task_runner.submit(
            task_id,
            task_fn,
            on_progress=on_progress,
            on_done=on_done,
            on_error=on_error,
        )
        if not started:
            popup.close()
            messagebox.showwarning("Aviso", "Nao foi possivel iniciar o ajuste em lote.")
    # --- Save & Upload ---


    def show_save_menu(self):
        m = Menu(self.root, tearoff=0)
        m.add_command(label="Salvar Imagens", command=self.save_all_images)
        m.add_command(label="Salvar ZIP", command=self.save_zip)
        m.add_command(label="Upload ImgChest", command=self.open_upload_window)
        m.post(self.root.winfo_pointerx(), self.root.winfo_pointery())

    @staticmethod
    def _task_popup_update(popup, current, total, msg):
        try:
            if not popup.window.winfo_exists():
                return
            popup.maximum = max(1, total)
            popup.update_progress(current, msg)
        except tk.TclError:
            return

    def _cancel_background_task(self, task_id, label):
        if self.task_runner.cancel(task_id):
            show_toast(self.root, "Cancelando", f"{label} em cancelamento...", "info")


    def save_all_images(self):
        if not self.image_list:
            messagebox.showwarning("Aviso", "Nenhuma imagem carregada.")
            return

        task_id = "save_all_images"
        if self.task_runner.is_running(task_id):
            messagebox.showwarning("Aviso", "Ja existe uma exportacao em andamento.")
            return

        d = filedialog.askdirectory()
        if not d:
            return

        popup = ProgressBarPopup(
            self.root,
            title="Salvando...",
            maximum=max(1, len(self.image_list)),
            on_cancel=lambda: self._cancel_background_task(task_id, "Exportacao"),
        )

        def task_fn(cancel_event, on_progress):
            return self.batch_controller.save_all_images(
                d,
                progress_callback=on_progress,
                cancel_event=cancel_event,
            )

        def on_progress(current, total, msg):
            self.root.after(0, lambda c=current, t=total, m=msg: self._task_popup_update(popup, c, t, m))

        def on_done(result):
            def finish():
                popup.close()
                if result.get("cancelled"):
                    show_toast(self.root, "Cancelado", "Exportacao cancelada.", "info")
                    return
                err_count = int(result.get("errors", 0))
                if err_count:
                    show_toast(self.root, "Concluido", f"Exportado com {err_count} erro(s).", "error")
                else:
                    show_toast(self.root, "Salvo", "Imagens salvas com sucesso.", "success")

            self.root.after(0, finish)

        def on_error(exc):
            self.root.after(0, lambda: (popup.close(), messagebox.showerror("Erro", str(exc))))

        started = self.task_runner.submit(
            task_id,
            task_fn,
            on_progress=on_progress,
            on_done=on_done,
            on_error=on_error,
        )
        if not started:
            popup.close()
            messagebox.showwarning("Aviso", "Nao foi possivel iniciar a exportacao.")

    def save_zip(self):
        if not self.image_list:
            messagebox.showwarning("Aviso", "Nenhuma imagem carregada.")
            return

        task_id = "save_zip"
        if self.task_runner.is_running(task_id):
            messagebox.showwarning("Aviso", "Ja existe um ZIP em andamento.")
            return

        f = filedialog.asksaveasfilename(defaultextension=".zip")
        if not f:
            return

        popup = ProgressBarPopup(
            self.root,
            title="Salvando ZIP...",
            maximum=max(1, len(self.image_list)),
            on_cancel=lambda: self._cancel_background_task(task_id, "ZIP"),
        )

        def task_fn(cancel_event, on_progress):
            return self.batch_controller.save_zip(
                f,
                progress_callback=on_progress,
                cancel_event=cancel_event,
            )

        def on_progress(current, total, msg):
            self.root.after(0, lambda c=current, t=total, m=msg: self._task_popup_update(popup, c, t, m))

        def on_done(result):
            def finish():
                popup.close()
                if result.get("cancelled"):
                    show_toast(self.root, "Cancelado", "Geracao de ZIP cancelada.", "info")
                    return
                written = int(result.get("written", 0))
                if written == 0:
                    show_toast(self.root, "Aviso", "Nenhum arquivo foi adicionado ao ZIP.", "error")
                else:
                    show_toast(self.root, "Salvo", "ZIP salvo com sucesso.", "success")

            self.root.after(0, finish)

        def on_error(exc):
            self.root.after(0, lambda: (popup.close(), messagebox.showerror("Erro", str(exc))))

        started = self.task_runner.submit(
            task_id,
            task_fn,
            on_progress=on_progress,
            on_done=on_done,
            on_error=on_error,
        )
        if not started:
            popup.close()
            messagebox.showwarning("Aviso", "Nao foi possivel iniciar a geracao de ZIP.")

    def open_upload_window(self):
        if not self.image_list:
            messagebox.showwarning("Aviso", "Nenhuma imagem carregada.")
            return

        top = ctk.CTkToplevel(self.root)
        top.title("Upload ImgChest")
        top.attributes('-topmost', True)
        
        ctk.CTkLabel(top, text="Título do Álbum:").pack(pady=5, padx=10)
        e_title = ctk.CTkEntry(top)
        e_title.pack(pady=5, padx=10)
        
        def do_upload():
            title = e_title.get() or "CustomMaker"
            top.destroy()
            task_id = "upload_imgchest"
            if self.task_runner.is_running(task_id):
                messagebox.showwarning("Aviso", "Ja existe um upload em andamento.")
                return

            popup = ProgressBarPopup(
                self.root,
                title="Enviando...",
                maximum=max(1, len(self.image_list)),
                on_cancel=lambda: self._cancel_background_task(task_id, "Upload"),
            )

            def task_fn(cancel_event, on_progress):
                return self.batch_controller.upload_to_imgchest(
                    title,
                    progress_callback=on_progress,
                    cancel_event=cancel_event,
                )

            def on_progress(current, total, msg):
                self.root.after(0, lambda c=current, t=total, m=msg: self._task_popup_update(popup, c, t, m))

            def on_done(result):
                def finish():
                    popup.close()
                    if result.get("cancelled"):
                        show_toast(self.root, "Cancelado", "Upload cancelado.", "info")
                        return

                    errors = result.get("errors") or []
                    links = result.get("links") or []
                    if errors:
                        messagebox.showwarning("Upload com avisos", "\n".join(errors))
                    if not links:
                        show_toast(self.root, "Erro", "Upload sem links validos.", "error")
                        return

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
                        self.root.update_idletasks()
                        btn_copy.configure(text="Copiado!", fg_color="green")
                        w.after(2000, lambda: btn_copy.configure(text="Copiar Comando", fg_color=["#3a7ebf", "#1f538d"]))

                    btn_copy = ctk.CTkButton(w, text="Copiar Comando", command=copy_command)
                    btn_copy.pack(pady=5)

                self.root.after(0, finish)

            def on_error(exc):
                self.root.after(0, lambda: (popup.close(), messagebox.showerror("Erro", str(exc))))

            started = self.task_runner.submit(
                task_id,
                task_fn,
                on_progress=on_progress,
                on_done=on_done,
                on_error=on_error,
            )
            if not started:
                popup.close()
                messagebox.showwarning("Aviso", "Nao foi possivel iniciar o upload.")

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
            self.custom_color_entry.pack(fill="x", pady=(0, 8))
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
        except Exception as exc:
            logger.warning("Falha ao abrir menu de contexto da lista: %s", exc)
    
    def remove_from_list(self):
        sel = self.image_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < 0 or idx >= len(self.image_list):
            return

        path = self.image_list.pop(idx)
        self.image_listbox.delete(idx)
        if path in self.images:
            self._remove_from_cache(path, close_image=True, reason="remove_from_list")
        if path in self.image_states:
            del self.image_states[path]
        if path in self.individual_bordas:
            del self.individual_bordas[path]
        if path in self.custom_borda_hex_individual:
            del self.custom_borda_hex_individual[path]

        if not self.image_list:
            self.current_image_index = None
            self.image_path = None
            if self.original_image:
                self.original_image.close()
                self.original_image = None
            if self.user_image:
                self.user_image.close()
                self.user_image = None
            self.update_canvas()
            self.refresh_list_empty_state()
            self.update_list_counter()
            self.status_var.set("Sem imagens carregadas.")
            return

        if self.current_image_index is None:
            self.current_image_index = 0
        elif idx < self.current_image_index:
            self.current_image_index -= 1
        elif idx == self.current_image_index:
            self.current_image_index = min(idx, len(self.image_list) - 1)
            self.load_image(self.current_image_index, preserve_undo=True)
            return

        self.update_canvas()
        self.refresh_list_empty_state()
        self.update_list_counter()

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

