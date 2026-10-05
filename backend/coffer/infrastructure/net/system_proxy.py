"""Network settings of a signed build come from the OS, not the environment.

An agent running as the same user can start the signed binary with
``HTTPS_PROXY`` at its own proxy and ``SSL_CERT_FILE`` trusting its own CA, and
every httpx client that honours the environment would then hand it injected
credentials. In a signed build we therefore drop those variables and read the
macOS system proxy settings instead, which cannot be changed without an admin
password. A development build keeps the environment untouched.
"""

from __future__ import annotations

import logging
import os
import sys
import urllib.request
from collections.abc import Callable, MutableMapping
from urllib.parse import urlsplit

from coffer.infrastructure.secret.build_identity import keychain_access_group

_logger = logging.getLogger(__name__)

_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
_CA_VARS = (
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
)
_ALWAYS_BYPASS = ("localhost", "127.0.0.1", "::1")


def read_system_proxies() -> dict[str, str]:
    """``{"http": url, "https": url, "no_proxy": "a,b"}`` from macOS; ``{}`` elsewhere."""
    if sys.platform != "darwin":
        return {}
    try:
        found = {
            k: v
            for k, v in urllib.request.getproxies_macosx_sysconf().items()  # type: ignore[attr-defined]
            if k in ("http", "https") and v
        }
        try:
            import _scproxy  # type: ignore[import-not-found]

            exceptions = _scproxy._get_proxy_settings().get("exceptions") or ()
            if exceptions:
                found["no_proxy"] = ",".join(str(e) for e in exceptions)
        except Exception:
            pass
        return found
    except Exception:
        return {}


def _host_port(url: str) -> str:
    try:
        parts = urlsplit(url if "://" in url else f"http://{url}")
        host = parts.hostname or ""
        return f"{host}:{parts.port}" if parts.port else host
    except ValueError:
        return "?"


def apply_system_network_settings(
    environ: MutableMapping[str, str] = os.environ,
    *,
    signed: bool | None = None,
    system_proxies: Callable[[], dict[str, str]] = read_system_proxies,
) -> None:
    if signed is None:
        signed = keychain_access_group() is not None
    if not signed:
        return
    for name in _PROXY_VARS + _CA_VARS:
        environ.pop(name, None)
        environ.pop(name.lower(), None)
    try:
        found = system_proxies()
    except Exception:
        found = {}
    http, https = found.get("http"), found.get("https")
    if http:
        environ["HTTP_PROXY"] = http
    if https:
        environ["HTTPS_PROXY"] = https
    if http or https:
        extra = [h for h in (found.get("no_proxy") or "").split(",") if h.strip()]
        environ["NO_PROXY"] = ",".join(dict.fromkeys([*_ALWAYS_BYPASS, *extra]))
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:
        pass
    _logger.info(
        "net.system_proxy",
        extra={
            "proxy_set": bool(http or https),
            "http": _host_port(http) if http else None,
            "https": _host_port(https) if https else None,
        },
    )
