import tkinter as tk
from tkinter import ttk, Menu, messagebox
import os

from functions import CustomMakerFunctions
from config import COLORS

class CustomMakerApp(CustomMakerFunctions):
    def __init__(self, root):
        super().__init__()
        self.root = root
        self.root.title("Custom Maker Pro (OpenCV)")

        try:
            icon_path = self.resource_path("icon.ico")
            if not os.path.exists(icon_path): icon_path = self.resource_path("icon.png")
            if os.path.exists(icon_path):
                if icon_path.endswith(".ico"): self.root.iconbitmap(icon_path)
                elif icon_path.endswith(".png"):
                    img = tk.PhotoImage(file=icon_path)
                    self.root.tk.call('wm', 'iconphoto', self.root._w, img)
        except Exception as e_icon:
            print(f"Aviso: Não foi possível definir o ícone da janela: {e_icon}")

        self.root.state('zoomed')
        self.root.configure(bg=COLORS["bg_dark"])
        
        self.initialize_state_variables()
        self.load_resources()
        self.configure_styles()
        self.create_widgets()
        
        self.after_id_init_canvas = self.root.after(100, self.update_canvas_if_ready)
        
        self.root.bind('<Control-z>', self.undo)
        self.root.bind('<Control-s>', lambda event: self.show_save_menu())
        self.root.bind('<Control-o>', lambda event: self.select_folder())
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        if messagebox.askokcancel("Sair", "Você tem certeza que quer sair do CustomMaker?", parent=self.root):
            self.close_resources()
            if hasattr(self, 'after_id_init_canvas'): self.root.after_cancel(self.after_id_init_canvas)
            if hasattr(self, 'after_id_update_canvas'): self.root.after_cancel(self.after_id_update_canvas)
            if hasattr(self, 'debounce_id_canvas_config'): self.root.after_cancel(self.debounce_id_canvas_config)
            self.root.destroy()

    def update_canvas_if_ready(self):
        if self.root.winfo_exists() and self.root.winfo_width() > 1 and self.root.winfo_height() > 1:
            self.update_canvas()
        else:
            if hasattr(self, 'after_id_init_canvas'):
                 if self.root.winfo_exists(): self.root.after_cancel(self.after_id_init_canvas)
            if self.root.winfo_exists():
                self.after_id_init_canvas = self.root.after(100, self.update_canvas_if_ready)

    def initialize_state_variables(self):
        self.image_path = None
        self.original_image = None
        self.user_image = None
        self.user_image_pos = (50, 50)
        self.user_image_size = None
        self.selected_image = False
        self.start_x = 0
        self.start_y = 0
        self.status_var = tk.StringVar(self.root, value="Pronto. Selecione uma pasta para começar.")
        self.selected_borda = tk.StringVar(self.root)
        self.images = {}
        self.image_states = {}
        self.image_list = []
        self.current_image_index = None
        self.undo_stack = []
        self.individual_bordas = {}
        self.uploaded_links = []

    def create_widgets(self):
        self.create_layout_frames()
        self.setup_canvas_events()
        self.status_bar = ttk.Label(self.left_frame, textvariable=self.status_var, anchor="w", style="TLabel", relief=tk.SUNKEN, padding=(5,2))
        self.status_bar.pack(side=tk.BOTTOM, fill="x", pady=(5, 0), padx=0)
        self.create_right_panel()
        
    def create_layout_frames(self):
        self.left_frame = ttk.Frame(self.root, style="TFrame")
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.right_frame = ttk.Frame(self.root, width=300, style="TFrame")
        self.right_frame.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.right_frame.grid_propagate(False)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=0)
        self.root.grid_rowconfigure(0, weight=1)
        self.canvas_frame = ttk.Frame(self.left_frame, style="TFrame")
        self.canvas_frame.pack(fill="both", expand=True, padx=0, pady=0)
        self.canvas = tk.Canvas(self.canvas_frame, bg=COLORS["bg_medium"], 
                                highlightthickness=1, highlightbackground=COLORS["bg_light"])
        self.canvas.pack(fill="both", expand=True)
        
    def setup_canvas_events(self):
        self.canvas.bind("<Button-1>", self.select_image)
        self.canvas.bind("<B1-Motion>", self.move_image)
        self.canvas.bind("<ButtonRelease-1>", self.release_image)
        self.canvas.bind("<Shift-B1-Motion>", self.resize_image_proportional)
        self.canvas.bind("<Configure>", self.on_canvas_configure)

    def on_canvas_configure(self, event=None):
        if hasattr(self, 'debounce_id_canvas_config'):
            if self.root.winfo_exists(): self.root.after_cancel(self.debounce_id_canvas_config)
        if self.root.winfo_exists():
             self.debounce_id_canvas_config = self.root.after(100, self.update_canvas_if_ready)

    def create_right_panel(self):
        container = self.right_frame
        title_label = ttk.Label(container, text="CustomMaker", style="Title.TLabel", anchor="center")
        title_label.pack(pady=(5, 15), fill="x")
        self.create_file_section(container)
        ttk.Separator(container, orient="horizontal").pack(fill="x", pady=10, padx=5)
        self.create_border_section(container)
        ttk.Separator(container, orient="horizontal").pack(fill="x", pady=10, padx=5)
        self.create_image_list_section(container)
        ttk.Separator(container, orient="horizontal").pack(fill="x", pady=10, padx=5)
        self.create_tips_section(container)
        self.create_context_menu_image_list()

    def create_border_section(self, parent_container):
        border_frame = ttk.Frame(parent_container, style="TFrame")
        border_frame.pack(fill="x", pady=5, padx=10)
        border_label = ttk.Label(border_frame, text="Cor da Borda Global:", style="TLabel")
        border_label.pack(anchor="w", pady=(0,3))
        
        borda_display_names = ['(Sem bordas)']
        default_borda = "White"
        if hasattr(self, 'bordas') and self.bordas and hasattr(self, 'borda_names') and self.borda_names:
            borda_display_names = [self.borda_names.get(b_class, b_class) for b_class in self.bordas]
            if not borda_display_names: borda_display_names = ["Padrão"]
            current_selected = self.selected_borda.get()
            if not current_selected or current_selected not in borda_display_names:
                if default_borda in borda_display_names: self.selected_borda.set(default_borda)
                elif borda_display_names: self.selected_borda.set(borda_display_names[0])
        else:
            self.selected_borda.set(default_borda if default_borda in self.borda_hex else "(Erro)")

        self.border_combo = ttk.Combobox(border_frame, textvariable=self.selected_borda,
                            values=borda_display_names, state="readonly", style="TCombobox", height=10)
        self.border_combo.pack(fill="x", pady=(0, 5))
        self.border_combo.bind("<<ComboboxSelected>>", self.on_borda_global_selected)

    def on_borda_global_selected(self, event=None):
        if self.current_image_index is not None and self.current_image_index < len(self.image_list):
            current_image_path = self.image_list[self.current_image_index]
            if current_image_path in self.individual_bordas:
                if messagebox.askyesno("Borda Individual Ativa",
                                       f"A imagem '{os.path.basename(current_image_path)}' usa uma borda individual.\n"
                                       "Deseja remover a borda individual e aplicar a nova borda global selecionada a ela?",
                                       parent=self.root, icon='question'):
                    del self.individual_bordas[current_image_path]
        self.update_canvas()

    def create_file_section(self, parent_container):
        file_ops_frame = ttk.Frame(parent_container, style="TFrame")
        file_ops_frame.pack(fill="x", pady=5, padx=10)
        file_label = ttk.Label(file_ops_frame, text="Arquivo e Edição:", style="TLabel")
        file_label.pack(anchor="w", pady=(0,5))
        
        btn_folder = ttk.Button(file_ops_frame, text="📂 Selecionar Pasta (Ctrl+O)", command=self.select_folder, style="TButton")
        btn_folder.pack(fill="x", pady=3)
        
        self.btn_intelligent_fit = ttk.Button(file_ops_frame, text="✨ Ajuste Inteligente de Rosto", command=self.intelligent_auto_frame, style="TButton")
        self.btn_intelligent_fit.pack(fill="x", pady=3)
        self.intelligent_fit_menu = Menu(self.root, tearoff=0, **self._get_menu_styles())
        self.intelligent_fit_menu.add_command(label="Aplicar à Imagem Atual", command=self.intelligent_auto_frame)
        self.intelligent_fit_menu.add_command(label="Aplicar a Todas as Imagens da Lista", command=self.apply_intelligent_to_all_ui_feedback)
        self.btn_intelligent_fit.bind("<Button-3>", lambda e: self.intelligent_fit_menu.post(e.x_root, e.y_root))

        self.btn_simple_fit = ttk.Button(file_ops_frame, text="🖼️ Ajustar/Preencher Borda", command=self.auto_fit_image, style="TButton")
        self.btn_simple_fit.pack(fill="x", pady=3)
        self.simple_fit_menu = Menu(self.root, tearoff=0, **self._get_menu_styles())
        self.simple_fit_menu.add_command(label="Aplicar à Imagem Atual", command=self.auto_fit_image)
        self.simple_fit_menu.add_command(label="Aplicar a Todas as Imagens da Lista", command=self.apply_auto_fit_to_all_ui_feedback)
        self.btn_simple_fit.bind("<Button-3>", lambda e: self.simple_fit_menu.post(e.x_root, e.y_root))
        
        btn_cancel_all = ttk.Button(file_ops_frame, text="🗑️ Limpar Tudo", command=self.cancel_image, style="TButton")
        btn_cancel_all.pack(fill="x", pady=3)
        self.btn_save_ref = ttk.Button(file_ops_frame, text="💾 Salvar Opções... (Ctrl+S)", style="Accent.TButton", command=self.show_save_menu)
        self.btn_save_ref.pack(fill="x", pady=(8,3))

    def _get_menu_styles(self):
        return {
            "bg": COLORS["bg_light"], "fg": COLORS["text"],
            "activebackground": COLORS["accent"], "activeforeground": COLORS["bg_dark"],
            "relief": tk.FLAT, "font": ("Segoe UI", 9)
        }

    def apply_intelligent_to_all_ui_feedback(self):
        if not self.image_list:
            messagebox.showwarning("Aviso", "Nenhuma imagem na lista para aplicar o ajuste.", parent=self.root)
            return
        if messagebox.askyesno("Confirmar Ação em Lote",
                               f"Aplicar 'Ajuste Inteligente' a todas as {len(self.image_list)} imagens da lista?\n"
                               "Isso pode levar um tempo e sobrescreverá edições manuais de posicionamento/tamanho.",
                               parent=self.root):
            self.apply_adjustment_to_all(self.intelligent_auto_frame, "Ajuste Inteligente")

    def apply_auto_fit_to_all_ui_feedback(self):
        if not self.image_list:
            messagebox.showwarning("Aviso", "Nenhuma imagem na lista para aplicar o ajuste.", parent=self.root)
            return
        if messagebox.askyesno("Confirmar Ação em Lote",
                               f"Aplicar 'Ajustar/Preencher Borda' a todas as {len(self.image_list)} imagens da lista?\n"
                               "Isso pode levar um tempo e sobrescreverá edições manuais de posicionamento/tamanho.",
                               parent=self.root):
            self.apply_adjustment_to_all(self.auto_fit_image, "Ajuste de Preenchimento")

    def create_image_list_section(self, parent_container):
        img_list_frame = ttk.Frame(parent_container, style="TFrame")
        img_list_frame.pack(fill="both", expand=True, pady=5, padx=10)
        images_label = ttk.Label(img_list_frame, text="Imagens na Pasta:", style="TLabel")
        images_label.pack(anchor="w", pady=(0,5))
        listbox_container = ttk.Frame(img_list_frame, style="TFrame")
        listbox_container.pack(fill="both", expand=True)
        self.image_listbox = tk.Listbox(listbox_container,
                                bg=COLORS["bg_medium"], fg=COLORS["text"],
                                selectbackground=COLORS["accent"], selectforeground=COLORS["bg_dark"],
                                borderwidth=0, highlightthickness=1, highlightcolor=COLORS["accent"],
                                font=("Segoe UI", 10), activestyle='none', exportselection=False)
        self.image_listbox.pack(side=tk.LEFT, fill="both", expand=True)
        scrollbar = ttk.Scrollbar(listbox_container, orient=tk.VERTICAL, command=self.image_listbox.yview, style="Vertical.TScrollbar")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.image_listbox.config(yscrollcommand=scrollbar.set)
        self.image_listbox.bind("<<ListboxSelect>>", self.on_image_select)
        self.image_listbox.bind("<Button-3>", self.show_context_menu_image_list)
        
    def create_context_menu_image_list(self):
        self.image_list_context_menu = Menu(self.root, tearoff=0, **self._get_menu_styles())
        self.image_list_context_menu.add_command(label="Remover da Lista", command=self.remove_from_list)
        self.image_list_context_menu.add_command(label="Definir/Remover Borda Individual", command=self.toggle_individual_borda)
        self.image_list_context_menu.add_separator()
        self.image_list_context_menu.add_command(label="Cancelar Menu")

    def show_context_menu_image_list(self, event):
        try:
            clicked_idx = self.image_listbox.nearest(event.y)
            current_selection = self.image_listbox.curselection()
            if not current_selection or clicked_idx not in current_selection:
                self.image_listbox.selection_clear(0, tk.END)
                self.image_listbox.selection_set(clicked_idx)
                self.image_listbox.activate(clicked_idx)
            self.image_list_context_menu.post(event.x_root, event.y_root)
        except tk.TclError: pass
        
    def create_tips_section(self, parent_container):
        tip_frame = ttk.Frame(parent_container, style="TFrame")
        tip_frame.pack(fill="x", side=tk.BOTTOM, pady=(10, 5), padx=10)
        tip_text = ("Dicas Rápidas:\n"
                    "• Arraste a imagem para mover.\n"
                    "• Shift + Arraste para redimensionar.\n"
                    "• Ctrl+Z para Desfazer última edição.\n"
                    "• Clique direito na lista para opções.")
        tip_label = ttk.Label(tip_frame, text=tip_text, wraplength=270, 
                              justify=tk.LEFT, font=("Segoe UI", 8), 
                              foreground=COLORS["text_dim"], style="TLabel")
        tip_label.pack(fill="x", pady=5)

if __name__ == "__main__":
    if not os.path.exists(".env"):
        try:
            with open(".env", "w") as f: f.write("IMG_CHEST_API_TOKEN=seu_token_imgchest_aqui\n")
            print("INFO: Arquivo .env de exemplo criado. Por favor, adicione seu token da API ImgChest.")
        except IOError: print("AVISO: Não foi possível criar o arquivo .env de exemplo.")
    root = tk.Tk()
    app = CustomMakerApp(root)
    root.mainloop()
