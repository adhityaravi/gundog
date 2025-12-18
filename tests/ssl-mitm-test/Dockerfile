FROM python:3.12-slim

# Install build dependencies for hnswlib
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install gundog from local source
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Install uv and the package
RUN pip install uv && uv pip install --system -e ".[onnx]"

# Test script
COPY tests/ssl-mitm-test/test_ssl.py ./test_ssl.py

CMD ["python", "test_ssl.py"]
