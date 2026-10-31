"""Cache das prévias de custom por conteúdo (Revisão em grade).

A chave descreve tudo o que define a custom; reabrir a Revisão ou clicar
Atualizar só renderiza o que mudou.
"""
import hashlib
import json
import os
import threading
from collections import OrderedDict

from src.core.color_adjustments import cache_token

# subir quando o pipeline de render mudar: invalida todas as entradas antigas
RENDER_VERSION = 1


def custom_cache_key(task_data, edit_version=0):
    """SHA-1 do conteúdo que gera a prévia estática da custom, ou None.

    - o arquivo de origem (caminho, mtime, tamanho): pode ser trocado no disco;
    - a posição **relativa à borda** e o tamanho: redimensionar a janela desloca a
      borda e os enquadramentos juntos sem mudar a custom;
    - cor e estilo da borda, ajustes de cor;
    - `edit_version`, só quando há edição de pixels (rotação, IA): a fonte muda
      sem mudar o caminho. Sem edição, a versão não entra — desfazer até o
      original volta a acertar o cache de antes.
    A animação não entra: a prévia da Revisão é estática.
    """
    path = task_data.get("path")
    try:
        stat = os.stat(path)
    except (OSError, TypeError):
        return None
    (x, y), (bx, by) = task_data["state"]["pos"], task_data["borda_pos"]
    edited = bool(task_data.get("source_path") or task_data.get("edited"))
    payload = {
        "v": RENDER_VERSION,
        "path": os.path.abspath(path),
        "mtime": stat.st_mtime_ns,
        "bytes": stat.st_size,
        "rel_pos": [int(round(x - bx)), int(round(y - by))],
        "size": [int(v) for v in task_data["state"]["size"]],
        "border": task_data.get("border_color"),
        "style": task_data.get("border_style") or "simples",
        "adjust": [list(item) for item in cache_token(task_data.get("adjustments"))],
        "edit": int(edit_version) if edited else None,
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


class RenderCache:
    """LRU de imagens com limite em bytes, seguro entre threads.

    `get` e `put` trabalham com cópias: quem recebe uma imagem é dono dela.
    """

    def __init__(self, max_bytes=48 * 1024 * 1024):
        self.max_bytes = max_bytes
        self._entries = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    @staticmethod
    def _cost(image):
        return image.width * image.height * len(image.getbands())

    def get(self, key):
        if key is None:
            return None
        with self._lock:
            image = self._entries.get(key)
            if image is None:
                return None
            self._entries.move_to_end(key)
            return image.copy()

    def put(self, key, image):
        if key is None or image is None:
            return
        stored = image.copy()
        cost = self._cost(stored)
        if cost > self.max_bytes:
            stored.close()
            return
        with self._lock:
            old = self._entries.pop(key, None)
            if old is not None:
                self._bytes -= self._cost(old)
                old.close()
            self._entries[key] = stored
            self._bytes += cost
            while self._bytes > self.max_bytes and self._entries:
                _key, evicted = self._entries.popitem(last=False)
                self._bytes -= self._cost(evicted)
                evicted.close()

    def clear(self):
        with self._lock:
            for image in self._entries.values():
                image.close()
            self._entries.clear()
            self._bytes = 0

    def __len__(self):
        with self._lock:
            return len(self._entries)

    @property
    def used_bytes(self):
        with self._lock:
            return self._bytes
