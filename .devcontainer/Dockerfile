FROM mcr.microsoft.com/devcontainers/python:1-3.11-bullseye

# Install system dependencies required for PDF parsing and OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
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