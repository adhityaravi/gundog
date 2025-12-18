"""Tests for SSL configuration module."""

import os
from unittest.mock import patch

import pytest

from gundog._ssl import (
    GUNDOG_NO_VERIFY_SSL,
    configure_ssl,
    get_ssl_error_help,
    is_ssl_error,
)


@pytest.fixture(autouse=True)
def reset_ssl_state():
    """Reset SSL configured state between tests."""
    import gundog._ssl

    gundog._ssl._ssl_configured = False
    yield
    gundog._ssl._ssl_configured = False


def test_is_ssl_error_detects_ssl_keyword():
    assert is_ssl_error(Exception("SSL: CERTIFICATE_VERIFY_FAILED")) is True


def test_is_ssl_error_detects_certificate_verify_failed():
    assert is_ssl_error(Exception("certificate_verify_failed")) is True


def test_is_ssl_error_detects_local_issuer():
    assert is_ssl_error(Exception("unable to get local issuer certificate")) is True


def test_is_ssl_error_returns_false_for_other_errors():
    assert is_ssl_error(Exception("Connection refused")) is False
    assert is_ssl_error(TimeoutError("timed out")) is False


def test_get_ssl_error_help_contains_options():
    help_text = get_ssl_error_help()
    assert "--no-verify-ssl" in help_text
    assert "GUNDOG_CA_BUNDLE" in help_text
    assert "GUNDOG_NO_VERIFY_SSL" in help_text


@patch("gundog._ssl._configure_hf_no_verify")
@patch("gundog._ssl._disable_hf_xet")
def test_configure_ssl_no_verify(mock_xet, mock_no_verify, monkeypatch):
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)

    configure_ssl(no_verify=True)

    assert os.environ.get("CURL_CA_BUNDLE") == ""
    assert os.environ.get("REQUESTS_CA_BUNDLE") == ""
    mock_xet.assert_called_once()
    mock_no_verify.assert_called_once()


@patch("gundog._ssl._configure_hf_ca_bundle")
@patch("gundog._ssl._disable_hf_xet")
def test_configure_ssl_ca_bundle(mock_xet, mock_ca_bundle, tmp_path, monkeypatch):
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text("cert")

    configure_ssl(ca_bundle=str(ca_file))

    assert os.environ.get("REQUESTS_CA_BUNDLE") == str(ca_file)
    mock_xet.assert_called_once()
    mock_ca_bundle.assert_called_once()


def test_configure_ssl_missing_ca_bundle_raises():
    with pytest.raises(FileNotFoundError, match="CA bundle not found"):
        configure_ssl(ca_bundle="/nonexistent/ca.pem")


@patch("gundog._ssl._configure_hf_no_verify")
@patch("gundog._ssl._disable_hf_xet")
def test_configure_ssl_env_var_no_verify(mock_xet, mock_no_verify, monkeypatch):
    monkeypatch.setenv(GUNDOG_NO_VERIFY_SSL, "1")

    configure_ssl()

    mock_xet.assert_called_once()
    mock_no_verify.assert_called_once()


@patch("gundog._ssl._configure_hf_no_verify")
@patch("gundog._ssl._disable_hf_xet")
def test_configure_ssl_only_runs_once(mock_xet, mock_no_verify, monkeypatch):
    configure_ssl(no_verify=True)
    configure_ssl(no_verify=True)

    mock_xet.assert_called_once()


def test_disable_hf_xet_sets_env(monkeypatch, capsys):
    from gundog._ssl import _disable_hf_xet

    monkeypatch.delenv("HF_HUB_DISABLE_XET", raising=False)

    _disable_hf_xet()

    assert os.environ.get("HF_HUB_DISABLE_XET") == "1"
    assert "hf-xet disabled" in capsys.readouterr().err
