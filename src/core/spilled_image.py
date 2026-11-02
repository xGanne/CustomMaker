"""Edição de pixels (IA) guardada num arquivo temporário, não na RAM."""

import atexit
import logging
import os
import shutil
import tempfile
import threading
import weakref

from PIL import Image

from src.core.image_processor import ImageProcessor


logger = logging.getLogger(__name__)

_DIR_PREFIX = "custommaker_edits_"
_dir = None
_dir_lock = threading.Lock()


def _spill_dir():
    """Pasta desta execução (criada na 1ª edição, apagada ao sair). O nome
    leva o PID: a limpeza de sobras nunca apaga a de outra janela aberta."""
    global _dir
    with _dir_lock:
        if _dir is None or not os.path.isdir(_dir):
            _remove_stale_dirs()
            _dir = tempfile.mkdtemp(prefix=f"{_DIR_PREFIX}{os.getpid()}_")
            atexit.register(shutil.rmtree, _dir, True)
        return _dir


def _pid_alive(pid):
    """Processo `pid` ainda existe? Na dúvida, sim (não apaga)."""
    if os.name == "nt":
        # os.kill(pid, 0) no Windows ENCERRA o processo: consulta pela API
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # acesso negado: existe, de outro usuário
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _remove_stale_dirs():
    """Sobras de execuções que fecharam sem limpar (crash, kill)."""
    base = tempfile.gettempdir()
    try:
        names = os.listdir(base)
    except OSError:
        return
    for name in names:
        if not name.startswith(_DIR_PREFIX):
            continue
        pid_text = name[len(_DIR_PREFIX):].split("_", 1)[0]
        if not pid_text.isdigit() or int(pid_text) == os.getpid() or _pid_alive(int(pid_text)):
            continue
        shutil.rmtree(os.path.join(base, name), ignore_errors=True)


def _remove_file(path):
    try:
        os.remove(path)
    except OSError:
        pass  # aberto por um worker (Windows) ou já apagado: sai com a pasta


class SpilledImage:
    """Imagem editada guardada em disco (TIFF), com a interface que o editor usa.

    Uma edição de IA numa foto de 24 MP custava ~92 MB de RAM até fechar o app,
    mais uma cópia por passo de desfazer e por exportação. Aqui fica só o
    caminho: o export lê o arquivo direto, o histórico compartilha o mesmo
    objeto (imutável, `copy()` devolve ele mesmo) e quem precisa dos pixels
    chama `load()`. O arquivo é apagado quando ninguém mais referencia o objeto.
    """

    __slots__ = ("path", "size", "mode", "__weakref__")

    def __init__(self, image):
        fd, path = tempfile.mkstemp(suffix=".tiff", dir=_spill_dir())
        os.close(fd)
        try:
            # packbits: rápido e encolhe muito as áreas transparentes (remover fundo)
            image.save(path, format="TIFF", compression="packbits")
        except BaseException:
            _remove_file(path)
            raise
        self.path = path
        self.size = image.size
        self.mode = image.mode
        weakref.finalize(self, _remove_file, path)

    @classmethod
    def from_image(cls, image):
        """SpilledImage de `image`; sem disco (cheio, sem permissão), uma cópia em RAM."""
        try:
            return cls(image)
        except Exception as exc:
            logger.warning("Edição mantida na memória (falha ao gravar o temporário): %s", exc)
            return image.copy()

    @property
    def width(self):
        return self.size[0]

    @property
    def height(self):
        return self.size[1]

    def load(self, max_dim=None):
        """Imagem nova (dona do chamador); com `max_dim`, reduzida para caber."""
        with Image.open(self.path) as source:
            image = source.copy()
        if max_dim is None:
            return image
        reduced = ImageProcessor.resize_image(image, max_dim, max_dim)
        if reduced is not image:
            image.close()
        return reduced

    def copy(self):
        return self  # imutável: compartilhar é seguro

    def close(self):
        """O arquivo sai quando o último dono solta o objeto (ver __init__)."""

    def __repr__(self):
        return f"SpilledImage({self.path!r}, {self.size})"


def is_lazy_edit(edit):
    """Edição guardada fora da RAM (rotação em graus ou imagem em disco)."""
    from src.core.rotated_source import RotatedOriginal
    return isinstance(edit, (RotatedOriginal, SpilledImage))
