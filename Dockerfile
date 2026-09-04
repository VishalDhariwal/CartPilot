# ==========================================
# Stage 1: Build the Unified Frontend
# ==========================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/cartpilot-merchant

COPY cartpilot-merchant/package*.json ./
RUN npm install

COPY cartpilot-merchant/ ./
RUN npm run build

# ==========================================
# Stage 2: Python Backend & Final Runtime
# ==========================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HF_HOME=/app/cache/huggingface

WORKDIR /app

# Install system dependencies and binutils for stripping debug symbols
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    binutils \
    && rm -rf /var/lib/apt/lists/*

# Install lightweight CPU-only PyTorch and Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt && \
    # Pre-warm SentenceTransformer embedding model weights so runtime doesn't re-download 120MB
    python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" && \
    # Strip debug symbols from all shared libraries (.so)
    find /usr/local/lib/python3.11/site-packages -name "*.so*" -exec strip --strip-unneeded {} + 2>/dev/null || true && \
    # Remove test suites, type stubs, C source files, and cache directories
    find /usr/local/lib/python3.11/site-packages -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.11/site-packages -type d -name "test" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.11/site-packages -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.11/site-packages \( -name "*.pyc" -o -name "*.pyi" -o -name "*.c" -o -name "*.h" \) -delete && \
    # Remove build tools and clean up apt
    apt-get purge -y binutils && apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* /tmp/* /root/.cache

# Copy Backend Code, operations & migration scripts, seed catalog data, and documentation
COPY backend/ ./backend/
COPY ops/ ./ops/
COPY seed_catalog.json .
COPY docs/ ./docs/

# Copy built frontend assets from Stage 1 into /app/cartpilot-merchant/dist
COPY --from=frontend-builder /app/cartpilot-merchant/dist ./cartpilot-merchant/dist

# Expose backend/frontend unified port
EXPOSE 8000

# Health check (verifies database connection and catalog engine readiness)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/catalog/ingest/status || exit 1

# Start the unified CartPilot server
CMD ["python3", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
