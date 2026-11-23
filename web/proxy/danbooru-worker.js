/**
 * Repassador do Danbooru para o CustomMaker no celular (Cloudflare Worker).
 *
 * Por quê: o Cloudflare do Danbooru barra pedidos feitos por navegador
 * (403 "cf-mitigated: challenge"), com ou sem login. Este Worker faz os mesmos
 * pedidos que o app do PC faz (identificado como programa, não navegador) e
 * devolve a resposta liberada para o app web.
 *
 * O que ele aceita — e nada além disso:
 *   GET /posts.json?...  -> https://danbooru.donmai.us/posts.json?...   (busca)
 *   GET /tags.json?...   -> https://danbooru.donmai.us/tags.json?...    (sugestões)
 *   GET /cdn/<caminho>   -> https://cdn.donmai.us/<caminho>             (imagens)
 * Só atende páginas de ALLOWED_ORIGINS; não repassa cookies, tokens nem
 * cabeçalhos do celular; guarda as imagens em cache na borda do Cloudflare.
 *
 * Publicar: Cloudflare › Workers & Pages › Create › Worker › Edit code ›
 * colar este arquivo inteiro › Deploy (instruções em docs/planos/PLANO_MOBILE.md).
 */

const API = "https://danbooru.donmai.us";
const CDN = "https://cdn.donmai.us";
const USER_AGENT = "CustomMakerv2/1.0 (by xGanne on GitHub; mobile)";
const ALLOWED_ORIGINS = [
  "https://xganne.github.io",
  "http://localhost:4173", // vite preview (testes)
  "http://localhost:5173", // vite dev
];
const API_PATHS = new Set(["/posts.json", "/tags.json"]);

/** Origem permitida que fez o pedido (Origin, ou Referer nas <img>), ou null. */
function allowedOrigin(request) {
  const origin = request.headers.get("Origin");
  if (origin) return ALLOWED_ORIGINS.includes(origin) ? origin : null;
  const referer = request.headers.get("Referer") || "";
  return ALLOWED_ORIGINS.find((allowed) => referer === allowed || referer.startsWith(`${allowed}/`)) || null;
}

function corsHeaders(origin) {
  return { "Access-Control-Allow-Origin": origin, Vary: "Origin" };
}

/** Resposta nova só com os cabeçalhos que interessam (sem cookies do Danbooru). */
function relay(upstream, origin) {
  const headers = new Headers(corsHeaders(origin));
  for (const name of ["Content-Type", "Cache-Control", "Content-Length", "ETag", "Last-Modified"]) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers });
}

export default {
  async fetch(request, _env, ctx) {
    const url = new URL(request.url);
    const origin = allowedOrigin(request);
    if (!origin) return new Response("Origem não permitida.", { status: 403 });
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: { ...corsHeaders(origin), "Access-Control-Allow-Methods": "GET", "Access-Control-Max-Age": "86400" },
      });
    }
    if (request.method !== "GET") {
      return new Response("Só GET.", { status: 405, headers: corsHeaders(origin) });
    }

    let target;
    if (API_PATHS.has(url.pathname)) target = `${API}${url.pathname}${url.search}`;
    else if (url.pathname.startsWith("/cdn/")) target = `${CDN}${url.pathname.slice(4)}`;
    else return new Response("Caminho não permitido.", { status: 404, headers: corsHeaders(origin) });

    const isImage = target.startsWith(CDN);
    // cache das imagens na borda (caches.default só existe no Cloudflare)
    const cache = isImage && typeof caches !== "undefined" ? caches.default : null;
    const cacheKey = new Request(target);
    if (cache) {
      const hit = await cache.match(cacheKey);
      if (hit) return relay(hit, origin);
    }

    const upstream = await fetch(target, {
      headers: { "User-Agent": USER_AGENT, Accept: isImage ? "image/*" : "application/json" },
    });
    if (cache && upstream.ok) {
      const response = relay(upstream, origin);
      ctx.waitUntil(cache.put(cacheKey, response.clone()));
      return response;
    }
    return relay(upstream, origin);
  },
};
