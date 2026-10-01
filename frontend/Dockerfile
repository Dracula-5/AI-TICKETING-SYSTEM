# ── Build ────────────────────────────────────────────────────────────────────
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY index.html vite.config.ts tsconfig*.json ./
COPY public/ public/
COPY src/ src/
# Set only for the public demo build (shows "Explore the demo" buttons).
ARG VITE_DEMO_PASSWORD=""
ENV VITE_DEMO_PASSWORD=$VITE_DEMO_PASSWORD
RUN npx vite build

# ── Serve ────────────────────────────────────────────────────────────────────
# nginx-unprivileged runs as a non-root user (listening on PORT, 8080 by default).
FROM nginxinc/nginx-unprivileged:1.27-alpine
# Rendered to /etc/nginx/conf.d/default.conf at start-up (envsubst of the
# variables below). API_UPSTREAM: where /api is proxied — the compose service by
# default, e.g. https://nexadesk-api.onrender.com on Render. PORT: hosting
# platforms such as Render may set their own.
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --chmod=755 nginx/10-api-upstream.envsh /docker-entrypoint.d/10-api-upstream.envsh
ENV API_UPSTREAM=http://backend:8000 \
    PORT=8080 \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
COPY security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- "http://127.0.0.1:${PORT}/" >/dev/null || exit 1
