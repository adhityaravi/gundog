"""Test module for SSL MITM feature."""

import os

import pytest
from pytest_bdd import scenarios

# Skip all tests in this module unless HTTPS_PROXY is set
pytestmark = pytest.mark.skipif(
    not os.environ.get("HTTPS_PROXY"),
    reason="Requires MITM proxy (run via docker compose)",
)

# Load all scenarios from the ssl_mitm feature file
scenarios("../features/ssl_mitm.feature")
