"""Where "does this tool write?" is kept, and how it is answered.

The judgement is a property of the tool, so it lives on the ``mcp_server``
resource that serves it — ``config["tool_write_class"]``, keyed by the server's
own unprefixed tool name. There is no table and no second store.

This module is the adapter side of ``application.workflow.ports.ToolClassPort``.
It satisfies that Protocol structurally and does **not** import it: the import
fence forbids ``application.mcp`` from reaching into ``application.workflow``,
and a Protocol is exactly what makes that possible — the workflow gate types its
dependency, the composition root passes this class, and neither package names
the other.
"""

from __future__ import annotations

from typing import Any

from coffer.application.resource_service import ResourceService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import ResourceRef

#: The config key the map lives under, in one place so the reader, the writer
#: and the Pydantic field cannot drift apart.
TOOL_WRITE_CLASS_KEY = "tool_write_class"


class ResourceToolClassifier:
    """Read and write an ``mcp_server``'s ``tool_write_class`` map."""

    def __init__(self, resources: ResourceService, *, actor: str = "workflow") -> None:
        self._resources = resources
        self._actor = actor

    async def classify(self, server: str, tool: str) -> str | None:
        """This tool's recorded judgement, or ``None`` when nothing judged it.

        ``None`` is also the answer for a server that is not registered. Both
        cases mean the same thing to the gate — nobody has said this call is
        safe — and the gate treats "nobody has said" as write-class (FR-036),
        which is the direction an error should fall.
        """
        recorded = await self._read_map(server)
        value = recorded.get(tool)
        return str(value) if isinstance(value, str) else None

    async def remember(self, server: str, tool: str, write_class: str) -> None:
        """Record the developer's answer so the same tool is asked about once.

        The whole config is rewritten because that is the only write the
        resource layer offers; the map is merged rather than replaced, so an
        answer about one tool never erases an answer about another. A write for
        an unregistered server is dropped rather than raised: the server may
        have been deleted between the question and the answer, and failing the
        developer's decision over it would be the wrong end to break.
        """
        ref = ResourceRef("mcp_server", server)
        try:
            resource = await self._resources.get(ref)
        except ResourceNotFound:
            return
        config: dict[str, Any] = dict(resource.config)
        current = config.get(TOOL_WRITE_CLASS_KEY)
        merged: dict[str, Any] = dict(current) if isinstance(current, dict) else {}
        merged[tool] = write_class
        config[TOOL_WRITE_CLASS_KEY] = merged
        await self._resources.update_config(ref, config, actor=self._actor)

    async def _read_map(self, server: str) -> dict[str, Any]:
        try:
            resource = await self._resources.get(ResourceRef("mcp_server", server))
        except ResourceNotFound:
            return {}
        recorded = resource.config.get(TOOL_WRITE_CLASS_KEY)
        return dict(recorded) if isinstance(recorded, dict) else {}
