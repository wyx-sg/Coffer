"""Preview a custom tool's request without sending it (a dry run).

Spec mcp-gateway "Preview a custom tool's request without sending it". The
preview goes through a test's own steps — the environment chosen by the
gateway's rules, the arguments checked against the tool's schema, the request
built by :func:`~coffer.domain.mcp.http_api_request.build_request` — and stops
before the two that touch the outside: no secret value is read or decrypted
(each secret header shows a placeholder, its secret's id, name, scheme and
whether it is there) and no HTTP request is made.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from coffer.application.mcp.custom_tool_views import SecretState
from coffer.application.mcp.custom_tools import CustomToolService, secret_name_of, validated_tool
from coffer.domain.mcp.custom_tool_env_errors import CustomToolRequestInvalid
from coffer.domain.mcp.custom_tool_errors import CustomToolNotFound
from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.mcp.http_api_environment import HttpApiEnvironment
from coffer.domain.mcp.http_api_render import ArgumentsInvalid, RenderError
from coffer.domain.mcp.http_api_request import build_request, placeholder_overlay
from coffer.domain.resource import Resource


@dataclass(frozen=True)
class PreviewSecret:
    """The stored secret a header reads: its reference, never its value."""

    id: str
    name: str
    scheme: str | None
    state: SecretState


@dataclass(frozen=True)
class PreviewHeader:
    name: str
    #: The value as sent; a secret header's credential is the placeholder.
    value: str
    secret: PreviewSecret | None = None


@dataclass(frozen=True)
class RequestPreview:
    environment: str
    method: str
    url: str
    headers: list[PreviewHeader]
    body: str | None
    timeout_seconds: int
    #: Whose timeout applies: the environment's own, or the group's.
    timeout_source: Literal["environment", "group"]
    #: The environment's variables (never secret) the templates may use.
    variables: dict[str, str] = field(default_factory=dict)


def preview_of(
    group: str,
    transport: HttpApiTransport,
    env: HttpApiEnvironment,
    tool: HttpApiTool,
    arguments: dict[str, Any],
    states: dict[str, SecretState],
) -> RequestPreview:
    """``tool``'s request in ``env`` as a call would send it, each secret
    header's credential replaced by the placeholder."""
    try:
        request = build_request(transport, env, tool, arguments, placeholder_overlay(env))
    except ArgumentsInvalid:
        raise
    except RenderError as e:
        raise CustomToolRequestInvalid(group, env.name, str(e)) from e
    secret_of = {h.lower(): h for h in env.secret_refs}
    headers = []
    for name, value in request.headers.items():
        header = secret_of.get(name.lower())
        secret = None
        if header is not None:
            ref = env.secret_refs[header]
            secret = PreviewSecret(
                id=ref,
                name=secret_name_of(ref),
                scheme=env.auth_schemes.get(header),
                state=states.get(header, "present"),
            )
        headers.append(PreviewHeader(name=name, value=value, secret=secret))
    return RequestPreview(
        environment=env.name,
        method=request.method,
        url=request.url,
        headers=headers,
        body=request.body.decode("utf-8") if request.body is not None else None,
        timeout_seconds=transport.timeout_for(env),
        timeout_source="environment" if env.timeout_seconds is not None else "group",
        variables=dict(env.variables),
    )


class CustomToolPreviews:
    """Dry runs of a saved tool or a draft, over the one service's checks."""

    def __init__(self, service: CustomToolService) -> None:
        self._service = service

    async def saved(
        self, name: str, tool_name: str, arguments: dict[str, Any], environment: str | None
    ) -> RequestPreview:
        resource, transport = await self._service.group(name)
        tool = transport.tool(tool_name)
        if tool is None:
            raise CustomToolNotFound(name, tool_name)
        return await self._preview(resource, transport, tool, arguments, environment)

    async def draft(
        self,
        name: str,
        raw_tool: dict[str, Any],
        arguments: dict[str, Any],
        environment: str | None,
    ) -> RequestPreview:
        resource, transport = await self._service.group(name)
        tool = validated_tool(raw_tool)
        return await self._preview(resource, transport, tool, arguments, environment)

    async def _preview(
        self,
        resource: Resource,
        transport: HttpApiTransport,
        tool: HttpApiTool,
        arguments: dict[str, Any],
        environment: str | None,
    ) -> RequestPreview:
        env, args = self._service.choose(resource, transport, tool, arguments, environment)
        states = (await self._service.secret_states(resource, env)).header_states
        return preview_of(resource.name, transport, env, tool, args, states)


__all__ = [
    "CustomToolPreviews",
    "PreviewHeader",
    "PreviewSecret",
    "RequestPreview",
    "preview_of",
]
