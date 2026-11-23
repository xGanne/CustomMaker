/**
 * Gravação de PNG RGBA sem passar pelo canvas.
 *
 * O canvas guarda os pixels premultiplicados: exportar por ele (toBlob) muda a
 * cor dos pixels semitransparentes (brilho/sombra sobre área transparente) e a
 * custom deixaria de ser igual à do PC. Aqui os bytes saem exatamente como estão.
 */
import type { Raster } from "./raster";

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type: string, data: Uint8Array): Uint8Array {
  const out = new Uint8Array(12 + data.length);
  const view = new DataView(out.buffer);
  view.setUint32(0, data.length);
  for (let i = 0; i < 4; i++) out[4 + i] = type.charCodeAt(i);
  out.set(data, 8);
  view.setUint32(8 + data.length, crc32(out.subarray(4, 8 + data.length)));
  return out;
}

async function zlib(data: Uint8Array): Promise<Uint8Array> {
  // "deflate" das Compression Streams = formato zlib, o que o PNG usa
  const stream = new Blob([data as BlobPart]).stream().pipeThrough(new CompressionStream("deflate"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** Distância de Paeth (especificação do PNG). */
function paeth(a: number, b: number, c: number): number {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
}

/**
 * Filtra as linhas como o Pillow/libpng: para cada linha testa os 5 filtros e
 * fica com o de menor soma dos bytes vistos como com sinal (o que costuma
 * comprimir melhor). Sem isso o PNG saía uns 20% maior que o do PC.
 */
function filterRows(data: Uint8ClampedArray, width: number, height: number): Uint8Array {
  const bpp = 4;
  const rowBytes = width * bpp;
  const out = new Uint8Array((rowBytes + 1) * height);
  const candidates = Array.from({ length: 5 }, () => new Uint8Array(rowBytes));
  const zero = new Uint8Array(rowBytes);
  for (let y = 0; y < height; y++) {
    const row = data.subarray(y * rowBytes, (y + 1) * rowBytes);
    const prev = y > 0 ? data.subarray((y - 1) * rowBytes, y * rowBytes) : zero;
    let best = 0;
    let bestSum = Infinity;
    for (let type = 0; type < 5; type++) {
      const line = candidates[type];
      let sum = 0;
      for (let i = 0; i < rowBytes; i++) {
        const a = i >= bpp ? row[i - bpp] : 0;
        const b = prev[i];
        const c = i >= bpp ? prev[i - bpp] : 0;
        const predictor = type === 0 ? 0 : type === 1 ? a : type === 2 ? b : type === 3 ? (a + b) >> 1 : paeth(a, b, c);
        const value = (row[i] - predictor) & 0xff;
        line[i] = value;
        sum += value < 128 ? value : 256 - value;
      }
      if (sum < bestSum) {
        bestSum = sum;
        best = type;
      }
    }
    out[y * (rowBytes + 1)] = best;
    out.set(candidates[best], y * (rowBytes + 1) + 1);
  }
  return out;
}

/** Bytes de um PNG RGBA 8 bits com os pixels de `raster`. */
export async function encodePng(raster: Raster): Promise<Uint8Array> {
  const { width, height, data } = raster;
  const header = new Uint8Array(13);
  const view = new DataView(header.buffer);
  view.setUint32(0, width);
  view.setUint32(4, height);
  header.set([8, 6, 0, 0, 0], 8); // 8 bits, RGBA, deflate, filtro adaptativo, sem entrelaçar

  const parts = [
    new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk("IHDR", header),
    chunk("IDAT", await zlib(filterRows(data, width, height))),
    chunk("IEND", new Uint8Array()),
  ];
  const out = new Uint8Array(parts.reduce((total, part) => total + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}
