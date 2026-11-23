/**
 * De onde sai o acesso ao Danbooru.
 *
 * O Cloudflare do Danbooru barra pedidos feitos por navegador (com ou sem login)
 * e pedidos vindos de servidores (um repassador no Cloudflare Workers foi
 * barrado também). Só o app Android consegue: lá, cada pedido ao Danbooru é
 * refeito pelo próprio app (android/.../DanbooruWebViewClient.java).
 */

const DANBOORU = "https://danbooru.donmai.us";

/** Rodando dentro do app Android (Capacitor)? */
export function isNativeApp(): boolean {
  const capacitor = (globalThis as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor;
  return Boolean(capacitor?.isNativePlatform?.());
}

/** Endereço da API do Danbooru, ou "" se este ambiente não consegue acessá-la. */
export function danbooruBase(): string {
  return isNativeApp() ? DANBOORU : "";
}
