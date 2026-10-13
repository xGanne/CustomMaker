"""Histórico de posts do Danbooru já importados (id do post -> arquivo local).

Evita baixar de novo (e duplicar no disco) um post já importado: enquanto o
arquivo existir, importar/gerar customs reaproveita o arquivo. Se o usuário
apagou o arquivo, o post volta a ser baixado normalmente.
"""
import json
import logging
import os
import threading
from collections import OrderedDict

from src.utils.resource_loader import app_data_path


logger = logging.getLogger(__name__)

# mais que isso, os registros mais antigos saem (o arquivo continua pequeno)
MAX_ENTRIES = 5000


class ImportHistory:
    def __init__(self, path=None):
        self.path = path or app_data_path("imported_posts.json")
        self._lock = threading.Lock()
        self._entries = OrderedDict()
        self._dirty = False
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            logger.warning("Histórico de importação ilegível, recomeçando: %s", exc)
            return
        if isinstance(data, dict):
            for post_id, path in data.items():
                if isinstance(path, str):
                    self._entries[str(post_id)] = path

    def get(self, post_id):
        """Arquivo local do post, se já foi importado e o arquivo ainda existe."""
        if post_id is None:
            return None
        with self._lock:
            path = self._entries.get(str(post_id))
        return path if path and os.path.isfile(path) else None

    def record(self, post_id, path):
        if post_id is None or not path:
            return
        with self._lock:
            key = str(post_id)
            self._entries.pop(key, None)
            self._entries[key] = path
            while len(self._entries) > MAX_ENTRIES:
                self._entries.popitem(last=False)
            self._dirty = True

    def save(self):
        """Grava se houve mudança (escrita atômica: tmp + replace)."""
        with self._lock:
            if not self._dirty:
                return
            data = dict(self._entries)
            self._dirty = False
        tmp_path = f"{self.path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp_path, self.path)
        except OSError as exc:
            logger.warning("Não foi possível salvar o histórico de importação: %s", exc)
            with self._lock:
                self._dirty = True
