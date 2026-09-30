FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first: this layer is cached until requirements change.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the embedding model into the image: containers never download models at
# runtime, and the model version is pinned to the image tag (reproducible).
ARG EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ENV EMBEDDING_MODEL=${EMBEDDING_MODEL} \
    MODEL_CACHE_DIR=/app/models \
    HF_HUB_OFFLINE=1
RUN HF_HUB_OFFLINE=0 python -c "import os; from fastembed import TextEmbedding; \
TextEmbedding(model_name=os.environ['EMBEDDING_MODEL'], cache_dir=os.environ['MODEL_CACHE_DIR'])" \
    && chmod -R a+rX /app/models

COPY app/ app/
COPY alembic.ini .
COPY alembic/ alembic/
COPY docker-entrypoint.sh .
# Normalize line endings defensively (see .gitattributes) and make executable.
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

# Non-root runtime user; it can write only /app/var (attachments volume).
# Code and model files stay root-owned and read-only (a chown -R /app would
# also duplicate the ~90 MB model into another layer).
RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /app/var/attachments \
    && chown -R appuser /app/var
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
# API_LIMIT_CONCURRENCY (optional): per-process cap on in-flight requests; beyond it uvicorn
# answers 503 at once instead of queueing requests that hold database connections (P11).
ENV API_LIMIT_CONCURRENCY=""
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS} --proxy-headers --forwarded-allow-ips '*' ${API_LIMIT_CONCURRENCY:+--limit-concurrency $API_LIMIT_CONCURRENCY}"]
