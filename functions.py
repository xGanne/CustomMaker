import os
import sys
import tempfile
import zipfile
from tkinter import filedialog, messagebox, Menu
import tkinter as tk
from tkinter import ttk
import cv2
import numpy as np
from PIL import Image, ImageTk, ImageDraw
import cssutils
from dotenv import load_dotenv
import time

from config import COLORS, BORDA_NAMES, BORDA_HEX, BORDA_WIDTH, BORDA_HEIGHT

class CustomMakerFunctions:
    def __init__(self):
        self.face_cascade = None
        try:
            cascade_file_name = "lbpcascade_animeface.xml"
            cascade_path = self.resource_path(cascade_file_name)
            if not os.path.exists(cascade_path) and not hasattr(sys, "_MEIPASS"):
                cwd_cascade_path = os.path.join(os.getcwd(), cascade_file_name)
                if os.path.exists(cwd_cascade_path):
                    cascade_path = cwd_cascade_path
            if not os.path.exists(cascade_path):
                 messagebox.showwarning("Aviso de Detector",
                                     f"Arquivo '{cascade_file_name}' não encontrado.\n"
                                     "A funcionalidade de 'Ajuste Inteligente' usará o modo de preenchimento simples.\n"
                                     f"Tentativa final de caminho: {cascade_path}")
                 print(f"AVISO: {cascade_file_name} não encontrado. Usando fallback.")
                 self.face_cascade = None
                 return
            self.face_cascade = cv2.CascadeClassifier(cv2.samples.findFile(cascade_path))
            if self.face_cascade.empty():
                messagebox.showerror("Erro de Detector",
                                     f"Falha ao carregar o classificador de faces de: {cascade_path}\n"
                                     "O 'Ajuste Inteligente' usará o modo de preenchimento simples.")
                print(f"ERRO: Falha ao carregar CascadeClassifier de {cascade_path}")
                self.face_cascade = None
            else:
                print(f"INFO: Detector de rostos OpenCV (LBP Cascade: {cascade_file_name}) carregado de {cascade_path}.")
        except Exception as e:
            print(f"ERRO CRÍTICO: Não foi possível carregar o classificador de faces OpenCV: {e}")
            messagebox.showerror("Erro de Detector",
                                 f"Não foi possível inicializar o detector de rostos OpenCV: {e}\n"
                                 "O 'Ajuste Inteligente' usará o modo de preenchimento simples.")
            self.face_cascade = None

    def load_resources(self):
        load_dotenv()
        self.bordas = self.load_bordas()
        self.borda_names = BORDA_NAMES
        self.borda_hex = BORDA_HEX

    def load_bordas(self):
        css_file = self.resource_path("bordas.css")
        if not os.path.exists(css_file) and not hasattr(sys, "_MEIPASS"):
            cwd_css_file = os.path.join(os.getcwd(), "bordas.css")
            if os.path.exists(cwd_css_file): css_file = cwd_css_file
        if not os.path.exists(css_file):
            messagebox.showerror("Erro de Recurso", f"Arquivo bordas.css não encontrado.\nTentativa: {css_file}")
            return []
        css_parser = cssutils.CSSParser()
        stylesheet = css_parser.parseFile(css_file)
        return [rule.selectorText for rule in stylesheet.cssRules if rule.type == rule.STYLE_RULE]

    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except AttributeError:
            base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, relative_path)

    def configure_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TFrame", background=COLORS["bg_dark"])
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
        style.configure("Accent.TButton",
                    background=COLORS["accent"],
                    foreground=COLORS["bg_dark"])
        style.map("Accent.TButton",
            background=[('active', COLORS["accent"]), ('pressed', COLORS["text_dim"])],
            foreground=[('active', COLORS["bg_dark"]), ('pressed', COLORS["bg_dark"])])
        style.configure("TLabel",
                    font=("Segoe UI", 10),
                    background=COLORS["bg_dark"],
                    foreground=COLORS["text"])
        style.configure("Title.TLabel",
                    font=("Segoe UI", 12, "bold"),
                    background=COLORS["bg_dark"],
                    foreground=COLORS["accent"])
        style.configure("TSeparator",
                    background=COLORS["bg_light"])
        style.configure("TCombobox",
                    selectbackground=COLORS["accent"],
                    fieldbackground=COLORS["bg_medium"],
                    background=COLORS["bg_light"],
                    foreground=COLORS["text"],
                    arrowcolor=COLORS["text"]) 
        style.map('TCombobox',
            fieldbackground=[('readonly', COLORS["bg_medium"])],
            selectbackground=[('readonly', COLORS["accent"])],
            selectforeground=[('readonly', COLORS["bg_dark"])],
            foreground=[('readonly', COLORS["text"])])
        style.configure("Vertical.TScrollbar",
                    background=COLORS["bg_medium"],
                    troughcolor=COLORS["bg_dark"],
                    arrowcolor=COLORS["text"])

    def select_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.status_var.set("Carregando imagens...")
            self.root.update_idletasks()
            self.image_list = [os.path.join(folder_path, f) for f in os.listdir(folder_path)
                          if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'))]
            self.image_listbox.delete(0, tk.END)
            self.images = {} 
            self.image_states = {} 
            self.individual_bordas = {} 
            self.undo_stack = [] 
            for image_path in self.image_list:
                self.image_listbox.insert(tk.END, os.path.basename(image_path))
            if self.image_list:
                self.current_image_index = -1 
                self.load_image(0)
                self.status_var.set(f"Carregadas {len(self.image_list)} imagens")
            else:
                self.original_image = None
                self.user_image = None
                self.update_canvas()
                self.status_var.set("Nenhuma imagem encontrada na pasta")

    def load_image(self, index, preserve_undo=False):
        if self.current_image_index is not None and self.current_image_index < len(self.image_list) :
             if self.image_path: 
                self.save_current_image_state() 
        self.current_image_index = index
        self.image_path = self.image_list[index]
        try:
            if hasattr(self, 'original_image') and self.original_image:
                self.original_image.close()
            self.original_image = Image.open(self.image_path).convert("RGBA")
            if self.image_path in self.image_states: 
                self.restore_image_state() 
            else: 
                if hasattr(self, 'user_image') and self.user_image: self.user_image.close()
                self.user_image = self.resize_image(self.original_image, 400, 300) 
                self.user_image_size = self.user_image.size
                canvas_width = self.canvas.winfo_width() if self.canvas.winfo_width() > 1 else 800
                canvas_height = self.canvas.winfo_height() if self.canvas.winfo_height() > 1 else 600
                self.user_image_pos = ((canvas_width - self.user_image_size[0]) // 2, 
                                       (canvas_height - self.user_image_size[1]) // 2)
            self.update_canvas()
            self.image_listbox.selection_clear(0, tk.END)
            self.image_listbox.selection_set(index)
            self.image_listbox.see(index) 
            filename = os.path.basename(self.image_path)
            self.status_var.set(f"Imagem carregada: {filename}")
            if not preserve_undo:
                self.undo_stack = [] 
            self.save_state() 
        except Exception as e:
            messagebox.showerror("Erro ao Carregar Imagem", f"Não foi possível carregar a imagem: {self.image_path}\n{str(e)}")
            self.status_var.set(f"Erro ao carregar imagem: {os.path.basename(self.image_path)}")

    def save_current_image_state(self):
        if self.image_path and self.user_image and self.user_image_pos and self.user_image_size:
            if self.image_path in self.images and self.images[self.image_path]:
                self.images[self.image_path].close()
            self.images[self.image_path] = self.user_image.copy()
            self.image_states[self.image_path] = {
                'pos': self.user_image_pos,
                'size': self.user_image_size
            }

    def restore_image_state(self):
        if self.image_path in self.images and self.image_path in self.image_states:
            if hasattr(self, 'user_image') and self.user_image: self.user_image.close()
            self.user_image = self.images[self.image_path].copy()
            state = self.image_states[self.image_path]
            self.user_image_pos = state['pos']
            self.user_image_size = state['size']

    def close_resources(self):
        if hasattr(self, 'original_image') and self.original_image:
            self.original_image.close(); self.original_image = None
        if hasattr(self, 'user_image') and self.user_image:
            self.user_image.close(); self.user_image = None
        for img_key in list(self.images.keys()): 
            if self.images[img_key]: self.images[img_key].close()
            del self.images[img_key]
        for state_tuple in self.undo_stack:
            if state_tuple[0]: state_tuple[0].close()
        self.undo_stack = []

    def on_image_select(self, event):
        selected_indices = self.image_listbox.curselection()
        if not selected_indices: return 
        index = selected_indices[0]
        if index != self.current_image_index: 
            self.load_image(index)

    def resize_image(self, image, max_width, max_height):
        if image is None: return None
        if image.width == 0 or image.height == 0: return image 
        width_ratio = max_width / image.width
        height_ratio = max_height / image.height
        best_ratio = min(width_ratio, height_ratio)
        new_width = int(image.width * best_ratio)
        new_height = int(image.height * best_ratio)
        new_width = max(1, new_width)
        new_height = max(1, new_height)
        return image.resize((new_width, new_height), Image.LANCZOS)

    def cancel_image(self):
        if not self.image_list and not self.original_image: 
            self.status_var.set("Nada para limpar.")
            return
        if messagebox.askyesno("Confirmar Limpeza", "Deseja remover todas as imagens da lista, limpar edições e cache?"):
            self.close_resources() 
            self.image_path = None
            self.user_image_size = None
            self.user_image_pos = (50,50) 
            self.image_list = []
            self.image_listbox.delete(0, tk.END)
            self.current_image_index = None
            self.images = {} 
            self.image_states = {} 
            self.individual_bordas = {}
            self.undo_stack = []
            self.update_canvas() 
            self.status_var.set("Todas as imagens e edições foram removidas.")

    def update_canvas(self, *_):
        self.canvas.delete("all")
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        if canvas_width <= 1 or canvas_height <= 1: 
            if hasattr(self, 'after_id_update_canvas'):
                 if self.root.winfo_exists(): self.root.after_cancel(self.after_id_update_canvas)
            if self.root.winfo_exists():
                self.after_id_update_canvas = self.root.after(50, self.update_canvas)
            return
        self.canvas.create_rectangle(0, 0, canvas_width, canvas_height, fill=COLORS["bg_medium"], outline="")
        borda_x = (canvas_width - BORDA_WIDTH) // 2
        borda_y = (canvas_height - BORDA_HEIGHT) // 2
        self.borda_pos = (borda_x, borda_y) 
        current_display_borda_name = self.selected_borda.get() 
        if self.image_path and self.image_path in self.individual_bordas:
            current_display_borda_name = self.individual_bordas[self.image_path] 
        border_color_hex = self.borda_hex.get(current_display_borda_name, self.borda_hex.get('White', '#FFFFFF')) 
        dash_pattern = (4, 4)
        self.canvas.create_rectangle(borda_x - 5, borda_y - 5, borda_x + BORDA_WIDTH + 5, borda_y + BORDA_HEIGHT + 5,
                                outline=COLORS["text_dim"], dash=dash_pattern, tags="area_trabalho")
        if self.user_image and self.user_image_pos and self.user_image_size:
            try:
                if not isinstance(self.user_image, Image.Image):
                    print("AVISO: self.user_image não é um objeto PIL.Image válido em update_canvas.")
                else:
                    self.user_tk = ImageTk.PhotoImage(self.user_image)
                    x_img, y_img = self.user_image_pos
                    self.canvas.create_image(x_img, y_img, anchor=tk.NW, image=self.user_tk, tags="user_image")
            except Exception as e:
                print(f"Erro ao criar PhotoImage para user_image em update_canvas: {e}")
        self.canvas.create_rectangle(borda_x, borda_y, borda_x + BORDA_WIDTH, borda_y + BORDA_HEIGHT,
                                outline=border_color_hex, width=2, tags="borda_visual")

    def select_image(self, event):
        if self.user_image and self.user_image_pos and self.user_image_size:
            x_img, y_img = self.user_image_pos
            w_img, h_img = self.user_image_size
            if x_img <= event.x <= x_img + w_img and y_img <= event.y <= y_img + h_img:
                self.selected_image = True
                self.start_x = event.x - x_img 
                self.start_y = event.y - y_img
                self.save_state() 
                self.status_var.set("Movendo imagem... (Shift+Arrastar para redimensionar)")
            else:
                self.selected_image = False
        else:
            self.selected_image = False

    def save_state(self):
        if self.user_image and self.user_image_pos and self.user_image_size:
            try:
                if isinstance(self.user_image, Image.Image):
                    self.undo_stack.append((self.user_image.copy(), self.user_image_pos, self.user_image_size))
                    if len(self.undo_stack) > 20: 
                        old_img_to_close, _, _ = self.undo_stack.pop(0)
                        if old_img_to_close: old_img_to_close.close()
                else:
                    print("AVISO: Tentativa de salvar estado com user_image inválido.")
            except Exception as e:
                print(f"Erro ao salvar estado para undo: {e}")

    def move_image(self, event):
        if self.user_image and self.selected_image: 
            new_x = event.x - self.start_x
            new_y = event.y - self.start_y
            self.user_image_pos = (new_x, new_y)
            self.update_canvas()

    def release_image(self, _):
        if self.selected_image:
            self.selected_image = False
            self.status_var.set("Pronto.")
            self.save_current_image_state() 

    def resize_image_proportional(self, event):
        if self.user_image and self.selected_image and self.original_image:
            img_canvas_x, img_canvas_y = self.user_image_pos 
            new_width_candidate = event.x - img_canvas_x
            new_height_candidate = event.y - img_canvas_y
            if new_width_candidate <= 10 or new_height_candidate <= 10: return 
            orig_w, orig_h = self.original_image.size
            if orig_w == 0 or orig_h == 0: return 
            aspect_ratio = orig_w / orig_h
            if new_width_candidate / aspect_ratio > new_height_candidate: 
                final_h = max(20, int(new_height_candidate))
                final_w = max(int(final_h * aspect_ratio), 20)
            else:
                final_w = max(20, int(new_width_candidate))
                final_h = max(int(final_w / aspect_ratio), 20)
            try:
                resized_original = self.original_image.resize((final_w, final_h), Image.LANCZOS)
                if self.user_image: self.user_image.close()
                self.user_image = resized_original
                self.user_image_size = (final_w, final_h)
                self.update_canvas()
                self.status_var.set(f"Redimensionando: {final_w}x{final_h}px")
            except Exception as e:
                print(f"Erro ao redimensionar proporcionalmente: {e}")

    def crop_image_to_borda(self, image_to_crop, image_pos_on_canvas, image_current_size):
        if not hasattr(self, 'borda_pos') or not self.borda_pos:
            self.update_canvas_if_ready() 
            if not hasattr(self, 'borda_pos') or not self.borda_pos: 
                canvas_width_fallback = 800; canvas_height_fallback = 600
                borda_canvas_x = (canvas_width_fallback - BORDA_WIDTH) // 2
                borda_canvas_y = (canvas_height_fallback - BORDA_HEIGHT) // 2
                print("AVISO: borda_pos não definido, usando fallback em crop_image_to_borda.")
            else: borda_canvas_x, borda_canvas_y = self.borda_pos
        else: borda_canvas_x, borda_canvas_y = self.borda_pos
        img_x_canvas, img_y_canvas = image_pos_on_canvas
        img_w, img_h = image_current_size
        crop_rel_x1 = max(0, borda_canvas_x - img_x_canvas)
        crop_rel_y1 = max(0, borda_canvas_y - img_y_canvas)
        crop_rel_x2 = min(img_w, borda_canvas_x + BORDA_WIDTH - img_x_canvas)
        crop_rel_y2 = min(img_h, borda_canvas_y + BORDA_HEIGHT - img_y_canvas)
        if crop_rel_x1 >= crop_rel_x2 or crop_rel_y1 >= crop_rel_y2:
            return Image.new("RGBA", (BORDA_WIDTH, BORDA_HEIGHT), (0, 0, 0, 0))
        content_to_paste = image_to_crop.crop((crop_rel_x1, crop_rel_y1, crop_rel_x2, crop_rel_y2))
        final_custom_area = Image.new("RGBA", (BORDA_WIDTH, BORDA_HEIGHT), (0, 0, 0, 0))
        paste_x_on_final = max(0, img_x_canvas - borda_canvas_x)
        paste_y_on_final = max(0, img_y_canvas - borda_canvas_y)
        final_custom_area.paste(content_to_paste, (paste_x_on_final, paste_y_on_final))
        if content_to_paste: content_to_paste.close() 
        return final_custom_area

    def add_borda_to_image(self, image_content_pil, image_path_key_for_borda_lookup):
        current_display_borda_name = self.selected_borda.get() 
        if image_path_key_for_borda_lookup in self.individual_bordas:
            current_display_borda_name = self.individual_bordas[image_path_key_for_borda_lookup]
        border_color_hex = self.borda_hex.get(current_display_borda_name, self.borda_hex.get('White', '#FFFFFF'))
        image_with_border = image_content_pil.copy()
        draw = ImageDraw.Draw(image_with_border)
        draw.rectangle([0, 0, BORDA_WIDTH - 1, BORDA_HEIGHT - 1], outline=border_color_hex, width=2)
        return image_with_border

    def show_save_menu(self, _=None):
        if not self.image_list:
            messagebox.showwarning("Aviso", "Nenhuma imagem na lista para salvar.")
            return
        if self.image_path: self.save_current_image_state()
        save_menu = Menu(self.root, tearoff=0, 
                         bg=COLORS["bg_medium"], fg=COLORS["text"], 
                         activebackground=COLORS["accent"], activeforeground=COLORS["bg_dark"])
        save_menu.add_command(label="Salvar Imagens Editadas", command=self.save_all_images)
        save_menu.add_command(label="Salvar em .zip", command=self.save_images_as_zip)
        save_menu.add_separator()
        save_menu.add_command(label="Publicar no ImgChest", command=self.upload_images_to_imgchest)
        try:
            if hasattr(self, 'btn_save_ref') and self.btn_save_ref:
                 x = self.btn_save_ref.winfo_rootx()
                 y = self.btn_save_ref.winfo_rooty() + self.btn_save_ref.winfo_height()
                 save_menu.post(x, y)
            else: save_menu.post(self.root.winfo_pointerx(), self.root.winfo_pointery())
        except: save_menu.post(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def _prepare_image_for_saving(self, image_path_key):
        base_image_for_processing = None
        pos_for_cropping = None
        size_for_cropping = None
        temp_original_image_local = None
        try:
            if self.image_path == image_path_key and self.original_image:
                if self.user_image_size and self.user_image_size[0] > 0 and self.user_image_size[1] > 0:
                    base_image_for_processing = self.original_image.resize(self.user_image_size, Image.LANCZOS)
                else: 
                    base_image_for_processing = self.original_image.copy() 
                pos_for_cropping = self.user_image_pos
                size_for_cropping = base_image_for_processing.size 
            elif image_path_key in self.image_states:
                state = self.image_states[image_path_key]
                target_size = state['size']
                pos_for_cropping = state['pos']
                try:
                    temp_original_image_local = Image.open(image_path_key).convert("RGBA")
                    base_image_for_processing = temp_original_image_local.resize(target_size, Image.LANCZOS)
                except Exception:
                    if image_path_key in self.images and self.images[image_path_key]:
                        base_image_for_processing = self.images[image_path_key].resize(target_size, Image.LANCZOS)
                    else: return None
                size_for_cropping = base_image_for_processing.size
            else:
                temp_original_image_local = Image.open(image_path_key).convert("RGBA")
                base_image_for_processing = self.resize_image(temp_original_image_local, BORDA_WIDTH * 2, BORDA_HEIGHT * 2)
                size_for_cropping = base_image_for_processing.size
                b_canvas_x, b_canvas_y = self.borda_pos if hasattr(self, 'borda_pos') and self.borda_pos else (400-BORDA_WIDTH//2, 300-BORDA_HEIGHT//2)
                pos_for_cropping = (b_canvas_x + (BORDA_WIDTH - size_for_cropping[0]) // 2, 
                                    b_canvas_y + (BORDA_HEIGHT - size_for_cropping[1]) // 2)
            if not base_image_for_processing or not pos_for_cropping or not size_for_cropping: return None
            cropped_content = self.crop_image_to_borda(base_image_for_processing, pos_for_cropping, size_for_cropping)
            final_image_with_border = self.add_borda_to_image(cropped_content, image_path_key)
            return final_image_with_border
        finally:
            if base_image_for_processing: base_image_for_processing.close()
            if temp_original_image_local: temp_original_image_local.close()

    def save_all_images(self):
        if not self.image_list: messagebox.showwarning("Aviso", "Nenhuma imagem na lista para salvar."); return
        if self.image_path: self.save_current_image_state()
        save_dir = filedialog.askdirectory(title="Selecione a pasta para salvar as imagens")
        if save_dir:
            self.status_var.set("Salvando imagens..."); self.root.update_idletasks()
            count_saved, count_failed = 0, 0
            for image_path_key in self.image_list:
                final_image_pil = None
                try:
                    final_image_pil = self._prepare_image_for_saving(image_path_key)
                    if final_image_pil:
                        original_name = os.path.basename(image_path_key)
                        name_without_ext, _ = os.path.splitext(original_name)
                        final_filename = f"{name_without_ext}_custom.png"
                        final_path = os.path.join(save_dir, final_filename)
                        final_image_pil.save(final_path, "PNG")
                        count_saved += 1
                    else: count_failed +=1
                except Exception as e:
                    count_failed +=1; messagebox.showerror("Erro ao Salvar", f"Erro ao salvar {os.path.basename(image_path_key)}:\n{str(e)}")
                finally:
                    if final_image_pil: final_image_pil.close()
            msg = f"{count_saved} salvas" + (f", {count_failed} falhas." if count_failed else ".")
            self.status_var.set(msg)
            messagebox.showinfo("Salvamento Concluído", f"{count_saved} imagens salvas em:\n{save_dir}" + (f"\n{count_failed} falharam." if count_failed else ""))

    def save_images_as_zip(self):
        if not self.image_list: messagebox.showwarning("Aviso", "Nenhuma imagem na lista para salvar em ZIP."); return
        if self.image_path: self.save_current_image_state()
        zip_save_path = filedialog.asksaveasfilename(defaultextension=".zip", filetypes=[("Arquivos ZIP", "*.zip")],
                                               initialfile="custom_maker_images.zip", title="Salvar imagens como ZIP")
        if zip_save_path:
            self.status_var.set("Criando arquivo ZIP..."); self.root.update_idletasks()
            count_zipped, count_failed_zip = 0, 0
            try:
                with tempfile.TemporaryDirectory() as temp_dir: 
                    with zipfile.ZipFile(zip_save_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for image_path_key in self.image_list:
                            final_image_pil = None
                            try:
                                final_image_pil = self._prepare_image_for_saving(image_path_key)
                                if final_image_pil:
                                    original_name = os.path.basename(image_path_key)
                                    name_without_ext, _ = os.path.splitext(original_name)
                                    temp_image_filename = f"{name_without_ext}_custom.png"
                                    temp_image_full_path = os.path.join(temp_dir, temp_image_filename)
                                    final_image_pil.save(temp_image_full_path, "PNG")
                                    zipf.write(temp_image_full_path, arcname=temp_image_filename)
                                    count_zipped += 1
                                else: count_failed_zip +=1
                            except Exception as e_zip_item:
                                count_failed_zip += 1; print(f"Erro ao processar {os.path.basename(image_path_key)} para ZIP: {e_zip_item}")
                            finally:
                                if final_image_pil: final_image_pil.close()
                msg_zip = f"{count_zipped} no ZIP" + (f", {count_failed_zip} falhas." if count_failed_zip else ".")
                self.status_var.set(msg_zip)
                messagebox.showinfo("ZIP Criado", f"{count_zipped} imagens salvas em:\n{zip_save_path}" + (f"\n{count_failed_zip} falharam." if count_failed_zip else ""))
            except Exception as e_zip_general:
                self.status_var.set("Erro crítico ao criar o ZIP."); messagebox.showerror("Erro ao Criar ZIP", f"Erro geral:\n{str(e_zip_general)}")

    def show_context_menu(self, event):
        try:
            clicked_idx = self.image_listbox.nearest(event.y)
            current_selection = self.image_listbox.curselection()
            if not current_selection or clicked_idx not in current_selection:
                self.image_listbox.selection_clear(0, tk.END)
                self.image_listbox.selection_set(clicked_idx)
                self.image_listbox.activate(clicked_idx) 
            self.image_list_context_menu.post(event.x_root, event.y_root)
        except tk.TclError: pass 

    def remove_from_list(self):
        selected_indices = self.image_listbox.curselection()
        if not selected_indices: messagebox.showwarning("Ação Inválida", "Nenhuma imagem selecionada.", parent=self.root); return
        index_to_remove = selected_indices[0] 
        if not (0 <= index_to_remove < len(self.image_list)): return
        image_path_key_removed = self.image_list.pop(index_to_remove)
        self.image_listbox.delete(index_to_remove)
        if image_path_key_removed in self.images:
            img_to_close = self.images.pop(image_path_key_removed)
            if img_to_close: img_to_close.close()
        if image_path_key_removed in self.image_states: del self.image_states[image_path_key_removed]
        if image_path_key_removed in self.individual_bordas: del self.individual_bordas[image_path_key_removed]
        self.status_var.set(f"'{os.path.basename(image_path_key_removed)}' removido.")
        if not self.image_list: 
            self.current_image_index = None; self.image_path = None
            if self.original_image: self.original_image.close(); self.original_image = None
            if self.user_image: self.user_image.close(); self.user_image = None
            self.update_canvas(); self.status_var.set("Lista de imagens vazia.")
        else:
            new_index_to_load = min(index_to_remove, len(self.image_list) - 1)
            if self.current_image_index == index_to_remove : 
                self.current_image_index = -1 
                self.load_image(new_index_to_load)
            elif self.current_image_index > index_to_remove: self.current_image_index -= 1

    def toggle_individual_borda(self):
        selected_indices = self.image_listbox.curselection()
        if not selected_indices: messagebox.showwarning("Ação Inválida", "Nenhuma imagem selecionada.", parent=self.root); return
        index = selected_indices[0]; image_path_key = self.image_list[index]
        img_basename = os.path.basename(image_path_key)
        if image_path_key in self.individual_bordas:
            del self.individual_bordas[image_path_key]
            self.status_var.set(f"Borda individual removida de '{img_basename}'.")
        else: 
            current_global_borda_name = self.selected_borda.get()
            self.individual_bordas[image_path_key] = current_global_borda_name
            self.status_var.set(f"Borda '{current_global_borda_name}' aplicada a '{img_basename}'.")
        if self.current_image_index == index: self.update_canvas()

    def undo(self, _=None):
        if self.undo_stack:
            if self.user_image: self.user_image.close()
            undone_image_pil, undone_pos, undone_size = self.undo_stack.pop()
            self.user_image = undone_image_pil 
            self.user_image_pos = undone_pos; self.user_image_size = undone_size
            self.update_canvas(); self.status_var.set("Última ação desfeita.")
        else: self.status_var.set("Nada para desfazer.")

    def upload_images_to_imgchest(self):
        if not self.image_list:
            messagebox.showwarning("Aviso", "Nenhuma imagem na lista para carregar.", parent=self.root)
            return
        if self.image_path: self.save_current_image_state()
        self.uploaded_links = []
        self.upload_window = tk.Toplevel(self.root)
        self.upload_window.title("Publicar no ImgChest")
        self.upload_window.geometry("550x600") 
        self.upload_window.configure(bg=COLORS["bg_dark"])
        self.upload_window.transient(self.root) 
        self.upload_window.grab_set() 
        upload_win_style = ttk.Style(self.upload_window)
        upload_win_style.theme_use('clam')
        upload_win_style.configure("TLabel", background=COLORS["bg_dark"], foreground=COLORS["text"])
        upload_win_style.configure("TEntry", fieldbackground=COLORS["bg_medium"], foreground=COLORS["text"])
        upload_win_style.configure("TRadiobutton", background=COLORS["bg_dark"], foreground=COLORS["text"], indicatorcolor=COLORS["text"])
        upload_win_style.map("TRadiobutton", foreground=[('active', COLORS["accent"])])
        upload_win_style.configure("TProgressbar", troughcolor=COLORS["bg_medium"], background=COLORS["accent"])
        upload_win_style.configure("TFrame", background=COLORS["bg_dark"])
        upload_win_style.configure("Upload.TButton", font=("Segoe UI", 10), background=COLORS["bg_light"], foreground=COLORS["text"])
        upload_win_style.map("Upload.TButton", background=[('active', COLORS["accent"])])
        lbl_nome = ttk.Label(self.upload_window, text="Nome do Personagem (para comando Mudae):") 
        lbl_nome.pack(pady=(15, 2), padx=20, anchor='w')
        self.entry_nome_album_upload = ttk.Entry(self.upload_window, width=50)
        self.entry_nome_album_upload.pack(pady=(0,10), fill="x", padx=20)
        privacy_frame = ttk.Frame(self.upload_window)
        privacy_frame.pack(pady=5, fill="x", padx=20)
        self.privacy_var_upload = tk.StringVar(value="hidden")
        lbl_privacy = ttk.Label(privacy_frame, text="Privacidade:")
        lbl_privacy.pack(side=tk.LEFT, padx=(0, 10))
        rb_hidden = ttk.Radiobutton(privacy_frame, text="Oculto", variable=self.privacy_var_upload, value="hidden")
        rb_hidden.pack(side=tk.LEFT, padx=5)
        rb_public = ttk.Radiobutton(privacy_frame, text="Público", variable=self.privacy_var_upload, value="public")
        rb_public.pack(side=tk.LEFT, padx=5)
        self.upload_status_var = tk.StringVar(value="Aguardando início...")
        upload_status_lbl = ttk.Label(self.upload_window, textvariable=self.upload_status_var, wraplength=500, justify=tk.LEFT)
        upload_status_lbl.pack(pady=5, padx=20, anchor='w')
        self.upload_progress_bar = ttk.Progressbar(self.upload_window, orient="horizontal", length=400, mode="determinate")
        self.upload_progress_bar.pack(pady=10, padx=20, fill='x')
        lbl_links = ttk.Label(self.upload_window, text="Links Gerados (um por linha):") 
        lbl_links.pack(pady=(10, 2), padx=20, anchor='w')
        self.links_text_widget_upload = tk.Text(self.upload_window, wrap=tk.WORD, height=8,
                                        bg=COLORS["bg_medium"], fg=COLORS["text"], 
                                        selectbackground=COLORS["accent"], selectforeground=COLORS["bg_dark"],
                                        font=("Segoe UI", 9), borderwidth=1, relief=tk.SUNKEN,
                                        highlightthickness=1, highlightbackground=COLORS["bg_light"])
        self.links_text_widget_upload.pack(fill="both", expand=True, padx=20, pady=(0,5))
        links_scroll_text = ttk.Scrollbar(self.links_text_widget_upload, orient=tk.VERTICAL, command=self.links_text_widget_upload.yview, style="Vertical.TScrollbar")
        links_scroll_text.pack(side=tk.RIGHT, fill=tk.Y)
        self.links_text_widget_upload.config(yscrollcommand=links_scroll_text.set)
        self.links_text_widget_upload.insert(tk.END, "Os links aparecerão aqui...\n")
        self.links_text_widget_upload.config(state=tk.DISABLED)
        buttons_frame = ttk.Frame(self.upload_window)
        buttons_frame.pack(fill="x", padx=20, pady=(10,15))
        self.btn_copiar_comando_upload = ttk.Button(buttons_frame, text="Copiar Comando Mudae", command=self.copy_mudae_command, state=tk.DISABLED, style="Upload.TButton")
        self.btn_copiar_comando_upload.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
        btn_fechar_upload = ttk.Button(buttons_frame, text="Fechar Janela", command=self.upload_window.destroy, style="Upload.TButton")
        btn_fechar_upload.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
        self.upload_window.after(200, self._begin_imgchest_upload_process_internal)

    def _begin_imgchest_upload_process_internal(self):
        import requests
        import shutil
        api_token = os.getenv('IMG_CHEST_API_TOKEN')
        if not api_token:
            self.upload_status_var.set("ERRO: Token da API ImgChest não configurado!"); messagebox.showerror("Erro de API", "Token não configurado.", parent=self.upload_window); self.upload_window.destroy(); return
        print(f"DEBUG: Using ImgChest Token: {api_token[:5]}...{api_token[-5:]}")
        headers = {'Authorization': f"Bearer {api_token}"}
        images_to_upload_paths = list(self.image_list)
        total_images = len(images_to_upload_paths)
        if total_images == 0: self.upload_status_var.set("Nenhuma imagem para enviar."); return
        try:
            from config import UPLOAD_BATCH_SIZE 
            batch_size = min(max(1, int(UPLOAD_BATCH_SIZE)), 20)
        except (ImportError, NameError, ValueError):
             batch_size = 20
        print(f"DEBUG: Upload batch size set to: {batch_size}")
        self.upload_progress_bar["maximum"] = total_images
        self.upload_progress_bar["value"] = 0
        temp_files_info = []
        temp_upload_dir = None 
        self.upload_status_var.set(f"Preparando {total_images} imagens..."); self.upload_window.update_idletasks()
        try:
            temp_upload_dir = tempfile.mkdtemp()
            for i, image_path_key in enumerate(images_to_upload_paths):
                self.upload_status_var.set(f"Processando {i+1}/{total_images}: {os.path.basename(image_path_key)}..."); self.upload_window.update_idletasks()
                final_image_pil = None
                try:
                    final_image_pil = self._prepare_image_for_saving(image_path_key)
                    if final_image_pil:
                        original_name = os.path.basename(image_path_key); name_without_ext, _ = os.path.splitext(original_name)
                        safe_filename = "".join(c if c.isalnum() or c in ['_','-','.'] else '_' for c in f"{name_without_ext}_custom.png")
                        temp_image_full_path = os.path.join(temp_upload_dir, safe_filename)
                        final_image_pil.save(temp_image_full_path, "PNG")
                        temp_files_info.append({'display_name': original_name, 'path': temp_image_full_path, 'server_filename': safe_filename})
                    else: print(f"Falha ao preparar {os.path.basename(image_path_key)} para upload.")
                except Exception as e_prep: print(f"Erro ao preparar {os.path.basename(image_path_key)}: {e_prep}")
                finally: 
                    if final_image_pil: final_image_pil.close()
            if not temp_files_info: self.upload_status_var.set("Nenhuma imagem preparada."); return
            all_uploaded_links_aggregate = []
            total_files_processed_in_upload = 0
            total_prepared_files = len(temp_files_info)
            total_batches = (total_prepared_files + batch_size - 1) // batch_size
            self.upload_progress_bar["value"] = 0
            self.upload_progress_bar["maximum"] = total_prepared_files
            base_album_title = self.entry_nome_album_upload.get().strip()
            if len(base_album_title) < 3: base_album_title = "CustomMaker"
            for i in range(0, total_prepared_files, batch_size):
                batch_files_info = temp_files_info[i : min(i + batch_size, total_prepared_files)]
                if not batch_files_info: continue
                batch_num = (i // batch_size) + 1
                self.upload_status_var.set(f"Enviando lote {batch_num}/{total_batches} ({len(batch_files_info)} imagens)..."); self.upload_window.update_idletasks()
                files_this_batch = []
                open_files_in_batch = []
                try:
                    files_this_batch = []
                    for f_info in batch_files_info:
                         file_obj = open(f_info['path'], 'rb')
                         open_files_in_batch.append(file_obj)
                         files_this_batch.append(('images[]', (f_info['server_filename'], file_obj, 'image/png')))
                    batch_title = f"{base_album_title} (Parte {batch_num})" if total_batches > 1 else base_album_title
                    if len(batch_title) < 3: batch_title = f"Customs_Part_{batch_num}"
                    payload_this_batch = {'title': batch_title, 'privacy': self.privacy_var_upload.get(), 'anonymous': '1', 'nsfw': '1'}
                    print(f"DEBUG: Enviando Lote {batch_num}, Payload: {payload_this_batch}")
                    response = requests.post('https://api.imgchest.com/v1/post', headers=headers, files=files_this_batch, data=payload_this_batch, timeout=120)
                    print(f"DEBUG: Lote {batch_num} - Status: {response.status_code}")
                    response_text_preview = response.text[:500] + ('...' if len(response.text) > 500 else '')
                    print(f"DEBUG: Lote {batch_num} - Resposta (prévia):\n'''\n{response_text_preview}\n'''")
                    if response.status_code == 200:
                        try:
                            response_data = response.json()
                            if isinstance(response_data, dict) and 'data' in response_data and isinstance(response_data['data'], dict) and 'images' in response_data['data'] and isinstance(response_data['data']['images'], list):
                                batch_image_data = response_data['data']['images']
                                batch_links = [img['link'] for img in batch_image_data if 'link' in img]
                                if batch_links:
                                    all_uploaded_links_aggregate.extend(batch_links)
                                    print(f"INFO: Lote {batch_num} bem-sucedido, {len(batch_links)} links adicionados.")
                                else:
                                    print(f"AVISO: Lote {batch_num} retornou sucesso, mas sem links válidos nos dados.")
                            else:
                                print(f"ERRO: Lote {batch_num} - Estrutura JSON inesperada: {response_data}")
                        except requests.exceptions.JSONDecodeError:
                            print(f"ERRO: Lote {batch_num} - Resposta 200 OK não era JSON: {response.text[:300]}")
                    else:
                        error_details = response.text[:300]
                        try: error_details = response.json().get('message', error_details)
                        except ValueError: pass
                        print(f"ERRO: Lote {batch_num} falhou - HTTP {response.status_code}: {error_details}")
                except requests.exceptions.RequestException as batch_req_ex:
                     print(f"ERRO de Rede no lote {batch_num}: {batch_req_ex}")
                except Exception as batch_ex:
                     print(f"ERRO inesperado no lote {batch_num}: {batch_ex}")
                finally:
                    for file_obj in open_files_in_batch:
                        if hasattr(file_obj, 'close'):
                            file_obj.close()
                    total_files_processed_in_upload += len(batch_files_info)
                    self.upload_progress_bar["value"] = total_files_processed_in_upload
                    self.upload_window.update_idletasks()
                    time.sleep(0.5) 
            self.uploaded_links = all_uploaded_links_aggregate
            if not self.uploaded_links:
                self.upload_status_var.set("Falha no upload. Nenhum link foi retornado.")
                messagebox.showerror("Falha no Upload", "Nenhuma imagem foi enviada com sucesso após processar todos os lotes.", parent=self.upload_window)
            else:
                links_display_text = "\n".join(self.uploaded_links)
                self.links_text_widget_upload.config(state=tk.NORMAL); self.links_text_widget_upload.delete('1.0', tk.END)
                self.links_text_widget_upload.insert(tk.END, links_display_text); self.links_text_widget_upload.config(state=tk.DISABLED)
                self.btn_copiar_comando_upload.config(state=tk.NORMAL)
                num_failures = total_prepared_files - len(self.uploaded_links)
                final_status = f"{len(self.uploaded_links)} links gerados."
                if num_failures > 0: final_status += f" ({num_failures} imagens podem ter falhado - ver console)."
                self.upload_status_var.set(final_status)
                messagebox.showinfo("Upload Concluído", final_status + "\nVerifique os links gerados.", parent=self.upload_window)
        except Exception as e_outer:
            print(f"ERRO Geral no Processo de Upload: {e_outer}")
            messagebox.showerror("Erro Crítico no Upload", f"Erro: {e_outer}", parent=self.upload_window)
            self.upload_status_var.set(f"Erro Crítico: {e_outer}")
        finally:
            if temp_upload_dir and os.path.exists(temp_upload_dir):
                try:
                    shutil.rmtree(temp_upload_dir)
                    print(f"DEBUG: Diretório temporário {temp_upload_dir} removido.")
                except Exception as e_clean:
                    print(f"Aviso: Falha ao limpar diretório temporário de upload {temp_upload_dir}: {e_clean}")

    def copy_mudae_command(self):
        if not self.uploaded_links:
            messagebox.showwarning("Aviso", "Nenhum link de imagem disponível para gerar o comando.", parent=self.upload_window if hasattr(self, 'upload_window') and self.upload_window.winfo_exists() else self.root)
            return
        character_name_for_mudae = self.entry_nome_album_upload.get().strip()
        if not character_name_for_mudae:
            if self.image_list: 
                character_name_for_mudae = os.path.splitext(os.path.basename(self.image_list[0]))[0]
            else:
                character_name_for_mudae = "Personagem" 
            print(f"AVISO: Nome do personagem não inserido, usando fallback '{character_name_for_mudae}' para o comando Mudae.")
        mudae_command = f"$ai {character_name_for_mudae} $" + " $".join(self.uploaded_links)
        parent_window = self.upload_window if hasattr(self, 'upload_window') and self.upload_window.winfo_exists() else self.root
        try:
            parent_window.clipboard_clear()
            parent_window.clipboard_append(mudae_command)
            if hasattr(self, 'upload_status_var'):
                 self.upload_status_var.set(f"Comando para '{character_name_for_mudae}' copiado!")
            messagebox.showinfo("Copiado", f"Comando Mudae para '{character_name_for_mudae}' copiado!", parent=parent_window)
        except Exception as e:
            if hasattr(self, 'upload_status_var'):
                 self.upload_status_var.set(f"Erro ao copiar: {e}")
            messagebox.showerror("Erro ao Copiar", f"Não foi possível copiar para a área de transferência:\n{e}", parent=parent_window)
    
    def intelligent_auto_frame(self):
        if not self.original_image: messagebox.showwarning("Aviso", "Nenhuma imagem carregada."); return
        if not self.face_cascade:
            messagebox.showinfo("Ajuste Inteligente", "Detector de rostos não carregado.\nUsando ajuste de preenchimento simples.", icon='info')
            self.auto_fit_image(); return
        self.save_state() 
        try:
            open_cv_image_rgb = np.array(self.original_image.convert('RGB'))
            open_cv_image_bgr = cv2.cvtColor(open_cv_image_rgb, cv2.COLOR_RGB2BGR)
            gray_image = cv2.cvtColor(open_cv_image_bgr, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray_image, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
        except Exception as e:
            messagebox.showerror("Erro de Detecção", f"OpenCV: {e}\nUsando fallback."); self.auto_fit_image(); return
        if len(faces) == 0: self.status_var.set("Nenhum rosto (OpenCV). Usando fallback."); self.auto_fit_image(); return
        best_face = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)[0]
        fx, fy, fw, fh = best_face
        if fh == 0 or fw == 0: self.status_var.set("Rosto com dimensão zero. Usando fallback."); self.auto_fit_image(); return
        target_face_height_ratio, target_face_top_margin_ratio = 0.55, 0.12
        scale_factor = (target_face_height_ratio * BORDA_HEIGHT) / fh
        new_w, new_h = int(self.original_image.width*scale_factor), int(self.original_image.height*scale_factor)
        if new_w < 1 or new_h < 1: self.status_var.set("Erro de escala. Usando fallback."); self.auto_fit_image(); return
        if self.user_image: self.user_image.close()
        self.user_image = self.original_image.resize((new_w, new_h), Image.LANCZOS)
        self.user_image_size = self.user_image.size
        sfx, sfy, sfw = fx*scale_factor, fy*scale_factor, fw*scale_factor
        if not hasattr(self, 'borda_pos') or not self.borda_pos: self.update_canvas()
        if not hasattr(self, 'borda_pos') or not self.borda_pos: messagebox.showerror("Erro Interno", "Posição da borda não definida."); return
        bx, by = self.borda_pos
        pos_x = int(bx + (BORDA_WIDTH/2) - (sfx + sfw/2))
        pos_y = int(by + (BORDA_HEIGHT*target_face_top_margin_ratio) - sfy)
        self.user_image_pos = (pos_x, pos_y)
        self.update_canvas(); self.status_var.set("Enquadrado (OpenCV).")

    def auto_fit_image(self):
        if not self.original_image: return
        self.save_state()
        orig_w, orig_h = self.original_image.size
        scale_w, scale_h = BORDA_WIDTH/orig_w, BORDA_HEIGHT/orig_h
        scale_factor = max(scale_w, scale_h) 
        new_w, new_h = int(orig_w*scale_factor), int(orig_h*scale_factor)
        if new_w < 1 or new_h < 1: self.status_var.set("Falha no auto_fit."); return
        if self.user_image: self.user_image.close()
        self.user_image = self.original_image.resize((new_w, new_h), Image.LANCZOS)
        self.user_image_size = self.user_image.size
        if not hasattr(self, 'borda_pos') or not self.borda_pos: self.update_canvas()
        if not hasattr(self, 'borda_pos') or not self.borda_pos: messagebox.showerror("Erro Interno", "Posição da borda não definida (auto_fit)."); return
        bx, by = self.borda_pos
        self.user_image_pos = (bx + (BORDA_WIDTH-new_w)//2, by + (BORDA_HEIGHT-new_h)//2)
        self.update_canvas(); self.status_var.set("Ajustado para preencher (simples).")

    def apply_adjustment_to_all(self, adjustment_function, adjustment_name):
        if not self.image_list:
            self.status_var.set("Nenhuma imagem na lista.")
            return
        total_images = len(self.image_list)
        original_selection_index = self.current_image_index
        progress_window = tk.Toplevel(self.root)
        progress_window.title(f"Aplicando {adjustment_name}...")
        progress_window.geometry("350x100")
        progress_window.transient(self.root)
        progress_window.grab_set()
        progress_window.resizable(False, False)
        ttk.Label(progress_window, text=f"Processando {total_images} imagens...", padding=(10,10)).pack()
        progress_bar = ttk.Progressbar(progress_window, orient="horizontal", length=300, mode="determinate", maximum=total_images)
        progress_bar.pack(pady=10)
        progress_label_var = tk.StringVar()
        ttk.Label(progress_window, textvariable=progress_label_var).pack()
        for i, image_path_key in enumerate(self.image_list):
            progress_label_var.set(f"{i+1}/{total_images}: {os.path.basename(image_path_key)}")
            progress_bar['value'] = i + 1
            progress_window.update_idletasks()
            is_current_image = (self.current_image_index == i)
            if not is_current_image:
                if image_path_key in self.image_states and image_path_key in self.images:
                    self.original_image = Image.open(image_path_key).convert("RGBA")
                else:
                    self.original_image = Image.open(image_path_key).convert("RGBA")
                current_original_image_backup = self.original_image
                current_user_image_backup = self.user_image.copy() if self.user_image else None
                current_user_pos_backup = self.user_image_pos
                current_user_size_backup = self.user_image_size
                current_image_path_backup = self.image_path
                self.image_path = image_path_key
                if self.original_image: self.original_image.close()
                self.original_image = Image.open(image_path_key).convert("RGBA")
                adjustment_function()
                self.save_current_image_state()
                self.image_path = current_image_path_backup
                if self.original_image: self.original_image.close()
                self.original_image = current_original_image_backup
                if self.user_image: self.user_image.close()
                self.user_image = current_user_image_backup
                self.user_image_pos = current_user_pos_backup
                self.user_image_size = current_user_size_backup
            else:
                adjustment_function()
                self.save_current_image_state()
        progress_window.destroy()
        if original_selection_index is not None and 0 <= original_selection_index < len(self.image_list):
            if self.current_image_index != original_selection_index:
                self.load_image(original_selection_index, preserve_undo=True)
            else:
                self.update_canvas()
        elif self.image_list:
             self.load_image(0, preserve_undo=True)
        self.status_var.set(f"'{adjustment_name}' aplicado a todas as {total_images} imagens.")
        messagebox.showinfo("Processo Concluído", f"'{adjustment_name}' foi aplicado a todas as imagens.", parent=self.root)
