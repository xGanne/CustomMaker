import { defineConfig } from "vitest/config";

export default defineConfig({
  // caminhos relativos: o mesmo build serve no GitHub Pages (/CustomMaker/) e
  // dentro do app Android (Capacitor serve na raiz)
  base: "./",
  build: { outDir: "dist", target: "es2022" },
  test: { environment: "node", include: ["tests/**/*.test.ts"] },
});
