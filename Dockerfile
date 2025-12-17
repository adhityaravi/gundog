FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml README.md ./
COPY src ./src

# Install the package
RUN uv pip install --system .

# Create directories for config and indexes
RUN mkdir -p /root/.config/gundog /data/indexes

# Default config location
ENV XDG_CONFIG_HOME=/root/.config

# Expose default port
EXPOSE 7676

# Default command - run daemon in foreground
CMD ["gundog", "daemon", "start", "--foreground"]
