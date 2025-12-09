import os
import shutil
import tempfile
import time
import requests
from src.config.settings import IMG_CHEST_API_TOKEN, UPLOAD_BATCH_SIZE

class ImgChestUploader:
    def __init__(self, api_token=None):
        self.api_token = api_token or IMG_CHEST_API_TOKEN
        
    def upload_images(self, images_data, album_title, privacy="hidden", progress_callback=None):
        """
        Uploads images to ImgChest.
        images_data: List of dicts {'path': str, 'filename': str}
        progress_callback: function(current, total, status_message)
        Returns: strict list of links or raises Exception.
        """
        if not self.api_token:
            raise ValueError("Token da API ImgChest não configurado.")

        headers = {'Authorization': f"Bearer {self.api_token}"}
        total_images = len(images_data)
        if total_images == 0: return []

        try:
            batch_size = min(max(1, int(UPLOAD_BATCH_SIZE)), 20)
        except (ValueError, TypeError):
            batch_size = 20

        all_uploaded_links = []
        total_processed = 0
        total_batches = (total_images + batch_size - 1) // batch_size

        for i in range(0, total_images, batch_size):
            batch_num = (i // batch_size) + 1
            batch_items = images_data[i : min(i + batch_size, total_images)]
            
            if progress_callback:
                progress_callback(total_processed, total_images, f"Enviando lote {batch_num}/{total_batches}...")

            files_payload = []
            open_files = []
            try:
                for item in batch_items:
                    f = open(item['path'], 'rb')
                    open_files.append(f)
                    # (field_name, (filename, file_object, content_type))
                    files_payload.append(('images[]', (item['filename'], f, 'image/png')))

                title_part = f"{album_title} (Part {batch_num})" if total_batches > 1 else album_title
                if len(title_part) < 3: title_part = f"Upload_{batch_num}"
                
                payload = {
                    'title': title_part,
                    'privacy': privacy,
                    'anonymous': '1', 
                    'nsfw': '1'
                }

                response = requests.post('https://api.imgchest.com/v1/post', headers=headers, files=files_payload, data=payload, timeout=120)
                
                if response.status_code == 200:
                    data = response.json()
                    if 'data' in data and 'images' in data['data']:
                        batch_links = [img['link'] for img in data['data']['images'] if 'link' in img]
                        all_uploaded_links.extend(batch_links)
                    else:
                        print(f"AVISO: Resposta JSON inesperada no lote {batch_num}: {data}")
                else:
                    print(f"ERRO: Lote {batch_num} falhou - HTTP {response.status_code}: {response.text[:200]}")
            
            except Exception as e:
                print(f"ERRO: Exceção no lote {batch_num}: {e}")
            finally:
                for f in open_files: f.close()
                total_processed += len(batch_items)
                if progress_callback:
                    progress_callback(total_processed, total_images, "Processando...")
                time.sleep(0.5)

        return all_uploaded_links
