# Builder Stage
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies if any
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy packaging files
COPY pyproject.toml README.md requirements.txt* ./
COPY . .

# We use uv or pip to install dependencies to a target folder or just install system-wide in builder
# Using a virtual environment makes it easy to copy to the runtime stage
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies
# If requirements.txt exists, we install from it, else from pyproject.toml
RUN if [ -f "requirements.txt" ]; then pip install --no-cache-dir -r requirements.txt; fi && \
    pip install --no-cache-dir ".[all]"


# Runtime Stage
FROM python:3.12-slim AS runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:$PATH"

# Create a non-root user
RUN useradd -m -s /bin/bash agentos

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY --chown=agentos:agentos . .

# Remove unnecessary files from the image (just to be absolutely safe even with .dockerignore)
RUN rm -rf .git tests *.md

# Change to non-root user
USER agentos

# Expose any necessary ports (e.g., if we run a dashboard/web server later)
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Default command
CMD ["python", "start.py"]
