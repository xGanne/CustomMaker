/** O repassador do Danbooru (web/proxy/danbooru-worker.js) só faz o que deve. */
import { afterEach, describe, expect, it, vi } from "vitest";

// @ts-expect-error: o Worker é JavaScript puro (colado no painel do Cloudflare)
import worker from "../proxy/danbooru-worker.js";

const SITE = "https://xganne.github.io";
const ctx = { waitUntil: () => undefined };

function call(path: string, init: RequestInit & { headers?: Record<string, string> } = {}) {
  return worker.fetch(new Request(`https://proxy.example${path}`, init), {}, ctx) as Promise<Response>;
}

function upstream() {
  const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) =>
    new Response("[]", { status: 200, headers: { "Content-Type": "application/json", "Set-Cookie": "x=1" } }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("repassador do Danbooru", () => {
  it("repassa a busca como programa (não navegador) e libera para o site", async () => {
    const fetchMock = upstream();
    const response = await call("/posts.json?tags=miku&limit=2", { headers: { Origin: SITE, Cookie: "segredo=1" } });
    expect(response.status).toBe(200);
    expect(response.headers.get("Access-Control-Allow-Origin")).toBe(SITE);
    expect(response.headers.get("Set-Cookie")).toBeNull(); // cookie do Danbooru não volta
    const [target, init] = fetchMock.mock.calls[0];
    expect(target).toBe("https://danbooru.donmai.us/posts.json?tags=miku&limit=2");
    const headers = new Headers(init?.headers);
    expect(headers.get("User-Agent")).toMatch(/^CustomMakerv2\//);
    expect(headers.get("Cookie")).toBeNull(); // nada do celular vai para o Danbooru
  });

  it("imagens: /cdn/... vira cdn.donmai.us e vale a página de origem (Referer das <img>)", async () => {
    const fetchMock = upstream();
    const response = await call("/cdn/preview/ab/cd/abcd.jpg", { headers: { Referer: `${SITE}/CustomMaker/` } });
    expect(response.status).toBe(200);
    expect(fetchMock.mock.calls[0][0]).toBe("https://cdn.donmai.us/preview/ab/cd/abcd.jpg");
  });

  it("recusa outros sites, outros caminhos e outros métodos", async () => {
    const fetchMock = upstream();
    expect((await call("/posts.json", { headers: { Origin: "https://outro.site" } })).status).toBe(403);
    expect((await call("/posts.json")).status).toBe(403); // sem origem nenhuma
    expect((await call("/users.json", { headers: { Origin: SITE } })).status).toBe(404);
    expect((await call("/posts.json", { method: "POST", headers: { Origin: SITE } })).status).toBe(405);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("responde o preflight do CORS", async () => {
    const response = await call("/posts.json", { method: "OPTIONS", headers: { Origin: SITE } });
    expect(response.status).toBe(204);
    expect(response.headers.get("Access-Control-Allow-Methods")).toBe("GET");
  });
});
