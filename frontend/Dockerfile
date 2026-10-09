# syntax=docker/dockerfile:1
# Build from the repository root: docker build -f frontend/Dockerfile .
FROM node:24-slim AS builder

# Match the pnpm version used in .github/workflows/ci.yml.
RUN npm install --global pnpm@12.9.1
WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN --mount=type=cache,id=bioverdict-pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile --store-dir /pnpm/store

COPY frontend/ ./
# The demo client imports this shared fixture outside frontend/.
COPY fixtures/bundles /app/fixtures/bundles

# This address is used by the browser, not by the container network.
# Pass an empty value to build the standalone offline snapshot.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}
RUN pnpm build

# Only static assets are needed at runtime; Node stays in the build stage.
FROM nginxinc/nginx-unprivileged:stable-alpine AS runtime
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/frontend/dist /usr/share/nginx/html

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --quiet --spider http://127.0.0.1:8080/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
