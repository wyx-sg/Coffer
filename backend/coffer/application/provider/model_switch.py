"""Review, then apply, a change of one agent's model (spec provider-switching).

The agent page's "Change model" dialog asks for a connection (or the built-in
login), a model and Claude Code's tier pins. Nothing is written
until the user has seen the files that change: :func:`preview` computes them without
touching disk and hands back, per file, what it holds now and what it would hold, with a
fingerprint of what was read. :func:`apply` refuses (``ConfigFileStale``, a 409)
when any of those files changed on disk after the preview was made, then does
what :func:`switch_ops.activate` / :func:`switch_ops.deactivate` do — project,
then record the binding and the connection — so the preview and the write cannot
disagree about the lines.

The model binding is the agent's own record (``AgentConfig.model`` and friends);
the projection is built from a copy of the agent that already carries the
requested binding, so the record is written only after the file write succeeded.
"""

from __future__ import annotations

import dataclasses
import pathlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from coffer.application.provider import switch_ops
from coffer.application.provider.projector import NativeModel, PlannedFile
from coffer.application.provider.switch_ops import activate_checks, agent_of_type
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType
from coffer.domain.errors import ResourceNotFound
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.resource import Resource
from coffer.domain.workspace_errors import ConfigFileStale

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService


class BindingWriter(Protocol):
    """The agent kind's one write a model switch needs beside the connection."""

    async def set_model_binding(
        self,
        *,
        uid: str,
        model: str | None = None,
        tier_models: dict[str, str] | None = None,
        clear_tiers: bool = False,
        clear_model: bool = False,
        actor: str = "api",
    ) -> Resource: ...


@dataclass(frozen=True)
class ModelSwitch:
    """What the dialog asks for. ``connection_uid`` ``None`` is the agent's own
    built-in login, which carries no Coffer binding or tiers: there the model
    is the agent's own top-level ``model`` key, written with ``native_model``
    (set it) or ``clear_native_model`` (remove it: the agent's built-in
    default); neither leaves it as it is."""

    agent_type: AgentType
    connection_uid: str | None = None
    model: str | None = None
    tier_models: Mapping[str, str] | None = None
    native_model: str | None = None
    clear_native_model: bool = False

    @property
    def native(self) -> NativeModel | None:
        """The change to the agent's own ``model`` key, if one is asked for."""
        if self.connection_uid is not None:
            return None
        if self.native_model is not None:
            return NativeModel(self.native_model)
        return NativeModel(None) if self.clear_native_model else None


@dataclass(frozen=True)
class SwitchPreview:
    agent_uid: str
    agent_name: str
    #: The connection the agent would run on; ``None``: its built-in login.
    connection_name: str | None
    files: list[PlannedFile]


def _with_binding(agent: Resource, switch: ModelSwitch) -> Resource:
    """The agent as it will be once the switch is recorded."""
    cfg = AgentConfig.model_validate(agent.config)
    overrides: dict[str, object] = {
        "model": switch.model,
        "tier_models": dict(switch.tier_models) if switch.tier_models else None,
    }
    new = AgentConfig.model_validate(cfg.model_dump() | overrides)
    return dataclasses.replace(agent, config=new.model_dump(mode="json"))


async def _plan(
    service: ProviderService, switch: ModelSwitch
) -> tuple[Resource, Resource | None, ProviderConfig | None, list[PlannedFile]]:
    agent = agent_of_type(await service._agents.list(), switch.agent_type)
    if agent is None:
        raise ResourceNotFound(switch.agent_type.default_name())
    if switch.connection_uid is None:
        return agent, None, None, service._projector.plan_deproject(agent, switch.native)
    resource = await service.get(switch.connection_uid)
    cfg = service._cfg(resource)
    await activate_checks(service, resource, cfg, agent, switch.agent_type)
    planned = service._projector.plan_project(resource, cfg, _with_binding(agent, switch))
    return agent, resource, cfg, planned


async def preview(service: ProviderService, switch: ModelSwitch) -> SwitchPreview:
    """The files the switch would change; nothing is written."""
    agent, resource, _cfg, planned = await _plan(service, switch)
    return SwitchPreview(
        agent_uid=agent.uid,
        agent_name=agent.name,
        connection_name=resource.name if resource is not None else None,
        files=planned,
    )


async def apply(
    service: ProviderService,
    agents: BindingWriter,
    switch: ModelSwitch,
    seen: Mapping[str, str],
    *,
    actor: str,
) -> SwitchPreview:
    """Write what :func:`preview` showed. ``seen`` maps each previewed file's
    path to the fingerprint the preview read; one that no longer matches the
    file on disk refuses the whole switch before anything is written."""
    async with service._hold():
        agent, resource, _cfg, planned = await _plan(service, switch)
        for path, was in seen.items():
            if service._projector.current_fingerprint(pathlib.Path(path)) != was:
                raise ConfigFileStale(path)
        if resource is None:
            await switch_ops.deactivate(
                service, switch.agent_type, actor=actor, native_model=switch.native
            )
            # The binding is a Coffer connection's; the built-in login has none.
            # Cleared after the file write, whose ``remove`` reads it to know
            # which model Coffer wrote.
            await agents.set_model_binding(
                uid=agent.uid, clear_model=True, clear_tiers=True, actor=actor
            )
        else:
            await _activate(service, agents, agent, resource, switch, actor=actor)
    return SwitchPreview(
        agent_uid=agent.uid,
        agent_name=agent.name,
        connection_name=resource.name if resource is not None else None,
        files=planned,
    )


async def _activate(
    service: ProviderService,
    agents: BindingWriter,
    agent: Resource,
    resource: Resource,
    switch: ModelSwitch,
    *,
    actor: str,
) -> None:
    """Record the binding, then project it (``activate`` reads the binding from
    the agent's record); the binding goes back as it was if the projection fails."""
    before = AgentConfig.model_validate(agent.config)
    await agents.set_model_binding(
        uid=agent.uid,
        model=switch.model,
        tier_models=dict(switch.tier_models) if switch.tier_models else None,
        clear_tiers=not switch.tier_models,
        actor=actor,
    )
    try:
        await switch_ops.activate(service, resource.uid, switch.agent_type, actor=actor)
    except Exception:
        await agents.set_model_binding(
            uid=agent.uid,
            model=before.model,
            tier_models=before.tier_models,
            clear_tiers=not before.tier_models,
            actor=actor,
        )
        raise


__all__ = ["BindingWriter", "ModelSwitch", "SwitchPreview", "apply", "preview"]
