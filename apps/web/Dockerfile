# Built from apps/web/ (see docker-compose.yml `context: ./apps/web`) — the
# frontend has no dependency on anything outside this directory.

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# next.config.mjs's rewrites() resolves BACKEND_ORIGIN into routes-manifest.json
# at `next build` time — setting it only at container-run time (e.g. compose's
# `environment:`) has no effect on the standalone server's routing. Must be a
# build arg. Safe to bake in: "backend:8000" is docker-compose's internal DNS
# name for the backend service, true for every environment this image runs in.
ARG BACKEND_ORIGIN=http://backend:8000
ENV BACKEND_ORIGIN=${BACKEND_ORIGIN}
RUN npm run build

# Standalone output (next.config.mjs `output: "standalone"`) copies only the
# node_modules actually used at runtime — a fraction of the full `npm ci` tree.
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
# server.js binds to process.env.HOSTNAME, and Docker auto-sets HOSTNAME to
# the container ID — without this override the app only listens on its own
# container IP, not on localhost, which fails both the healthcheck below and
# `docker compose exec web wget localhost:3000` (container-to-container
# traffic via the "web" service name still resolves straight to that IP, so
# it works either way — only same-container-via-localhost breaks).
ENV HOSTNAME=0.0.0.0
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget -qO- http://127.0.0.1:3000/ || exit 1

CMD ["node", "server.js"]
