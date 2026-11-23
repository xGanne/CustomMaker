import { defineConfig } from "vitest/config";

export default defineConfig({
  // publicado em https://xganne.github.io/CustomMaker/
  base: "/CustomMaker/",
  build: { outDir: "dist", target: "es2022" },
  test: { environment: "node", include: ["tests/**/*.test.ts"] },
});
