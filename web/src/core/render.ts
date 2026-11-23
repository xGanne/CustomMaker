/**
 * Recorte da custom, igual a ImageProcessor.render_image_to_borda do PC:
 * redimensiona a imagem inteira para o tamanho enquadrado e recorta a área da
 * borda. O que fica fora da imagem sai transparente.
 */
import { resizeLanczos } from "./resample";
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
  const resized = resizeLanczos(source, imgW, imgH);

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
  const x1 = pyRound(relX2);
  const y1 = pyRound(relY2);
  const pasteX = pyRound(Math.max(0, x - bx));
  const pasteY = pyRound(Math.max(0, y - by));

  for (let cy = y0; cy < y1; cy++) {
    const ty = pasteY + (cy - y0);
    if (ty < 0 || ty >= H) continue;
    for (let cx = x0; cx < x1; cx++) {
      const tx = pasteX + (cx - x0);
      if (tx < 0 || tx >= W) continue; // paste do Pillow corta o que passa da custom
      const s = (cy * resized.width + cx) * 4;
      const t = (ty * W + tx) * 4;
      out.data[t] = resized.data[s];
      out.data[t + 1] = resized.data[s + 1];
      out.data[t + 2] = resized.data[s + 2];
      out.data[t + 3] = resized.data[s + 3];
    }
  }
  return out;
}
