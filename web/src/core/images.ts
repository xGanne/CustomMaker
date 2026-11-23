/** Abrir imagens (arquivo do celular ou URL do Danbooru) como Raster. */
import type { Raster } from "./raster";

// fotos de celular passam de 4000 px: acima disto, decodifica já reduzida
export const MAX_SOURCE_SIDE = 2400;

/**
 * Largura e altura (já com a rotação do EXIF) sem decodificar os pixels: o
 * navegador lê só o cabeçalho até a imagem ser desenhada. null se não der.
 */
async function peekSize(blob: Blob): Promise<[number, number] | null> {
  if (typeof Image === "undefined" || typeof URL.createObjectURL !== "function") return null;
  const url = URL.createObjectURL(blob);
  try {
    const image = new Image();
    await new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = reject;
      image.src = url;
    });
    return image.naturalWidth && image.naturalHeight ? [image.naturalWidth, image.naturalHeight] : null;
  } catch {
    return null;
  } finally {
    URL.revokeObjectURL(url);
  }
}

/**
 * Decodifica sem conversão de cor (o Pillow do PC também ignora o perfil da
 * imagem). Fotos maiores que `maxSide` já saem reduzidas do decodificador: uma
 * foto de 108 MP aberta inteira ocuparia mais de 400 MB e derrubaria o app.
 */
export async function decodeImage(blob: Blob, maxSide = MAX_SOURCE_SIDE): Promise<Raster> {
  const options: ImageBitmapOptions = { colorSpaceConversion: "none", premultiplyAlpha: "none" };
  const size = await peekSize(blob);
  let bitmap: ImageBitmap;
  if (size && Math.max(...size) > maxSide) {
    // só o lado maior: o outro segue a proporção (mesmo se o EXIF girar a foto)
    const resize: ImageBitmapOptions = size[0] >= size[1]
      ? { resizeWidth: maxSide }
      : { resizeHeight: maxSide };
    bitmap = await createImageBitmap(blob, { ...options, ...resize, resizeQuality: "high" });
  } else {
    bitmap = await createImageBitmap(blob, options);
  }
  const longest = Math.max(bitmap.width, bitmap.height);
  if (longest > maxSide) {
    // sem o tamanho prévio (ou o EXIF trocou os lados): reduz a partir do bitmap
    const scale = maxSide / longest;
    const [w, h] = [Math.max(1, Math.round(bitmap.width * scale)), Math.max(1, Math.round(bitmap.height * scale))];
    const reduced = await createImageBitmap(bitmap, { ...options, resizeWidth: w, resizeHeight: h, resizeQuality: "high" });
    bitmap.close();
    bitmap = reduced;
  }
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const context = canvas.getContext("2d");
  if (!context) throw new Error("canvas indisponível");
  context.drawImage(bitmap, 0, 0);
  const image = context.getImageData(0, 0, bitmap.width, bitmap.height);
  bitmap.close();
  return { width: image.width, height: image.height, data: image.data };
}

/** Baixa e decodifica (a CDN do Danbooru aceita CORS). */
export async function fetchImage(url: string, signal?: AbortSignal, maxSide = MAX_SOURCE_SIDE): Promise<Raster> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`imagem: HTTP ${response.status}`);
  return decodeImage(await response.blob(), maxSide);
}
