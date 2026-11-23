"""Exporta do código do PC as regras e as máscaras de borda usadas pelo app web.

Uma fonte só: medidas da custom, cores, estilos e limites vêm de src/, e as
máscaras dos estilos (que dependem de desfoque do Pillow) são geradas pelo
próprio border_styles.py. O web só pinta as máscaras com a cor escolhida, então
a custom sai igual à do PC sem reimplementar o desfoque.

Uso:  python scripts/export_web_rules.py
Gera: web/src/generated/rules.json e web/public/generated/masks.bin.gz
      (tests/test_web_export.py falha se estiverem desatualizados)
"""
import gzip
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

from src.config.settings import BORDA_HEIGHT, BORDA_HEX, BORDA_WIDTH, BORDER_THICKNESS  # noqa: E402
from src.core import border_styles, custom_scorer, danbooru  # noqa: E402
from src.core.mudae import DISCORD_MESSAGE_LIMIT  # noqa: E402

RULES_PATH = os.path.join(ROOT, "web", "src", "generated", "rules.json")
MASKS_PATH = os.path.join(ROOT, "web", "public", "generated", "masks.bin.gz")
SIZE = (BORDA_WIDTH, BORDA_HEIGHT)
# ordem das máscaras dentro de masks.bin (cada uma: largura x altura bytes, 0-255)
MASK_ORDER = ("band", "dupla", "brilho", "sombra")
_PROBE_COLOR = (200, 30, 90)


def _overlay(style, rgb=_PROBE_COLOR):
    return np.asarray(border_styles._render_overlay(style, rgb, SIZE)).astype(np.int64)


def build_masks():
    """{nome: np.uint8 (altura, largura)} — conferindo as premissas do web."""
    band = np.asarray(border_styles._band(SIZE, BORDER_THICKNESS))
    assert set(np.unique(band)) <= {0, 255}, "faixa da borda deixou de ser binária"

    masks = {"band": band}
    for style in ("dupla", "brilho"):
        overlay = _overlay(style)
        visible = overlay[..., 3] > 0
        # uma cor só: o web pinta a máscara com a cor escolhida
        assert (overlay[visible][:, :3] == _PROBE_COLOR).all(), f"{style}: cor não é uniforme"
        masks[style] = overlay[..., 3].astype(np.uint8)

    sombra = _overlay("sombra")
    on_band = band == 255
    assert (sombra[on_band][:, :3] == _PROBE_COLOR).all() and (sombra[on_band][:, 3] == 255).all(), \
        "sombra: a faixa deixou de ser a cor sólida"
    off_band = ~on_band & (sombra[..., 3] > 0)
    assert (sombra[off_band][:, :3] == 0).all(), "sombra: o desfoque deixou de ser preto"
    masks["sombra"] = sombra[..., 3].astype(np.uint8)

    degrade = _overlay("degrade")
    assert (degrade[..., 3] == band).all(), "degradê: o alfa deixou de ser a faixa"
    return masks


def build_rules():
    return {
        "_aviso": "Gerado por scripts/export_web_rules.py a partir de src/ — não edite à mão.",
        "border": {"width": BORDA_WIDTH, "height": BORDA_HEIGHT, "thickness": BORDER_THICKNESS},
        "colors": dict(BORDA_HEX),
        "styles": dict(border_styles.BORDER_STYLES),
        "defaultStyle": border_styles.DEFAULT_STYLE,
        "masks": {"file": "generated/masks.bin.gz", "order": list(MASK_ORDER)},
        "discordMessageLimit": DISCORD_MESSAGE_LIMIT,
        "danbooru": {
            "postFields": danbooru.POST_FIELDS,
            "imageExtensions": sorted(danbooru.IMAGE_FILE_EXTENSIONS),
            "ratingTags": dict(danbooru.RATING_TAGS),
            "sortTags": dict(danbooru.SORT_TAGS),
            "portraitRatioTag": danbooru.PORTRAIT_RATIO_TAG,
            "sampleWidth": danbooru.DANBOORU_SAMPLE_WIDTH,
            "importMinSize": list(danbooru.IMPORT_MIN_SIZE),
            "maxPage": danbooru.MAX_PAGE,
            "autoSelectMaxPages": danbooru.AUTO_SELECT_MAX_PAGES,
        },
        # ★ Auto: tabelas e limites de custom_scorer.py (as fórmulas são portadas
        # em web/src/core/scorer.ts e conferidas por tests/fixtures/scorer.json)
        "scorer": {
            "tagBoosts": dict(custom_scorer._TAG_BOOSTS),
            "tagPenalties": dict(custom_scorer._TAG_PENALTIES),
            "qualityBoosts": dict(custom_scorer._QUALITY_BOOSTS),
            "qualityPenalties": dict(custom_scorer._QUALITY_PENALTIES),
            "autoRatings": sorted(custom_scorer.AUTO_RATINGS),
            "sensitiveRatingPenalty": custom_scorer._SENSITIVE_RATING_PENALTY,
            "defaultAvoidTags": custom_scorer.DEFAULT_AVOID_TAGS,
            "avoidTagPenalty": custom_scorer._AVOID_TAG_PENALTY,
            "minAutoScore": custom_scorer.MIN_AUTO_SCORE,
            "grayscalePenalty": custom_scorer._GRAYSCALE_PENALTY,
            "minColorFraction": custom_scorer._MIN_COLOR_FRACTION,
        },
    }


def masks_payload(masks):
    """masks.bin.gz determinístico (mtime 0): mesmo conteúdo, mesmos bytes."""
    raw = b"".join(masks[name].tobytes() for name in MASK_ORDER)
    return gzip.compress(raw, compresslevel=9, mtime=0)


def rules_text(rules):
    return json.dumps(rules, ensure_ascii=False, indent=2) + "\n"


def main():
    rules, masks = build_rules(), build_masks()
    os.makedirs(os.path.dirname(RULES_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(MASKS_PATH), exist_ok=True)
    with open(RULES_PATH, "w", encoding="utf-8", newline="\n") as file_obj:
        file_obj.write(rules_text(rules))
    payload = masks_payload(masks)
    with open(MASKS_PATH, "wb") as file_obj:
        file_obj.write(payload)
    print(f"{os.path.relpath(RULES_PATH, ROOT)}")
    print(f"{os.path.relpath(MASKS_PATH, ROOT)} ({len(payload):,} bytes; {len(MASK_ORDER)} máscaras {SIZE[0]}x{SIZE[1]})")


if __name__ == "__main__":
    main()
