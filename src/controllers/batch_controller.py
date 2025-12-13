
import os
import threading
import tempfile
import zipfile
import shutil
from PIL import Image
from src.core.image_processor import ImageProcessor
from src.core.animation_processor import AnimationProcessor
from src.config.settings import BORDA_WIDTH, BORDA_HEIGHT

class BatchController:
    def __init__(self, app_context):
        """
        app_context: Reference to the CustomMakerApp instance to access state.
                     (image_states, animation_type, bordas, etc.)
        """
        self.app = app_context

    def _prepare_animated_gif(self, path):
        # Access state from app
        state = self.app.image_states.get(path)
        if not state: return None, None
        
        anim_type = self.app.animation_type.get()
        if anim_type == "Nenhuma": return None, None

        try:
             orig = Image.open(path).convert("RGBA")
             resized = orig.resize(state['size'], Image.LANCZOS)
             cropped = ImageProcessor.crop_image_to_borda(resized, state['pos'], state['size'], self.app.borda_pos)
             
             frames = []
             duration = 50
             
             # Get Color
             b_name = self.app.individual_bordas.get(path, self.app.selected_borda.get())
             if b_name == "Cor Personalizada":
                 b_hex = self.app.custom_borda_hex_individual.get(path, self.app.custom_borda_hex)
             else:
                 b_hex = self.app.borda_hex.get(b_name, '#FFFFFF')

             if anim_type == "Rainbow":
                 frames, duration = AnimationProcessor.generate_rainbow_frames(cropped, total_frames=40, border_width=10)
             elif anim_type == "Neon Pulsante":
                 frames, duration = AnimationProcessor.generate_neon_frames(cropped, b_hex, total_frames=40, border_width=10)
             elif anim_type == "Strobe (Pisca)":
                 frames, duration = AnimationProcessor.generate_strobe_frames(cropped, total_frames=10, border_width=10)
             else:
                 # Default fallback
                 frames, duration = AnimationProcessor.generate_rainbow_frames(cropped, total_frames=40, border_width=10)
             
             # Enforce strict dimensions
             final_frames = []
             for f in frames:
                 if f.size != (BORDA_WIDTH, BORDA_HEIGHT):
                     f = f.resize((BORDA_WIDTH, BORDA_HEIGHT), Image.LANCZOS)
                 final_frames.append(f)

             orig.close()
             return final_frames, duration
        except Exception as e: 
             print(f"Gif/WebP error: {e}")
             return None, None

    def _prepare_final_image(self, path):
        state = self.app.image_states.get(path)
        if not state: return None
        try:
             orig = Image.open(path).convert("RGBA")
             resized = orig.resize(state['size'], Image.LANCZOS)
             cropped = ImageProcessor.crop_image_to_borda(resized, state['pos'], state['size'], self.app.borda_pos)
             b_name = self.app.individual_bordas.get(path, self.app.selected_borda.get())
             if b_name == "Cor Personalizada":
                 b_hex = self.app.custom_borda_hex_individual.get(path, self.app.custom_borda_hex)
             else:
                 b_hex = self.app.borda_hex.get(b_name, '#FFFFFF')
             final = ImageProcessor.add_borda_to_image(cropped, b_hex)
             orig.close()
             return final
        except Exception: return None

    def save_all_images(self, target_dir, on_progress, on_finish):
        """
        target_dir: Directory to save files
        on_progress(current, total, message): Callback for UI updates
        on_finish(): Callback when done
        """
        is_anim = (self.app.animation_type.get() != "Nenhuma")
        images = self.app.image_list
        total = len(images)

        def task():
            count = 0
            for i, path in enumerate(images):
                try:
                    if is_anim:
                        frames, duration = self._prepare_animated_gif(path)
                        if frames:
                            out = os.path.join(target_dir, os.path.splitext(os.path.basename(path))[0] + "_custom.webp")
                            frames[0].save(out, save_all=True, append_images=frames[1:], loop=0, duration=duration, optimize=True, quality=90)
                    else:
                        img = self._prepare_final_image(path)
                        if img:
                            out = os.path.join(target_dir, os.path.splitext(os.path.basename(path))[0] + "_custom.png")
                            img.save(out)
                            
                    count += 1
                    if on_progress:
                        # Use app.root.after to ensure thread safety for UI callbacks
                        self.app.root.after(0, lambda c=count: on_progress(c, total, f"Salvando {c}/{total}"))
                except Exception as e:
                    print(f"Error saving {path}: {e}")
            
            if on_finish:
                self.app.root.after(0, on_finish)

        threading.Thread(target=task, daemon=True).start()

    def save_zip(self, target_file, on_progress, on_finish):
        is_anim = (self.app.animation_type.get() != "Nenhuma")
        images = self.app.image_list
        total = len(images)

        def task():
            with zipfile.ZipFile(target_file, 'w') as z:
                for i, path in enumerate(images):
                    try:
                        if on_progress:
                            self.app.root.after(0, lambda v=i: on_progress(v, total, f"Processando {os.path.basename(path)}..."))
                        
                        if is_anim:
                            frames, duration = self._prepare_animated_gif(path)
                            if frames:
                                with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as tmp:
                                    frames[0].save(tmp.name, save_all=True, append_images=frames[1:], loop=0, duration=duration, optimize=True, quality=90)
                                    tmp_name = tmp.name
                                z.write(tmp_name, os.path.splitext(os.path.basename(path))[0] + "_custom.webp")
                                os.unlink(tmp_name)
                        else:
                            img = self._prepare_final_image(path)
                            if img:
                                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                                    img.save(tmp.name)
                                    tmp_name = tmp.name
                                z.write(tmp_name, os.path.splitext(os.path.basename(path))[0] + "_custom.png")
                                os.unlink(tmp_name)
                    except Exception as e:
                        print(f"Zip error {path}: {e}")

            if on_finish:
                self.app.root.after(0, on_finish)

        threading.Thread(target=task, daemon=True).start()

    def upload_to_imgchest(self, title, on_progress, on_finish_links, on_error):
        is_anim = (self.app.animation_type.get() != "Nenhuma")
        images = self.app.image_list
        total = len(images)
        uploader = self.app.uploader

        def task():
            files = []
            tmp_dir = tempfile.mkdtemp()
            try:
                for i, path in enumerate(images):
                    if on_progress:
                        self.app.root.after(0, lambda v=i: on_progress(0, total, f"Preparando {os.path.basename(path)}..."))
                    
                    if is_anim:
                        frames, duration = self._prepare_animated_gif(path)
                        if frames:
                            fname = os.path.splitext(os.path.basename(path))[0] + "_custom.webp"
                            fpath = os.path.join(tmp_dir, fname)
                            frames[0].save(fpath, save_all=True, append_images=frames[1:], loop=0, duration=duration, optimize=True, quality=90)
                            files.append({'path': fpath, 'filename': fname})
                    else:
                        img = self._prepare_final_image(path)
                        if img:
                            fname = os.path.splitext(os.path.basename(path))[0] + "_custom.png"
                            fpath = os.path.join(tmp_dir, fname)
                            img.save(fpath)
                            files.append({'path': fpath, 'filename': fname})
                
                if on_progress:
                    self.app.root.after(0, lambda: on_progress(0, total, "Enviando para ImgChest..."))
                
                links = uploader.upload_images(files, title)
                if on_finish_links:
                    self.app.root.after(0, lambda: on_finish_links(links))
            except Exception as e:
                if on_error:
                    self.app.root.after(0, lambda: on_error(str(e)))
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
        
        threading.Thread(target=task, daemon=True).start()
