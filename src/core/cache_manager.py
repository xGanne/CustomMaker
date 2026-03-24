import hashlib
import logging
import os
import threading
import time


logger = logging.getLogger(__name__)


class CacheManager:
    def __init__(self, cache_dir=".cache", max_age_days=3, max_disk_size_mb=512):
        self.cache_dir = cache_dir
        self.max_age_days = max_age_days
        self.max_disk_size_bytes = max(0, int(float(max_disk_size_mb) * 1024 * 1024))
        self._lock = threading.Lock()

        try:
            os.makedirs(self.cache_dir, exist_ok=True)
        except OSError as exc:
            logger.warning("Falha ao criar diretorio de cache '%s': %s", self.cache_dir, exc)

        threading.Thread(target=self.cleanup, daemon=True).start()

    def _get_path(self, key):
        hashed = hashlib.md5(key.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, hashed)

    def get(self, key):
        path = self._get_path(key)
        if not os.path.exists(path):
            return None
        try:
            os.utime(path, None)
            with open(path, "rb") as f:
                return f.read()
        except OSError as exc:
            logger.debug("Falha ao ler cache para key=%s: %s", key, exc)
            return None

    def set(self, key, data):
        if not data:
            return

        try:
            path = self._get_path(key)
            with open(path, "wb") as f:
                f.write(data)
        except OSError as exc:
            logger.debug("Falha ao gravar cache para key=%s: %s", key, exc)
            return

        with self._lock:
            self._evict_by_size_limit()

    def _iter_cache_files(self):
        try:
            file_names = os.listdir(self.cache_dir)
        except OSError:
            return []

        files = []
        for fname in file_names:
            path = os.path.join(self.cache_dir, fname)
            if not os.path.isfile(path):
                continue
            try:
                stat = os.stat(path)
            except OSError:
                continue
            files.append((path, stat.st_mtime, stat.st_size))
        return files

    def _evict_old_files(self):
        now = time.time()
        cutoff = now - (self.max_age_days * 86400)
        for path, mtime, _size in self._iter_cache_files():
            if mtime < cutoff:
                try:
                    os.remove(path)
                    logger.debug("Cache removido por idade: %s", os.path.basename(path))
                except OSError:
                    continue

    def _evict_by_size_limit(self):
        if self.max_disk_size_bytes <= 0:
            return

        files = self._iter_cache_files()
        current_size = sum(size for _path, _mtime, size in files)
        if current_size <= self.max_disk_size_bytes:
            return

        files.sort(key=lambda item: item[1])  # oldest first (LRU by mtime)
        for path, _mtime, size in files:
            if current_size <= self.max_disk_size_bytes:
                break
            try:
                os.remove(path)
                current_size -= size
                logger.debug("Cache removido por limite de disco: %s (%s bytes)", os.path.basename(path), size)
            except OSError:
                continue

    def cleanup(self):
        with self._lock:
            try:
                self._evict_old_files()
                self._evict_by_size_limit()
            except OSError as exc:
                logger.debug("Falha no cleanup de cache: %s", exc)
