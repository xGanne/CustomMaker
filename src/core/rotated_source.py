"""Edição só de rotação, guardada como graus em vez de uma cópia da imagem."""

from PIL import Image

from src.core.image_processor import ImageProcessor


def open_rotated(path, degrees, draft_size=None):
    """Arquivo `path` em RGBA, girado `degrees` graus (anti-horário, como
    Image.rotate). `draft_size` (largura, altura do resultado) deixa o JPEG ser
    decodificado já reduzido. Múltiplos de 90° são exatos (transposição)."""
    with Image.open(path) as source:
        if draft_size is not None:
            w, h = draft_size
            if degrees % 180:
                w, h = h, w  # o arquivo ainda não está girado
            source.draft(source.mode, (int(w), int(h)))
        image = source.convert("RGBA")
    if not degrees % 360:
        return image
    rotated = image.rotate(degrees, expand=True)
    image.close()
    return rotated


class RotatedOriginal:
    """O arquivo original girado, sem a imagem em memória.

    Uma foto de 24 MP girada custava ~92 MB guardados até fechar o app (e mais
    uma cópia por exportação); estes graus custam nada. Quem precisa dos pixels
    chama `load()` e recebe uma imagem nova, dona do chamador. Imutável:
    pode ser lido de qualquer thread.
    """

    __slots__ = ("path", "degrees", "_size", "__weakref__")  # weakref: sessão

    def __init__(self, path, degrees):
        self.path = path
        self.degrees = int(degrees) % 360
        self._size = None

    @property
    def size(self):
        """Tamanho já girado, lido só do cabeçalho do arquivo."""
        if self._size is None:
            with Image.open(self.path) as source:
                w, h = source.size
            self._size = (h, w) if self.degrees % 180 else (w, h)
        return self._size

    def load(self, max_dim=None):
        """Imagem girada; com `max_dim`, reduzida para caber nesse lado."""
        if max_dim is None:
            return open_rotated(self.path, self.degrees)
        image = open_rotated(self.path, self.degrees, (max_dim, max_dim))
        reduced = ImageProcessor.resize_image(image, max_dim, max_dim)
        if reduced is not image:
            image.close()
        return reduced

    def close(self):
        """Nada a liberar (mesma interface das imagens editadas)."""

    def __repr__(self):
        return f"RotatedOriginal({self.path!r}, {self.degrees})"
