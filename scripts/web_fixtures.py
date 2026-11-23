"""Customs de referência geradas pelo código do PC, para os testes de paridade do web.

Cada caso passa uma imagem de teste pelo mesmo caminho do export
(ImageProcessor.render_image_to_borda + border_styles.apply_border). O web tem
que reproduzir cada custom pixel a pixel.

Uso:  python scripts/web_fixtures.py
Gera: web/tests/fixtures/ (tests/test_web_export.py falha se estiver desatualizado)
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402
from PIL import Image, ImageColor  # noqa: E402

from src.config.settings import BORDA_HEX  # noqa: E402
from src.core.border_styles import _gradient_end, apply_border  # noqa: E402
from src.core.image_processor import ImageProcessor  # noqa: E402

FIXTURES_DIR = os.path.join(ROOT, "web", "tests", "fixtures")
# a borda fica em coordenadas de cena (não em 0,0), como no canvas do PC
BORDA_POS = (40, 25)


def build_sources():
    """{nome: PIL RGBA} determinísticos. Gradientes + xadrez: as bordas duras
    exercitam o Lanczos (inclusive o "anel" perto delas) e o arquivo comprime bem."""

    def textured(w, h, alpha=None):
        y, x = np.mgrid[0:h, 0:w]
        img = np.empty((h, w, 4), dtype=np.uint8)
        img[..., 0] = (x * 255 // max(1, w - 1))
        img[..., 1] = (y * 255 // max(1, h - 1))
        img[..., 2] = ((x // 7 + y // 11) % 2) * 200 + 30
        img[..., 3] = 255 if alpha is None else alpha
        return Image.fromarray(img, "RGBA")

    h, w = 260, 260
    y, x = np.mgrid[0:h, 0:w]
    ring = np.hypot(x - w / 2, y - h / 2)
    alpha = np.clip(255 - (ring - 70) * 4, 0, 255).astype(np.uint8)  # círculo com borda suave
    return {
        "retrato": textured(300, 420),
        "pequena": textured(150, 200),
        "paisagem": textured(640, 360),
        "transparente": textured(w, h, alpha),
    }


def build_cases():
    bx, by = BORDA_POS
    fit = ImageProcessor.calculate_auto_fit_pos(Image.new("RGBA", (300, 420)), BORDA_POS)
    fit_w, fit_h, fit_x, fit_y = fit
    cases = []
    for style in ("simples", "dupla", "brilho", "degrade", "sombra"):
        cases.append({"name": f"autofit-{style}", "source": "retrato", "pos": [fit_x, fit_y],
                      "size": [fit_w, fit_h], "color": "#89b4fa", "style": style})
    cases += [
        # imagem deslocada: parte da custom fica transparente
        {"name": "deslocada", "source": "retrato", "pos": [bx + 60, by - 40], "size": [250, 350],
         "color": "#f38ba8", "style": "simples"},
        # menor que a borda: amplia
        {"name": "ampliada", "source": "pequena", "pos": [bx - 30, by - 10], "size": [300, 400],
         "color": "#a6e3a1", "style": "dupla"},
        # bem maior: reduz bastante (o filtro alarga)
        {"name": "reduzida", "source": "paisagem", "pos": [bx - 120, by - 5], "size": [622, 350],
         "color": "#f9e2af", "style": "degrade"},
        # cor clara: o degradê escurece em vez de clarear
        {"name": "degrade-claro", "source": "retrato", "pos": [fit_x, fit_y], "size": [fit_w, fit_h],
         "color": "#cdd6f4", "style": "degrade"},
        # transparência: premultiplicação no resize e alfa parcial na borda
        {"name": "transparente-brilho", "source": "transparente", "pos": [bx - 20, by + 30],
         "size": [270, 270], "color": "#cba6f7", "style": "brilho"},
        {"name": "transparente-sombra", "source": "transparente", "pos": [bx - 20, by + 30],
         "size": [270, 270], "color": "#fab387", "style": "sombra"},
        # posição fracionária: o recorte arredonda como o Python (round-half-even)
        {"name": "fracionaria", "source": "retrato", "pos": [bx - 12.5, by - 7.5], "size": [260, 380],
         "color": "#11111b", "style": "simples"},
    ]
    for case in cases:
        case["bordaPos"] = list(BORDA_POS)
        case["expected"] = f"{case['name']}.png"
    return cases, {"source": "retrato", "bordaPos": list(BORDA_POS), "fit": list(fit)}


def render_case(sources, case):
    cropped = ImageProcessor.render_image_to_borda(
        sources[case["source"]], tuple(case["pos"]), tuple(case["size"]), tuple(case["bordaPos"]))
    return apply_border(cropped, case["style"], case["color"])


def gradient_table():
    """Cor final do degradê para várias cores (confere o porte do colorsys)."""
    rng = np.random.default_rng(7)
    colors = sorted(set(BORDA_HEX.values())) + [
        "#%02x%02x%02x" % tuple(int(v) for v in rng.integers(0, 256, 3)) for _ in range(40)
    ] + ["#000000", "#ffffff", "#808080", "#ff0000", "#00ff00", "#0000ff"]
    return [{"color": c, "end": list(_gradient_end(ImageColor.getrgb(c)[:3]))} for c in colors]


def build_all():
    """(sources, cases, autofit, gradient) — sem gravar nada (usado pelo teste)."""
    sources = build_sources()
    cases, autofit = build_cases()
    return sources, cases, autofit, gradient_table()


def main():
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    sources, cases, autofit, gradient = build_all()
    for name, image in sources.items():
        image.save(os.path.join(FIXTURES_DIR, f"source-{name}.png"))
    for case in cases:
        render_case(sources, case).save(os.path.join(FIXTURES_DIR, case["expected"]))
    manifest = {"cases": cases, "autofit": autofit, "gradient": gradient}
    with open(os.path.join(FIXTURES_DIR, "cases.json"), "w", encoding="utf-8", newline="\n") as file_obj:
        file_obj.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(sources)} imagens de teste, {len(cases)} customs de referência, "
          f"{len(gradient)} cores de degradê em {os.path.relpath(FIXTURES_DIR, ROOT)}")


if __name__ == "__main__":
    main()
