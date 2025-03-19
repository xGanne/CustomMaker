import tkinter as tk
from tkinter import filedialog, StringVar, messagebox, Menu
from tkinter import ttk
from PIL import Image, ImageTk, ImageDraw
from dotenv import load_dotenv
import cssutils
import os
import sys
import zipfile
import tempfile

load_dotenv()

class CustomMakerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Custom Maker")
        
        self.root.state('zoomed')
        self.root.configure(bg='#2e2e2e')
        
        self.borda_class = None
        self.image_path = None
        self.original_image = None
        self.user_image = None
        self.user_image_pos = (287, 25)
        self.user_image_size = None
        self.selected_image = False
        self.start_x = 0
        self.start_y = 0

        self.bordas = self.load_bordas()
        self.borda_names = {
            '.borda_red': 'Red', '.borda_blue': 'Blue', '.borda_green': 'Green', '.borda_yellow': 'Yellow',
            '.borda_purple': 'Purple', '.borda_orange': 'Orange', '.borda_white': 'White', '.borda_black': 'Black',
            '.borda_gray': 'Gray', '.borda_cyan': 'Cyan', '.borda_magenta': 'Magenta', '.borda_brown': 'Brown',
            '.borda_pink': 'Pink', '.borda_lime': 'Lime', '.borda_olive': 'Olive', '.borda_maroon': 'Maroon',
            '.borda_navy': 'Navy', '.borda_teal': 'Teal', '.borda_aqua': 'Aqua', '.borda_silver': 'Silver'
        }
        self.selected_borda = StringVar(self.root)
        self.selected_borda.set('White')

        self.images = {}
        self.image_states = {}
        self.image_list = []
        self.current_image_index = None
        self.undo_stack = []
        self.individual_bordas = {}
        self.uploaded_links = []

        self.create_widgets()
        self.root.after(100, self.update_canvas)
        self.root.bind('<Control-z>', self.undo)

    def load_bordas(self):
        css_file = self.resource_path("bordas.css")
        css_parser = cssutils.CSSParser()
        stylesheet = css_parser.parseFile(css_file)
        return [rule.selectorText for rule in stylesheet.cssRules if rule.type == rule.STYLE_RULE]

    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def create_widgets(self):
        style = ttk.Style()
        style.configure("TButton", font=("Helvetica", 10), padding=10, background="#555555", foreground="black")
        style.configure("TLabel", font=("Helvetica", 12, "bold"), background="#1e1e1e", foreground="white")
        style.configure("TFrame", background="#2e2e2e")
        style.configure("TListbox", background="#2e2e2e", foreground="white", selectbackground="#4e4e4e", font=("Helvetica", 10))

        self.left_frame = ttk.Frame(self.root)
        self.left_frame.grid(row=0, column=0, sticky="nsew")
        self.right_frame = ttk.Frame(self.root, width=300)
        self.right_frame.grid(row=0, column=1, sticky="ns")

        self.root.grid_columnconfigure(0, weight=100)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.left_frame, bg='#2e2e2e')
        self.canvas.pack(fill="both", expand=True, padx=20, pady=5)
        self.canvas.bind("<Button-1>", self.select_image)
        self.canvas.bind("<B1-Motion>", self.move_image)
        self.canvas.bind("<ButtonRelease-1>", self.release_image)
        self.canvas.bind("<Shift-B1-Motion>", self.resize_image_proportional)

        lbl_bordas = ttk.Label(self.right_frame, text="Escolher bordas")
        lbl_bordas.pack(pady=(20,5))
        borda_menu = ttk.OptionMenu(self.right_frame, self.selected_borda, self.selected_borda.get(), *[self.borda_names[borda] for borda in self.bordas], command=lambda _: self.update_canvas())
        borda_menu.pack(pady=5, fill="x", padx=10)
        
        lbl_pasta = ttk.Label(self.right_frame, text="Selecionar pasta")
        lbl_pasta.pack(pady=(20,5))
        btn_pasta = ttk.Button(self.right_frame, text="Selecionar pasta", command=self.select_folder)
        btn_pasta.pack(pady=5, fill="x", padx=10)

        btn_cancel = ttk.Button(self.right_frame, text="Cancelar", command=self.cancel_image)
        btn_cancel.pack(pady=5, fill="x", padx=10)

        btn_save = ttk.Button(self.right_frame, text="Salvar", command=self.show_save_menu)
        btn_save.pack(pady=5, fill="x", padx=10)

        sep = ttk.Separator(self.right_frame, orient="horizontal")
        sep.pack(fill="x", padx=10, pady=10)

        lbl_lista = ttk.Label(self.right_frame, text="Imagens")
        lbl_lista.pack(pady=(10,5))
        
        listbox_frame = ttk.Frame(self.right_frame)
        listbox_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.image_listbox = tk.Listbox(listbox_frame, bg='#2e2e2e', fg='white', selectbackground='#4e4e4e', font=("Helvetica", 10))
        self.image_listbox.pack(side=tk.LEFT, fill="both", expand=True)
        self.image_listbox.bind("<<ListboxSelect>>", self.on_image_select)
        self.image_listbox.bind("<Button-3>", self.show_context_menu)
        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.image_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.image_listbox.config(yscrollcommand=scrollbar.set)

        self.context_menu = Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Remover da lista", command=self.remove_from_list)
        self.context_menu.add_command(label="Borda individual", command=self.toggle_individual_borda)

    def show_save_menu(self, _=None):
        save_menu = Menu(self.root, tearoff=0)
        save_menu.add_command(label="Salvar Imagens", command=self.save_all_images)
        save_menu.add_command(label="Salvar em .zip", command=self.save_images_as_zip)
        save_menu.add_command(label="Publicar no Imgchest", command=self.upload_images_to_imgchest)
        save_menu.post(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def select_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.image_list = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            self.image_listbox.delete(0, tk.END)
            self.images = {}
            self.image_states = {}
            for image_path in self.image_list:
                self.image_listbox.insert(tk.END, os.path.basename(image_path))
            if self.image_list:
                self.load_image(0)

    def load_image(self, index):
        if self.current_image_index is not None:
            self.save_current_image()
        self.current_image_index = index
        self.image_path = self.image_list[index]
        self.original_image = Image.open(self.image_path)
        self.user_image = self.resize_image(self.original_image, 400, 300)
        self.user_image_size = self.user_image.size
        self.user_image_pos = ((800 - self.user_image_size[0]) // 2, (400 - self.user_image_size[1]) // 2)
        self.restore_image_state()
        self.update_canvas()

    def save_current_image(self):
        if self.current_image_index is not None and self.user_image is not None:
            self.images[self.image_list[self.current_image_index]] = self.user_image.copy()
            self.image_states[self.image_list[self.current_image_index]] = {
                'pos': self.user_image_pos,
                'size': self.user_image_size
            }

    def restore_image_state(self):
        if self.image_path in self.image_states:
            state = self.image_states[self.image_path]
            self.user_image_pos = state['pos']
            self.user_image_size = state['size']
            self.user_image = self.original_image.resize(self.user_image_size, Image.LANCZOS)

    def close_resources(self):
        if self.original_image:
            self.original_image.close()
            self.original_image = None
        if self.user_image:
            self.user_image.close()
            self.user_image = None

    def on_image_select(self, _):
        if self.image_listbox.curselection():
            index = self.image_listbox.curselection()[0]
            self.load_image(index)

    def insert_image(self):
        path = filedialog.askopenfilename(filetypes=[("Image files", "*.png;*.jpg;*.jpeg")])
        if path:
            self.image_path = path
            self.original_image = Image.open(self.image_path)
            self.user_image = self.resize_image(self.original_image, 400, 300)
            self.user_image_size = self.user_image.size
            self.user_image_pos = ((800 - self.user_image_size[0]) // 2, (400 - self.user_image_size[1]) // 2)
            self.update_canvas()

    def resize_image(self, image, max_width, max_height):
        width_ratio = max_width / image.width
        height_ratio = max_height / image.height
        best_ratio = min(width_ratio, height_ratio)
        new_width = int(image.width * best_ratio)
        new_height = int(image.height * best_ratio)
        return image.resize((new_width, new_height), Image.LANCZOS)

    def cancel_image(self):
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

    def update_canvas(self, *_):
        self.canvas.delete("all")
        if self.user_image:
            self.user_tk = ImageTk.PhotoImage(self.user_image)
            x, y = self.user_image_pos
            self.canvas.create_image(x, y, anchor=tk.NW, image=self.user_tk, tags="user_image")
        if self.selected_borda.get():
            borda_class = [key for key, value in self.borda_names.items() if value == self.selected_borda.get()][0]
            borda_x = (self.canvas.winfo_width() - 225) // 2
            borda_y = (self.canvas.winfo_height() - 350) // 2
            self.borda_pos = (borda_x, borda_y)
            border_color = borda_class.split('_')[1]
            if self.image_path in self.individual_bordas:
                individual_borda = self.individual_bordas[self.image_path]
                borda_class = [key for key, value in self.borda_names.items() if value == individual_borda][0]
                border_color = borda_class.split('_')[1]
            self.canvas.create_rectangle(borda_x, borda_y, borda_x + 225, borda_y + 350, outline=border_color, width=1, tags="borda")

    def select_image(self, event):
        if self.user_image:
            x, y = self.user_image_pos
            width, height = self.user_image_size
            if x <= event.x <= x + width and y <= event.y <= y + height:
                self.selected_image = True
                self.start_x = event.x - x
                self.start_y = event.y - y
                self.save_state()
            else:
                self.selected_image = False

    def move_image(self, event):
        if self.user_image and self.selected_image:
            new_x = event.x - self.start_x
            new_y = event.y - self.start_y
            self.user_image_pos = (new_x, new_y)
            self.update_canvas()

    def release_image(self, _):
        self.selected_image = False

    def resize_image_proportional(self, event):
        if self.user_image and self.selected_image:
            x, y = self.user_image_pos
            dx = event.x - x
            dy = event.y - y
            factor = min(dx / self.user_image_size[0], dy / self.user_image_size[1])
            new_width = max(1, int(self.user_image_size[0] * factor))
            new_height = max(1, int(self.user_image_size[1] * factor))
            self.user_image = self.original_image.resize((new_width, new_height), Image.LANCZOS)
            self.user_image_size = (new_width, new_height)
            self.update_canvas()
            self.save_state()

    def crop_image_to_borda(self, image, pos, size):
        borda_x, borda_y = self.borda_pos
        borda_width, borda_height = 225, 350
        user_x, user_y = pos
        crop_x1 = max(0, borda_x - user_x)
        crop_y1 = max(0, borda_y - user_y)
        crop_x2 = min(size[0], crop_x1 + borda_width)
        crop_y2 = min(size[1], crop_y1 + borda_height)
        return image.crop((crop_x1, crop_y1, crop_x2, crop_y2))

    def add_borda_to_image(self, image, image_path):
        if image_path in self.individual_bordas:
            borda_class = [key for key, value in self.borda_names.items() if value == self.individual_bordas[image_path]][0]
        else:
            borda_class = [key for key, value in self.borda_names.items() if value == self.selected_borda.get()][0]
        border_color = borda_class.split('_')[1]
        final_image = Image.new("RGBA", (225, 350), (0, 0, 0, 0))
        final_image.paste(image, (0, 0))
        draw = ImageDraw.Draw(final_image)
        draw.rectangle([0, 0, 224, 349], outline=border_color, width=1)
        return final_image

    def save_all_images(self):
        if not self.images:
            messagebox.showwarning("Aviso", "Nenhuma imagem para salvar.")
            return
        self.save_current_image()
        save_dir = filedialog.askdirectory()
        if save_dir:
            for i, (path, image) in enumerate(self.images.items(), start=1):
                if path in self.image_states:
                    state = self.image_states[path]
                    cropped_image = self.crop_image_to_borda(image, state['pos'], state['size'])
                    final_image = self.add_borda_to_image(cropped_image, path)
                    final_image.save(os.path.join(save_dir, f"imagem_{i}.png"))
            messagebox.showinfo("Informação", "Imagens salvas com sucesso.")

    def save_images_as_zip(self):
        if not self.images:
            messagebox.showwarning("Aviso", "Nenhuma imagem para salvar.")
            return
        self.save_current_image()
        save_path = filedialog.asksaveasfilename(defaultextension=".zip", filetypes=[("ZIP files", "*.zip")])
        if save_path:
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(save_path, 'w') as zipf:
                    for i, (path, image) in enumerate(self.images.items(), start=1):
                        if path in self.image_states:
                            state = self.image_states[path]
                            cropped_image = self.crop_image_to_borda(image, state['pos'], state['size'])
                            final_image = self.add_borda_to_image(cropped_image, path)
                            image_path = os.path.join(temp_dir, f"imagem_{i}.png")
                            final_image.save(image_path)
                            zipf.write(image_path, os.path.basename(image_path))
            messagebox.showinfo("Informação", "Imagens salvas como ZIP com sucesso.")

    def upload_images_to_imgchest(self):
        self.uploaded_links = []
        self.save_current_image()
        if not self.images:
            messagebox.showwarning("Aviso", "Nenhuma imagem para salvar.")
            return
        self.upload_window = tk.Toplevel(self.root)
        self.upload_window.title("Publicar no Imgchest")
        self.upload_window.geometry("400x400")
        self.upload_window.configure(bg='#2e2e2e')

        lbl_nome = ttk.Label(self.upload_window, text="Nome:")
        lbl_nome.pack(pady=(20, 5))
        self.entry_nome = ttk.Entry(self.upload_window)
        self.entry_nome.pack(pady=5, fill="x", padx=10)

        self.links_listbox = tk.Listbox(self.upload_window, bg='#2e2e2e', fg='white', selectbackground='#4e4e4e', font=("Helvetica", 10))
        self.links_listbox.pack(fill="both", expand=True, padx=10, pady=5)

        btn_copiar = ttk.Button(self.upload_window, text="Copiar", command=self.copy_links)
        btn_copiar.pack(pady=5, fill="x", padx=10)

        self.upload_images()

    def upload_images(self):
        import requests
        headers = {
            'Authorization': f"Bearer {os.getenv('IMG_CHEST_API_TOKEN')}"
        }
        files = []
        images_to_upload = list(self.images.items())
        batch_size = 20

        for batch_start in range(0, len(images_to_upload), batch_size):
            batch = images_to_upload[batch_start:batch_start + batch_size]
            files = []
            for path, image in batch:
                if path in self.image_states:
                    state = self.image_states[path]
                    cropped_image = self.crop_image_to_borda(image, state['pos'], state['size'])
                    final_image = self.add_borda_to_image(cropped_image, path)
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                        final_image.save(temp_file.name)
                        files.append(('images[]', (os.path.basename(temp_file.name), open(temp_file.name, 'rb'), 'image/png')))
            
            title = self.entry_nome.get()
            if len(title) < 3:
                title = "Untitled"
            
            response = requests.post(
                'https://api.imgchest.com/v1/post',
                headers=headers,
                files=files,
                data={
                    'title': title,
                    'privacy': 'hidden',
                    'anonymous': '1',
                    'nsfw': '1'
                }
            )
            
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
                messagebox.showerror("Erro", f"Falha ao fazer upload das imagens\n{error_message}")
                print(f"Status Code: {response.status_code}")
                print(f"Response Text: {response.text}")

    def copy_links(self):
        nome = self.entry_nome.get()
        links_text = f"$ai {nome} $" + " $".join(self.uploaded_links)
        self.root.clipboard_clear()
        self.root.clipboard_append(links_text)
        messagebox.showinfo("Informação", "Links copiados para a área de transferência.")

    def save_state(self):
        if self.current_image_index is not None and self.user_image is not None:
            self.undo_stack.append((self.user_image.copy(), self.user_image_pos, self.user_image_size))

    def undo(self, _=None):
        if self.undo_stack:
            last_image, last_pos, last_size = self.undo_stack.pop()
            self.user_image = last_image
            self.user_image_pos = last_pos
            self.user_image_size = last_size
            self.update_canvas()

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

if __name__ == "__main__":
    root = tk.Tk()
    app = CustomMakerApp(root)
    root.mainloop()