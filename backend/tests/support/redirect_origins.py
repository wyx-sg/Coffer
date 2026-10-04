"""Two real origins on 127.0.0.1 for the secret boundary's redirect tests.

Spec secret "Send a secret only to the origin it was approved for". Origin
``first`` answers every request with a redirect to the same path on origin
``second`` (a different port, so a different origin); ``second`` records every
request it receives — headers, path and query — and answers 200. A test that
makes Coffer send a secret to ``first`` then reads ``second.seen`` to see
whether the secret followed the redirect.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass
class Origin:
    port: int = 0
    seen: list[dict[str, str]] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def received(self, needle: str) -> bool:
        """Whether ``needle`` arrived in any header, the path or the query."""
        return any(needle in value for request in self.seen for value in request.values())


@dataclass
class RedirectOrigins:
    first: Origin
    second: Origin
    #: The status ``first`` redirects with.
    status: int = 307


def _handler(origin: Origin, redirect: RedirectOrigins | None) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            return None

        def _answer(self) -> None:
            length = int(self.headers.get("content-length") or 0)
            if length:
                self.rfile.read(length)
            origin.seen.append(
                {
                    **{k.lower(): v for k, v in self.headers.items()},
                    ":path": self.path,
                    ":method": self.command,
                }
            )
            if redirect is not None:
                self.send_response(redirect.status)
                self.send_header("Location", f"{redirect.second.url}{self.path}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = _answer  # noqa: N815
        do_POST = _answer  # noqa: N815
        do_PUT = _answer  # noqa: N815
        do_PATCH = _answer  # noqa: N815
        do_DELETE = _answer  # noqa: N815

    return Handler


@contextmanager
def redirect_origins(status: int = 307) -> Iterator[RedirectOrigins]:
    second = Origin()
    first = Origin()
    pair = RedirectOrigins(first=first, second=second, status=status)
    servers = [
        (second, ThreadingHTTPServer(("127.0.0.1", 0), _handler(second, None))),
    ]
    second.port = servers[0][1].server_address[1]
    servers.append((first, ThreadingHTTPServer(("127.0.0.1", 0), _handler(first, pair))))
    first.port = servers[1][1].server_address[1]
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for _, s in servers]
    for thread in threads:
        thread.start()
    try:
        yield pair
    finally:
        for _, server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)
