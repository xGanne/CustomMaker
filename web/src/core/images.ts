/** Abrir imagens (arquivo do celular ou URL do Danbooru) como Raster. */
import type { Raster } from "./raster";

// fotos de celular passam de 4000 px: acima disto, decodifica já reduzida
export const MAX_SOURCE_SIDE = 2400;

/** Decodifica sem conversão de cor (o Pillow do PC também ignora o perfil da imagem). */
export async function decodeImage(blob: Blob, maxSide = MAX_SOURCE_SIDE): Promise<Raster> {
  const options: ImageBitmapOptions = { colorSpaceConversion: "none", premultiplyAlpha: "none" };
  let bitmap = await createImageBitmap(blob, options);
  const longest = Math.max(bitmap.width, bitmap.height);
  if (longest > maxSide) {
    const scale = maxSide / longest;
    const [w, h] = [Math.round(bitmap.width * scale), Math.round(bitmap.height * scale)];
    bitmap.close();
    bitmap = await createImageBitmap(blob, { ...options, resizeWidth: w, resizeHeight: h, resizeQuality: "high" });
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
