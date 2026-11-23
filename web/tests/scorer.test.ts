/** ★ Auto igual ao do PC (tests/fixtures/scorer.json, gerado pelo Python). */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { PNG } from "pngjs";
import { describe, expect, it } from "vitest";

import type { Post } from "../src/core/danbooru";
import type { Raster } from "../src/core/raster";
import {
  autoSelect,
  colorfulFraction,
  isAutoEligible,
  metadataScore,
  parseAvoidTags,
} from "../src/core/scorer";

const fixtures = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
const data = JSON.parse(readFileSync(join(fixtures, "scorer.json"), "utf-8")) as {
  scorer: {
    customAvoidTags: string;
    posts: { post: Post; eligible: boolean; score: number; scoreCustomAvoid: number; scoreNoAvoid: number }[];
  };
  color: { image: string; fraction: number; grayscale: boolean }[];
};

function readPng(name: string): Raster {
  const png = PNG.sync.read(readFileSync(join(fixtures, name)));
  return { width: png.width, height: png.height, data: new Uint8ClampedArray(png.data) };
}

describe("pontuação igual à do PC", () => {
  const custom = parseAvoidTags(data.scorer.customAvoidTags);
  for (const row of data.scorer.posts) {
    it(`post ${row.post.id} (${row.post.rating || "sem classificação"}: ${row.post.tag_string})`, () => {
      expect(isAutoEligible(row.post)).toBe(row.eligible);
      expect(metadataScore(row.post)).toBeCloseTo(row.score, 10);
      expect(metadataScore(row.post, custom)).toBeCloseTo(row.scoreCustomAvoid, 10);
      expect(metadataScore(row.post, new Set())).toBeCloseTo(row.scoreNoAvoid, 10);
    });
  }
});

describe("checagem de cor (pega mangá sem a tag certa)", () => {
  for (const row of data.color) {
    it(row.image, () => {
      const fraction = colorfulFraction(readPng(row.image));
      // o PC reduz com outro filtro antes de contar (no sépia muitos pixels ficam no
      // limite de saturação): a fração fica próxima e a decisão, igual
      expect(Math.abs(fraction - row.fraction)).toBeLessThan(0.05);
      expect(fraction < 0.05).toBe(row.grayscale);
    });
  }
});

describe("★ Auto em várias páginas", () => {
  const post = (id: number, rating: string, tags = "1girl solo upper_body"): Post => ({
    id, rating, tag_string: tags, tag_string_character: "miku", image_width: 1000,
    image_height: 1500, file_ext: "png", fav_count: 10,
  });
  const manga = "monochrome comic speech_bubble multiple_girls";
  const colorful = async () => null; // sem prévia: só os metadados contam

  it("segue para as próximas páginas até achar a quantidade", async () => {
    const pages: Record<number, Post[]> = {
      2: [post(3, "g", manga), post(4, "g")],
      3: [post(5, "g", "1girl solo"), post(6, "q")],
    };
    const fetched: number[] = [];
    const result = await autoSelect({
      count: 2, firstPage: 1, firstPosts: [post(1, "g", manga), post(2, "e")], pageSize: 2,
      fetchPage: async (page) => {
        fetched.push(page);
        return pages[page] ?? [];
      },
      loadPreview: colorful, alreadySelected: new Set(),
    });
    expect(result.posts.map((p) => p.id).sort()).toEqual([4, 5]);
    expect(fetched).toEqual([2, 3]);
    expect([result.pages, result.lastPage, result.excluded]).toEqual([3, 3, 2]);
  });

  it("nunca escolhe questionável/explícito nem o já marcado, e não completa com ruins", async () => {
    const result = await autoSelect({
      count: 5, firstPage: 1, pageSize: 40, fetchPage: null, loadPreview: colorful,
      firstPosts: [post(1, "e"), post(2, "q"), post(3, "g"), post(4, "g", manga), post(5, "g")],
      alreadySelected: new Set([5]),
    });
    expect(result.posts.map((p) => p.id)).toEqual([3]);
  });

  it("prévia em P&B derruba um candidato que passava pelas tags", async () => {
    const gray: Raster = { width: 4, height: 4, data: new Uint8ClampedArray(64).fill(128) };
    const red: Raster = { width: 4, height: 4, data: new Uint8ClampedArray(64).map((_, i) => (i % 4 === 0 || i % 4 === 3 ? 255 : 0)) };
    const candidate = { ...post(1, "g", ""), fav_count: 0 }; // ~2,9 pontos: só proporção e personagem
    expect(metadataScore(candidate)).toBeGreaterThan(0);
    expect(metadataScore(candidate)).toBeLessThan(4); // a penalidade de P&B é 4
    const run = (preview: Raster) => autoSelect({
      count: 1, firstPage: 1, pageSize: 40, fetchPage: null, alreadySelected: new Set(),
      firstPosts: [candidate], loadPreview: async () => preview,
    });
    expect((await run(red)).posts.map((p) => p.id)).toEqual([1]);
    expect((await run(gray)).posts).toEqual([]);
  });
});
