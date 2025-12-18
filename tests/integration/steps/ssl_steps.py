"""Step definitions for SSL MITM features."""

import os
import socket
import time

import pytest
from pytest_bdd import given, then, when


def wait_for_proxy(host="proxy", port=8080, timeout=30):
    """Wait for proxy to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            sock.connect((host, port))
            sock.close()
            return True
        except (OSError, TimeoutError):
            time.sleep(0.5)
    return False


@pytest.fixture
def ssl_context():
    """Context for SSL tests."""
    return {
        "ssl_configured": False,
        "request_result": None,
        "request_error": None,
        "model_info": None,
    }


@given("a MITM proxy environment")
def mitm_proxy_environment(ssl_context):
    """Verify MITM proxy is available."""
    proxy_url = os.environ.get("HTTPS_PROXY", "")
    if "proxy:" in proxy_url:
        assert wait_for_proxy(), "Proxy not ready"


@given("SSL verification is disabled")
def disable_ssl_verification(ssl_context):
    """Configure SSL to skip verification."""
    import gundog._ssl

    gundog._ssl._ssl_configured = False

    from gundog._ssl import configure_ssl

    configure_ssl(no_verify=True)
    ssl_context["ssl_configured"] = True


@when("I make a direct HTTPS request to HuggingFace")
def make_https_request(ssl_context):
    """Make a direct HTTPS request."""
    import requests

    try:
        resp = requests.get(
            "https://huggingface.co/api/models/BAAI/bge-small-en-v1.5",
            timeout=10,
        )
        ssl_context["request_result"] = resp
        ssl_context["request_error"] = None
    except Exception as e:
        ssl_context["request_result"] = None
        ssl_context["request_error"] = e


@when("I fetch model info from HuggingFace Hub")
def fetch_model_info(ssl_context):
    """Fetch model info using HuggingFace Hub."""
    from huggingface_hub import model_info

    try:
        info = model_info("BAAI/bge-small-en-v1.5")
        ssl_context["model_info"] = info
        ssl_context["request_error"] = None
    except Exception as e:
        ssl_context["model_info"] = None
        ssl_context["request_error"] = e


@then("the request should fail with an SSL error")
def verify_ssl_error(ssl_context):
    """Verify the request failed with SSL error."""
    import requests

    assert ssl_context["request_error"] is not None
    assert isinstance(ssl_context["request_error"], requests.exceptions.SSLError)


@then("the request should succeed")
def verify_request_success(ssl_context):
    """Verify the request succeeded."""
    assert ssl_context["request_error"] is None
    assert ssl_context["request_result"] is not None
    assert ssl_context["request_result"].status_code == 200


@then("the model info should be retrieved successfully")
def verify_model_info(ssl_context):
    """Verify model info was retrieved."""
    assert ssl_context["request_error"] is None
    assert ssl_context["model_info"] is not None
    assert ssl_context["model_info"].id == "BAAI/bge-small-en-v1.5"
