"""Header rows of a custom-tool group: names, line breaks and secret-looking values.

Shared by a group's environments and its tools (``http_api_environment``,
``http_api``). Pure: the standard library only.
"""

from __future__ import annotations

import re

from coffer.domain.mcp.http_api_render import holes_in

#: An HTTP header name (RFC 9110 token).
HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$")

#: Static values that look like secrets are refused, as on the other transports.
_SECRET_PATTERNS = (
    re.compile(r"^Bearer\s+\S"),
    re.compile(r"^(ghp_|gho_|github_pat_|sk-|xox[abp]-)"),
    re.compile(r"^eyJ[A-Za-z0-9_-]{20,}"),
)


def looks_like_secret(value: str) -> bool:
    return any(p.search(value) for p in _SECRET_PATTERNS)


def check_headers(values: dict[str, str], *, allow_holes: bool) -> dict[str, str]:
    for name, value in values.items():
        if not HEADER_NAME_RE.match(name):
            raise ValueError(f"{name!r} is not a valid header name")
        if "\n" in value or "\r" in value:
            raise ValueError(f"header {name!r} holds a line break")
        if not allow_holes and holes_in(value):
            raise ValueError(f"group header {name!r} may not hold an argument hole")
        if looks_like_secret(value):
            raise ValueError(
                f"static value for header {name!r} looks like a secret; bind a stored "
                "secret to the header instead"
            )
    return values


__all__ = ["HEADER_NAME_RE", "check_headers", "looks_like_secret"]
