# =============================================================================
# SRE Copilot - Docker Image
# =============================================================================
# Multi-stage build for optimized Python application
#
# Build:
#   docker build -t sre-copilot:latest .
#
# Run:
#   docker run -p 8000:8000 --env-file .env sre-copilot:latest
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder
# -----------------------------------------------------------------------------
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install pip and build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy project files
COPY pyproject.toml ./
COPY src ./src

# Build wheel
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels .

# -----------------------------------------------------------------------------
# Stage 2: Runtime
# -----------------------------------------------------------------------------
FROM python:3.11-slim as runtime

WORKDIR /app

# Create non-root user
RUN groupadd --gid 1000 sre && \
    useradd --uid 1000 --gid sre --shell /bin/bash --create-home sre

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder
COPY --from=builder /app/wheels /wheels

# Install the application
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

# Switch to non-root user
USER sre

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WEBHOOK_HOST=0.0.0.0 \
    WEBHOOK_PORT=8000

# Expose webhook port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the application
ENTRYPOINT ["sre-copilot"]
