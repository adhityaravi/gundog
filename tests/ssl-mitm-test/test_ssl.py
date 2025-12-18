#!/usr/bin/env python3
"""Test script to reproduce and verify SSL MITM fix."""

import os
import sys
import time
import socket

def wait_for_proxy(host="proxy", port=8080, timeout=30):
    """Wait for proxy to be ready."""
    print(f"Waiting for proxy at {host}:{port}...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            sock.connect((host, port))
            sock.close()
            print("Proxy is ready!")
            return True
        except (socket.error, socket.timeout):
            time.sleep(0.5)
    print("Proxy not ready after timeout")
    return False

print("=" * 60)
print("SSL MITM Test Suite")
print("=" * 60)
print(f"HTTPS_PROXY: {os.environ.get('HTTPS_PROXY', 'not set')}")
print(f"HTTP_PROXY: {os.environ.get('HTTP_PROXY', 'not set')}")
print()

# Wait for proxy to be ready
wait_for_proxy()
print()

# =============================================================================
# Part 1: Reproduce the SSL error (without fix)
# =============================================================================
print("[Part 1] Reproducing SSL error WITHOUT fix...")
print("-" * 40)

# Test 1: Direct requests to HuggingFace (should fail)
print("[Test 1.1] Direct HTTPS request (should FAIL)...")
try:
    import requests
    resp = requests.get("https://huggingface.co/api/models/BAAI/bge-small-en-v1.5", timeout=10)
    print(f"  UNEXPECTED SUCCESS: {resp.status_code}")
except Exception as e:
    if "ssl" in str(e).lower() or "certificate" in str(e).lower():
        print(f"  EXPECTED FAILURE (SSL): {type(e).__name__}")
    else:
        print(f"  FAILED (other): {type(e).__name__}: {e}")

print()

# =============================================================================
# Part 2: Verify the fix works
# =============================================================================
print("[Part 2] Testing SSL fix with --no-verify-ssl...")
print("-" * 40)

# Apply the SSL fix
from gundog._ssl import configure_ssl
configure_ssl(no_verify=True)

# Test 2: Direct requests after fix
print("[Test 2.1] Direct HTTPS request with SSL disabled...")
try:
    import requests
    resp = requests.get("https://huggingface.co/api/models/BAAI/bge-small-en-v1.5", timeout=10)
    print(f"  SUCCESS: {resp.status_code}")
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")

print()

# Test 3: huggingface_hub library after fix
print("[Test 2.2] HuggingFace Hub model info with SSL disabled...")
try:
    from huggingface_hub import model_info
    info = model_info("BAAI/bge-small-en-v1.5")
    print(f"  SUCCESS: Model {info.id}")
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")

print()

# Test 4: Gundog embedder after fix
print("[Test 2.3] Gundog embedder with SSL disabled...")
try:
    from gundog._embedder import create_embedder
    embedder = create_embedder(model_name="BAAI/bge-small-en-v1.5", enable_onnx=True)
    result = embedder.embed_text("test")
    print(f"  SUCCESS: Embedding shape {result.shape}")
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")

print()
print("=" * 60)
print("Test complete")
