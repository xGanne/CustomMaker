/**
 * Estilos de borda, iguais a src/core/border_styles.py.
 *
 * As máscaras (onde a borda cobre e com que opacidade) vêm prontas do Python
 * (generated/masks.gz.bin), inclusive o desfoque do Brilho e da Sombra; aqui só se pinta
 * com a cor e se compõe sobre o recorte com a mesma conta do Pillow.
 */
import { cloneRaster, parseHexColor, pyMod, pyRound, type Raster } from "./raster";
import { rules, type BorderStyle } from "./rules";

export type BorderMasks = Record<"band" | "dupla" | "brilho" | "sombra", Uint8Array>;

/** Lê o arquivo das máscaras (gzip ou já descompactado) na ordem de rules.masks.order. */
export async function loadMasks(gzipped: ArrayBuffer | Uint8Array): Promise<BorderMasks> {
  const bytes = gzipped instanceof Uint8Array ? gzipped : new Uint8Array(gzipped);
  // um servidor que mande o .gz com Content-Encoding faz o navegador já descompactar
  const isGzip = bytes[0] === 0x1f && bytes[1] === 0x8b;
  const raw = isGzip
    ? new Uint8Array(await new Response(
      new Blob([bytes as BlobPart]).stream().pipeThrough(new DecompressionStream("gzip")),
    ).arrayBuffer())
    : bytes;
  const size = rules.border.width * rules.border.height;
  const masks = {} as BorderMasks;
  rules.masks.order.forEach((name, index) => {
    masks[name as keyof BorderMasks] = raw.subarray(index * size, (index + 1) * size);
  });
  if (raw.length !== size * rules.masks.order.length) {
    throw new Error(`máscaras com tamanho inesperado (${raw.length} bytes)`);
  }
  return masks;
}

/** Image.alpha_composite do Pillow para um pixel (src sobre dst), em `d` a partir de `i`. */
function compositePixel(d: Uint8ClampedArray, i: number, r: number, g: number, b: number, a: number): void {
  if (a === 0) return;
  const PB = 7;
  const div255 = (v: number) => ((v >> 8) + v) >> 8;
  const blend = d[i + 3] * (255 - a);
  const outa255 = a * 255 + blend;
  const coef1 = Math.floor((a * 255 * 255 * (1 << PB)) / outa255);
  const coef2 = 255 * (1 << PB) - coef1;
  d[i] = div255(r * coef1 + d[i] * coef2 + (0x80 << PB)) >> PB;
  d[i + 1] = div255(g * coef1 + d[i + 1] * coef2 + (0x80 << PB)) >> PB;
  d[i + 2] = div255(b * coef1 + d[i + 2] * coef2 + (0x80 << PB)) >> PB;
  d[i + 3] = div255(outa255 + 0x80);
}

// colorsys do Python, linha a linha (o degradê depende dos mesmos doubles)
function rgbToHls(r: number, g: number, b: number): [number, number, number] {
  const maxc = Math.max(r, g, b);
  const minc = Math.min(r, g, b);
  const sumc = maxc + minc;
  const rangec = maxc - minc;
  const l = sumc / 2.0;
  if (minc === maxc) return [0.0, l, 0.0];
  const s = l <= 0.5 ? rangec / sumc : rangec / (2.0 - maxc - minc);
  const rc = (maxc - r) / rangec;
  const gc = (maxc - g) / rangec;
  const bc = (maxc - b) / rangec;
  let h: number;
  if (r === maxc) h = bc - gc;
  else if (g === maxc) h = 2.0 + rc - bc;
  else h = 4.0 + gc - rc;
  return [pyMod(h / 6.0, 1.0), l, s];
}

const ONE_THIRD = 1.0 / 3.0;
const ONE_SIXTH = 1.0 / 6.0;
const TWO_THIRD = 2.0 / 3.0;

function hueChannel(m1: number, m2: number, hue: number): number {
  hue = pyMod(hue, 1.0);
  if (hue < ONE_SIXTH) return m1 + (m2 - m1) * hue * 6.0;
  if (hue < 0.5) return m2;
  if (hue < TWO_THIRD) return m1 + (m2 - m1) * (TWO_THIRD - hue) * 6.0;
  return m1;
}

function hlsToRgb(h: number, l: number, s: number): [number, number, number] {
  if (s === 0.0) return [l, l, l];
  const m2 = l <= 0.5 ? l * (1.0 + s) : l + s - l * s;
  const m1 = 2.0 * l - m2;
  return [hueChannel(m1, m2, h + ONE_THIRD), hueChannel(m1, m2, h), hueChannel(m1, m2, h - ONE_THIRD)];
}

/** _gradient_end: mesma matiz, 25% mais clara (ou mais escura, se já for muito clara). */
export function gradientEnd(rgb: [number, number, number]): [number, number, number] {
  const [h, l0, s] = rgbToHls(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255);
  const l = l0 > 0.75 ? l0 - 0.25 : Math.min(1.0, l0 + 0.25);
  return hlsToRgb(h, l, s).map((c) => pyRound(c * 255)) as [number, number, number];
}

/** apply_border: o recorte 225x350 com a borda do estilo (imagem nova). */
export function applyBorder(cropped: Raster, style: BorderStyle, colorHex: string, masks: BorderMasks): Raster {
  const out = cloneRaster(cropped);
  const d = out.data;
  const [r, g, b] = parseHexColor(colorHex);
  const { width, height } = out;
  const band = masks.band;

  if (style === "degrade") {
    const end = gradientEnd([r, g, b]);
    for (let y = 0; y < height; y++) {
      const t = y / Math.max(1, height - 1);
      const [gr, gg, gb] = [r, g, b].map((v, c) => pyRound(v + (end[c] - v) * t));
      for (let x = 0; x < width; x++) {
        const m = y * width + x;
        compositePixel(d, m * 4, gr, gg, gb, band[m]);
      }
    }
    return out;
  }

  for (let m = 0; m < width * height; m++) {
    const i = m * 4;
    if (style === "simples" || !(style in masks)) {
      // draw.rectangle do Pillow: troca o pixel pela cor sólida
      if (band[m] === 255) {
        d[i] = r;
        d[i + 1] = g;
        d[i + 2] = b;
        d[i + 3] = 255;
      }
    } else if (style === "sombra") {
      // faixa na cor; fora dela, a sombra preta desfocada
      if (band[m] === 255) compositePixel(d, i, r, g, b, masks.sombra[m]);
      else compositePixel(d, i, 0, 0, 0, masks.sombra[m]);
    } else {
      compositePixel(d, i, r, g, b, masks[style as "dupla" | "brilho"][m]);
    }
  }
  return out;
}
