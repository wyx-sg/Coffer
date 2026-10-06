"""POST /{uid}/resources/read and /{uid}/prompts/get — the row details' previews.

Spec mcp-gateway "Preview a resource or a prompt from the server page". The
server page's Resources and Prompts rows open to their details; reading the
resource's content or filling the prompt is asked for there, one row at a
time. An error the server answers with comes back in ``error`` beside an empty
``contents``; a server that cannot be reached is ``UPSTREAM_UNAVAILABLE``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from coffer.application.mcp.capability_preview import Preview, get_prompt, read_resource
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.resource_service import ResourceService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.mcp.dependencies import get_capability_discovery, require_mcp_server

router = APIRouter(
    prefix="/api/v1/resources/mcp_server",
    tags=["mcp"],
    dependencies=[Depends(require_token)],
)


class ResourceReadBody(BaseModel):
    uri: str = Field(min_length=1, description="The resource's URI as the server lists it.")


class PromptGetBody(BaseModel):
    name: str = Field(min_length=1, description="The prompt's name as the server lists it.")
    arguments: dict[str, str] = Field(default_factory=dict)


class PreviewContentOut(BaseModel):
    """One body of a resource, or one message of a prompt."""

    kind: str = Field(description="text, blob, or a prompt content type such as image.")
    text: str | None = None
    truncated: bool = Field(False, description="The text was cut at 64 KiB.")
    size_bytes: int | None = Field(
        None, description="A binary body's size; its bytes are not sent."
    )
    uri: str | None = None
    mime_type: str | None = None
    role: str | None = Field(None, description="A prompt message's role: user or assistant.")


class CapabilityPreviewOut(BaseModel):
    contents: list[PreviewContentOut]
    description: str | None = None
    error: str | None = Field(None, description="The error the server answered with.")


def _out(preview: Preview) -> CapabilityPreviewOut:
    return CapabilityPreviewOut(
        contents=[PreviewContentOut(**vars(c)) for c in preview.contents],
        description=preview.description,
        error=preview.error,
    )


@router.post("/{uid}/resources/read", response_model=CapabilityPreviewOut)
async def read_resource_preview(
    uid: str,
    body: ResourceReadBody,
    discovery: CapabilityDiscovery = Depends(get_capability_discovery),  # noqa: B008
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> CapabilityPreviewOut:
    """Read one of the server's resources now, for its row's details."""
    resource = await require_mcp_server(uid, resource_service)
    return _out(await read_resource(discovery, resource.name, body.uri))


@router.post("/{uid}/prompts/get", response_model=CapabilityPreviewOut)
async def get_prompt_preview(
    uid: str,
    body: PromptGetBody,
    discovery: CapabilityDiscovery = Depends(get_capability_discovery),  # noqa: B008
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> CapabilityPreviewOut:
    """Fill one of the server's prompts with the given arguments, for its row's details."""
    resource = await require_mcp_server(uid, resource_service)
    return _out(await get_prompt(discovery, resource.name, body.name, body.arguments))
