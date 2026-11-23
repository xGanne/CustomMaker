/** Auto fit, igual a ImageProcessor.calculate_auto_fit_pos: cobre a borda inteira. */
import { rules } from "./rules";

/** [largura, altura, x, y] da imagem enquadrada, ou null se não der. */
export function autoFit(
  imageWidth: number,
  imageHeight: number,
  bordaPos: [number, number],
): [number, number, number, number] | null {
  const { width: W, height: H } = rules.border;
  const scale = Math.max(W / imageWidth, H / imageHeight);
  const newW = Math.trunc(imageWidth * scale);
  const newH = Math.trunc(imageHeight * scale);
  if (newW < 1 || newH < 1) return null;
  const [bx, by] = bordaPos;
  // // do Python arredonda para baixo (o resultado é negativo quando a imagem é maior)
  const posX = Math.trunc(bx + Math.floor((W - newW) / 2));
  const posY = Math.trunc(by + Math.floor((H - newH) / 2));
  return [newW, newH, posX, posY];
}
