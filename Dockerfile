# Multi-stage build — lean runtime image for the RRR CLI.
#
# Stage 1 (builder): installs all Python deps into /app/venv
# Stage 2 (runtime): copies only the venv + source; runs as non-root (NFR-8)
#
# Build:   docker build -t rrr:latest .
# Run:     docker run --rm -v ./brain:/data/brain -v ./data:/data/local rrr:latest \
#            rrr --release "my-release" --config /app/configs/demo.yaml
#
# Optional Ollama sidecar: see docker-compose.yml

ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /build

# Install build tools needed for native extension deps (e.g. chromadb/onnx optional)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/

# Create isolated venv and install the package (core deps only; extras are opt-in)
RUN python -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /app/venv/bin/pip install --no-cache-dir ".[dev]"

# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

# Non-root user for least-privilege execution (NFR-8)
RUN groupadd -r rrr && useradd -r -g rrr -d /app -s /bin/false rrr

WORKDIR /app

# Copy installed venv and source from builder stage
COPY --from=builder /app/venv /app/venv
COPY --from=builder /build/src /app/src
COPY configs/ /app/configs/

# Persistent data volumes — SQLite DB, Chroma vectors, brain extracts
VOLUME ["/data/brain", "/data/local"]

# Make venv the active Python environment
ENV PATH="/app/venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER rrr

ENTRYPOINT ["rrr"]
CMD ["--help"]
