"""Imagens de uma pasta, na ordem usada em todo o app."""
import os

from src.config.settings import SUPPORTED_EXTENSIONS


def list_folder_images(folder):
    """Imagens da pasta (sem subpastas), em ordem alfabética.

    A mesma ordem para "Abrir pasta", arrastar uma pasta e o modo --batch:
    a lista de customs (e os links do upload) sai sempre igual.
    """
    return [
        os.path.join(folder, name)
        for name in sorted(os.listdir(folder))
        if os.path.isfile(os.path.join(folder, name)) and name.lower().endswith(SUPPORTED_EXTENSIONS)
    ]
