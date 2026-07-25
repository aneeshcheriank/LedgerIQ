## Docker file

```dockerfile
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
```

- `--no-install-recommends`: instruct not to install optional packages comes with installed packages
    - not requred for the package to function
- packages
    - build-essential: Python packages requiring C/C++ extentions
    - poppler-utils: pdf rendering and extraction
    - tesseract-ocr:
    - libmagic1: identifies file type
    - curl: command line tool for data transfer
- `apt-get clean`: removes the installers
- `rm -rf /var/lib/apt/lists/*`: removes package index list created by `apt-get update`
    - `apt-get update` fetches thousands of metadata records listing every package available in the remote repositories. These index lists take up significant space. Deleting them removes that cached list metadata from the current layer.

- `COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv`
    - This line copies the compiled `uv` **executable** directly out of Astral's official container image (`ghcr.io/astral-sh/uv:latest`) and drops it into your own image at `/bin/uv`.
