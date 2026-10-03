"""Deleting a connection that agents run on (spec provider-switching).

A delete is not only a row removal: every agent whose record names the
connection carries Coffer's projection in its native config file, and leaving
that behind would point the agent at a proxy route with nothing behind it. So
the delete first puts each such agent back on its built-in login (the same
de-projection ``deactivate`` performs, audited the same way), and only then
removes the row. A de-projection that is refused (a file edited on disk) aborts
the delete with the row still there.

``preview`` is the read-only twin: the files that de-projection would change,
with their diffs, so the person sees what Delete will do before choosing it.

Lives here because ``provider/service.py`` is at its file-size ceiling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.application.provider.line_diff import DiffRow, line_diff
from coffer.application.provider.results import (
    DeletePreview,
    DeletePreviewAgent,
    DeletePreviewFile,
)
from coffer.application.provider.switch_ops import deactivate
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService


async def _agents_on(service: ProviderService, uid: str) -> list[tuple[Resource, AgentConfig]]:
    """The agents whose record names connection ``uid`` (enabled or not)."""
    on: list[tuple[Resource, AgentConfig]] = []
    for agent in await service._agents.list():
        try:
            cfg = AgentConfig.model_validate(agent.config)
        except ValueError:
            continue
        if cfg.connection_uid == uid:
            on.append((agent, cfg))
    return on


async def delete(service: ProviderService, uid: str, *, actor: str) -> None:
    """De-project every agent on ``uid``, then delete the connection."""
    resource = await service.get(uid)  # 404 (and the kind check) before anything is touched
    cfg = service._cfg(resource)
    # ``hold`` is re-entrant, so each ``deactivate`` inside it holds nothing more.
    async with service._hold():
        types: list[AgentType] = []
        for _agent, agent_cfg in await _agents_on(service, uid):
            if agent_cfg.type not in types:
                types.append(agent_cfg.type)
        for agent_type in types:
            await deactivate(service, agent_type, actor=actor)
        await service._resources.delete(uid, actor)
        if service._engine is not None:
            # The flag leaves with the row; the model chosen for it would
            # otherwise dangle against whatever connection is set next.
            if cfg.internal_default:
                await service._engine.drop_model_unless_curated(set(), actor=actor)
            if cfg.transcribe_default:
                await service._engine.drop_transcribe_model_unless_curated(set(), actor=actor)


def _rows(before: str | None, after: str | None) -> list[DiffRow]:
    return line_diff(before, after)


async def preview(service: ProviderService, uid: str) -> DeletePreview:
    """What deleting ``uid`` would change in agents' config files; writes nothing."""
    await service.get(uid)
    agents: list[DeletePreviewAgent] = []
    for agent, cfg in await _agents_on(service, uid):
        files: list[DeletePreviewFile] = []
        # A disabled agent's file is never touched by a de-projection.
        planned = service._projector.plan_deproject(agent) if agent.enabled else []
        for p in planned:
            files.append(
                DeletePreviewFile(
                    path=str(p.path),
                    op="remove" if p.after is None else "modify",
                    diff=_rows(p.before, p.after),
                )
            )
        if files:
            agents.append(
                DeletePreviewAgent(
                    agent_uid=agent.uid,
                    agent_type=cfg.type.value,
                    agent_name=agent.name,
                    files=files,
                )
            )
    return DeletePreview(agents=agents)


__all__ = ["delete", "preview"]
