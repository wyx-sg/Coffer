"""Path portability for exported config (spec vault-export-import, ADR: vault-export-import).

The user's machines have different usernames/home layouts, so absolute paths
inside resource configs (``config_dir``, command paths) break when carried
verbatim. Export rewrites string values whose prefix is the exporting
machine's home directory to ``${HOME}/...``; import expands the token against
the importing machine's home. Paths outside ``$HOME`` are carried verbatim and
may simply not resolve on the other machine — which surfaces as a reported
import failure for that resource, not a silent mismatch.

Everything here is pure: homes are passed in, IO lives in infrastructure.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

HOME_TOKEN = "${HOME}"


def _map_strings(value: Any, fn: Any) -> Any:
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, Mapping):
        return {k: _map_strings(v, fn) for k, v in value.items()}
    if isinstance(value, list):
        return [_map_strings(v, fn) for v in value]
    return value


def normalize_home(config: Mapping[str, Any], home: str) -> dict[str, Any]:
    """Rewrite string values under ``home`` to portable ``${HOME}/...`` form.

    Only prefix matches at a path-boundary count: ``/Users/xing/x`` matches for
    home ``/Users/xing``, ``/Users/xingelsewhere`` does not. A value already
    containing the literal token is left as-is (documented edge)."""
    root = home.rstrip("/")
    if not root:
        return dict(config)

    def rewrite(s: str) -> str:
        if s == root:
            return HOME_TOKEN
        if s.startswith(root + "/"):
            return HOME_TOKEN + s[len(root) :]
        return s

    result: dict[str, Any] = _map_strings(dict(config), rewrite)
    return result


def expand_home(config: Mapping[str, Any], home: str) -> dict[str, Any]:
    """Expand ``${HOME}`` tokens to this machine's home directory."""
    root = home.rstrip("/")

    def rewrite(s: str) -> str:
        if s == HOME_TOKEN:
            return root
        if s.startswith(HOME_TOKEN + "/"):
            return root + s[len(HOME_TOKEN) :]
        return s

    result: dict[str, Any] = _map_strings(dict(config), rewrite)
    return result
