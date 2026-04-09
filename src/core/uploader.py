import logging
import mimetypes
import time
from typing import List, Tuple

import requests

from src.config.settings import IMG_CHEST_API_TOKEN, UPLOAD_BATCH_SIZE


logger = logging.getLogger(__name__)


class ImgChestUploader:
    def __init__(self, api_token=None, session: requests.Session = None):
        self.api_token = api_token or IMG_CHEST_API_TOKEN
        self.session = session or requests.Session()

    @staticmethod
    def _guess_content_type(filename: str) -> str:
        extension_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".mp4": "video/mp4",
        }
        lower_name = str(filename or "").lower()
        for ext, mime in extension_map.items():
            if lower_name.endswith(ext):
                return mime

        guessed, _ = mimetypes.guess_type(filename)
        return guessed or "application/octet-stream"

    @staticmethod
    def _is_retryable_http_status(status_code: int) -> bool:
        if status_code in {408, 425, 429}:
            return True
        return 500 <= status_code <= 599

    def upload_images(
        self,
        images_data,
        album_title,
        privacy="hidden",
        progress_callback=None,
        retries=2,
        cancel_event=None,
    ) -> Tuple[List[str], List[str]]:
        """
        Uploads images to ImgChest.
        images_data: List[{'path': str, 'filename': str}]
        progress_callback: function(current, total, status_message)
        Returns: (uploaded_links, errors)
        """
        if not self.api_token:
            raise ValueError("Token da API ImgChest nao configurado.")

        headers = {"Authorization": f"Bearer {self.api_token}"}
        total_images = len(images_data)
        if total_images == 0:
            return [], []

        try:
            batch_size = min(max(1, int(UPLOAD_BATCH_SIZE)), 20)
        except (ValueError, TypeError):
            batch_size = 20

        all_uploaded_links: List[str] = []
        errors: List[str] = []
        total_processed = 0
        total_batches = (total_images + batch_size - 1) // batch_size

        for i in range(0, total_images, batch_size):
            if cancel_event and cancel_event.is_set():
                errors.append("Upload cancelado pelo usuario.")
                break

            batch_num = (i // batch_size) + 1
            batch_items = images_data[i : min(i + batch_size, total_images)]

            if progress_callback:
                progress_callback(total_processed, total_images, f"Enviando lote {batch_num}/{total_batches}...")

            try:
                title_part = f"{album_title} (Part {batch_num})" if total_batches > 1 else album_title
                if len(title_part) < 3:
                    title_part = f"Upload_{batch_num}"

                payload = {
                    "title": title_part,
                    "privacy": privacy,
                    "anonymous": "1",
                    "nsfw": "1",
                }

                batch_uploaded = False
                last_exc = None

                for attempt in range(retries + 1):
                    if cancel_event and cancel_event.is_set():
                        errors.append(f"Lote {batch_num}: cancelado pelo usuario.")
                        batch_uploaded = True
                        break

                    files_payload = []
                    open_files = []
                    try:
                        for item in batch_items:
                            f = open(item["path"], "rb")
                            open_files.append(f)
                            filename = item["filename"]
                            content_type = item.get("content_type") or self._guess_content_type(filename)
                            files_payload.append(("images[]", (filename, f, content_type)))

                        response = self.session.post(
                            "https://api.imgchest.com/v1/post",
                            headers=headers,
                            files=files_payload,
                            data=payload,
                            timeout=120,
                        )

                        if response.status_code == 200:
                            data = response.json()
                            if "data" in data and "images" in data["data"]:
                                batch_links = [img["link"] for img in data["data"]["images"] if "link" in img]
                                all_uploaded_links.extend(batch_links)
                                batch_uploaded = True
                                break

                            err = f"Lote {batch_num}: resposta JSON inesperada."
                            logger.warning("%s data=%s", err, data)
                            errors.append(err)
                            batch_uploaded = True
                            break

                        err = f"Lote {batch_num} falhou - HTTP {response.status_code}: {response.text[:200]}"
                        logger.error(err)
                        if not self._is_retryable_http_status(response.status_code):
                            errors.append(err)
                            batch_uploaded = True
                            break
                        last_exc = RuntimeError(err)
                    except Exception as exc:
                        last_exc = exc
                        logger.warning("Erro no lote %s tentativa %s/%s: %s", batch_num, attempt + 1, retries + 1, exc)
                    finally:
                        for f in open_files:
                            try:
                                f.close()
                            except Exception:
                                pass

                    if attempt < retries:
                        time.sleep(1.0 * (attempt + 1))

                if not batch_uploaded and last_exc:
                    errors.append(f"Lote {batch_num}: {last_exc}")
            except Exception as exc:
                logger.exception("Excecao no lote %s: %s", batch_num, exc)
                errors.append(f"Lote {batch_num}: {exc}")
            finally:
                total_processed += len(batch_items)
                if progress_callback:
                    progress_callback(total_processed, total_images, "Processando...")

        return all_uploaded_links, errors
