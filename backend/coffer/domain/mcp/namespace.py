"""Namespace transform: <server>__<tool>, coffer://<server>/<orig> URIs.

These are pure functions; tests under `tests/unit/` exercise them. Keep
no dependencies beyond the domain error class.
"""

from __future__ import annotations

from coffer.domain.errors import InvalidPrefix


def prefix_tool(server: str, tool: str) -> str:
    return f"{server}__{tool}"


def parse_prefixed_tool(prefixed: str) -> tuple[str, str]:
    server, sep, tool = prefixed.partition("__")
    if not sep or not server or not tool:
        raise InvalidPrefix(f"not a coffer-prefixed tool name: {prefixed!r}")
    return server, tool


def prefix_resource_uri(server: str, uri: str) -> str:
    return f"coffer://{server}/{uri}"


def parse_prefixed_uri(prefixed: str) -> tuple[str, str]:
    if not prefixed.startswith("coffer://"):
        raise InvalidPrefix(f"not a coffer-prefixed uri: {prefixed!r}")
    rest = prefixed.removeprefix("coffer://")
    server, sep, original = rest.partition("/")
    if not sep or not server or not original:
        raise InvalidPrefix(f"malformed prefixed uri: {prefixed!r}")
    return server, original


def prefix_prompt(server: str, prompt: str) -> str:
    return f"{server}__{prompt}"


def parse_prefixed_prompt(prefixed: str) -> tuple[str, str]:
    return parse_prefixed_tool(prefixed)
