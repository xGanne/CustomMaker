"""Ajustes leves de cor, não destrutivos: guardados como parâmetros por imagem.

Aplicados no export depois do recorte e antes da borda (a cor da borda nunca
muda), e na prévia do canvas. Para a prévia e o export darem o mesmo tom:
  - o contraste gira em torno de 128 fixo (o ImageEnhance.Contrast usa a média
    da imagem: na prévia é a imagem inteira, no export só o recorte);
  - brilho e contraste viram uma única tabela (LUT) por canal;
  - a saturação é por pixel (ImageEnhance.Color).
A nitidez depende da vizinhança e da escala — só no export/Revisão.
"""
import logging

from PIL import ImageEnhance


logger = logging.getLogger(__name__)

KEYS = ("brightness", "contrast", "saturation", "sharpness")
LABELS = {"brightness": "Brilho", "contrast": "Contraste", "saturation": "Saturação", "sharpness": "Nitidez"}
LIMIT = 100


def normalize(adjustments):
    """Só as chaves conhecidas, inteiras e dentro de -100..100 (o resto é descartado)."""
    if not isinstance(adjustments, dict):
        if adjustments:
            logger.warning("Ajustes de cor inválidos descartados: %r", adjustments)
        return {}
    result = {}
    for key in KEYS:
        try:
            value = int(round(float(adjustments.get(key, 0) or 0)))
        except (TypeError, ValueError):
            logger.warning("Ajuste %s inválido descartado: %r", key, adjustments.get(key))
            continue
        value = max(-LIMIT, min(LIMIT, value))
        if value:
            result[key] = value
    return result


def is_neutral(adjustments):
    return not normalize(adjustments)


def _tone_lut(brightness, contrast):
    brightness_factor = 1 + brightness / 100
    contrast_factor = 1 + contrast / 100
    table = []
    for value in range(256):
        v = value * brightness_factor
        v = (v - 128) * contrast_factor + 128
        table.append(max(0, min(255, int(round(v)))))
    return table * 3


def _split_alpha(image):
    if image.mode == "RGBA":
        return image.convert("RGB"), image.getchannel("A")
    return image.convert("RGB"), None


def _merge_alpha(rgb, alpha):
    if alpha is None:
        return rgb
    rgb.putalpha(alpha)
    return rgb


def apply_tone(image, adjustments):
    """Brilho + contraste (LUT) + saturação. Neutro: devolve a própria imagem."""
    adj = normalize(adjustments)
    brightness, contrast, saturation = adj.get("brightness", 0), adj.get("contrast", 0), adj.get("saturation", 0)
    if not (brightness or contrast or saturation):
        return image
    rgb, alpha = _split_alpha(image)
    if brightness or contrast:
        rgb = rgb.point(_tone_lut(brightness, contrast))
    if saturation:
        rgb = ImageEnhance.Color(rgb).enhance(1 + saturation / 100)
    return _merge_alpha(rgb, alpha)


def apply_all(image, adjustments):
    """apply_tone + nitidez — o que o export grava. Neutro: a própria imagem."""
    adj = normalize(adjustments)
    toned = apply_tone(image, adj)
    sharpness = adj.get("sharpness", 0)
    if not sharpness:
        return toned
    rgb, alpha = _split_alpha(toned)
    rgb = ImageEnhance.Sharpness(rgb).enhance(max(0.0, min(3.0, 1 + sharpness / 50)))
    if toned is not image:
        toned.close()
    return _merge_alpha(rgb, alpha)


def cache_token(adjustments):
    """Forma hasheável e estável dos ajustes (chaves de cache)."""
    return tuple(sorted(normalize(adjustments).items()))

