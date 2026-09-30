"""OpenAPI import and re-import for custom-tool groups.

Spec mcp-gateway "Import custom tools from an OpenAPI document"; design
add-http-custom-tools §8. Reading a document changes nothing; creating a
group from the chosen operations is ``CustomToolService.create_group`` with
the drafts the reading returned. Re-import previews first and applies only on
request, through the service's one write path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from coffer.application.mcp.custom_tool_ports import OpenApiSourcePort
from coffer.application.mcp.custom_tool_views import GroupView
from coffer.application.mcp.custom_tools import CustomToolService
from coffer.domain.mcp.custom_tool_errors import (
    NotImportedFromOpenApi,
    OpenApiFileNeeded,
    OpenApiUnreadable,
)
from coffer.domain.mcp.http_api import HttpApiTransport
from coffer.domain.mcp.openapi_import import (
    OpenApiError,
    OpenApiReading,
    ReimportPlan,
    apply_reimport,
    plan_reimport,
    read_openapi,
)


@dataclass(frozen=True)
class ToolChange:
    """A kept tool whose request a re-import would refresh."""

    name: str
    method: str
    path: str
    new_required: list[str]
    request_changed: bool


def _required(schema: dict[str, object]) -> set[str]:
    required = schema.get("required")
    return {r for r in required if isinstance(r, str)} if isinstance(required, list) else set()


def changed_tools(transport: HttpApiTransport, reading: OpenApiReading) -> list[ToolChange]:
    """The kept tools whose operation the spec now describes differently: a new
    required argument, or a moved method, path or body template."""
    in_doc = reading.by_key()
    out: list[ToolChange] = []
    for tool in transport.tools:
        fresh = in_doc.get(tool.operation) if tool.operation else None
        if fresh is None:
            continue
        new_required = sorted(_required(fresh.tool.input_schema) - _required(tool.input_schema))
        request_changed = (fresh.tool.method, fresh.tool.path, fresh.tool.body_template) != (
            tool.method,
            tool.path,
            tool.body_template,
        )
        if new_required or request_changed:
            out.append(
                ToolChange(
                    name=tool.name,
                    method=fresh.tool.method,
                    path=fresh.tool.path,
                    new_required=new_required,
                    request_changed=request_changed,
                )
            )
    return out


@dataclass(frozen=True)
class ImportReading:
    reading: OpenApiReading
    kind: Literal["url", "file"]
    location: str


class CustomToolImporter:
    def __init__(self, service: CustomToolService, source: OpenApiSourcePort) -> None:
        self._service = service
        self._source = source

    async def read(
        self,
        *,
        url: str | None,
        document: str | None,
        filename: str | None,
        taken: set[str] | None = None,
    ) -> ImportReading:
        """A document, from a URL (through the SSRF guard) or as given."""
        if url:
            final_url, text = await self._source.fetch(url)
            return ImportReading(self._read(text, final_url, taken), "url", url)
        if document is None:
            raise OpenApiUnreadable("give the document's URL or its contents")
        return ImportReading(self._read(document, None, taken), "file", filename or "openapi")

    def _read(self, text: str, source_url: str | None, taken: set[str] | None) -> OpenApiReading:
        doc = self._source.parse(text)
        try:
            return read_openapi(doc, source_url=source_url, taken_names=taken)
        except OpenApiError as e:
            raise OpenApiUnreadable(str(e)) from e

    async def _reread(
        self, transport: HttpApiTransport, name: str, document: str | None
    ) -> OpenApiReading:
        source = transport.source
        if source is None:
            raise NotImportedFromOpenApi(name)
        taken = {t.name for t in transport.tools}
        if document is not None:
            return (
                await self.read(url=None, document=document, filename=None, taken=taken)
            ).reading
        if source.kind == "file":
            raise OpenApiFileNeeded(name)
        return (
            await self.read(url=source.location, document=None, filename=None, taken=taken)
        ).reading

    async def preview(
        self, name: str, *, document: str | None
    ) -> tuple[OpenApiReading, ReimportPlan, list[ToolChange]]:
        """What a re-import would add, remove, keep and change — nothing is written."""
        _, transport = await self._service.group(name)
        reading = await self._reread(transport, name, document)
        return reading, plan_reimport(transport, reading), changed_tools(transport, reading)

    async def apply(
        self, name: str, *, document: str | None, add_keys: set[str], actor: str
    ) -> GroupView:
        resource, transport = await self._service.group(name)
        reading = await self._reread(transport, name, document)
        plan = plan_reimport(transport, reading)
        updated = apply_reimport(
            transport, reading, add_keys=add_keys, fetched_at=self._service.now()
        )
        await self._service.write_transport(resource, updated, actor)
        await self._service.reach.delete_tools(resource.uid, plan.removed)
        return await self._service.view(name)


__all__ = ["CustomToolImporter", "ImportReading", "ToolChange", "changed_tools"]
