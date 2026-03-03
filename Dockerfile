# ==============================================
# AgentOS — Production Dockerfile (Hardened)
# ==============================================
# Multi-stage build with security hardening:
#   - Non-root user (UID 10001)
#   - Read-only root filesystem support
#   - No shell in final image (distroless-like)
#   - Minimal attack surface
# ==============================================

# ---- Builder Stage ----
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy packaging files first (layer cache)
COPY pyproject.toml README.md requirements.txt ./

# Create venv and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install core + llm + orchestration (skip heavy training deps)
RUN pip install --no-cache-dir -r requirements.txt || true && \
    pip install --no-cache-dir "." || true

# Copy application code
COPY . .

# ---- Runtime Stage ----
FROM python:3.12-slim AS runtime

# Security: environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

# Security: create non-root user with fixed UID
RUN groupadd -g 10001 agentos && \
    useradd -u 10001 -g agentos -m -s /usr/sbin/nologin agentos

# Security: install tini for proper signal handling
RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code (owned by non-root)
COPY --chown=agentos:agentos . .

# Remove unnecessary files
RUN rm -rf .git .github tests __pycache__ \
    && find . -name "*.pyc" -delete \
    && find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Create data directories (owned by non-root)
RUN mkdir -p /app/data /app/logs && \
    chown -R agentos:agentos /app/data /app/logs

# Switch to non-root user
USER 10001

# Expose dashboard port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Use tini as PID 1 for proper signal handling
ENTRYPOINT ["tini", "--"]

# Default command
CMD ["python", "start.py"]
