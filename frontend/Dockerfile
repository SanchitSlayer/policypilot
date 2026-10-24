# syntax=docker/dockerfile:1
# Targets:
#   dev  - Next.js dev server used by docker-compose (code is bind-mounted)
#   prod - default: Next.js standalone server, non-root, no node_modules or sources

ARG NODE_VERSION=20

# ---------------------------------------------------------------- deps
FROM node:${NODE_VERSION}-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---------------------------------------------------------------- dev
FROM deps AS dev
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]

# ---------------------------------------------------------------- build
FROM deps AS build
# NEXT_PUBLIC_* values are inlined into the browser bundle at build time, so the API URL
# must be known when the image is built (see docs/DEPLOY.md).
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_MAX_UPLOAD_MB=20
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_PUBLIC_MAX_UPLOAD_MB=${NEXT_PUBLIC_MAX_UPLOAD_MB} \
    NEXT_TELEMETRY_DISABLED=1
RUN test -n "$NEXT_PUBLIC_API_URL" || (echo "Build arg NEXT_PUBLIC_API_URL is required" && exit 1)
COPY . .
RUN npm run build

# ---------------------------------------------------------------- prod
FROM node:${NODE_VERSION}-alpine AS prod
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=8080 HOSTNAME=0.0.0.0
WORKDIR /app
RUN addgroup -S nextjs && adduser -S nextjs -G nextjs
COPY --from=build --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nextjs /app/.next/static ./.next/static
COPY --from=build --chown=nextjs:nextjs /app/public ./public
USER nextjs
EXPOSE 8080
CMD ["node", "server.js"]
