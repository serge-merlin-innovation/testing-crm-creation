import type { NextConfig } from "next";
import { resolve } from "node:path";

const nextConfig: NextConfig = {
  reactCompiler: true,
  // Emits a self-contained server plus only the traced node_modules, so the published image
  // carries the app instead of the whole pnpm workspace. Traced from `turbopack.root`, so the
  // bundle nests under apps/frontend/ — see the runner stage of apps/frontend/Dockerfile.
  output: "standalone",
  // FastAPI routes collections with a trailing slash (`/api/v1/roles/`). Without this, Next would
  // answer 308 to the slashless form before the relay ever runs, and FastAPI would 307 it back.
  // Pages are unaffected: the page gate normalises trailing slashes itself.
  skipTrailingSlashRedirect: true,
  turbopack: {
    root: resolve(__dirname, "../.."),
  },
};

export default nextConfig;
