import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Keep the literal `tests/` prefix: it is the only thing keeping `.next/` (1.5k files) out of
    // the collection crawl, since Vitest 4 excludes only node_modules and .git. Widening this to
    // `**/` costs ~10x. Which tier runs is the `test` script's job, not this glob's — the backend
    // splits the same two concerns across `testpaths` and its pytest arguments.
    include: ["tests/**/*.{test,spec}.{ts,tsx}"],
    // jsdom/happy-dom and Testing Library are absent from package.json, which is what actually
    // makes component rendering untestable here; this pins the default that assumes it.
    environment: "node",
    reporters: ["default", "../../scripts/check-failures/vitest-reporter.mjs"],
  },
  resolve: {
    // Vitest does not read tsconfig `paths`, so `@/` imports need this second declaration of
    // `tsconfig.json`'s `@/*` mapping, which stays the source of truth.
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
});
