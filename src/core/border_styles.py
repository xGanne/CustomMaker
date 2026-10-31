"""Estilos de borda das customs (prévia do canvas e export usam estas funções).

A custom tem exatamente 225x350 e não existe área fora da borda: brilho e
sombra vão para dentro, sobre a imagem.
"""
import colorsys
import logging
from functools import lru_cache

from PIL import Image, ImageColor, ImageDraw, ImageFilter

from src.config.settings import BORDA_HEIGHT, BORDA_WIDTH, BORDER_THICKNESS
from src.core.image_processor import ImageProcessor


logger = logging.getLogger(__name__)

DEFAULT_STYLE = "simples"
BORDER_STYLES = {
    "simples": "Simples",
    "dupla": "Dupla",
    "brilho": "Brilho",
    "degrade": "Degradê",
    "sombra": "Sombra",
}


def normalize_style(style):
    if style in BORDER_STYLES:
        return style
    if style:
        logger.warning("Estilo de borda desconhecido %r: usando o simples.", style)
    return DEFAULT_STYLE


def _band(size, width, inset=0):
    """Máscara L com a faixa da borda (largura `width`, recuada `inset` px)."""
    w, h = size
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rectangle(
        [inset, inset, w - 1 - inset, h - 1 - inset], outline=255, width=width
    )
    return mask


def _solid(size, rgb, mask):
    layer = Image.new("RGBA", size, rgb + (0,))
    layer.putalpha(mask)
    return layer


def _scaled_mask(mask, opacity):
    return mask.point(lambda v: int(v * opacity))


def _gradient_end(rgb):
    """Mesma matiz, 25% mais clara (ou mais escura, se já for muito clara)."""
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    l = l - 0.25 if l > 0.75 else min(1.0, l + 0.25)
    return tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, l, s))


def _render_overlay(style, rgb, size):
    w, h = size
    band = _band(size, BORDER_THICKNESS)
    if style == "dupla":
        # 3 px por fora, vão de 2 px mostrando a imagem, 1 px por dentro
        outer = _band(size, 3)
        inner = _band(size, 1, inset=5)
        mask = Image.new("L", size, 0)
        mask.paste(255, mask=outer)
        mask.paste(255, mask=inner)
        return _solid(size, rgb, mask)
    if style == "brilho":
        glow = _scaled_mask(band.filter(ImageFilter.GaussianBlur(6)), 0.55)
        overlay = _solid(size, rgb, glow)
        overlay.alpha_composite(_solid(size, rgb, band))
        return overlay
    if style == "sombra":
        shadow = _scaled_mask(_band(size, BORDER_THICKNESS + 4).filter(ImageFilter.GaussianBlur(5)), 0.4)
        overlay = _solid(size, (0, 0, 0), shadow)
        overlay.alpha_composite(_solid(size, rgb, band))
        return overlay
    if style == "degrade":
        end = _gradient_end(rgb)
        gradient = Image.new("RGBA", size)
        draw = ImageDraw.Draw(gradient)
        for y in range(h):
            t = y / max(1, h - 1)
            draw.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(rgb, end)) + (255,))
        gradient.putalpha(band)
        return gradient
    return _solid(size, rgb, band)


@lru_cache(maxsize=64)
def _overlay_bytes(style, color_hex, size):
    rgb = ImageColor.getrgb(color_hex)[:3]
    return _render_overlay(style, rgb, size).tobytes()


def border_overlay(style, color_hex, size=(BORDA_WIDTH, BORDA_HEIGHT)):
    """RGBA do tamanho da custom: borda + efeito do estilo, transparente no resto."""
    style = normalize_style(style)
    return Image.frombytes("RGBA", size, _overlay_bytes(style, color_hex, tuple(size)))


def apply_border(cropped, style, color_hex):
    """O recorte 225x350 com a borda do estilo aplicada (imagem nova)."""
    style = normalize_style(style)
    if style == DEFAULT_STYLE:
        # exatamente o caminho de sempre: customs "Simples" saem byte a byte iguais
        return ImageProcessor.add_borda_to_image(cropped, color_hex)
    result = cropped.convert("RGBA") if cropped.mode != "RGBA" else cropped.copy()
    overlay = border_overlay(style, color_hex, result.size)
    try:
        result.alpha_composite(overlay)
    finally:
        overlay.close()
    return result
