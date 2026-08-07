FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer-cached until requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source + Alembic migration environment
COPY app/ app/
COPY alembic.ini .
COPY alembic/ alembic/
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

# Non-root user for runtime security
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
