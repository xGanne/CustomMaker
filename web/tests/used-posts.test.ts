import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { markUsed, usedPosts } from "../src/core/used-posts";

// localStorage de mentira (os testes rodam no Node)
const memory = new Map<string, string>();
beforeEach(() => {
  memory.clear();
  (globalThis as { localStorage?: unknown }).localStorage = {
    getItem: (key: string) => memory.get(key) ?? null,
    setItem: (key: string, value: string) => void memory.set(key, value),
  };
});
afterEach(() => {
  delete (globalThis as { localStorage?: unknown }).localStorage;
});

describe("posts já usados", () => {
  it("guarda sem repetir e lembra depois", () => {
    markUsed([10, 20, 10]);
    markUsed([30, 20]);
    expect([...usedPosts()].sort((a, b) => a - b)).toEqual([10, 20, 30]);
    expect(JSON.parse(memory.get("custommaker:usedPosts") ?? "[]")).toEqual([10, 30, 20]);
  });

  it("mantém só os 5000 mais recentes", () => {
    markUsed(Array.from({ length: 5000 }, (_, i) => i));
    markUsed([9001, 9002]);
    const used = usedPosts();
    expect(used.size).toBe(5000);
    expect([used.has(0), used.has(1), used.has(2), used.has(9002)]).toEqual([false, false, true, true]);
  });

  it("ignora lixo no armazenamento", () => {
    memory.set("custommaker:usedPosts", JSON.stringify([1, "x", 2.5, null, 3]));
    expect([...usedPosts()]).toEqual([1, 3]);
    memory.set("custommaker:usedPosts", "{quebrado");
    expect(usedPosts().size).toBe(0);
  });
});
