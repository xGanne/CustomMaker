import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ImgChestAuthError, uploadCustoms } from "../src/core/imgchest";
import { mudaeCommands, suggestTitle } from "../src/core/mudae";

const fixtures = join(dirname(fileURLToPath(import.meta.url)), "fixtures");

afterEach(() => vi.unstubAllGlobals());

describe("comando $ai igual ao do PC", () => {
  const cases = JSON.parse(readFileSync(join(fixtures, "mudae.json"), "utf-8")) as
    { title: string; links: string[]; commands: string[] }[];
  for (const c of cases) {
    it(`${c.title}: ${c.links.length} imagem(ns) -> ${c.commands.length} mensagem(ns)`, () => {
      expect(mudaeCommands(c.title, c.links)).toEqual(c.commands);
      for (const command of c.commands) expect(command.length).toBeLessThanOrEqual(2000);
    });
  }

  it("sugere o nome da custom a partir da tag buscada", () => {
    expect(suggestTitle("hatsune_miku rating:g")).toBe("Hatsune Miku");
    expect(suggestTitle("nihilux_(honkai:_star_rail)")).toBe("Nihilux");
    expect(suggestTitle("")).toBe("");
  });
});

describe("envio ao ImgChest", () => {
  const files = (n: number) => Array.from({ length: n }, (_, i) => ({ name: `${i}_custom.png`, png: new Blob([`png${i}`]) }));
  const ok = (links: string[]) => new Response(JSON.stringify({ data: { images: links.map((link) => ({ link })) } }), { status: 200 });

  it("lotes de 10, post oculto, sem anônimo, pedindo JSON; links na ordem", async () => {
    const calls: { headers: Headers; form: FormData }[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init: RequestInit) => {
      const form = init.body as FormData;
      calls.push({ headers: new Headers(init.headers), form });
      return ok(form.getAll("images[]").map((f) => `https://imgchest/${(f as File).name}`));
    }));
    const result = await uploadCustoms(files(23), "Hatsune Miku", " tok ");
    expect(calls.length).toBe(3);
    expect(calls.map((c) => c.form.get("title"))).toEqual(["Hatsune Miku (Part 1)", "Hatsune Miku (Part 2)", "Hatsune Miku (Part 3)"]);
    expect(calls[0].form.get("privacy")).toBe("hidden");
    expect(calls[0].form.has("anonymous")).toBe(false);
    expect(calls[0].headers.get("Authorization")).toBe("Bearer tok");
    expect(calls[0].headers.get("Accept")).toBe("application/json");
    expect(result.links).toEqual(files(23).map((f) => `https://imgchest/${f.name}`));
    expect(result.errors).toEqual([]);
  });

  it("token inválido para tudo com uma mensagem clara", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response('{"message":"Unauthenticated."}', { status: 401 })));
    await expect(uploadCustoms(files(2), "Miku", "errado")).rejects.toBeInstanceOf(ImgChestAuthError);
    await expect(uploadCustoms(files(2), "Miku", "  ")).rejects.toThrow(/Configure o token/);
  });

  it("tenta de novo em erro temporário (500/429) e segue para o próximo lote se um falhar", async () => {
    let call = 0;
    vi.stubGlobal("fetch", vi.fn(async () => {
      call++;
      if (call === 1) return new Response("", { status: 503 }); // lote 1: falha temporária, depois passa
      if (call === 2) return ok(["a"]);
      return new Response("ruim", { status: 422 }); // lote 2: erro definitivo
    }));
    const result = await uploadCustoms(files(11), "Miku", "tok", { retryDelayMs: 0 });
    expect(result.links).toEqual(["a"]);
    expect(result.errors).toEqual(["Lote 2: HTTP 422 ruim"]);
  });
});
