import { describe, expect, it } from "vitest";

import { autoFit } from "../src/core/autofit";
import { BORDA_POS, fitFraming, framingKey, MAX_ZOOM, MIN_ZOOM, pan, rounded, zoomAt } from "../src/core/framing";

describe("enquadramento", () => {
  it("o encaixe automático é o mesmo auto fit do PC", () => {
    const fit = autoFit(1000, 1500, BORDA_POS)!;
    expect(fitFraming(1000, 1500)).toEqual({ pos: [fit[2], fit[3]], size: [fit[0], fit[1]] });
  });

  it("arrastar move sem mudar o tamanho", () => {
    const start = fitFraming(1000, 1500)!;
    const moved = pan(start, 12, -7);
    expect(moved.size).toEqual(start.size);
    expect(moved.pos).toEqual([start.pos[0] + 12, start.pos[1] - 7]);
  });

  it("o ponto entre os dedos fica parado no zoom", () => {
    const start = { pos: [-20, -10] as [number, number], size: [300, 450] as [number, number] };
    const [cx, cy] = [100, 150];
    // ponto da imagem sob os dedos, em proporção da imagem, antes e depois
    const before = [(cx - start.pos[0]) / start.size[0], (cy - start.pos[1]) / start.size[1]];
    const zoomed = zoomAt(start, 2, cx, cy, 300);
    const after = [(cx - zoomed.pos[0]) / zoomed.size[0], (cy - zoomed.pos[1]) / zoomed.size[1]];
    expect(after[0]).toBeCloseTo(before[0], 10);
    expect(after[1]).toBeCloseTo(before[1], 10);
    expect(zoomed.size[0] / zoomed.size[1]).toBeCloseTo(start.size[0] / start.size[1], 10); // proporção mantida
  });

  it("o zoom tem limites relativos ao encaixe", () => {
    const start = { pos: [0, 0] as [number, number], size: [300, 450] as [number, number] };
    expect(zoomAt(start, 1000, 0, 0, 300).size[0]).toBeCloseTo(300 * MAX_ZOOM, 10);
    expect(zoomAt(start, 0.0001, 0, 0, 300).size[0]).toBeCloseTo(300 * MIN_ZOOM, 10);
  });

  it("arredonda para inteiros (como o PC guarda) e a chave muda com o enquadramento", () => {
    const framing = { pos: [10.4, -3.6] as [number, number], size: [250.5, 380.2] as [number, number] };
    expect(rounded(framing)).toEqual({ pos: [10, -4], size: [251, 380] });
    expect(framingKey(framing)).not.toBe(framingKey(pan(framing, 3, 0)));
  });
});
