/**
 * Recorte da custom, igual a ImageProcessor.render_image_to_borda do PC:
 * redimensiona a imagem inteira para o tamanho enquadrado e recorta a área da
 * borda. O que fica fora da imagem sai transparente. Aqui só a área recortada
 * é redimensionada (mesmos pixels, bem menos conta).
 */
import { resizeLanczosRegion } from "./resample";
import { createRaster, pyRound, type Raster } from "./raster";
import { rules } from "./rules";

export type Point = [number, number];

/** Recorte 225x350 (sem borda) da imagem posicionada em `pos` com tamanho `size`. */
export function renderToBorder(source: Raster, pos: Point, size: Point, bordaPos: Point): Raster {
  const { width: W, height: H } = rules.border;
  const out = createRaster(W, H);
  const imgW = Math.trunc(size[0]);
  const imgH = Math.trunc(size[1]);
  if (imgW <= 0 || imgH <= 0) return out;

  const [bx, by] = bordaPos;
  const [x, y] = pos;
  const relX1 = Math.max(0, bx - x);
  const relY1 = Math.max(0, by - y);
  const relX2 = Math.min(imgW, bx + W - x);
  const relY2 = Math.min(imgH, by + H - y);
  if (relX1 >= relX2 || relY1 >= relY2) return out;

  // Image.crop arredonda com round() do Python; paste também
  const x0 = pyRound(relX1);
  const y0 = pyRound(relY1);
  const pasteX = pyRound(Math.max(0, x - bx));
  const pasteY = pyRound(Math.max(0, y - by));
  // paste do Pillow corta o que passa da custom: nem precisa calcular essa parte
  const x1 = Math.min(pyRound(relX2), x0 + W - pasteX);
  const y1 = Math.min(pyRound(relY2), y0 + H - pasteY);
  if (x0 >= x1 || y0 >= y1) return out;

  const piece = resizeLanczosRegion(source, imgW, imgH, [x0, y0, x1, y1]);
  const rowBytes = piece.width * 4;
  for (let row = 0; row < piece.height; row++) {
    const from = row * rowBytes;
    out.data.set(piece.data.subarray(from, from + rowBytes), ((pasteY + row) * W + pasteX) * 4);
  }
  return out;
}
