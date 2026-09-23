"""Where "does this tool write?" is kept, and how it is answered.

The judgement is a property of the tool, so it lives on the ``mcp_server``
resource that serves it — ``config["tool_write_class"]``, keyed by the server's
own unprefixed tool name. There is no table and no second store.

This module is the adapter side of ``application.workflow.ports.ToolClassPort``.
It satisfies that Protocol structurally and does **not** import it: the import
fence forbids ``application.mcp`` from reaching into ``application.workflow``,
and a Protocol is exactly what makes that possible — the workflow gate types its
dependency, the composition root passes this class, and neither package names
the other. (Which is also why the parameter here is spelled ``server_name``
while the Protocol still says ``server``: structural matching does not hold the
two spellings together, and this side is the one that knows which it has.)

**The server argument is a NAME, not a uid**, and this is the one corner of the
gateway's neighbourhood where that is the honest answer rather than a leftover
from the old model. Both callers derive it by splitting a prefixed tool name —
the gate from the ``tools/call`` an agent just sent, the approval service from
the ``tool_name`` stored on the approval row — and that prefix is built by
``prefix_tool`` out of ``server_name`` (``application.mcp.discovery``), because
the prefix is what an agent reads in ``tools/list`` and types back. A uid is
unreadable by construction; making a model spell one in every tool call would
buy nothing. So a name arrives, and the resolution to a row happens here, at the
boundary, with the row's ``uid`` used for the write.

Keeping the judgements *inside* the resolved row's config is what makes a name
key safe under the uid model: rename an ``mcp_server`` and its recorded
judgements travel with it, because they were never in a table keyed on the old
name. The one thing a name key cannot tell apart is a server deleted and
re-registered under the same name — and inheriting the old judgements is the
right answer there anyway, since the agent addresses those tools by exactly that
name either way.
"""

from __future__ import annotations

from typing import Any

from coffer.application.resource_service import ResourceService
from coffer.domain.resource import Resource

#: The config key the map lives under, in one place so the reader, the writer
#: and the Pydantic field cannot drift apart.
TOOL_WRITE_CLASS_KEY = "tool_write_class"


class ResourceToolClassifier:
    """Read and write an ``mcp_server``'s ``tool_write_class`` map."""

    def __init__(self, resources: ResourceService, *, actor: str = "workflow") -> None:
        self._resources = resources
        self._actor = actor

    async def classify(self, server_name: str, tool: str) -> str | None:
        """This tool's recorded judgement, or ``None`` when nothing judged it.

        ``None`` is also the answer for a name no server answers to. Both cases
        mean the same thing to the gate — nobody has said this call is safe —
        and the gate treats "nobody has said" as write-class (spec workflow
        "Treat an unjudged tool as write-class and remember the answer"), which
        is the direction an error should fall.
        """
        recorded = await self._read_map(server_name)
        value = recorded.get(tool)
        return str(value) if isinstance(value, str) else None

    async def remember(self, server_name: str, tool: str, write_class: str) -> None:
        """Record the developer's answer so the same tool is asked about once.

        The write is addressed by the resolved row's ``uid``, which is the only
        identity ``update_config`` accepts and the only one that still points at
        the right row if a rename lands between the resolution and the write.

        The whole config is rewritten because that is the only write the
        resource layer offers; the map is merged rather than replaced, so an
        answer about one tool never erases an answer about another. A write for
        an unregistered server is dropped rather than raised: the server may
        have been deleted between the question and the answer, and failing the
        developer's decision over it would be the wrong end to break.
        """
        resource = await self._resolve(server_name)
        if resource is None:
            return
        config: dict[str, Any] = dict(resource.config)
        current = config.get(TOOL_WRITE_CLASS_KEY)
        merged: dict[str, Any] = dict(current) if isinstance(current, dict) else {}
        merged[tool] = write_class
        config[TOOL_WRITE_CLASS_KEY] = merged
        await self._resources.update_config(resource.uid, config, actor=self._actor)

    async def _read_map(self, server_name: str) -> dict[str, Any]:
        resource = await self._resolve(server_name)
        if resource is None:
            return {}
        recorded = resource.config.get(TOOL_WRITE_CLASS_KEY)
        return dict(recorded) if isinstance(recorded, dict) else {}

    async def _resolve(self, server_name: str) -> Resource | None:
        """The row a gateway prefix names, or ``None`` if nothing answers to it.

        ``find_by_name`` rather than ``get_by_name`` because "no such server" is
        an ordinary answer on both paths above — the reader falls back to
        write-class, the writer drops the judgement — and neither wants to catch
        ``ResourceNotFound`` to say so.
        """
        return await self._resources.find_by_name("mcp_server", server_name)
