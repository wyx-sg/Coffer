"""Composition helper for the chat runtime factory.

Kept out of ``app.py`` to hold the line under the 400-line guideline and to
isolate the (lazy) infrastructure import. The default factory resolves the
daemon's own ``/mcp`` gateway endpoint + token from ``daemon.json`` at build
time, so the built-in agent can call the vault's tools.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any

from coffer.infrastructure.daemon.pid_lock import read as read_daemon_json


def _daemon_json_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "daemon.json"


def _gateway_endpoint() -> tuple[str | None, str | None]:
    path = _daemon_json_path()
    if not path.exists():
        return None, None
    try:
        info = read_daemon_json(path)
    except (ValueError, KeyError, OSError):
        return None, None
    return f"http://127.0.0.1:{info.port}/mcp", info.token


def build_default_runtime_factory(keyring: Any) -> Any:
    from coffer.infrastructure.chat.runtime_factory import CompositeRuntimeFactory

    return CompositeRuntimeFactory(gateway_endpoint=_gateway_endpoint, keyring=keyring)
