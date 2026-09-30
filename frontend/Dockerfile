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
# nginx-unprivileged runs as a non-root user and listens on 8080.
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1
