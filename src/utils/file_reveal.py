"""Abrir o gerenciador de arquivos do sistema com um arquivo selecionado (M9)."""
import logging
import os
import subprocess
import sys


logger = logging.getLogger(__name__)


def reveal_command(path, platform=None):
    """Comando que abre o gerenciador de arquivos destacando `path`."""
    platform = platform or sys.platform
    if platform.startswith("win"):
        # "/select," precisa vir colado ao caminho para o Explorer selecionar o arquivo
        return ["explorer", f"/select,{os.path.normpath(path)}"]
    if platform == "darwin":
        return ["open", "-R", path]
    # Linux/BSD: não há um "selecionar" padrão — abre a pasta que contém o arquivo
    return ["xdg-open", os.path.dirname(path) or "."]


def open_with_default_app(path):
    """Abre `path` no programa associado (ex.: Bloco de Notas para .env)."""
    if not path or not os.path.exists(path):
        return False
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except OSError as exc:
        logger.warning("Não foi possível abrir %s: %s", path, exc)
        return False


def reveal_in_file_manager(path):
    """Mostra `path` no Explorer/Finder. Retorna False se não foi possível."""
    if not path or not os.path.exists(path):
        return False
    try:
        subprocess.Popen(reveal_command(path))
        return True
    except OSError as exc:
        logger.warning("Não foi possível revelar %s: %s", path, exc)
        return False
