/**
 * Endereço do repassador do Danbooru (web/proxy/danbooru-worker.js).
 *
 * O Cloudflare do Danbooru barra pedidos feitos por navegador, com ou sem
 * login: busca, sugestões e imagens passam pelo repassador.
 */
import { store } from "./storage";

/** Preenchido depois de publicar o Worker (o endereço depende da conta do Cloudflare). */
export const DEFAULT_PROXY = "";

/** Endereço em uso: o configurado no aparelho, senão o padrão. Sem barra no fim. */
export function proxyBase(): string {
  return (store.get<string>("proxy", "") || DEFAULT_PROXY).replace(/\/+$/, "");
}

/** URL da CDN do Danbooru passando pelo repassador; outras URLs ficam como estão. */
export function viaProxy(url: string | undefined | null): string {
  if (!url) return "";
  try {
    const parsed = new URL(url);
    if (parsed.hostname === "cdn.donmai.us" && proxyBase()) return `${proxyBase()}/cdn${parsed.pathname}`;
  } catch {
    /* URL relativa ou inválida: devolve como veio */
  }
  return url;
}
