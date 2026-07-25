# Use Bookworm (Debian 12) to avoid expired key errors in older Bullseye images
FROM mcr.microsoft.com/devcontainers/python:1-3.11-bookworm

# Clean up broken third-party APT sources if present, then install required dependencies
RUN rm -f /etc/apt/sources.list.d/yarn.list /etc/apt/sources.list.d/node.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    poppler-utils \
    tesseract-ocr \
    libmagic1 \
    git \
    curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install uv for fast, deterministic Python package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /workspace