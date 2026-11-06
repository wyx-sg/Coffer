"""The kind of an HTTP upstream's network failure, never its text."""

from __future__ import annotations

import socket
import ssl

import httpx2

from coffer.infrastructure.mcp.failure_detail import http_failure_kind


def _caused(outer: Exception, cause: BaseException) -> Exception:
    outer.__cause__ = cause
    return outer


def test_each_network_failure_has_its_own_words() -> None:
    req = httpx2.Request("GET", "https://mcp.example/mcp?key=s3cret")
    cases = {
        "the server's host name does not resolve": _caused(
            httpx2.ConnectError("boom", request=req), socket.gaierror(8, "nodename nor servname")
        ),
        "the connection was refused": _caused(
            httpx2.ConnectError("All connection attempts failed", request=req),
            ConnectionRefusedError(61, "Connection refused"),
        ),
        "the TLS handshake failed": _caused(
            httpx2.ConnectError("x", request=req), ssl.SSLError(1, "bad cert")
        ),
        "connecting timed out": httpx2.ConnectTimeout("t", request=req),
        "the server stopped answering mid-request": httpx2.ReadTimeout("t", request=req),
        "the proxy refused the connection": httpx2.ProxyError("p", request=req),
        "the server closed the connection mid-answer": httpx2.RemoteProtocolError("r", request=req),
    }
    for words, exc in cases.items():
        assert http_failure_kind(exc) == words
        assert "s3cret" not in http_failure_kind(exc)
