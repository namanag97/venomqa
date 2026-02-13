# VenomQA Docker Image
#
# A lightweight Docker image for running VenomQA tests.
#
# Build:
#   docker build -f docker/Dockerfile -t venomqa:latest .
#
# Usage:
#   docker run --rm \
#     -e VENOMQA_BASE_URL=http://host.docker.internal:8000 \
#     -v $(pwd)/qa:/app/qa:ro \
#     -v $(pwd)/reports:/app/reports \
#     venomqa:latest run
#
# With a specific journey:
#   docker run --rm \
#     -v $(pwd)/qa:/app/qa:ro \
#     -v $(pwd)/reports:/app/reports \
#     venomqa:latest run checkout_journey
#
# Exit codes:
#   0 - All journeys passed
#   1 - Some journeys failed
#   2 - Configuration error

FROM python:3.12-slim AS base

# Metadata
LABEL maintainer="VenomQA Team"
LABEL description="VenomQA - Stateful Journey QA Framework"
LABEL version="1.0.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # VenomQA defaults
    VENOMQA_BASE_URL=http://localhost:8000 \
    VENOMQA_TIMEOUT=30 \
    VENOMQA_REPORT_DIR=/app/reports \
    VENOMQA_LOG_LEVEL=INFO

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # For HTTP health checks
    curl \
    # For waiting on services
    netcat-openbsd \
    # CA certificates for HTTPS
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Create non-root user for security
RUN groupadd -r venomqa && useradd -r -g venomqa venomqa

# Copy and install VenomQA
COPY pyproject.toml ./
COPY venomqa/ ./venomqa/

# Install VenomQA with minimal dependencies
RUN pip install --no-cache-dir -e . && \
    # Verify installation
    venomqa --version

# Create required directories
RUN mkdir -p /app/qa /app/reports /app/logs && \
    chown -R venomqa:venomqa /app

# Switch to non-root user
USER venomqa

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import venomqa; print('healthy')" || exit 1

# Default working directory for QA files
WORKDIR /app/qa

# Set entrypoint to venomqa CLI
ENTRYPOINT ["venomqa"]

# Default command - show help
CMD ["--help"]


# =============================================================================
# Full image with additional tools (for CI/CD and debugging)
# =============================================================================
FROM base AS full

USER root

# Install additional tools for CI/CD environments
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Database clients for debugging
    postgresql-client \
    default-mysql-client \
    redis-tools \
    # JSON processing
    jq \
    # Git for potential operations
    git \
    # Process tools
    procps \
    # For wait-for-it style scripts
    bash \
    && rm -rf /var/lib/apt/lists/*

# Install additional Python packages
RUN pip install --no-cache-dir \
    # For all optional features
    venomqa[all] \
    # Useful extras
    httpx[http2] \
    python-dotenv

# Copy helper scripts
COPY docker/scripts/ /usr/local/bin/
RUN chmod +x /usr/local/bin/*.sh 2>/dev/null || true

USER venomqa

# =============================================================================
# Development image with debugging tools
# =============================================================================
FROM full AS dev

USER root

# Install development tools
RUN pip install --no-cache-dir \
    ipython \
    pytest \
    pytest-cov \
    pytest-asyncio \
    mypy \
    ruff

# Install additional debugging tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    vim-tiny \
    less \
    htop \
    && rm -rf /var/lib/apt/lists/*

USER venomqa

# Override entrypoint for development
ENTRYPOINT []
CMD ["/bin/bash"]
