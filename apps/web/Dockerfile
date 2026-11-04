# LEADFORGE web app (Next.js standalone server). Build from the repository root:
#   docker build -f apps/web/Dockerfile -t leadforge-web .
# Configuration (SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, API_BASE_URL) is read at
# runtime, so the same image works in every environment.

FROM node:22-alpine AS deps
WORKDIR /repo
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/shared/package.json packages/shared/package.json
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /repo
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /repo ./
COPY apps/web apps/web
COPY packages/shared packages/shared
RUN npm run build -w @leadforge/web

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN adduser -D -u 10001 leadforge
COPY --from=build --chown=leadforge /repo/apps/web/.next/standalone ./
COPY --from=build --chown=leadforge /repo/apps/web/.next/static ./apps/web/.next/static
USER leadforge
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
