/**
 * ★ Auto: "isso daria um bom custom?", igual a src/core/custom_scorer.py.
 *
 * Pesos e limites vêm do rules.json (gerado do Python); aqui só as fórmulas,
 * conferidas contra o PC em tests/fixtures/scorer.json. Sem detector de rosto
 * nesta versão: a parte visual é só a checagem de cor (como o PC sem o cascade).
 */
import { resizeLanczos } from "./resample";
import type { Raster } from "./raster";
import { rules } from "./rules";
import { isImagePost, type Post } from "./danbooru";

const S = rules.scorer;
const TARGET_RATIO = rules.border.width / rules.border.height;

/** "a b  c" -> {"a", "b", "c"} (minúsculas). */
export function parseAvoidTags(text: string | null | undefined): Set<string> {
  return new Set((text ?? "").split(/\s+/).filter(Boolean).map((t) => t.toLowerCase()));
}

export const DEFAULT_AVOID = parseAvoidTags(S.defaultAvoidTags);

/** Só Geral e Sensível — questionável, explícito e sem classificação nunca entram no Auto. */
export function isAutoEligible(post: Post): boolean {
  return S.autoRatings.includes(String(post.rating ?? "").toLowerCase());
}

function aspectRatioScore(width?: number | null, height?: number | null): number {
  if (!width || !height) return 0;
  return Math.max(0, 2.0 - Math.abs(width / height - TARGET_RATIO) * 3.0);
}

function resolutionScore(width?: number | null, height?: number | null): number {
  if (!width || !height) return 0;
  const { width: W, height: H } = rules.border;
  if (width < W || height < H) return -2.0; // teria que ampliar
  if (width < W * 2 || height < H * 2) return -0.5; // pouca margem para enquadrar
  return 0;
}

function characterScore(post: Post): number {
  if (!("tag_string_character" in post)) return 0; // sem o campo: neutro
  const characters = String(post.tag_string_character ?? "").split(/\s+/).filter(Boolean);
  return characters.length === 1 ? 1.0 : -1.0;
}

function popularityScore(post: Post): number {
  const favs = Number(post.fav_count) || 0;
  const score = Number(post.score) || 0;
  return Math.log1p(Math.max(0, favs)) * 0.3 + Math.log1p(Math.max(0, score)) * 0.2;
}

/** Pontuação só com os campos da busca (sem baixar nada). Maior é melhor. */
export function metadataScore(post: Post, avoidTags: Set<string> = DEFAULT_AVOID): number {
  const tags = new Set(String(post.tag_string ?? "").split(/\s+/).filter(Boolean));
  let score = 0;
  // mesma ordem de soma do Python (resultado igual até a última casa)
  for (const [table, sign] of [[S.tagBoosts, 1], [S.tagPenalties, -1], [S.qualityBoosts, 1], [S.qualityPenalties, -1]] as const) {
    for (const [tag, weight] of Object.entries(table)) if (tags.has(tag)) score += sign * weight;
  }
  let avoided = 0;
  for (const tag of tags) if (avoidTags.has(tag)) avoided++;
  score -= S.avoidTagPenalty * avoided;
  if (String(post.rating ?? "").toLowerCase() === "s") score -= S.sensitiveRatingPenalty;
  score += aspectRatioScore(post.image_width, post.image_height);
  score += resolutionScore(post.image_width, post.image_height);
  score += characterScore(post);
  score += popularityScore(post);
  return score;
}

/** Fração (0-1) dos pixels com cor visível — mangá/P&B fica perto de 0. */
export function colorfulFraction(image: Raster): number {
  // o PC reduz para caber em 160x160 antes de contar
  const scale = Math.min(1, 160 / image.width, 160 / image.height);
  const small = scale < 1
    ? resizeLanczos(image, Math.max(1, Math.round(image.width * scale)), Math.max(1, Math.round(image.height * scale)))
    : image;
  let colorful = 0;
  const d = small.data;
  for (let i = 0; i < d.length; i += 4) {
    // conversão RGB->HSV do Pillow: S = int((max-min)/max*255), V = max
    const max = Math.max(d[i], d[i + 1], d[i + 2]);
    const min = Math.min(d[i], d[i + 1], d[i + 2]);
    const s = max === min ? 0 : Math.trunc(((max - min) / max) * 255);
    if (s > 50 && max > 40) colorful++;
  }
  return colorful / Math.max(1, small.width * small.height);
}

/** Parte visual: -penalidade se a prévia é praticamente P&B, senão 0. */
export function visualScore(preview: Raster | null): number {
  if (!preview) return 0;
  return colorfulFraction(preview) < S.minColorFraction ? -S.grayscalePenalty : 0;
}

export interface AutoSelectOptions {
  count: number;
  firstPage: number;
  firstPosts: Post[];
  pageSize: number;
  /** busca outra página (null: só a atual) */
  fetchPage: ((page: number) => Promise<Post[]>) | null;
  /** prévia decodificada do post (para a checagem de cor), ou null */
  loadPreview: (post: Post) => Promise<Raster | null>;
  alreadySelected: Set<number>;
  avoidTags?: Set<string>;
  maxPages?: number;
  signal?: AbortSignal;
  onProgress?: (message: string) => void;
}

export interface AutoSelectResult {
  posts: Post[];
  pages: number;
  lastPage: number;
  excluded: number; // questionável/explícito
}

/**
 * O ★ Auto do PC: pontua a página atual e, sem candidatos bons suficientes,
 * segue para as próximas (até maxPages). Nunca escolhe questionável/explícito,
 * nem o que já está marcado, nem candidatos abaixo da nota mínima.
 */
export async function autoSelect(options: AutoSelectOptions): Promise<AutoSelectResult> {
  const avoid = options.avoidTags ?? DEFAULT_AVOID;
  const maxPages = options.fetchPage ? options.maxPages ?? rules.danbooru.autoSelectMaxPages : 1;
  const lastAllowed = options.firstPage + maxPages - 1;
  const good: [number, Post][] = [];
  const seen = new Set<number>();
  let excluded = 0;
  let pages = 0;
  let page = options.firstPage;
  let posts = options.firstPosts;
  for (;;) {
    pages++;
    const images = posts.filter((p) => isImagePost(p) && !seen.has(p.id));
    images.forEach((p) => seen.add(p.id));
    const eligible = images.filter(isAutoEligible);
    excluded += images.length - eligible.length;
    const fresh = eligible.filter((p) => !options.alreadySelected.has(p.id));
    const missing = options.count - good.length;
    // a parte visual (que baixa a prévia) só para os mais promissores
    const ranked = fresh
      .map((post) => [metadataScore(post, avoid), post] as [number, Post])
      .sort((a, b) => b[0] - a[0])
      .slice(0, Math.max(missing * 2, missing + 5));
    for (const [index, [base, post]] of ranked.entries()) {
      if (options.signal?.aborted) throw new DOMException("cancelado", "AbortError");
      options.onProgress?.(`Página ${page}: avaliando ${index + 1}/${ranked.length}...`);
      const total = base + visualScore(await options.loadPreview(post));
      if (total >= S.minAutoScore) good.push([total, post]);
    }
    if (good.length >= options.count || page >= lastAllowed || posts.length < options.pageSize || !options.fetchPage) break;
    page++;
    options.onProgress?.(`Poucos bons até aqui (${good.length}/${options.count}): buscando a página ${page}...`);
    try {
      posts = await options.fetchPage(page);
    } catch (error) {
      if ((error as Error).name === "AbortError") throw error;
      break; // sem a próxima página: fica com o que achou
    }
    if (!posts.length) break;
  }
  good.sort((a, b) => b[0] - a[0]);
  return { posts: good.slice(0, options.count).map(([, post]) => post), pages, lastPage: page, excluded };
}
