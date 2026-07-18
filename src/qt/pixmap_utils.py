"""Conversão PIL → QPixmap compartilhada (M19).

Deve ser chamada apenas na GUI thread — QPixmap não pode ser criado em workers.
"""
from src.qt.compat import QT_AVAILABLE

if QT_AVAILABLE:
    from src.qt.compat import QImage, QPixmap


def pil_to_qpixmap(image):
    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimage = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimage.copy())
