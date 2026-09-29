# ── Build stage ──────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --production=false

COPY public/ public/
COPY src/ src/

ARG REACT_APP_API_BASE_URL=http://localhost:8000
ENV REACT_APP_API_BASE_URL=$REACT_APP_API_BASE_URL

RUN npm run build

# ── Serve stage ───────────────────────────────────────────────────────────────
# nginxinc/nginx-unprivileged already runs as the non-root "nginx" user and
# listens on 8080 by default -- no need to hand-roll a USER/port switch.
FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY --from=builder /app/build /usr/share/nginx/html

RUN printf 'server {\n  listen 8080;\n  root /usr/share/nginx/html;\n  index index.html;\n  gzip on;\n  gzip_types text/plain text/css application/javascript application/json image/svg+xml;\n  add_header X-Content-Type-Options nosniff always;\n  add_header X-Frame-Options DENY always;\n  add_header Referrer-Policy strict-origin-when-cross-origin always;\n  location /static/ {\n    add_header Cache-Control "public, max-age=31536000, immutable";\n  }\n  location / {\n    try_files $uri $uri/ /index.html;\n    add_header Cache-Control "no-cache";\n  }\n}\n' \
    > /etc/nginx/conf.d/default.conf

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://localhost:8080/ || exit 1
