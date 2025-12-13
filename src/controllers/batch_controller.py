
import os
import threading
import tempfile
import zipfile
import shutil
from PIL import Image
from src.core.image_processor import ImageProcessor
from src.core.animation_processor import AnimationProcessor
from src.config.settings import BORDA_WIDTH, BORDA_HEIGHT

import concurrent.futures
from src.core.batch_worker import process_image_task

class BatchController:
    def __init__(self, app_context):
        self.app = app_context

    def _get_task_data(self, path, output_path=None):
        state = self.app.image_states.get(path)
        if not state: return None
        
        anim_type = self.app.animation_type.get()
        
        b_name = self.app.individual_bordas.get(path, self.app.selected_borda.get())
        if b_name == "Cor Personalizada":
            b_hex = self.app.custom_borda_hex_individual.get(path, self.app.custom_borda_hex)
        else:
            b_hex = self.app.borda_hex.get(b_name, '#FFFFFF')
            
        return {
            'path': path,
            'state': state,
            'borda_pos': self.app.borda_pos,
            'anim_type': anim_type,
            'border_color': b_hex,
            'output_path': output_path
        }

    def _run_batch(self, tasks, on_progress, on_finish):
        total = len(tasks)
        completed = 0
        results = []
        
        # Max workers = CPU count (default)
        with concurrent.futures.ProcessPoolExecutor() as executor:
            futures = {executor.submit(process_image_task, t): t for t in tasks}
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    res = future.result()
                    results.append(res)
                except Exception as e:
                    print(f"Batch Error: {e}")
                
                completed += 1
                if on_progress:
                    # Run UI callback in main thread
                    self.app.root.after(0, lambda c=completed: on_progress(c, total, f"Processando {c}/{total}"))
        
        if on_finish:
            self.app.root.after(0, lambda: on_finish(results))

    def save_all_images(self, target_dir, on_progress, on_finish):
        tasks = []
        is_anim = (self.app.animation_type.get() != "Nenhuma")
        ext = "_custom.webp" if is_anim else "_custom.png"
        
        for path in self.app.image_list:
            out = os.path.join(target_dir, os.path.splitext(os.path.basename(path))[0] + ext)
            data = self._get_task_data(path, out)
            if data: tasks.append(data)
            
        def finish_wrapper(results):
             if on_finish: on_finish()

        threading.Thread(target=self._run_batch, args=(tasks, on_progress, finish_wrapper), daemon=True).start()

    def save_zip(self, target_file, on_progress, on_finish):
        tmp_dir = tempfile.mkdtemp()
        tasks = []
        is_anim = (self.app.animation_type.get() != "Nenhuma")
        ext = ".webp" if is_anim else ".png"

        for path in self.app.image_list:
            fname = os.path.splitext(os.path.basename(path))[0] + f"_custom{ext}"
            out = os.path.join(tmp_dir, fname)
            data = self._get_task_data(path, out)
            if data: tasks.append(data)

        def zip_finish(results):
            try:
                # Zip in main thread or another thread? Better another thread to not freeze UI
                def zip_packaging():
                    with zipfile.ZipFile(target_file, 'w') as z:
                        for r in results:
                            if r['status'] == 'success' and 'saved_to' in r:
                                z.write(r['saved_to'], os.path.basename(r['saved_to']))
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    if on_finish: self.app.root.after(0, on_finish)
                
                threading.Thread(target=zip_packaging, daemon=True).start()
            except Exception as e:
                print(f"Zip Error: {e}")

        threading.Thread(target=self._run_batch, args=(tasks, on_progress, zip_finish), daemon=True).start()

    def upload_to_imgchest(self, title, on_progress, on_finish_links, on_error):
        tmp_dir = tempfile.mkdtemp()
        tasks = []
        is_anim = (self.app.animation_type.get() != "Nenhuma")
        ext = ".webp" if is_anim else ".png"

        for path in self.app.image_list:
            fname = os.path.splitext(os.path.basename(path))[0] + f"_custom{ext}"
            out = os.path.join(tmp_dir, fname)
            data = self._get_task_data(path, out)
            if data: tasks.append(data)

        def upload_finish(results):
            def upload_active():
                files = []
                for r in results:
                     if r['status'] == 'success' and 'saved_to' in r:
                         files.append({'path': r['saved_to'], 'filename': os.path.basename(r['saved_to'])})
                
                try:
                    if on_progress: self.app.root.after(0, lambda: on_progress(0, len(files), "Enviando..."))
                    links = self.app.uploader.upload_images(files, title)
                    if on_finish_links: self.app.root.after(0, lambda: on_finish_links(links))
                except Exception as e:
                    if on_error: self.app.root.after(0, lambda: on_error(str(e)))
                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)

            threading.Thread(target=upload_active, daemon=True).start()

        threading.Thread(target=self._run_batch, args=(tasks, on_progress, upload_finish), daemon=True).start()
