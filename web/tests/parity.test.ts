/**
 * Paridade com o PC: as customs geradas aqui têm que ser idênticas, pixel a
 * pixel, às de referência geradas pelo código Python (scripts/web_fixtures.py).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { PNG } from "pngjs";
import { beforeAll, describe, expect, it } from "vitest";

import { autoFit } from "../src/core/autofit";
import { applyBorder, gradientEnd, loadMasks, type BorderMasks } from "../src/core/borders";
import { parseHexColor, pyRound, type Raster } from "../src/core/raster";
import { renderToBorder } from "../src/core/render";
import type { BorderStyle } from "../src/core/rules";

const here = dirname(fileURLToPath(import.meta.url));
const fixtures = join(here, "fixtures");

interface Case {
  name: string;
  source: string;
  pos: [number, number];
  size: [number, number];
  bordaPos: [number, number];
  color: string;
  style: BorderStyle;
  expected: string;
}

const manifest = JSON.parse(readFileSync(join(fixtures, "cases.json"), "utf-8")) as {
  cases: Case[];
  autofit: { source: string; bordaPos: [number, number]; fit: [number, number, number, number] };
  gradient: { color: string; end: [number, number, number] }[];
};

function readPng(name: string): Raster {
  const png = PNG.sync.read(readFileSync(join(fixtures, name)));
  return { width: png.width, height: png.height, data: new Uint8ClampedArray(png.data) };
}

/** Quantos pixels diferem e o primeiro deles (para a mensagem do erro). */
function compare(actual: Raster, expected: Raster) {
  let differing = 0;
  let first = "";
  for (let i = 0; i < expected.data.length; i += 4) {
    for (let c = 0; c < 4; c++) {
      if (actual.data[i + c] !== expected.data[i + c]) {
        if (!first) {
          const p = i / 4;
          first = `(${p % expected.width},${Math.floor(p / expected.width)}) ` +
            `obtido ${[...actual.data.slice(i, i + 4)]} esperado ${[...expected.data.slice(i, i + 4)]}`;
        }
        differing++;
        break;
      }
    }
  }
  return { differing, first };
}

let masks: BorderMasks;

beforeAll(async () => {
  masks = await loadMasks(readFileSync(join(here, "..", "public", "generated", "masks.bin.gz")));
});

describe("custom igual à do PC", () => {
  for (const testCase of manifest.cases) {
    it(testCase.name, () => {
      const source = readPng(`source-${testCase.source}.png`);
      const cropped = renderToBorder(source, testCase.pos, testCase.size, testCase.bordaPos);
      const custom = applyBorder(cropped, testCase.style, testCase.color, masks);
      const expected = readPng(testCase.expected);
      expect([custom.width, custom.height]).toEqual([expected.width, expected.height]);
      const { differing, first } = compare(custom, expected);
      expect(differing, `${differing} pixel(s) diferentes; primeiro: ${first}`).toBe(0);
    });
  }
});

describe("peças do render", () => {
  it("auto fit igual ao do PC", () => {
    const source = readPng(`source-${manifest.autofit.source}.png`);
    expect(autoFit(source.width, source.height, manifest.autofit.bordaPos)).toEqual(manifest.autofit.fit);
  });

  it("cor final do degradê igual ao colorsys do Python", () => {
    for (const { color, end } of manifest.gradient) {
      expect(gradientEnd(parseHexColor(color)), color).toEqual(end);
    }
  });

  it("round do Python arredonda .5 para o par", () => {
    expect([0.5, 1.5, 2.5, -0.5, -1.5, 2.4, 2.6].map(pyRound)).toEqual([0, 2, 2, 0, -2, 2, 3]);
  });
});
