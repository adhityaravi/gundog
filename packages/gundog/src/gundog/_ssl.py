"""SSL configuration for networks with custom CA certificates."""

import os
import sys
from pathlib import Path

import requests
import urllib3

# Environment variable names
GUNDOG_CA_BUNDLE = "GUNDOG_CA_BUNDLE"
GUNDOG_NO_VERIFY_SSL = "GUNDOG_NO_VERIFY_SSL"

# Standard SSL env vars that underlying libraries respect
_SSL_ENV_VARS = [
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "SSL_CERT_FILE",
]

# Track if SSL has been configured
_ssl_configured = False


def configure_ssl(
    no_verify: bool = False,
    ca_bundle: str | Path | None = None,
) -> None:
    """
    Configure SSL settings for HuggingFace downloads.

    Args:
        no_verify: Disable SSL verification entirely (insecure!)
        ca_bundle: Path to custom CA bundle file
    """
    global _ssl_configured
    if _ssl_configured:
        return
    _ssl_configured = True

    if ca_bundle is None:
        ca_bundle = os.environ.get(GUNDOG_CA_BUNDLE)

    if not no_verify:
        no_verify = os.environ.get(GUNDOG_NO_VERIFY_SSL, "").lower() in ("1", "true", "yes")

    ca_path_str: str | None = None
    if ca_bundle:
        ca_path = Path(ca_bundle).expanduser().resolve()
        if not ca_path.exists():
            raise FileNotFoundError(f"CA bundle not found: {ca_path}")
        ca_path_str = str(ca_path)

    if no_verify:
        # Must disable xet BEFORE importing huggingface_hub (reads env at import time)
        _disable_hf_xet()
        _configure_hf_no_verify()
        os.environ["CURL_CA_BUNDLE"] = ""
        os.environ["REQUESTS_CA_BUNDLE"] = ""
    elif ca_path_str:
        # Must disable xet BEFORE importing huggingface_hub (reads env at import time)
        _disable_hf_xet()
        _configure_hf_ca_bundle(ca_path_str)
        for var in _SSL_ENV_VARS:
            os.environ[var] = ca_path_str


def _disable_hf_xet() -> None:
    """Disable hf-xet."""
    # NOTE: hf-xet has its own SSL stack we can't configure
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    print("[ssl] hf-xet disabled, huggingface model downloads may be slower", file=sys.stderr)


def _configure_hf_no_verify() -> None:
    """Configure huggingface_hub to skip SSL verification."""
    # huggingface is kinda heavy, so lazy load
    from huggingface_hub import configure_http_backend

    def no_verify_backend_factory() -> requests.Session:
        session = requests.Session()
        session.verify = False
        return session

    configure_http_backend(backend_factory=no_verify_backend_factory)
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _configure_hf_ca_bundle(ca_path: str) -> None:
    """Configure huggingface_hub to use a custom CA bundle."""
    # huggingface is kinda heavy, so lazy load
    from huggingface_hub import configure_http_backend

    def ca_bundle_backend_factory() -> requests.Session:
        session = requests.Session()
        session.verify = ca_path
        return session

    configure_http_backend(backend_factory=ca_bundle_backend_factory)


def get_ssl_error_help() -> str:
    """Return helpful error message for SSL certificate errors."""
    return """
[bold red]SSL Certificate Error[/bold red]

Your network may be using a custom SSL certificate that Python doesn't trust.

[bold]You can disable SSL verification (less secure):[/bold]
  gundog index --no-verify-ssl

[bold]Or you can provide your network's CA certificate:[/bold]
  export GUNDOG_CA_BUNDLE=/path/to/ca-bundle.pem
  gundog index

[dim]Set GUNDOG_NO_VERIFY_SSL=1 to always skip verification.[/dim]
"""


def is_ssl_error(error: Exception) -> bool:
    """Check if an exception is an SSL certificate error."""
    error_str = str(error).lower()
    ssl_indicators = [
        "ssl",
        "certificate_verify_failed",
        "unable to get local issuer",
    ]
    return any(indicator in error_str for indicator in ssl_indicators)
