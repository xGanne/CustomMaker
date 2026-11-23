import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  buildTags,
  DanbooruError,
  filterBlacklisted,
  importSource,
  parseTagList,
  searchPosts,
  type Post,
} from "../src/core/danbooru";

const PROXY = "https://repassador.example";

/** localStorage de mentira com o repassador configurado (como no aparelho). */
function withProxy(base: string | null = PROXY) {
  const data = new Map<string, string>();
  if (base) data.set("custommaker:proxy", JSON.stringify(base));
  vi.stubGlobal("localStorage", { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => data.set(k, v) });
}

beforeEach(() => withProxy());
afterEach(() => vi.unstubAllGlobals());

describe("montagem da busca", () => {
  it("junta texto, classificação, ordenação e proporção retrato", () => {
    expect(buildTags({ query: " hatsune_miku ", rating: "Geral", sort: "Mais recentes", portraitOnly: false }))
      .toBe("hatsune_miku rating:g");
    expect(buildTags({ query: "miku", rating: "Qualquer classificação", sort: "Melhor avaliados", portraitOnly: true }))
      .toBe("miku order:score ratio:0.5..0.85");
  });

  it("blacklist: minúsculas, sem '-' e sem repetir; filtra pelas tags do post", () => {
    expect(parseTagList("Gore  -blood gore")).toEqual(["gore", "blood"]);
    const posts = [{ id: 1, tag_string: "solo gore" }, { id: 2, tag_string: "solo" }] as Post[];
    expect(filterBlacklisted(posts, ["gore"]).map((p) => p.id)).toEqual([2]);
  });
});

describe("imagem a baixar (igual ao import_source do PC)", () => {
  const base = { id: 1, file_ext: "png", file_url: "https://cdn/orig.png", large_file_url: "https://cdn/large.jpg" };

  it("usa a versão large quando ela cobre o dobro da custom", () => {
    expect(importSource({ ...base, image_width: 1700, image_height: 2400 })).toBe("https://cdn/large.jpg");
  });

  it("usa o original quando a large ficaria baixa demais (imagem muito larga)", () => {
    expect(importSource({ ...base, image_width: 4000, image_height: 1500 })).toBe("https://cdn/orig.png");
  });

  it("vídeo não vira custom", () => {
    expect(importSource({ ...base, file_ext: "mp4", image_width: 1000, image_height: 1500 })).toBeNull();
  });
});

describe("erros da busca viram mensagens claras", () => {
  const respond = (status: number, body: unknown) =>
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));

  it("limite de tags (422) explica o que conta no limite", async () => {
    respond(422, { error: "PostQuery::TagLimitError", message: "You cannot search for more than 2 tags at a time" });
    await expect(searchPosts("a b c", 1, 40)).rejects.toThrow(/limite de tags.*classificação/s);
  });

  it("sem internet", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }));
    await expect(searchPosts("miku", 1, 40)).rejects.toBeInstanceOf(DanbooruError);
  });

  it("pede só os campos que o app usa, pelo repassador, e respeita o limite de páginas", async () => {
    const fetchMock = vi.fn(async () => new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await searchPosts("miku", 5000, 40);
    const url = new URL(String((fetchMock.mock.calls[0] as unknown[])[0]));
    expect(url.origin + url.pathname).toBe(`${PROXY}/posts.json`);
    expect(url.searchParams.get("page")).toBe("1000");
    expect(url.searchParams.get("only")).toContain("tag_string_character");
  });

  it("sem repassador configurado explica em vez de tentar o Danbooru direto", async () => {
    withProxy(null);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(searchPosts("miku", 1, 40)).rejects.toThrow(/repassador/);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("imagens pelo repassador", () => {
  it("URLs da CDN do Danbooru passam pelo repassador", () => {
    const post = {
      id: 1, file_ext: "png", image_width: 1700, image_height: 2400,
      file_url: "https://cdn.donmai.us/original/ab/cd/abcd.png",
      large_file_url: "https://cdn.donmai.us/sample/ab/cd/sample-abcd.jpg",
    };
    expect(importSource(post)).toBe(`${PROXY}/cdn/sample/ab/cd/sample-abcd.jpg`);
  });
});
