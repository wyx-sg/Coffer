"""A fake HTTP API on 127.0.0.1 for custom-tool tests (spec mcp-gateway).

A real socket, so the gateway's own HTTP client makes a real request: the
tests can see exactly which method, path, query, headers and body arrived.
Routes answer by path:

* ``/big``       — 2 MiB of text that embeds :attr:`FakeHttpApi.echo_secret`
* ``/missing``   — 404
* ``/forbidden`` — 403 HTML with diagnostic headers, a cookie, an auth
  challenge, an unknown header and :attr:`FakeHttpApi.echo_secret` in a trace id
* ``/slow``      — sleeps 3 s, then answers like any other path
* ``/redirect``  — 302 to :attr:`FakeHttpApi.redirect_to`
* ``/openapi.json`` — :attr:`FakeHttpApi.openapi` as JSON
* anything else  — 200 JSON ``{"ok": true, "path": …}``
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass
class Seen:
    method: str
    path: str
    headers: dict[str, str]
    body: bytes


@dataclass
class FakeHttpApi:
    port: int = 0
    seen: list[Seen] = field(default_factory=list)
    echo_secret: str = ""
    redirect_to: str = "http://127.0.0.1:9/elsewhere"
    openapi: dict[str, Any] = field(default_factory=dict)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def _handler(api: FakeHttpApi) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            return None

        def _answer(self) -> None:
            length = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(length) if length else b""
            api.seen.append(
                Seen(self.command, self.path, {k.lower(): v for k, v in self.headers.items()}, body)
            )
            path = self.path.split("?", 1)[0]
            if path.endswith("/big"):
                chunk = ("x" * 1000 + api.echo_secret + "\n").encode()
                payload = chunk * (2 * 1024 * 1024 // len(chunk) + 1)
                self._send(200, payload, "text/plain")
            elif path.endswith("/missing"):
                self._send(404, b'{"error": "not found"}', "application/json")
            elif path.endswith("/forbidden"):
                payload = b"<html><body><h1>403 Forbidden</h1></body></html>"
                self.send_response(403)
                self.send_header("Content-Type", "text/html")
                self.send_header("X-Request-Id", "req-123")
                self.send_header("X-Trace-Id", "trace-" + api.echo_secret)
                self.send_header("Set-Cookie", "session=s3cr3t-cookie; HttpOnly")
                self.send_header("WWW-Authenticate", 'Bearer realm="api"')
                self.send_header("X-Internal-Node", "node-7")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            elif path.endswith("/sp-error"):
                payload = b'{"error": "denied"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-Sp-Error", "101")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            elif path.endswith("/token"):
                token = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
                self._send(200, f"minted {token} for you".encode(), "text/plain")
            elif path.endswith("/slow"):
                time.sleep(3)
                self._send(200, b'{"ok": true, "slow": true}', "application/json")
            elif path.endswith("/redirect"):
                self.send_response(302)
                self.send_header("Location", api.redirect_to)
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif path.endswith("/openapi.json"):
                self._send(200, json.dumps(api.openapi).encode(), "application/json")
            else:
                reply = {
                    "ok": True,
                    "path": self.path,
                    "auth": bool(self.headers.get("authorization")),
                }
                self._send(200, json.dumps(reply).encode(), "application/json")

        def _send(self, status: int, payload: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = _answer  # noqa: N815
        do_POST = _answer  # noqa: N815
        do_PUT = _answer  # noqa: N815
        do_PATCH = _answer  # noqa: N815
        do_DELETE = _answer  # noqa: N815

    return Handler


class _Server(ThreadingHTTPServer):
    # The default backlog of 5 drops connections when a test fires dozens at once.
    request_queue_size = 128


@contextmanager
def fake_http_api() -> Iterator[FakeHttpApi]:
    api = FakeHttpApi()
    server = _Server(("127.0.0.1", 0), _handler(api))
    api.port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield api
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
