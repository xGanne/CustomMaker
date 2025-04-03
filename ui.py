import tkinter as tk
from tkinter import ttk, Menu

from functions import CustomMakerFunctions
from config import COLORS

class CustomMakerApp(CustomMakerFunctions):
    def __init__(self, root):
        self.root = root
        self.root.title("Custom Maker")
        
        # Configura a janela
        self.root.state('zoomed')
        self.root.configure(bg=COLORS["bg_dark"])
        
        # Inicializa variáveis de estado
        self.initialize_state_variables()
        
        # Carrega as bordas disponíveis
        self.load_resources()
        
        # Configuração da interface
        self.configure_styles()
        self.create_widgets()
        
        # Configura eventos e timers
        self.root.after(100, self.update_canvas)
        self.root.bind('<Control-z>', self.undo)
    
    def initialize_state_variables(self):
        """Inicializa todas as variáveis de estado"""
        self.borda_class = None
        self.image_path = None
        self.original_image = None
        self.user_image = None
        self.user_image_pos = (287, 25)
        self.user_image_size = None
        self.selected_image = False
        self.start_x = 0
        self.start_y = 0
        self.is_uploading = False
        
        # Status
        self.status_var = tk.StringVar(self.root)
        self.status_var.set("Pronto")
        
        # Bordas
        self.selected_borda = tk.StringVar(self.root)
        self.selected_borda.set('White')
        
        # Estruturas de dados
        self.images = {}
        self.image_states = {}
        self.image_list = []
        self.current_image_index = None
        self.undo_stack = []
        self.individual_bordas = {}
        self.uploaded_links = []
        
    def create_widgets(self):
        """Cria todos os elementos da interface gráfica"""
        # Configuração do layout básico
        self.create_layout_frames()
        
        # Configura os eventos do canvas
        self.setup_canvas_events()
        
        # Status bar
        self.status_bar = ttk.Label(self.left_frame, textvariable=self.status_var, anchor="w")
        self.status_bar.pack(fill="x", pady=(5, 0))
        
        # Painel lateral direito
        self.create_right_panel()
        
    def create_layout_frames(self):
        """Cria os frames principais do layout"""
        self.left_frame = ttk.Frame(self.root)
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)
        
        self.right_frame = ttk.Frame(self.root, width=300)
        self.right_frame.grid(row=0, column=1, sticky="ns", padx=(0, 15), pady=15)
        
        # Configuração de pesos para redimensionamento
        self.root.grid_columnconfigure(0, weight=100)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        
        # Canvas para edição de imagem
        self.canvas_frame = ttk.Frame(self.left_frame)
        self.canvas_frame.pack(fill="both", expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg=COLORS["bg_medium"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=2, pady=2)
        
    def setup_canvas_events(self):
        """Configura eventos para o canvas"""
        self.canvas.bind("<Button-1>", self.select_image)
        self.canvas.bind("<B1-Motion>", self.move_image)
        self.canvas.bind("<ButtonRelease-1>", self.release_image)
        self.canvas.bind("<Shift-B1-Motion>", self.resize_image_proportional)
        
    def create_right_panel(self):
        """Cria o painel lateral com controles"""
        # Título
        title_label = ttk.Label(self.right_frame, text="Custom Maker", style="Title.TLabel")
        title_label.pack(pady=(0, 15))
        
        # Seção de bordas
        self.create_border_section()
        
        ttk.Separator(self.right_frame, orient="horizontal").pack(fill="x", pady=10)
        
        # Seção de arquivo
        self.create_file_section()
        
        ttk.Separator(self.right_frame, orient="horizontal").pack(fill="x", pady=10)
        
        # Lista de imagens
        self.create_image_list_section()
        
        # Menu de contexto
        self.create_context_menu()
        
        # Dicas de uso
        self.create_tips_section()
        
    def create_border_section(self):
        """Cria a seção de seleção de bordas"""
        border_frame = ttk.Frame(self.right_frame)
        border_frame.pack(fill="x", pady=5)
        
        border_label = ttk.Label(border_frame, text="Escolher borda")
        border_label.pack(anchor="w")
        
        border_combo = ttk.Combobox(border_frame,
                            textvariable=self.selected_borda,
                            values=[self.borda_names[borda] for borda in self.bordas],
                            state="readonly")
        border_combo.pack(fill="x", pady=(5, 0))
        border_combo.bind("<<ComboboxSelected>>", self.update_canvas)
        
    def create_file_section(self):
        """Cria a seção de gerenciamento de arquivos"""
        file_label = ttk.Label(self.right_frame, text="Gerenciar imagens")
        file_label.pack(anchor="w", pady=(5, 5))
        
        btn_folder = ttk.Button(self.right_frame, text="Selecionar pasta", command=self.select_folder)
        btn_folder.pack(fill="x", pady=2)
        
        btn_cancel = ttk.Button(self.right_frame, text="Cancelar", command=self.cancel_image)
        btn_cancel.pack(fill="x", pady=2)
        
        btn_save = ttk.Button(self.right_frame, text="Salvar", style="Accent.TButton", command=self.show_save_menu)
        btn_save.pack(fill="x", pady=2)
        
    def create_image_list_section(self):
        """Cria a seção de lista de imagens"""
        images_label = ttk.Label(self.right_frame, text="Imagens")
        images_label.pack(anchor="w", pady=(5, 5))
        
        listbox_frame = ttk.Frame(self.right_frame)
        listbox_frame.pack(fill="both", expand=True)
        
        self.image_listbox = tk.Listbox(listbox_frame,
                                bg=COLORS["bg_medium"],
                                fg=COLORS["text"],
                                selectbackground=COLORS["accent"],
                                selectforeground=COLORS["bg_dark"],
                                borderwidth=0,
                                highlightthickness=0,
                                font=("Segoe UI", 10))
        self.image_listbox.pack(side=tk.LEFT, fill="both", expand=True)
        self.image_listbox.bind("<<ListboxSelect>>", self.on_image_select)
        self.image_listbox.bind("<Button-3>", self.show_context_menu)
        
        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.image_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.image_listbox.config(yscrollcommand=scrollbar.set)
        
    def create_context_menu(self):
        """Cria o menu de contexto para o listbox de imagens"""
        self.context_menu = Menu(self.root, tearoff=0, bg=COLORS["bg_medium"], fg=COLORS["text"], activebackground=COLORS["accent"])
        self.context_menu.add_command(label="Remover da lista", command=self.remove_from_list)
        self.context_menu.add_command(label="Borda individual", command=self.toggle_individual_borda)
        
    def create_tips_section(self):
        """Cria a seção de dicas de uso"""
        tip_frame = ttk.Frame(self.right_frame)
        tip_frame.pack(fill="x", pady=(10, 0))
        
        tip_label = ttk.Label(tip_frame,
                     text="Dicas: Arraste para mover, Shift+arraste para redimensionar",
                     wraplength=250,
                     foreground=COLORS["text_dim"])
        tip_label.pack(fill="x")

if __name__ == "__main__":
    root = tk.Tk()
    app = CustomMakerApp(root)
    root.mainloop()