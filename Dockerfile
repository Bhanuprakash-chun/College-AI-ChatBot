# ============================================================
# College AI Assistant – Single-server Dockerfile
# Builds the React frontend AND the FastAPI backend into one
# image. The built SPA is served by FastAPI itself (no nginx).
# ============================================================

# ---- Stage 1: Build the React frontend ----
FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# ---- Stage 2: Python backend + frontend static ----
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    HF_HOME=/app/.cache/huggingface \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

WORKDIR /app

# Install Python dependencies (CPU-only PyTorch keeps image small).
COPY backend/requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install -r requirements.txt

# Bake the embedding model so containers start offline-capable.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy backend source.
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini .
COPY backend/pytest.ini .

# Copy the built React SPA into /app/static (main.py looks for it there).
COPY --from=frontend-build /build/dist ./static

# Create non-root user and data directories.
RUN useradd --create-home --uid 10001 appuser \
 && mkdir -p /data/chroma_db /data/documents /app/.cache \
 && chown -R appuser:appuser /app /data
USER appuser

# Default storage paths (overridable via env vars on Render).
ENV CHROMA_PATH=/data/chroma_db \
    DOCUMENTS_DIR=/data/documents \
    SQLITE_PATH=/data/college_ai.db \
    ENVIRONMENT=production

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
  CMD python -c "import os, urllib.request; p = os.environ.get('PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{p}/health', timeout=5)" || exit 1

# Apply DB migrations, then serve with gunicorn + uvicorn workers.
CMD ["sh", "-c", "alembic upgrade head && gunicorn app.main:app --bind 0.0.0.0:${PORT:-8000} --workers 1 --worker-class uvicorn.workers.UvicornWorker --timeout 120 --forwarded-allow-ips='*'"]
