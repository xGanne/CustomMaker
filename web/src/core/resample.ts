/**
 * Redimensionamento Lanczos idêntico ao do Pillow (Resample.c), bit a bit.
 *
 * O PC usa Image.resize(..., LANCZOS). O canvas do navegador não tem Lanczos e o
 * de outras bibliotecas não sai igual; isto reproduz o algoritmo do Pillow:
 * coeficientes em double, convertidos para ponto fixo de 22 bits, passada
 * horizontal e depois vertical. Imagens com transparência são premultiplicadas
 * antes (RGBA -> RGBa) e desfeitas depois, como o Pillow faz.
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
  bounds: Int32Array; // [xmin, xmax] por pixel de saída
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

function clip8(value: number): number {
  const v = value >> PRECISION_BITS;
  return v < 0 ? 0 : v > 255 ? 255 : v;
}

function horizontal(src: Raster, outWidth: number): Raster {
  const { ksize, bounds, weights } = precompute(src.width, outWidth);
  const out = createRaster(outWidth, src.height);
  const half = 1 << (PRECISION_BITS - 1);
  for (let y = 0; y < src.height; y++) {
    const row = y * src.width * 4;
    for (let xx = 0; xx < outWidth; xx++) {
      const xmin = bounds[xx * 2];
      const xmax = bounds[xx * 2 + 1];
      const kOffset = xx * ksize;
      let s0 = half, s1 = half, s2 = half, s3 = half;
      for (let x = 0; x < xmax; x++) {
        const w = weights[kOffset + x];
        const p = row + (x + xmin) * 4;
        s0 += src.data[p] * w;
        s1 += src.data[p + 1] * w;
        s2 += src.data[p + 2] * w;
        s3 += src.data[p + 3] * w;
      }
      const o = (y * outWidth + xx) * 4;
      out.data[o] = clip8(s0);
      out.data[o + 1] = clip8(s1);
      out.data[o + 2] = clip8(s2);
      out.data[o + 3] = clip8(s3);
    }
  }
  return out;
}

function vertical(src: Raster, outHeight: number): Raster {
  const { ksize, bounds, weights } = precompute(src.height, outHeight);
  const out = createRaster(src.width, outHeight);
  const half = 1 << (PRECISION_BITS - 1);
  const stride = src.width * 4;
  for (let yy = 0; yy < outHeight; yy++) {
    const ymin = bounds[yy * 2];
    const ymax = bounds[yy * 2 + 1];
    const kOffset = yy * ksize;
    for (let x = 0; x < src.width; x++) {
      let s0 = half, s1 = half, s2 = half, s3 = half;
      for (let y = 0; y < ymax; y++) {
        const w = weights[kOffset + y];
        const p = (y + ymin) * stride + x * 4;
        s0 += src.data[p] * w;
        s1 += src.data[p + 1] * w;
        s2 += src.data[p + 2] * w;
        s3 += src.data[p + 3] * w;
      }
      const o = (yy * src.width + x) * 4;
      out.data[o] = clip8(s0);
      out.data[o + 1] = clip8(s1);
      out.data[o + 2] = clip8(s2);
      out.data[o + 3] = clip8(s3);
    }
  }
  return out;
}

/** RGBA -> RGBa do Pillow (MULDIV255). Devolve null se a imagem é opaca. */
function premultiply(src: Raster): Raster | null {
  const d = src.data;
  let opaque = true;
  for (let i = 3; i < d.length; i += 4) {
    if (d[i] !== 255) {
      opaque = false;
      break;
    }
  }
  if (opaque) return null; // multiplicar por 255 não muda nada
  const out = createRaster(src.width, src.height);
  for (let i = 0; i < d.length; i += 4) {
    const a = d[i + 3];
    for (let c = 0; c < 3; c++) {
      const tmp = d[i + c] * a + 128;
      out.data[i + c] = ((tmp >> 8) + tmp) >> 8;
    }
    out.data[i + 3] = a;
  }
  return out;
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

/** Image.resize((width, height), Image.LANCZOS) do Pillow. */
export function resizeLanczos(src: Raster, width: number, height: number): Raster {
  if (width === src.width && height === src.height) {
    return { width, height, data: new Uint8ClampedArray(src.data) };
  }
  const premultiplied = premultiply(src);
  let work = premultiplied ?? src;
  if (width !== work.width) work = horizontal(work, width);
  if (height !== work.height) work = vertical(work, height);
  return premultiplied ? unpremultiply(work) : work;
}
