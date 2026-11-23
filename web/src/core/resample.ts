/**
 * Redimensionamento Lanczos idêntico ao do Pillow (Resample.c), bit a bit.
 *
 * O PC usa Image.resize(..., LANCZOS). O canvas do navegador não tem Lanczos e o
 * de outras bibliotecas não sai igual; isto reproduz o algoritmo do Pillow:
 * coeficientes em double, convertidos para ponto fixo de 22 bits, passada
 * horizontal e depois vertical. Imagens com transparência são premultiplicadas
 * antes (RGBA -> RGBa) e desfeitas depois, como o Pillow faz.
 *
 * Cada pixel de saída depende só dos seus coeficientes, então dá para calcular
 * apenas um pedaço da imagem redimensionada (resizeLanczosRegion) com o mesmo
 * resultado de redimensionar tudo e recortar — a custom usa só 225x350 dela.
 */
import { createRaster, type Raster } from "./raster";

const PRECISION_BITS = 32 - 8 - 2;
const SUPPORT = 3.0;

function sinc(x: number): number {
  if (x === 0) return 1;
  const px = x * Math.PI;
  return Math.sin(px) / px;
}

function lanczos(x: number): number {
  return x >= -3.0 && x < 3.0 ? sinc(x) * sinc(x / 3) : 0;
}

interface Coefficients {
  ksize: number;
  bounds: Int32Array; // [xmin, xmax] por pixel de saída (xmax = quantos pixels de entrada)
  weights: Int32Array; // ksize pesos por pixel de saída
}

function precompute(inSize: number, outSize: number): Coefficients {
  const scale = inSize / outSize;
  const filterScale = Math.max(1.0, scale);
  const support = SUPPORT * filterScale;
  const ksize = Math.ceil(support) * 2 + 1;
  const bounds = new Int32Array(outSize * 2);
  const weights = new Int32Array(outSize * ksize);
  const k = new Float64Array(ksize);
  for (let xx = 0; xx < outSize; xx++) {
    const center = (xx + 0.5) * scale;
    const ss = 1.0 / filterScale;
    let xmin = Math.trunc(center - support + 0.5);
    if (xmin < 0) xmin = 0;
    let xmax = Math.trunc(center + support + 0.5);
    if (xmax > inSize) xmax = inSize;
    xmax -= xmin;
    let ww = 0.0;
    for (let x = 0; x < xmax; x++) {
      const w = lanczos((x + xmin - center + 0.5) * ss);
      k[x] = w;
      ww += w;
    }
    for (let x = 0; x < ksize; x++) {
      let w = x < xmax ? k[x] : 0;
      if (x < xmax && ww !== 0.0) w /= ww;
      // normalize_coeffs_8bpc: arredonda para longe do zero
      weights[xx * ksize + x] = w < 0
        ? Math.trunc(-0.5 + w * (1 << PRECISION_BITS))
        : Math.trunc(0.5 + w * (1 << PRECISION_BITS));
    }
    bounds[xx * 2] = xmin;
    bounds[xx * 2 + 1] = xmax;
  }
  return { ksize, bounds, weights };
}

/** Faixa [início, fim) da entrada que as saídas [from, to) leem. */
function inputSpan(c: Coefficients, from: number, to: number): [number, number] {
  let start = Infinity;
  let end = 0;
  for (let i = from; i < to; i++) {
    start = Math.min(start, c.bounds[i * 2]);
    end = Math.max(end, c.bounds[i * 2] + c.bounds[i * 2 + 1]);
  }
  return [start, end];
}

function clip8(value: number): number {
  const v = value >> PRECISION_BITS;
  return v < 0 ? 0 : v > 255 ? 255 : v;
}

/**
 * Passada horizontal só das colunas de saída [x0, x1). `src` começa na coluna
 * `srcX` da imagem de entrada (as coordenadas dos coeficientes são absolutas).
 */
function horizontal(src: Raster, srcX: number, c: Coefficients, x0: number, x1: number): Raster {
  const { ksize, bounds, weights } = c;
  const outWidth = x1 - x0;
  const out = createRaster(outWidth, src.height);
  const sd = src.data;
  const od = out.data;
  const half = 1 << (PRECISION_BITS - 1);
  for (let y = 0; y < src.height; y++) {
    const row = y * src.width * 4;
    for (let xx = x0; xx < x1; xx++) {
      const xmin = bounds[xx * 2] - srcX;
      const xmax = bounds[xx * 2 + 1];
      const kOffset = xx * ksize;
      let s0 = half, s1 = half, s2 = half, s3 = half;
      for (let x = 0; x < xmax; x++) {
        const w = weights[kOffset + x];
        const p = row + (x + xmin) * 4;
        s0 += sd[p] * w;
        s1 += sd[p + 1] * w;
        s2 += sd[p + 2] * w;
        s3 += sd[p + 3] * w;
      }
      const o = (y * outWidth + (xx - x0)) * 4;
      od[o] = clip8(s0);
      od[o + 1] = clip8(s1);
      od[o + 2] = clip8(s2);
      od[o + 3] = clip8(s3);
    }
  }
  return out;
}

/** Passada vertical só das linhas de saída [y0, y1); `src` começa na linha `srcY`. */
function vertical(src: Raster, srcY: number, c: Coefficients, y0: number, y1: number): Raster {
  const { ksize, bounds, weights } = c;
  const out = createRaster(src.width, y1 - y0);
  const sd = src.data;
  const od = out.data;
  const half = 1 << (PRECISION_BITS - 1);
  const stride = src.width * 4;
  for (let yy = y0; yy < y1; yy++) {
    const ymin = bounds[yy * 2] - srcY;
    const ymax = bounds[yy * 2 + 1];
    const kOffset = yy * ksize;
    for (let x = 0; x < src.width; x++) {
      let s0 = half, s1 = half, s2 = half, s3 = half;
      for (let y = 0; y < ymax; y++) {
        const w = weights[kOffset + y];
        const p = (y + ymin) * stride + x * 4;
        s0 += sd[p] * w;
        s1 += sd[p + 1] * w;
        s2 += sd[p + 2] * w;
        s3 += sd[p + 3] * w;
      }
      const o = ((yy - y0) * src.width + x) * 4;
      od[o] = clip8(s0);
      od[o + 1] = clip8(s1);
      od[o + 2] = clip8(s2);
      od[o + 3] = clip8(s3);
    }
  }
  return out;
}

/**
 * Copia o retângulo [x0, x1) x [y0, y1) da imagem; com alfa parcial, já
 * premultiplicado como o RGBA -> RGBa do Pillow (MULDIV255).
 */
function extract(src: Raster, x0: number, y0: number, x1: number, y1: number): { raster: Raster; premultiplied: boolean } {
  const width = x1 - x0;
  const out = createRaster(width, y1 - y0);
  const sd = src.data;
  const od = out.data;
  let premultiplied = false;
  for (let y = y0; y < y1; y++) {
    const from = (y * src.width + x0) * 4;
    od.set(sd.subarray(from, from + width * 4), (y - y0) * width * 4);
    if (!premultiplied) {
      for (let i = from + 3; i < from + width * 4; i += 4) {
        if (sd[i] !== 255) {
          premultiplied = true;
          break;
        }
      }
    }
  }
  if (premultiplied) {
    // multiplicar por 255 não muda nada: só vale a pena com alfa parcial
    for (let i = 0; i < od.length; i += 4) {
      const a = od[i + 3];
      for (let c = 0; c < 3; c++) {
        const tmp = od[i + c] * a + 128;
        od[i + c] = ((tmp >> 8) + tmp) >> 8;
      }
    }
  }
  return { raster: out, premultiplied };
}

/** RGBa -> RGBA do Pillow (divisão inteira, alfa 0 e 255 intactos). */
function unpremultiply(raster: Raster): Raster {
  const d = raster.data;
  for (let i = 0; i < d.length; i += 4) {
    const a = d[i + 3];
    if (a === 255 || a === 0) continue;
    for (let c = 0; c < 3; c++) d[i + c] = Math.min(255, Math.floor((255 * d[i + c]) / a));
  }
  return raster;
}

/** Retângulo [x0, y0, x1, y1) de uma imagem. */
export type Box = [number, number, number, number];

/**
 * O mesmo que `resizeLanczos(src, width, height)` recortado em `box`, calculando
 * só os pixels do recorte (e só a parte da entrada que eles leem).
 */
export function resizeLanczosRegion(src: Raster, width: number, height: number, box: Box): Raster {
  const [x0, y0, x1, y1] = box;
  if (!(0 <= x0 && x0 <= x1 && x1 <= width && 0 <= y0 && y0 <= y1 && y1 <= height)) {
    throw new RangeError(`recorte fora da imagem: ${box} em ${width}x${height}`);
  }
  if (x0 === x1 || y0 === y1) return createRaster(x1 - x0, y1 - y0);
  const hc = width !== src.width ? precompute(src.width, width) : null;
  const vc = height !== src.height ? precompute(src.height, height) : null;
  // pedaço da entrada que o recorte usa
  const [sx0, sx1] = hc ? inputSpan(hc, x0, x1) : [x0, x1];
  const [sy0, sy1] = vc ? inputSpan(vc, y0, y1) : [y0, y1];
  const { raster: part, premultiplied } = extract(src, sx0, sy0, sx1, sy1);
  // mesma ordem do Pillow: horizontal, depois vertical
  let work = hc ? horizontal(part, sx0, hc, x0, x1) : part;
  if (vc) work = vertical(work, sy0, vc, y0, y1);
  return premultiplied ? unpremultiply(work) : work;
}

/** Image.resize((width, height), Image.LANCZOS) do Pillow. */
export function resizeLanczos(src: Raster, width: number, height: number): Raster {
  return resizeLanczosRegion(src, width, height, [0, 0, width, height]);
}
