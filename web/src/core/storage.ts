/** Guarda valores pequenos no navegador do aparelho; nunca falha (aba anônima, sem espaço). */
export const store = {
  get<T>(key: string, fallback: T): T {
    try {
      const raw = globalThis.localStorage?.getItem(`custommaker:${key}`);
      return raw === null || raw === undefined ? fallback : (JSON.parse(raw) as T);
    } catch {
      return fallback;
    }
  },
  set(key: string, value: unknown): void {
    try {
      globalThis.localStorage?.setItem(`custommaker:${key}`, JSON.stringify(value));
    } catch {
      /* sem armazenamento: segue sem lembrar */
    }
  },
};
