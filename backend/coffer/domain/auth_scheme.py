"""The auth scheme a secret header is sent with.

A secret header (``secret_refs`` on an HTTP server or a custom-tool group) stores
only the credential — the key a provider hands out — and the header row names
the scheme the request puts in front of it (``auth_schemes``): ``Authorization:
Bearer <key>``. A slot without a scheme sends the stored value as it is, for a
header such as ``X-Api-Key`` whose whole value is the key.

Pure: the standard library only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal

AuthScheme = Literal["Bearer", "Token"]
AUTH_SCHEMES: tuple[AuthScheme, ...] = ("Bearer", "Token")

_PREFIXED = re.compile(r"^\s*(bearer|token)\s+(\S.*?)\s*$", re.IGNORECASE | re.DOTALL)


def header_value(scheme: str | None, credential: str) -> str:
    """What goes on the wire for a slot: ``<scheme> <credential>``, or the
    credential alone for a slot without a scheme."""
    return f"{scheme} {credential}" if scheme else credential


def split_scheme(value: str) -> tuple[AuthScheme | None, str]:
    """A pasted header value as (scheme, credential): ``"Bearer abc"`` →
    ``("Bearer", "abc")``; a value without a known scheme is all credential."""
    m = _PREFIXED.match(value)
    if m is None:
        return None, value
    scheme: AuthScheme = "Bearer" if m.group(1).lower() == "bearer" else "Token"
    return scheme, m.group(2)


def with_schemes(overlay: Mapping[str, str], schemes: Mapping[str, str]) -> dict[str, str]:
    """The secret headers as sent: each stored credential behind its slot's scheme."""
    return {name: header_value(schemes.get(name), value) for name, value in overlay.items()}


def check_schemes(schemes: Mapping[str, str], secret_refs: Mapping[str, str]) -> None:
    """A scheme belongs to a secret header: one named in ``secret_refs``."""
    stray = sorted(set(schemes) - set(secret_refs))
    if stray:
        raise ValueError(
            "an auth scheme is set only on a secret header; not secret: " + ", ".join(stray)
        )


__all__ = [
    "AUTH_SCHEMES",
    "AuthScheme",
    "check_schemes",
    "header_value",
    "split_scheme",
    "with_schemes",
]
