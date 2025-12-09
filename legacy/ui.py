import tkinter as tk
from tkinter import ttk, Menu, messagebox
import os

from functions import CustomMakerFunctions
from config import COLORS, BORDA_WIDTH, BORDA_HEIGHT, SUPPORTED_EXTENSIONS # Importar BORDA_WIDTH, BORDA_HEIGHT, SUPPORTED_EXTENSIONS

class Tooltip:
        def __init__(self, widget, text):
            self.widget = widget
            self.text = text
            self.tooltip_window = None
            self.id = None
            self.widget.bind("<Enter>", self.show_tooltip)
            self.widget.bind("<Leave>", self.hide_tooltip)

        def show_tooltip(self, event=None):
            self.id = self.widget.after(500, self._show_tooltip) # Atraso de 500ms

        def _show_tooltip(self):
            if self.tooltip_window:
                return
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
            self.tooltip_window = tk.Toplevel(self.widget)
            self.tooltip_window.wm_overrideredirect(True) # Remove borda e título
            self.tooltip_window.wm_geometry(f"+{x}+{y}")
            label = tk.Label(self.tooltip_window, text=self.text, background=COLORS["bg_light"],
                            foreground=COLORS["text"], relief=tk.SOLID, borderwidth=1,
                            font=("Segoe UI", 9), padx=5, pady=2)
            label.pack()

        def hide_tooltip(self, event=None):
            if self.id:
                self.widget.after_cancel(self.id)
            if self.tooltip_window:
                self.tooltip_window.destroy()
            self.tooltip_window = None

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

        if self.config['last_global_borda'] in self.borda_hex: # Verifique se a borda existe
            self.selected_borda.set(self.config['last_global_borda'])
        else:
            self.selected_borda.set('White') # Fallback
        
        self.after_id_init_canvas = self.root.after(100, self.update_canvas_if_ready)
        
        self.root.bind('<Control-z>', self.undo)
        self.root.bind('<Control-s>', lambda event: self.show_save_menu())
        self.root.bind('<Control-o>', lambda event: self.select_folder())
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        super().on_closing() # Chama a função on_closing da classe pai para salvar as configurações
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
        self.custom_borda_hex = "#FFFFFF" # Cor hexadecimal padrão para personalizada
        self.custom_borda_hex_individual = {} # Dicionário para bordas individuais personalizadas
        self.current_hover_item_index = -1 # Para controle de tooltip
        self.hover_tooltip = None # Objeto Tooltip ativo
        self.drag_data = {"item": None, "index": None, "original_index_on_start": None} # Para drag and drop


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
        self.canvas.bind("<MouseWheel>", self.zoom_image)
        self.canvas.bind("<Button-4>", self.zoom_image)
        self.canvas.bind("<Button-5>", self.zoom_image)


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
            borda_display_names.append("Cor Personalizada") # Adicionar a opção personalizada
            if not borda_display_names: borda_display_names = ["Padrão"]
            current_selected = self.selected_borda.get()
            if not current_selected or current_selected not in borda_display_names:
                if self.config['last_global_borda'] in borda_display_names: # Usar persistência
                    self.selected_borda.set(self.config['last_global_borda'])
                elif borda_display_names:
                    self.selected_borda.set(borda_display_names[0])
        else:
            self.selected_borda.set(default_borda if default_borda in self.borda_hex else "(Erro)")

        self.border_combo = ttk.Combobox(border_frame, textvariable=self.selected_borda,
                            values=borda_display_names, state="readonly", style="TCombobox", height=10)
        self.border_combo.pack(fill="x", pady=(0, 5))
        self.border_combo.bind("<<ComboboxSelected>>", self.on_borda_global_selected)

        # Campo para cor hexadecimal personalizada
        self.custom_color_entry = ttk.Entry(border_frame, width=10, style="TEntry")
        self.custom_color_entry.pack(fill="x", pady=(5,0))
        self.custom_color_entry.insert(0, self.custom_borda_hex) # Valor inicial
        self.custom_color_entry.bind("<KeyRelease>", self.on_custom_color_change)
        
        # Ocultar/Exibir o campo de entrada baseado na seleção do combobox
        self._toggle_custom_color_entry() # Chama na inicialização para estado correto

    def on_custom_color_change(self, event=None):
        hex_color = self.custom_color_entry.get().strip()
        if len(hex_color) == 7 and hex_color.startswith("#") and all(c in '0123456789abcdefABCDEF' for c in hex_color[1:]):
            self.custom_borda_hex = hex_color
            if self.selected_borda.get() == "Cor Personalizada":
                self.update_canvas() # Atualiza apenas se a opção personalizada estiver selecionada

    def on_borda_global_selected(self, event=None):
        # A chamada para super().on_borda_global_selected(event) foi movida para dentro desta função
        # para que a lógica de salvamento de configuração e toggle do entry seja executada.
        # No entanto, a lógica de confirmação de borda individual deve ser antes do update_canvas na super().
        # Para evitar duplicação, deixarei a lógica de confirmação aqui e chamarei o update_canvas.
        if self.current_image_index is not None and self.current_image_index < len(self.image_list):
            current_image_path = self.image_list[self.current_image_index]
            # Se a imagem atual tem uma borda individual, pergunta se deseja remover
            if current_image_path in self.individual_bordas:
                if messagebox.askyesno("Borda Individual Ativa",
                                       f"A imagem '{os.path.basename(current_image_path)}' usa uma borda individual.\n"
                                       "Deseja remover a borda individual e aplicar a nova borda global selecionada a ela?",
                                       parent=self.root, icon='question'):
                    del self.individual_bordas[current_image_path]
                    if current_image_path in self.custom_borda_hex_individual: # Remover a cor individual personalizada também
                        del self.custom_borda_hex_individual[current_image_path]
        
        self.update_canvas()
        self._toggle_custom_color_entry() # Atualiza a visibilidade do campo de cor personalizada
        super().save_app_config() # Salva a nova borda selecionada


    def _toggle_custom_color_entry(self):
        if self.selected_borda.get() == "Cor Personalizada":
            self.custom_color_entry.pack(fill="x", pady=(5,0))
        else:
            self.custom_color_entry.pack_forget()

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
        btn_reset_image = ttk.Button(file_ops_frame, text="↩️ Redefinir Imagem Atual", command=self.reset_current_image, style="TButton")
        btn_reset_image.pack(fill="x", pady=3)


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

        # Adicionar eventos de Drag and Drop
        self.image_listbox.bind("<Button-1>", self.start_drag)
        self.image_listbox.bind("<B1-Motion>", self.do_drag)
        self.image_listbox.bind("<ButtonRelease-1>", self.stop_drag)

        self.image_listbox.bind("<Motion>", self.on_listbox_hover) # Evento para tooltip ao passar o mouse
        self.image_listbox.bind("<Leave>", self.on_listbox_leave) # Evento para ocultar tooltip
        self.current_hover_item_index = -1
        self.hover_tooltip = None

    def on_listbox_hover(self, event):
        index = self.image_listbox.nearest(event.y)
        if 0 <= index < len(self.image_list):
            if index != self.current_hover_item_index:
                self.current_hover_item_index = index
                if self.hover_tooltip:
                    self.hover_tooltip.hide_tooltip()
                
                image_path_key = self.image_list[index]
                tooltip_text = f"Arquivo: {os.path.basename(image_path_key)}"
                if image_path_key in self.individual_bordas:
                    tooltip_text += f"\nBorda Individual: {self.individual_bordas[image_path_key]}"
                    if self.individual_bordas[image_path_key] == "Cor Personalizada" and image_path_key in self.custom_borda_hex_individual:
                        tooltip_text += f" ({self.custom_borda_hex_individual[image_path_key]})"

                # Crie uma nova instância de Tooltip para o item
                self.hover_tooltip = Tooltip(self.image_listbox, tooltip_text)
                self.hover_tooltip.show_tooltip() # Chame explicitamente o show_tooltip
        else:
            self.on_listbox_leave()

    def on_listbox_leave(self, event=None):
        if self.hover_tooltip:
            self.hover_tooltip.hide_tooltip()
            self.hover_tooltip = None
        self.current_hover_item_index = -1
        
    def start_drag(self, event):
        if event.widget == self.image_listbox:
            try:
                index = self.image_listbox.nearest(event.y)
                if index != -1:
                    self.drag_data["item"] = self.image_listbox.get(index)
                    self.drag_data["index"] = index # Índice atual (pode mudar durante o drag)
                    self.drag_data["original_index_on_start"] = index # Índice quando o drag começou
            except tk.TclError:
                self.drag_data = {"item": None, "index": None, "original_index_on_start": None}

    def do_drag(self, event):
        if self.drag_data["item"] and self.drag_data["index"] is not None:
            current_y = event.y
            
            # Calcule o novo índice baseado na posição do mouse
            new_index = self.image_listbox.nearest(current_y)
            
            # Garanta que o novo índice é válido e diferente do atual
            if new_index != -1 and new_index != self.drag_data["index"]:
                # Move o item visualmente na Listbox
                item_to_move = self.image_listbox.get(self.drag_data["index"])
                self.image_listbox.delete(self.drag_data["index"])
                self.image_listbox.insert(new_index, item_to_move)
                
                # Atualiza o índice interno de onde o item "está" atualmente durante o drag
                self.drag_data["index"] = new_index
                
                # Mantém a seleção no item que está sendo arrastado
                self.image_listbox.selection_clear(0, tk.END)
                self.image_listbox.selection_set(new_index)
                self.image_listbox.activate(new_index)
                self.image_listbox.see(new_index)

    def stop_drag(self, event):
        if self.drag_data["item"] and self.drag_data["original_index_on_start"] is not None:
            original_idx = self.drag_data["original_index_on_start"]
            final_idx = self.image_listbox.nearest(event.y) # Índice final após soltar

            if original_idx != final_idx:
                # Atualizar a lista interna self.image_list
                item_path = self.image_list.pop(original_idx)
                self.image_list.insert(final_idx, item_path)

                # Atualizar o `current_image_index` se a imagem selecionada foi movida
                if self.current_image_index == original_idx:
                    self.current_image_index = final_idx
                elif (original_idx < self.current_image_index and final_idx >= self.current_image_index) or \
                     (original_idx > self.current_image_index and final_idx <= self.current_image_index):
                    # Se a imagem selecionada não foi a arrastada, mas sua posição relativa mudou
                    if original_idx < final_idx: # Arrastou para baixo
                        self.current_image_index -= 1
                    else: # Arrastou para cima
                        self.current_image_index += 1
                
                self.status_var.set(f"Imagens reordenadas. Imagem atual: {os.path.basename(self.image_list[self.current_image_index])}")
                
                # Recarregar a imagem atual para garantir que o canvas esteja correto
                # O `load_image` já cuida de salvar o estado atual antes de carregar uma nova
                self.load_image(self.current_image_index, preserve_undo=True) # preserve_undo para não limpar o histórico de desfazer

            self.drag_data = {"item": None, "index": None, "original_index_on_start": None}
        
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