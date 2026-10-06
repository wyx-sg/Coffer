"""One custom tool's request in one environment, as the gateway sends it.

Spec mcp-gateway "Make a custom tool's request in the gateway" and "Preview a
custom tool's request without sending it". The gateway, a page test and a
dry-run preview all build the request here, so a preview shows exactly what a
call would send — only with each secret header's credential replaced by a
placeholder.

Pure: the standard library and the custom-tool domain only.
"""

from __future__ import annotations

from typing import Any

from coffer.domain.auth_scheme import with_schemes
from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.mcp.http_api_environment import HttpApiEnvironment
from coffer.domain.mcp.http_api_render import RenderedRequest, render_request

#: What a preview shows in place of a stored secret's value.
SECRET_PLACEHOLDER = "***"


def build_request(
    transport: HttpApiTransport,
    env: HttpApiEnvironment,
    tool: HttpApiTool,
    arguments: dict[str, Any] | None,
    header_overlay: dict[str, str],
) -> RenderedRequest:
    """The request for ``tool`` in ``env``: the arguments validated against the
    tool's schema, the environment's base URL, headers and variables, and its
    secret headers (``{header: value}``) added last, so no tool header can
    replace them. ``arguments`` no longer holds the environment choice."""
    rendered = render_request(
        base_url=str(env.base_url),
        method=tool.method,
        path=tool.path,
        group_headers=env.headers,
        tool_headers=tool.headers,
        body_template=tool.body_template,
        input_schema=tool.input_schema,
        arguments=arguments,
        variables=env.variables,
    )
    for header, value in with_schemes(header_overlay, env.auth_schemes).items():
        # Header names compare case-insensitively: drop any spelling a tool gave.
        for name in [n for n in rendered.headers if n.lower() == header.lower()]:
            del rendered.headers[name]
        rendered.headers[header] = value
    return rendered


def placeholder_overlay(env: HttpApiEnvironment) -> dict[str, str]:
    """Every secret header of ``env`` holding :data:`SECRET_PLACEHOLDER`."""
    return dict.fromkeys(env.secret_refs, SECRET_PLACEHOLDER)


__all__ = ["SECRET_PLACEHOLDER", "build_request", "placeholder_overlay"]
