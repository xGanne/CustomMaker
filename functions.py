import os
import sys
import tempfile
import zipfile
from tkinter import filedialog, messagebox, Menu
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageDraw
import cssutils
from dotenv import load_dotenv

from config import COLORS, BORDA_NAMES, BORDA_HEX

class CustomMakerFunctions:
    def load_resources(self):
        """Carrega as bordas e outros recursos necessários"""
        # Carrega variáveis de ambiente do arquivo .env
        load_dotenv()
        
        # Carrega as bordas disponíveis
        self.bordas = self.load_bordas()
        self.borda_names = BORDA_NAMES
        self.borda_hex = BORDA_HEX
    
    def load_bordas(self):
        """Carrega as bordas disponíveis do arquivo CSS"""
        css_file = self.resource_path("bordas.css")
        css_parser = cssutils.CSSParser()
        stylesheet = css_parser.parseFile(css_file)
        return [rule.selectorText for rule in stylesheet.cssRules if rule.type == rule.STYLE_RULE]

    def resource_path(self, relative_path):
        """Obtém o caminho do recurso mesmo quando empacotado com PyInstaller"""
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def configure_styles(self):
        """Configura os estilos personalizados para a aplicação"""
        style = ttk.Style()
        
        # Configuração do tema geral
        style.theme_use('clam')
        
        # Configuração de estilos específicos
        style.configure("TFrame", background=COLORS["bg_dark"])
        
        # Botões
        style.configure("TButton",
                    font=("Segoe UI", 10),
                    background=COLORS["bg_light"],
                    foreground=COLORS["text"],
                    borderwidth=0,
                    focuscolor=COLORS["accent"],
                    relief="flat")
        style.map("TButton",
            background=[('active', COLORS["accent"]), ('pressed', COLORS["bg_medium"])],
            foreground=[('active', COLORS["bg_dark"]), ('pressed', COLORS["text"])])
        
        # Botão de ação principal
        style.configure("Accent.TButton",
                    background=COLORS["accent"],
                    foreground=COLORS["bg_dark"])
        style.map("Accent.TButton",
            background=[('active', COLORS["accent"]), ('pressed', COLORS["text_dim"])],
            foreground=[('active', COLORS["bg_dark"]), ('pressed', COLORS["bg_dark"])])
        
        # Rótulos
        style.configure("TLabel",
                    font=("Segoe UI", 10),
                    background=COLORS["bg_dark"],
                    foreground=COLORS["text"])
        
        # Rótulos de título
        style.configure("Title.TLabel",
                    font=("Segoe UI", 12, "bold"),
                    background=COLORS["bg_dark"],
                    foreground=COLORS["accent"])
        
        # Separadores
        style.configure("TSeparator",
                    background=COLORS["bg_light"])
        
        # Menus suspensos
        style.configure("TCombobox",
                    selectbackground=COLORS["accent"],
                    fieldbackground=COLORS["bg_medium"],
                    background=COLORS["bg_light"],
                    foreground=COLORS["text"])
        
        # Barras de rolagem
        style.configure("Vertical.TScrollbar",
                    background=COLORS["bg_medium"],
                    troughcolor=COLORS["bg_dark"],
                    arrowcolor=COLORS["text"])

    # --- Funções de manipulação de imagem ---
    
    def select_folder(self):
        """Seleciona uma pasta contendo imagens"""
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.status_var.set("Carregando imagens...")
            self.root.update_idletasks()
            
            # Filtra apenas imagens válidas
            self.image_list = [os.path.join(folder_path, f) for f in os.listdir(folder_path)
                          if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'))]
            
            self.image_listbox.delete(0, tk.END)
            self.images = {}
            self.image_states = {}
            
            for image_path in self.image_list:
                self.image_listbox.insert(tk.END, os.path.basename(image_path))
            
            if self.image_list:
                self.load_image(0)
                self.status_var.set(f"Carregadas {len(self.image_list)} imagens")
            else:
                self.status_var.set("Nenhuma imagem encontrada na pasta")

    def load_image(self, index):
        """Carrega a imagem selecionada"""
        if self.current_image_index is not None:
            self.save_current_image()
        
        self.current_image_index = index
        self.image_path = self.image_list[index]
        
        try:
            self.original_image = Image.open(self.image_path).convert("RGBA")
            self.user_image = self.resize_image(self.original_image, 400, 300)
            self.user_image_size = self.user_image.size
            self.user_image_pos = ((800 - self.user_image_size[0]) // 2, (400 - self.user_image_size[1]) // 2)
            
            # Restaura o estado da imagem se já tiver sido editada antes
            self.restore_image_state()
            self.update_canvas()
            
            self.image_listbox.selection_clear(0, tk.END)
            self.image_listbox.selection_set(index)
            self.image_listbox.see(index)
            
            filename = os.path.basename(self.image_path)
            self.status_var.set(f"Imagem carregada: {filename}")
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível carregar a imagem: {str(e)}")
            self.status_var.set(f"Erro ao carregar imagem: {str(e)}")

    def save_current_image(self):
        """Salva o estado atual da imagem"""
        if self.current_image_index is not None and self.user_image is not None:
            self.images[self.image_list[self.current_image_index]] = self.user_image.copy()
            self.image_states[self.image_list[self.current_image_index]] = {
                'pos': self.user_image_pos,
                'size': self.user_image_size
            }

    def restore_image_state(self):
        """Restaura o estado salvo da imagem"""
        if self.image_path in self.image_states:
            state = self.image_states[self.image_path]
            self.user_image_pos = state['pos']
            self.user_image_size = state['size']
            self.user_image = self.original_image.resize(self.user_image_size, Image.LANCZOS)

    def close_resources(self):
        """Libera os recursos de imagem"""
        if hasattr(self, 'original_image') and self.original_image:
            self.original_image.close()
            self.original_image = None
        if hasattr(self, 'user_image') and self.user_image:
            self.user_image.close()
            self.user_image = None

    def on_image_select(self, event):
        """Manipula a seleção de imagem na listbox"""
        if self.image_listbox.curselection():
            index = self.image_listbox.curselection()[0]
            if index != self.current_image_index:
                self.load_image(index)

    def resize_image(self, image, max_width, max_height):
        """Redimensiona uma imagem mantendo a proporção"""
        width_ratio = max_width / image.width
        height_ratio = max_height / image.height
        best_ratio = min(width_ratio, height_ratio)
        new_width = int(image.width * best_ratio)
        new_height = int(image.height * best_ratio)
        return image.resize((new_width, new_height), Image.LANCZOS)

    def cancel_image(self):
        """Cancela a edição atual e limpa todas as imagens"""
        if not self.image_list:
            return
        
        if messagebox.askyesno("Confirmar", "Deseja limpar todas as imagens?"):
            self.close_resources()
            self.image_path = None
            self.original_image = None
            self.user_image = None
            self.user_image_size = None
            self.image_list = []
            self.image_listbox.delete(0, tk.END)
            self.current_image_index = None
            self.images = {}
            self.image_states = {}
            self.update_canvas()
            self.status_var.set("Todas as imagens foram removidas")

    def update_canvas(self, *_):
        """Atualiza o canvas com a imagem atual e a borda"""
        self.canvas.delete("all")
                
        # Obtém as dimensões do canvas
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
                
        # Desenha um fundo mais claro para a área de edição
        self.canvas.create_rectangle(0, 0, canvas_width, canvas_height,
                                fill=COLORS["bg_medium"], outline="")
                
        # Posiciona a borda no centro do canvas
        borda_x = (canvas_width - 225) // 2
        borda_y = (canvas_height - 350) // 2
        self.borda_pos = (borda_x, borda_y)
                
        # Determina a cor da borda (geral ou individual)
        border_color = self.borda_hex[self.selected_borda.get()]
        if self.image_path in self.individual_bordas:
            individual_borda = self.individual_bordas[self.image_path]
            border_color = self.borda_hex[individual_borda]
                
        # Desenha uma área tracejada para representar a área de trabalho
        dash_pattern = (4, 4)
        self.canvas.create_rectangle(borda_x-5, borda_y-5, borda_x+230, borda_y+355,
                                outline=COLORS["text_dim"], dash=dash_pattern)
        
        # Desenha a imagem do usuário primeiro (agora antes da borda)
        if self.user_image:
            self.user_tk = ImageTk.PhotoImage(self.user_image)
            x, y = self.user_image_pos
            self.canvas.create_image(x, y, anchor=tk.NW, image=self.user_tk, tags="user_image")
                
        # Desenha a borda por último, para que fique por cima da imagem
        self.canvas.create_rectangle(borda_x, borda_y, borda_x+225, borda_y+350,
                                outline=border_color, width=2)

    # --- Funções de interação com canvas ---
    
    def select_image(self, event):
        """Inicia o processo de seleção da imagem para movimentação"""
        if self.user_image:
            x, y = self.user_image_pos
            width, height = self.user_image_size
            if x <= event.x <= x + width and y <= event.y <= y + height:
                self.selected_image = True
                self.start_x = event.x - x
                self.start_y = event.y - y
                self.save_state()
                self.status_var.set("Movendo imagem... (Shift para redimensionar)")
            else:
                self.selected_image = False

    def save_state(self):
        if self.current_image_index is not None and self.user_image is not None:
            self.undo_stack.append((self.user_image.copy(), self.user_image_pos, self.user_image_size))

    def move_image(self, event):
        """Move a imagem selecionada"""
        if self.user_image and self.selected_image:
            new_x = event.x - self.start_x
            new_y = event.y - self.start_y
            self.user_image_pos = (new_x, new_y)
            self.update_canvas()

    def release_image(self, _):
        """Finaliza o movimento da imagem"""
        if self.selected_image:
            self.selected_image = False
            self.status_var.set("Pronto")

    def resize_image_proportional(self, event):
        """Redimensiona a imagem proporcionalmente usando Shift+arraste"""
        if self.user_image and self.selected_image:
            x, y = self.user_image_pos
            orig_width, orig_height = self.user_image_size
            
            # Calcula o fator de escala
            dx = max(10, event.x - x)
            dy = max(10, event.y - y)
            
            # Mantém a proporção original
            aspect_ratio = orig_width / orig_height
            if dx / dy > aspect_ratio:
                dx = dy * aspect_ratio
            else:
                dy = dx / aspect_ratio
                
            # Aplica um limite mínimo
            new_width = max(20, int(dx))
            new_height = max(20, int(dy))
            
            # Redimensiona a imagem
            self.user_image = self.original_image.resize((new_width, new_height), Image.LANCZOS)
            self.user_image_size = (new_width, new_height)
            self.update_canvas()
            
            # Atualiza a mensagem de status
            self.status_var.set(f"Redimensionando: {new_width}x{new_height}px")

    # --- Funções de processamento de imagem ---
    
    def crop_image_to_borda(self, image, pos, size):
        """Recorta a imagem para se ajustar à borda"""
        borda_x, borda_y = self.borda_pos
        borda_width, borda_height = 225, 350
        user_x, user_y = pos
        
        # Calcula as coordenadas do recorte
        crop_x1 = max(0, borda_x - user_x)
        crop_y1 = max(0, borda_y - user_y)
        crop_x2 = min(size[0], crop_x1 + borda_width)
        crop_y2 = min(size[1], crop_y1 + borda_height)
        
        # Verifica se há área válida para recorte
        if crop_x2 <= crop_x1 or crop_y2 <= crop_y1:
            # Se não há área válida, cria uma imagem transparente do tamanho da borda
            return Image.new("RGBA", (borda_width, borda_height), (0, 0, 0, 0))
            
        return image.crop((crop_x1, crop_y1, crop_x2, crop_y2))

    def add_borda_to_image(self, image, image_path):
        """Adiciona uma borda à imagem"""
        # Determina a cor da borda
        if image_path in self.individual_bordas:
            borda_name = self.individual_bordas[image_path]
            border_color = self.borda_hex[borda_name]
        else:
            borda_name = self.selected_borda.get()
            border_color = self.borda_hex[borda_name]
        
        # Cria uma nova imagem transparente do tamanho da borda
        final_image = Image.new("RGBA", (225, 350), (0, 0, 0, 0))
        
        # Cola a imagem recortada
        final_image.paste(image, (0, 0))
        
        # Adiciona a borda
        draw = ImageDraw.Draw(final_image)
        draw.rectangle([0, 0, 224, 349], outline=border_color, width=2)
        
        return final_image

    # --- Funções de salvamento ---
    
    def show_save_menu(self, _=None):
        """Exibe o menu de opções de salvamento"""
        save_menu = Menu(self.root, tearoff=0, bg=COLORS["bg_medium"], fg=COLORS["text"], activebackground=COLORS["accent"])
        save_menu.add_command(label="Salvar Imagens", command=self.save_all_images)
        save_menu.add_command(label="Salvar em .zip", command=self.save_images_as_zip)
        save_menu.add_command(label="Publicar no Imgchest", command=self.upload_images_to_imgchest)
        save_menu.post(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def save_all_images(self):
        """Salva todas as imagens em uma pasta"""
        if not self.images and not self.image_list:
            messagebox.showwarning("Aviso", "Nenhuma imagem para salvar.")
            return
        
        # Salva a imagem atual
        self.save_current_image()
        
        # Solicita o diretório de destino
        save_dir = filedialog.askdirectory()
        if save_dir:
            self.status_var.set("Salvando imagens...")
            self.root.update_idletasks()
            
            count = 0
            for i, (path, image) in enumerate(self.images.items(), start=1):
                try:
                    if path in self.image_states:
                        state = self.image_states[path]
                        cropped_image = self.crop_image_to_borda(image, state['pos'], state['size'])
                        final_image = self.add_borda_to_image(cropped_image, path)
                        
                        # Usa o nome original do arquivo, mas adiciona um sufixo
                        original_name = os.path.basename(path)
                        name_without_ext = os.path.splitext(original_name)[0]
                        final_path = os.path.join(save_dir, f"{name_without_ext}_custom.png")
                        
                        final_image.save(final_path)
                        count += 1
                except Exception as e:
                    messagebox.showerror("Erro", f"Erro ao salvar {os.path.basename(path)}: {str(e)}")
            
            self.status_var.set(f"{count} imagens salvas com sucesso em {save_dir}")
            messagebox.showinfo("Concluído", f"{count} imagens foram salvas com sucesso.")

    def show_context_menu(self, event):
        try:
            self.image_listbox.selection_clear(0, tk.END)
            self.image_listbox.selection_set(self.image_listbox.nearest(event.y))
            self.context_menu.post(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
    
    def remove_from_list(self):
        selected_index = self.image_listbox.curselection()
        if selected_index:
            index = selected_index[0]
            image_path = self.image_list.pop(index)
            self.image_listbox.delete(index)
            if image_path in self.images:
                del self.images[image_path]
            if image_path in self.image_states:
                del self.image_states[image_path]
            if image_path in self.individual_bordas:
                del self.individual_bordas[image_path]
            self.current_image_index = None
            self.update_canvas()

    def toggle_individual_borda(self):
        selected_index = self.image_listbox.curselection()
        if selected_index:
            index = selected_index[0]
            image_path = self.image_list[index]
            if image_path in self.individual_bordas:
                del self.individual_bordas[image_path]
            else:
                self.individual_bordas[image_path] = self.selected_borda.get()
            self.update_canvas()

    def undo(self, _=None):
        if self.undo_stack:
            last_image, last_pos, last_size = self.undo_stack.pop()
            self.user_image = last_image
            self.user_image_pos = last_pos
            self.user_image_size = last_size
            self.update_canvas()

    def save_images_as_zip(self):
        """Salva todas as imagens em um arquivo ZIP"""
        if not self.images and not self.image_list:
            messagebox.showwarning("Aviso", "Nenhuma imagem para salvar.")
            return
        
        # Salva a imagem atual
        self.save_current_image()
        
        # Solicita o caminho do arquivo ZIP
        save_path = filedialog.asksaveasfilename(
            defaultextension=".zip",
            filetypes=[("ZIP files", "*.zip")],
            initialfile="custom_maker_images.zip"
        )
        
        if save_path:
            self.status_var.set("Criando arquivo ZIP...")
            self.root.update_idletasks()
            
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    count = 0
                    with zipfile.ZipFile(save_path, 'w') as zipf:
                        for i, (path, image) in enumerate(self.images.items(), start=1):
                            if path in self.image_states:
                                state = self.image_states[path]
                                cropped_image = self.crop_image_to_borda(image, state['pos'], state['size'])
                                final_image = self.add_borda_to_image(cropped_image, path)
                                
                                # Usa o nome original do arquivo
                                original_name = os.path.basename(path)
                                name_without_ext = os.path.splitext(original_name)[0]
                                image_path = os.path.join(temp_dir, f"{name_without_ext}_custom.png")
                                
                                final_image.save(image_path)
                                zipf.write(image_path, os.path.basename(image_path))
                                count += 1
                    self.status_var.set(f"{count} imagens salvas no arquivo ZIP: {save_path}")
                    messagebox.showinfo("Concluído", f"{count} imagens foram salvas no arquivo ZIP com sucesso.")
            except Exception as e:
                self.status_var.set("Erro ao criar o arquivo ZIP.")
                messagebox.showerror("Erro", f"Erro ao criar o arquivo ZIP: {str(e)}")

    def upload_images_to_imgchest(self):
        """Carrega todas as imagens para o ImgChest e gera os links"""
        self.uploaded_links = []
        
        # Verifica se há imagens para carregar
        if not self.images and not self.image_list:
            messagebox.showwarning("Aviso", "Nenhuma imagem para carregar.")
            return
            
        # Salva a imagem atual
        self.save_current_image()
        
        # Cria a janela de upload
        self.upload_window = tk.Toplevel(self.root)
        self.upload_window.title("Publicar no ImgChest")
        self.upload_window.geometry("500x500")
        self.upload_window.configure(bg='#2e2e2e')
        self.upload_window.transient(self.root)
        self.upload_window.grab_set()
        
        # Configura o estilo
        upload_style = ttk.Style()
        upload_style.configure("TLabel", background="#2e2e2e", foreground="white")
        
        # Campo para o nome do álbum
        lbl_nome = ttk.Label(self.upload_window, text="Nome do álbum:")
        lbl_nome.pack(pady=(20, 5))
        self.entry_nome = ttk.Entry(self.upload_window, width=40)
        self.entry_nome.pack(pady=5, fill="x", padx=20)
        
        # Opções de privacidade
        privacy_frame = ttk.Frame(self.upload_window)
        privacy_frame.pack(pady=10, fill="x", padx=20)
        
        self.privacy_var = tk.StringVar(value="hidden")
        lbl_privacy = ttk.Label(privacy_frame, text="Privacidade:")
        lbl_privacy.pack(side=tk.LEFT, padx=(0, 10))
        
        rb_hidden = ttk.Radiobutton(privacy_frame, text="Oculto", variable=self.privacy_var, value="hidden")
        rb_hidden.pack(side=tk.LEFT, padx=5)
        
        rb_public = ttk.Radiobutton(privacy_frame, text="Público", variable=self.privacy_var, value="public")
        rb_public.pack(side=tk.LEFT, padx=5)
        
        # Área de status
        self.upload_status_var = tk.StringVar(value="Aguardando...")
        upload_status_lbl = ttk.Label(self.upload_window, textvariable=self.upload_status_var)
        upload_status_lbl.pack(pady=5)
        
        # Barra de progresso
        self.upload_progress = ttk.Progressbar(self.upload_window, orient="horizontal", length=400, mode="determinate")
        self.upload_progress.pack(pady=10, padx=20)
        
        # Lista de links
        lbl_links = ttk.Label(self.upload_window, text="Links gerados:")
        lbl_links.pack(pady=(10, 5))
        
        links_frame = ttk.Frame(self.upload_window)
        links_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        self.links_listbox = tk.Listbox(links_frame, bg='#2e2e2e', fg='white', selectbackground='#4e4e4e', font=("Helvetica", 10))
        self.links_listbox.pack(side=tk.LEFT, fill="both", expand=True)
        links_scroll = ttk.Scrollbar(links_frame, orient=tk.VERTICAL, command=self.links_listbox.yview)
        links_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.links_listbox.config(yscrollcommand=links_scroll.set)
        
        # Botões
        buttons_frame = ttk.Frame(self.upload_window)
        buttons_frame.pack(fill="x", padx=20, pady=10)
        
        btn_copiar = ttk.Button(buttons_frame, text="Copiar comando Mudae", command=self.copy_links_command)
        btn_copiar.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
        
        btn_copiar_links = ttk.Button(buttons_frame, text="Copiar apenas links", command=self.copy_links_only)
        btn_copiar_links.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
        
        btn_cancelar = ttk.Button(buttons_frame, text="Fechar", command=self.upload_window.destroy)
        btn_cancelar.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
        
        # Inicia o upload
        self.upload_window.after(100, self.begin_upload)

    def begin_upload(self):
        """Inicia o processo de upload das imagens"""
        import requests
        
        # Verifica o token da API
        api_token = os.getenv('IMG_CHEST_API_TOKEN')
        if not api_token:
            self.upload_status_var.set("Erro: Token da API ImgChest não configurado no arquivo .env")
            messagebox.showerror("Erro", "Token da API ImgChest não configurado.\nVerifique o arquivo .env.")
            return
            
        headers = {
            'Authorization': f"Bearer {api_token}"
        }
        
        # Prepara as imagens
        images_to_upload = list(self.images.items())
        total_images = len(images_to_upload)
        self.upload_progress["maximum"] = total_images
        
        # Tamanho do lote para evitar sobrecarregar a API
        batch_size = 10
        temp_files = []
        
        try:
            for batch_start in range(0, total_images, batch_size):
                batch = images_to_upload[batch_start:batch_start + batch_size]
                files = []
                
                # Atualiza status
                self.upload_status_var.set(f"Preparando lote {batch_start//batch_size + 1} de {(total_images-1)//batch_size + 1}...")
                self.upload_window.update_idletasks()
                
                # Prepara as imagens do lote
                for path, image in batch:
                    if path in self.image_states:
                        state = self.image_states[path]
                        try:
                            cropped_image = self.crop_image_to_borda(image, state['pos'], state['size'])
                            final_image = self.add_borda_to_image(cropped_image, path)
                            
                            # Cria arquivo temporário
                            temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                            temp_files.append(temp_file.name)
                            
                            # Salva a imagem e adiciona ao lote
                            final_image.save(temp_file.name)
                            original_name = os.path.basename(path)
                            name_without_ext = os.path.splitext(original_name)[0]
                            files.append(('images[]', (f"{name_without_ext}_custom.png", open(temp_file.name, 'rb'), 'image/png')))
                        except Exception as e:
                            self.upload_status_var.set(f"Erro ao processar imagem: {os.path.basename(path)}")
                            print(f"Erro ao processar imagem: {str(e)}")
                            continue
                
                # Verifica se há imagens para enviar
                if not files:
                    continue
                    
                # Prepara os dados do post
                title = self.entry_nome.get().strip()
                if len(title) < 3:
                    title = "Custom Maker Images"
                
                # Faz o upload
                self.upload_status_var.set(f"Enviando lote {batch_start//batch_size + 1}...")
                self.upload_window.update_idletasks()
                
                try:
                    response = requests.post(
                        'https://api.imgchest.com/v1/post',
                        headers=headers,
                        files=files,
                        data={
                            'title': title,
                            'privacy': self.privacy_var.get(),
                            'anonymous': '1',
                            'nsfw': '0'  # Alterado para não marcar como nsfw por padrão
                        },
                        timeout=60  # Tempo limite razoável
                    )
                    
                    # Processa a resposta
                    if response.status_code == 200:
                        post_data = response.json()['data']
                        for image in post_data['images']:
                            link = image['link']
                            self.uploaded_links.append(link)
                            self.links_listbox.insert(tk.END, link)
                    else:
                        try:
                            error_message = response.json().get('message', 'Erro desconhecido')
                        except ValueError:
                            error_message = response.text
                        self.upload_status_var.set(f"Erro no lote {batch_start//batch_size + 1}: {error_message}")
                        print(f"Status Code: {response.status_code}")
                        print(f"Response Text: {response.text}")
                        
                except Exception as e:
                    self.upload_status_var.set(f"Erro de conexão: {str(e)}")
                    print(f"Erro de conexão: {str(e)}")
                    
                # Atualiza a barra de progresso
                self.upload_progress["value"] = min(batch_start + len(batch), total_images)
                self.upload_window.update_idletasks()
                
            # Finaliza
            if self.uploaded_links:
                self.upload_status_var.set(f"{len(self.uploaded_links)} imagens enviadas com sucesso!")
            else:
                self.upload_status_var.set("Nenhuma imagem foi enviada com sucesso.")
                
        except Exception as e:
            self.upload_status_var.set(f"Erro no upload: {str(e)}")
            messagebox.showerror("Erro", f"Ocorreu um erro durante o upload: {str(e)}")
        
        finally:
            # Limpa arquivos temporários
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.unlink(temp_file)
                except:
                    pass

    def copy_links_command(self):
        """Copia o comando do Mudae com os links para a área de transferência"""
        if not self.uploaded_links:
            messagebox.showwarning("Aviso", "Nenhum link para copiar.")
            return
            
        nome = self.entry_nome.get().strip()
        if not nome:
            nome = "CustomMaker"
            
        links_text = f"$ai {nome} $" + " $".join(self.uploaded_links)
        self.root.clipboard_clear()
        self.root.clipboard_append(links_text)
        messagebox.showinfo("Copiado", "Comando do Mudae copiado para a área de transferência.")

    def copy_links_only(self):
        """Copia apenas os links para a área de transferência"""
        if not self.uploaded_links:
            messagebox.showwarning("Aviso", "Nenhum link para copiar.")
            return
            
        links_text = "\n".join(self.uploaded_links)
        self.root.clipboard_clear()
        self.root.clipboard_append(links_text)
        messagebox.showinfo("Copiado", "Links copiados para a área de transferência.")