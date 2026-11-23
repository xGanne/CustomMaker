/**
 * Posts do Danbooru já usados neste aparelho (customs enviadas ao ImgChest ou
 * compartilhadas). O ★ Auto pula esses, como o PC pula os já importados — sem
 * isso ele escolheria sempre as mesmas imagens da mesma busca.
 */
import { store } from "./storage";

const KEY = "usedPosts";
// os mais recentes ficam; ~6 bytes por id no armazenamento do aparelho
const LIMIT = 5000;

export function usedPosts(): Set<number> {
  const ids = store.get<unknown>(KEY, []);
  return new Set(Array.isArray(ids) ? ids.filter((id): id is number => Number.isInteger(id)) : []);
}

export function markUsed(ids: Iterable<number>): void {
  const fresh = [...new Set(ids)];
  if (!fresh.length) return;
  const known = [...usedPosts()].filter((id) => !fresh.includes(id));
  store.set(KEY, [...known, ...fresh].slice(-LIMIT));
}
