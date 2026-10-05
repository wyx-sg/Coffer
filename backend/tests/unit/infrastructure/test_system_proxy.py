from __future__ import annotations

import logging

import pytest

from coffer.infrastructure.net.system_proxy import apply_system_network_settings


def _env() -> dict[str, str]:
    return {
        "HTTPS_PROXY": "http://evil:1",
        "http_proxy": "http://evil:1",
        "ALL_PROXY": "x",
        "no_proxy": "y",
        "SSL_CERT_FILE": "/evil.pem",
        "SSL_CERT_DIR": "/d",
        "REQUESTS_CA_BUNDLE": "/r",
        "CURL_CA_BUNDLE": "/c",
        "NODE_EXTRA_CA_CERTS": "/n",
        "PATH": "/bin",
    }


def test_signed_replaces_environment_with_system_values() -> None:
    env = _env()
    apply_system_network_settings(
        env,
        signed=True,
        system_proxies=lambda: {
            "http": "http://corp:8080",
            "https": "http://corp:8080",
            "no_proxy": "*.corp,10.0.0.1",
        },
    )
    assert env == {
        "PATH": "/bin",
        "HTTP_PROXY": "http://corp:8080",
        "HTTPS_PROXY": "http://corp:8080",
        "NO_PROXY": "localhost,127.0.0.1,::1,*.corp,10.0.0.1",
    }


def test_signed_without_system_proxy_leaves_none() -> None:
    env = _env()
    apply_system_network_settings(env, signed=True, system_proxies=dict)
    assert env == {"PATH": "/bin"}


def test_development_build_is_untouched() -> None:
    env = _env()
    before = dict(env)
    apply_system_network_settings(env, signed=False, system_proxies=lambda: {"http": "http://a:1"})
    assert env == before


def test_reader_failure_means_no_proxy() -> None:
    def boom() -> dict[str, str]:
        raise RuntimeError("no sysconf")

    env = _env()
    apply_system_network_settings(env, signed=True, system_proxies=boom)
    assert env == {"PATH": "/bin"}


def test_userinfo_is_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        apply_system_network_settings(
            {},
            signed=True,
            system_proxies=lambda: {"https": "http://user:s3cret@corp:8080"},
        )
    rec = next(r for r in caplog.records if r.getMessage() == "net.system_proxy")
    assert rec.https == "corp:8080"  # type: ignore[attr-defined]
    assert "s3cret" not in caplog.text and "user" not in str(rec.__dict__)
