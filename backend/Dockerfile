FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first: this layer is cached until requirements change.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ app/
COPY alembic.ini .
COPY alembic/ alembic/
COPY docker-entrypoint.sh .
# Normalize line endings defensively (see .gitattributes) and make executable.
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

# Non-root runtime user; attachments live on a mounted volume.
RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /app/var/attachments \
    && chown -R appuser /app
USER appuser

ENV ATTACHMENT_DIR=/app/var/attachments
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

ENTRYPOINT ["./docker-entrypoint.sh"]
# --proxy-headers: trust X-Forwarded-For from the reverse proxy so rate limits
# and audit logs see the real client address. The API port is reachable only
# on the internal Docker network (the proxy is the sole client), which is what
# makes trusting forwarded headers from any peer acceptable.
ENV API_WORKERS=1
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS} --proxy-headers --forwarded-allow-ips '*'"]
