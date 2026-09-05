import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Unit tests only, for plain TS logic under src/lib and src/hooks - no DOM,
// no React rendering. Mirrors the "@/*" alias from tsconfig.json so test
// files can import the same way application code does.
const dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(dirname, "./src"),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
