import { describe, expect, it } from "vitest";

import { type Box, resizeLanczos, resizeLanczosRegion } from "../src/core/resample";
import { createRaster, type Raster } from "../src/core/raster";

function noise(width: number, height: number, alpha: (i: number) => number): Raster {
  const raster = createRaster(width, height);
  let seed = 12345;
  for (let i = 0; i < raster.data.length; i++) {
    seed = (seed * 1103515245 + 12345) >>> 0;
    raster.data[i] = i % 4 === 3 ? alpha(i >> 2) : seed >>> 24;
  }
  return raster;
}

function crop(raster: Raster, [x0, y0, x1, y1]: Box): Raster {
  const out = createRaster(x1 - x0, y1 - y0);
  for (let y = y0; y < y1; y++) {
    out.data.set(raster.data.subarray((y * raster.width + x0) * 4, (y * raster.width + x1) * 4), (y - y0) * out.width * 4);
  }
  return out;
}

describe("redimensionar só um pedaço", () => {
  const opaque = noise(97, 131, () => 255);
  const transparent = noise(97, 131, (p) => (p * 7) % 256);
  // reduzir, ampliar, um eixo só, mesmo tamanho; recortes no meio e nas bordas
  const cases: [string, Raster, number, number, Box][] = [
    ["reduz", opaque, 40, 61, [5, 7, 33, 50]],
    ["amplia", opaque, 230, 300, [0, 12, 225, 300]],
    ["reduz com alfa", transparent, 40, 61, [0, 0, 40, 61]],
    ["amplia com alfa", transparent, 200, 260, [100, 3, 200, 140]],
    ["só a largura", transparent, 50, 131, [10, 20, 45, 131]],
    ["só a altura", opaque, 97, 300, [0, 290, 97, 300]],
    ["mesmo tamanho", transparent, 97, 131, [3, 4, 50, 60]],
    ["pedaço opaco de imagem com alfa", noise(60, 60, (p) => (p < 1800 ? 255 : 90)), 31, 31, [0, 0, 31, 10]],
  ];
  for (const [name, source, width, height, box] of cases) {
    it(name, () => {
      const region = resizeLanczosRegion(source, width, height, box);
      expect(region).toEqual(crop(resizeLanczos(source, width, height), box));
    });
  }

  it("recorte vazio e recorte fora da imagem", () => {
    expect(resizeLanczosRegion(opaque, 40, 61, [5, 5, 5, 20]).data.length).toBe(0);
    expect(() => resizeLanczosRegion(opaque, 40, 61, [0, 0, 41, 61])).toThrow(RangeError);
  });
});
