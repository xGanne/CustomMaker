/**
 * Enquadramento: onde a imagem fica em relação à borda (mesmo modelo do PC:
 * posição e tamanho em pixels da custom, com a borda em BORDA_POS).
 *
 * Funções puras: os gestos da tela (arrastar, pinça, toque duplo) só chamam
 * estas contas, que são testadas sem tela.
 */
import { autoFit } from "./autofit";

export interface Framing {
  pos: [number, number];
  size: [number, number];
}

export const BORDA_POS: [number, number] = [0, 0];

/** Limites do zoom, relativos ao encaixe automático. */
export const MIN_ZOOM = 0.25;
export const MAX_ZOOM = 12;

/** Encaixe automático (cobre a borda inteira, centralizado). */
export function fitFraming(imageWidth: number, imageHeight: number): Framing | null {
  const fit = autoFit(imageWidth, imageHeight, BORDA_POS);
  if (!fit) return null;
  const [w, h, x, y] = fit;
  return { pos: [x, y], size: [w, h] };
}

/** Arrastar: move a imagem `dx, dy` pixels da custom. */
export function pan(framing: Framing, dx: number, dy: number): Framing {
  return { pos: [framing.pos[0] + dx, framing.pos[1] + dy], size: framing.size };
}

/**
 * Zoom em torno de um ponto (o meio dos dedos), que fica parado na tela.
 * `fitWidth` é a largura do encaixe automático: o zoom fica entre
 * MIN_ZOOM e MAX_ZOOM vezes ela.
 */
export function zoomAt(framing: Framing, factor: number, cx: number, cy: number, fitWidth: number): Framing {
  const [w, h] = framing.size;
  const minW = fitWidth * MIN_ZOOM;
  const maxW = fitWidth * MAX_ZOOM;
  const newW = Math.min(maxW, Math.max(minW, w * factor));
  const applied = newW / w;
  const [x, y] = framing.pos;
  return {
    pos: [cx - (cx - x) * applied, cy - (cy - y) * applied],
    size: [newW, h * applied],
  };
}

/** Enquadramento como o PC guarda e o render usa: números inteiros. */
export function rounded(framing: Framing): Framing {
  return {
    pos: [Math.round(framing.pos[0]), Math.round(framing.pos[1])],
    size: [Math.max(1, Math.round(framing.size[0])), Math.max(1, Math.round(framing.size[1]))],
  };
}

export function framingKey(framing: Framing): string {
  const r = rounded(framing);
  return `${r.pos.join(",")}|${r.size.join(",")}`;
}
