# Frontend image. Build context is the REPO ROOT, because the app is a pnpm workspace member
# and the lockfile it must install from lives there:
#   docker build -f apps/frontend/Dockerfile -t merlin-frontend .
#
# No build args: every setting this app reads (BACKEND_URL, BFF_TRUSTED_PROXY_HOPS,
# BACKEND_TIMEOUT_MS) is read at runtime inside a lib/ accessor, so one image serves every
# environment.
FROM node:22-slim AS base
ENV PNPM_HOME=/pnpm
ENV PATH="$PNPM_HOME:$PATH"
ENV NEXT_TELEMETRY_DISABLED=1
# Pins the pnpm version from the root package.json `packageManager` field.
RUN corepack enable
WORKDIR /repo

# ===================== Dependencies =====================
# Manifests only, so this layer is rebuilt when dependencies change and not on every edit.
# apps/backend/package.json is a workspace member pnpm must see for --frozen-lockfile to
# validate; nothing from it reaches the image.
FROM base AS deps

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/frontend/package.json apps/frontend/
COPY apps/backend/package.json apps/backend/

RUN --mount=type=cache,target=/pnpm/store \
    pnpm install --frozen-lockfile --filter @merlin/frontend...

# ===================== Build =====================
# Inherits the installed node_modules trees rather than listing them by hand — pnpm's
# workspace layout is its business, not this Dockerfile's.
FROM deps AS build

COPY apps/frontend apps/frontend

RUN pnpm --filter @merlin/frontend run build

# Git does not track empty directories, so a public/ with no committed files (a legitimate
# state) is simply absent after a fresh checkout. Guarantee it exists before the prod stage
# copies it below, instead of depending on public/ always having tracked content.
RUN mkdir -p apps/frontend/public

# ===================== Runtime =====================
FROM base AS prod

ENV NODE_ENV=production

# `output: "standalone"` traces from the workspace root, so the bundle mirrors the repo layout:
# server.js sits under apps/frontend/ and the traced node_modules at the bundle root.
COPY --from=build /repo/apps/frontend/.next/standalone ./
# Static assets and public/ are deliberately excluded from the standalone trace.
COPY --from=build /repo/apps/frontend/.next/static ./apps/frontend/.next/static
COPY --from=build /repo/apps/frontend/public ./apps/frontend/public

# node:22-slim ships an unprivileged `node` user; the app never writes to its own filesystem.
USER node

ENV PORT=3000
ENV HOSTNAME=0.0.0.0
EXPOSE 3000

CMD ["node", "apps/frontend/server.js"]
