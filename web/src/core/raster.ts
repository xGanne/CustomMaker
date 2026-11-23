/** Imagem RGBA em memória (mesmo formato do ImageData do navegador, sem premultiplicar). */
export interface Raster {
  width: number;
  height: number;
  data: Uint8ClampedArray<ArrayBuffer>;
}

export function createRaster(width: number, height: number): Raster {
  return { width, height, data: new Uint8ClampedArray(width * height * 4) };
}

export function cloneRaster(raster: Raster): Raster {
  return { width: raster.width, height: raster.height, data: new Uint8ClampedArray(raster.data) };
}

/** round() do Python: arredonda .5 para o par (o Pillow usa isso no recorte). */
export function pyRound(value: number): number {
  const floor = Math.floor(value);
  const diff = value - floor;
  if (diff > 0.5) return floor + 1;
  if (diff < 0.5) return floor;
  return floor % 2 === 0 ? floor : floor + 1;
}

/** % do Python para floats: o resultado tem o sinal do divisor. */
export function pyMod(value: number, divisor: number): number {
  let mod = value % divisor;
  if (mod !== 0 && divisor < 0 !== mod < 0) mod += divisor;
  return mod;
}

/** "#rrggbb" ou "#rgb" -> [r, g, b]. */
export function parseHexColor(hex: string): [number, number, number] {
  let value = hex.trim().replace(/^#/, "");
  if (value.length === 3) value = [...value].map((c) => c + c).join("");
  if (!/^[0-9a-fA-F]{6}$/.test(value)) throw new Error(`cor inválida: ${hex}`);
  return [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16)) as [number, number, number];
}
