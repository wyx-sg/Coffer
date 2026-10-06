"""Wire models of a custom tool's request preview (a dry run).

Spec mcp-gateway "Preview a custom tool's request without sending it".
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from coffer.application.mcp.custom_tool_preview import RequestPreview

SecretStateName = Literal["none", "present", "missing", "rejected", "pending_approval"]


class CustomToolPreviewSecretOut(BaseModel):
    """The stored secret a header reads — its reference, never its value."""

    id: str
    #: The name the Secrets page shows: its label, else the id's name.
    name: str
    scheme: str | None
    #: ``present``, ``missing`` or ``pending_approval``.
    state: SecretStateName


class CustomToolPreviewHeaderOut(BaseModel):
    name: str
    #: The value as it would be sent; a secret header's credential is ``***``.
    value: str
    #: Set for a header whose credential is a stored secret.
    secret: CustomToolPreviewSecretOut | None = None


class CustomToolRequestPreviewOut(BaseModel):
    """What one call would send; nothing was sent and no secret was read."""

    environment: str
    method: str
    url: str
    headers: list[CustomToolPreviewHeaderOut]
    body: str | None
    timeout_seconds: int
    timeout_source: Literal["environment", "group"]
    variables: dict[str, str]


def preview_out(
    p: RequestPreview, label_of: Callable[[str], str | None] = lambda _ref: None
) -> CustomToolRequestPreviewOut:
    """The wire shape; ``label_of`` names a secret by its label when it has one."""
    return CustomToolRequestPreviewOut(
        environment=p.environment,
        method=p.method,
        url=p.url,
        headers=[
            CustomToolPreviewHeaderOut(
                name=h.name,
                value=h.value,
                secret=(
                    CustomToolPreviewSecretOut(
                        id=h.secret.id,
                        name=label_of(h.secret.id) or h.secret.name,
                        scheme=h.secret.scheme,
                        state=h.secret.state,
                    )
                    if h.secret is not None
                    else None
                ),
            )
            for h in p.headers
        ],
        body=p.body,
        timeout_seconds=p.timeout_seconds,
        timeout_source=p.timeout_source,
        variables=p.variables,
    )


__all__ = [
    "CustomToolPreviewHeaderOut",
    "CustomToolPreviewSecretOut",
    "CustomToolRequestPreviewOut",
    "preview_out",
]
