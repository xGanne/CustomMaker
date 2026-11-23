/**
 * Busca no Danbooru, pelo repassador (core/proxy.ts): o Cloudflare do Danbooru
 * barra pedidos feitos por navegador. Mesmas regras de src/core/danbooru.py;
 * filtros e campos vêm do rules.json.
 */
import { proxyBase, viaProxy } from "./proxy";
import { rules } from "./rules";

function api(): string {
  const base = proxyBase();
  if (!base) {
    throw new DanbooruError(
      "O repassador do Danbooru ainda não está configurado (o Danbooru barra buscas feitas direto do navegador).",
    );
  }
  return base;
}

export interface Post {
  id: number;
  rating?: string;
  score?: number;
  fav_count?: number;
  image_width?: number | null;
  image_height?: number | null;
  file_ext?: string;
  tag_string?: string;
  tag_string_character?: string;
  file_url?: string;
  large_file_url?: string;
  preview_file_url?: string;
  [field: string]: unknown;
}

export interface SearchOptions {
  query: string;
  rating: string; // rótulo de rules.danbooru.ratingTags
  sort: string; // rótulo de rules.danbooru.sortTags
  portraitOnly: boolean;
}

/** Imagem (vira custom)? Vídeos, ugoira e flash não. */
export function isImagePost(post: Post): boolean {
  const ext = String(post.file_ext ?? "").toLowerCase();
  return !ext || rules.danbooru.imageExtensions.includes(ext);
}

/** "gore  -blood" -> ["gore", "blood"]: minúsculas, sem "-" e sem repetir. */
export function parseTagList(text: string): string[] {
  const tags: string[] = [];
  for (const raw of (text || "").split(/\s+/)) {
    const tag = raw.trim().replace(/^-+/, "").toLowerCase();
    if (tag && !tags.includes(tag)) tags.push(tag);
  }
  return tags;
}

/** Tira posts com alguma tag da blacklist (fora da busca: sem login são só 2 tags). */
export function filterBlacklisted(posts: Post[], blacklist: string[]): Post[] {
  if (!blacklist.length) return [...posts];
  const excluded = new Set(blacklist);
  return posts.filter((post) => !(post.tag_string ?? "").toLowerCase().split(/\s+/).some((t) => excluded.has(t)));
}

/** Tags da busca: texto + classificação + ordenação + proporção retrato. */
export function buildTags(options: SearchOptions): string {
  const parts = [
    options.query.trim(),
    rules.danbooru.ratingTags[options.rating] ?? "",
    rules.danbooru.sortTags[options.sort] ?? "",
    options.portraitOnly ? rules.danbooru.portraitRatioTag : "",
  ];
  return parts.filter(Boolean).join(" ").trim();
}

/**
 * URL a baixar para fazer a custom (import_source do PC): a versão "large"
 * (850 px de largura, dezenas de vezes menor) quando cobre o dobro da custom;
 * senão o original.
 */
export function importSource(post: Post, minSize = rules.danbooru.importMinSize): string | null {
  if (!isImagePost(post)) return null;
  const fileUrl = post.file_url;
  const largeUrl = post.large_file_url;
  const width = post.image_width || 0;
  const height = post.image_height || 0;
  let chosen: string | undefined;
  if (largeUrl && largeUrl !== fileUrl && width && height) {
    const sample = rules.danbooru.sampleWidth;
    const [largeW, largeH] = width > sample ? [sample, (height * sample) / width] : [width, height];
    if (largeW >= minSize[0] && largeH >= minSize[1]) chosen = largeUrl;
  }
  return viaProxy(chosen || fileUrl || largeUrl) || null;
}

/** Erro da busca já com a mensagem para o usuário. */
export class DanbooruError extends Error {}

function tagLimitMessage(payload: unknown): string | null {
  const data = payload as { error?: string; message?: string } | null;
  if (!data || data.error !== "PostQuery::TagLimitError") return null;
  return (
    `A busca passou do limite de tags (${data.message ?? "limite de tags"}). ` +
    "A ordenação (Melhor avaliados / Mais favoritos) conta como uma tag; a classificação " +
    "não conta. Sem login o limite é de 2 tags: remova uma ou use \"Mais recentes\"."
  );
}

/** Uma página de resultados. */
export async function searchPosts(tags: string, page: number, limit: number, signal?: AbortSignal): Promise<Post[]> {
  const params = new URLSearchParams({
    tags,
    limit: String(limit),
    page: String(Math.max(1, Math.min(rules.danbooru.maxPage, page))),
    only: rules.danbooru.postFields,
  });
  const base = api();
  let response: Response;
  try {
    response = await fetch(`${base}/posts.json?${params}`, { signal });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new DanbooruError("Sem conexão com o Danbooru. Verifique a internet e tente de novo.");
  }
  if (response.ok) return (await response.json()) as Post[];
  const payload = await response.json().catch(() => null);
  if (response.status === 422) {
    throw new DanbooruError(tagLimitMessage(payload) ?? "O Danbooru não entendeu a busca (422).");
  }
  if (response.status === 429) throw new DanbooruError("Muitas buscas seguidas: aguarde alguns segundos.");
  if (response.status === 403) {
    throw new DanbooruError("Acesso negado (403): o conteúdo pode estar restrito para contas sem login.");
  }
  throw new DanbooruError(`Danbooru: erro HTTP ${response.status}.`);
}

export interface TagSuggestion {
  name: string;
  postCount: number;
}

/** Tags que começam com o texto digitado, das mais usadas para as menos. */
export async function suggestTags(query: string, signal?: AbortSignal): Promise<TagSuggestion[]> {
  const term = query.trim().split(/\s+/).pop() ?? "";
  if (term.length < 2) return [];
  const params = new URLSearchParams({
    "search[name_matches]": `${term}*`,
    "search[order]": "count",
    limit: "10",
  });
  try {
    const response = await fetch(`${api()}/tags.json?${params}`, { signal });
    if (!response.ok) return [];
    const data = (await response.json()) as { name?: string; post_count?: number }[];
    return data.filter((t) => t.name).map((t) => ({ name: t.name as string, postCount: t.post_count ?? 0 }));
  } catch {
    return []; // sugestão é opcional: falhar em silêncio
  }
}
