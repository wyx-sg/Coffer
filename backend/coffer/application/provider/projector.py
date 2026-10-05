"""Native-config projection orchestration for ``ProviderService`` (spec provider-switching).

Extracted from the service so each file stays within its size budget. A
``ProviderProjector`` reads an agent's native config file, asks the agent's
provider projection facet (ADR agent-mechanisms-are-optional-facets-on-the-
descriptor) for a plan, and performs its writes through the atomic store. The
translation is the AGENT's — not the connection's ``protocol`` — so an
openai-compatible endpoint routed to Claude Code writes Claude's
``settings.json`` (anthropic shape), and vice versa. An agent whose projection
has no provider entry receives nothing.

A plan may carry files beside the main one (Codex's model catalogue): those it
writes are written BEFORE the main file points at them, and those it removes
are removed AFTER the pointer is gone, so the agent never reads a pointer to a
file that is not there.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol as _Protocol

from coffer.application.provider.cli_path import default_coffer_cli_resolver
from coffer.application.provider.projection_request import (
    binding_of,
    projected_models,
    projection_request,
)
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.facets import AgentCatalog
from coffer.domain.agent.types import AgentType
from coffer.domain.model_proxy.state import DEFAULT_PROXY_PORT
from coffer.domain.model_proxy.state import proxy_root as proxy_root_at
from coffer.domain.provider.agent_projection import (
    ProjectionPlan,
    ProviderProjection,
    ProviderProjectionRequest,
)
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.resource import Resource
from coffer.domain.usage.records import Wire

#: The content each file a projection wrote or removed held before it
#: (``None``: the file did not exist) — what an undo puts back.
Priors = dict[pathlib.Path, str | None]


@dataclass(frozen=True)
class PlannedFile:
    """One file a projection WOULD change, before anything is written: what it
    holds now (``None``: absent), what it would hold (``None``: removed), and
    the fingerprint of the content read — what a later write is checked against."""

    path: pathlib.Path
    before: str | None
    after: str | None
    fingerprint: str


@dataclass(frozen=True)
class NativeModel:
    """A request to set the agent's OWN top-level ``model`` while taking Coffer's
    projection out: ``name`` is the model, ``None`` removes the key (the agent's
    built-in default)."""

    name: str | None


class ProjectionConfigStore(_Protocol):
    def read_text(self, path: pathlib.Path) -> str | None: ...
    def write_text_atomic(
        self, path: pathlib.Path, text: str, *, expected_fingerprint: str | None = None
    ) -> None: ...
    def fingerprint(self, text: str | None) -> str: ...
    # Needed only for the Codex model catalogue: de-projection must REMOVE the
    # file, not blank it, or Codex keeps reading a catalogue that no longer
    # describes anything. ``delete_with_backup`` already existed on the store for
    # agent config files, so the projector's narrow view of it just widened by one
    # method — no new infrastructure.
    def delete_with_backup(self, path: pathlib.Path) -> bool: ...


class ProviderProjector:
    """Projects / de-projects a connection into agents' native config files."""

    def __init__(
        self,
        config_store: ProjectionConfigStore,
        *,
        agents: AgentCatalog,
        cli_resolver: Callable[[], str] = default_coffer_cli_resolver,
        proxy_root: Callable[[], str] = lambda: proxy_root_at(DEFAULT_PROXY_PORT),
    ) -> None:
        self._config_store = config_store
        self._catalog = agents
        # Where the ``coffer`` CLI is, for the ``apiKeyHelper`` line: asked at
        # each projection, so a CLI installed after the daemon started is found.
        self._resolve_cli = cli_resolver
        # Where the local model proxy listens — asked at each projection, so a
        # port the user moved in daemon-config.json is what gets written.
        self._proxy_root = proxy_root

    @staticmethod
    def agents_of_type(agents: list[Resource], agent_type: AgentType) -> list[Resource]:
        """The agents of a given type among ``agents``."""
        return [a for a in agents if AgentConfig.model_validate(a.config).type == agent_type]

    def projection_for(self, agent_type: AgentType) -> ProviderProjection | None:
        """The agent type's provider projection facet, or ``None`` when it
        cannot be put on a connection."""
        return self._catalog.provider_projection(agent_type)

    def project_type(
        self,
        connection: Resource,
        cfg: ProviderConfig,
        agents: list[Resource],
        agent_type: AgentType,
        priors: Priors | None = None,
    ) -> list[str]:
        """Project ``connection`` into every enabled agent of ``agent_type``;
        return the projected agent names (empty if the type is unprojectable or no
        such agent is registered). Each file written is recorded into ``priors``
        as it is written, so a caller whose later step fails can :meth:`restore`
        what this one already did.

        The whole resource rather than its name, because the projection needs
        both halves of it and they are no longer the same thing: its UID is what
        the ``apiKeyHelper`` resolves, its NAME is only what a human reads in
        Codex's provider label.
        """
        facet = self.projection_for(agent_type)
        if facet is None:
            return []
        projected: list[str] = []
        for agent in self.agents_of_type(agents, agent_type):
            self._project(connection, cfg, agent, facet, priors)
            projected.append(agent.name)
        return projected

    def deproject_type(
        self,
        agents: list[Resource],
        agent_type: AgentType,
        priors: Priors | None = None,
        native_model: NativeModel | None = None,
    ) -> list[str]:
        """Remove Coffer's projection from every enabled agent of ``agent_type``
        so it falls back to its own built-in login; return the reverted names.
        ``priors`` collects what each file held before, as in :meth:`project_type`.
        ``native_model`` also sets (or clears) the agent's own ``model`` key, in
        the same write."""
        facet = self.projection_for(agent_type)
        if facet is None:
            return []
        reverted: list[str] = []
        for agent in self.agents_of_type(agents, agent_type):
            self._deproject(agent, facet, priors, native_model)
            reverted.append(agent.name)
        return reverted

    def request_for(
        self, connection: Resource, cfg: ProviderConfig, agent: Resource
    ) -> ProviderProjectionRequest:
        """What a projection of ``connection`` into this agent is built from."""
        agent_cfg = AgentConfig.model_validate(agent.config)
        facet = self.projection_for(agent_cfg.type)
        wire = Wire(facet.protocols[0]) if facet is not None and facet.protocols else Wire.ANTHROPIC
        return projection_request(
            connection,
            cfg,
            agent,
            agent_cfg,
            coffer_cli=self._resolve_cli(),
            proxy_root=self._proxy_root(),
            wire=wire,
        )

    def plan_project(
        self, connection: Resource, cfg: ProviderConfig, agent: Resource
    ) -> list[PlannedFile]:
        """The files projecting ``connection`` into ``agent`` would change, in
        the order they would be written; nothing is written."""
        facet = self.projection_for(AgentConfig.model_validate(agent.config).type)
        if facet is None:
            return []
        agent_cfg = AgentConfig.model_validate(agent.config)
        spec = spec_for(agent_cfg.type, facet.config_key, agent_cfg.resolved_config_dir())
        current = self._config_store.read_text(spec.path)
        request = self.request_for(connection, cfg, agent)
        return self._planned(spec.path, current, facet.apply(current or "", request, spec.path))

    def plan_deproject(
        self, agent: Resource, native_model: NativeModel | None = None
    ) -> list[PlannedFile]:
        """The files taking Coffer's projection out of ``agent`` would change
        (and, given ``native_model``, setting its own ``model`` key)."""
        agent_cfg = AgentConfig.model_validate(agent.config)
        facet = self.projection_for(agent_cfg.type)
        if facet is None:
            return []
        spec = spec_for(agent_cfg.type, facet.config_key, agent_cfg.resolved_config_dir())
        current = self._config_store.read_text(spec.path)
        plan = self._deprojection(facet, current or "", spec.path, agent_cfg, native_model)
        if plan is None:
            return []
        return self._planned(spec.path, current, plan)

    @staticmethod
    def _deprojection(
        facet: ProviderProjection,
        text: str,
        path: pathlib.Path,
        agent_cfg: AgentConfig,
        native_model: NativeModel | None,
    ) -> ProjectionPlan | None:
        """What leaving the connection (and naming the agent's own model) writes
        to the main file; ``None`` when there is nothing to do."""
        if text.strip():
            plan = facet.remove(text, path, binding_of(agent_cfg))
        elif native_model is None:
            return None  # nothing was ever projected
        else:
            plan = ProjectionPlan("")
        if native_model is None:
            return plan
        return replace(plan, text=facet.set_native_model(plan.text, native_model.name))

    def current_fingerprint(self, path: pathlib.Path) -> str:
        """The fingerprint of what ``path`` holds now."""
        return self._config_store.fingerprint(self._config_store.read_text(path))

    def _planned(
        self, path: pathlib.Path, current: str | None, plan: ProjectionPlan
    ) -> list[PlannedFile]:
        planned: list[PlannedFile] = []

        def add(where: pathlib.Path, before: str | None, after: str | None) -> None:
            if after is None and before is None:
                return
            if after is not None and after == (before or ""):
                return
            planned.append(
                PlannedFile(where, before, after, self._config_store.fingerprint(before))
            )

        for side in plan.before:
            if side.text is not None:
                add(side.path, self._config_store.read_text(side.path), side.text)
        add(path, current, plan.text)
        for side in plan.after:
            add(side.path, self._config_store.read_text(side.path), side.text)
        return planned

    def restore(self, priors: Priors) -> None:
        """Put every file in ``priors`` back as it was (delete one that did not
        exist) — the undo of a switch that failed part-way. Best effort per
        file: one that cannot be restored does not stop the others."""
        for path, before in priors.items():
            try:
                if before is None:
                    self._config_store.delete_with_backup(path)
                else:
                    self._config_store.write_text_atomic(path, before)
            except Exception:
                continue

    def project_agent(self, connection: Resource, cfg: ProviderConfig, agent: Resource) -> Priors:
        """Project ``connection`` into one agent; return the prior content of
        every file written or removed (``None`` for one that did not exist)."""
        facet = self.projection_for(AgentConfig.model_validate(agent.config).type)
        if facet is None:
            return {}
        return self._project(connection, cfg, agent, facet)

    def deproject_agent(self, agent: Resource) -> Priors:
        """Remove Coffer's projection from one agent; return the prior content
        of every file written or removed."""
        facet = self.projection_for(AgentConfig.model_validate(agent.config).type)
        if facet is None:
            return {}
        return self._deproject(agent, facet)

    # --- internals -----------------------------------------------------------

    def _project(
        self,
        connection: Resource,
        cfg: ProviderConfig,
        agent: Resource,
        facet: ProviderProjection,
        priors: Priors | None = None,
    ) -> Priors:
        agent_cfg = AgentConfig.model_validate(agent.config)
        spec = spec_for(agent_cfg.type, facet.config_key, agent_cfg.resolved_config_dir())
        current = self._config_store.read_text(spec.path)
        request = self.request_for(connection, cfg, agent)
        return self._perform(
            spec.path, current, facet.apply(current or "", request, spec.path), priors
        )

    def _deproject(
        self,
        agent: Resource,
        facet: ProviderProjection,
        priors: Priors | None = None,
        native_model: NativeModel | None = None,
    ) -> Priors:
        agent_cfg = AgentConfig.model_validate(agent.config)
        spec = spec_for(agent_cfg.type, facet.config_key, agent_cfg.resolved_config_dir())
        current = self._config_store.read_text(spec.path)
        plan = self._deprojection(facet, current or "", spec.path, agent_cfg, native_model)
        if plan is None:
            return {}
        return self._perform(spec.path, current, plan, priors)

    def _perform(
        self,
        path: pathlib.Path,
        current: str | None,
        plan: ProjectionPlan,
        priors: Priors | None = None,
    ) -> Priors:
        """Run the plan's writes in order, recording each file's prior content
        into ``priors`` (the caller's accumulator when given) as it is written."""
        priors = {} if priors is None else priors
        for side in plan.before:
            if side.text is not None:
                self._write_if_changed(
                    side.path, self._config_store.read_text(side.path), side.text, priors
                )
        self._write_if_changed(path, current, plan.text, priors)
        for side in plan.after:
            if side.text is None:
                before = self._config_store.read_text(side.path)
                if self._config_store.delete_with_backup(side.path):
                    priors.setdefault(side.path, before)
            else:
                self._write_if_changed(
                    side.path, self._config_store.read_text(side.path), side.text, priors
                )
        return priors

    def _write_if_changed(
        self, path: pathlib.Path, current: str | None, new: str, priors: Priors
    ) -> None:
        """Write only a real change, and only over the content that was read.

        The reconciler re-derives the projection, and touching
        an agent's config file when nothing differs would churn its mtime — and
        hide, in any file audit, the one case that matters: a projection that
        had actually gone missing.

        ``current`` is what :meth:`read_text` returned (``None`` for an absent
        file); its fingerprint travels with the write so the store refuses
        (``ConfigFileStale``, a 409) if the user's editor changed the file in
        between — this is THEIR settings file, and a projection that overwrote
        an edit they had just saved would lose it silently.
        """
        if new != (current or ""):
            self._config_store.write_text_atomic(
                path, new, expected_fingerprint=self._config_store.fingerprint(current)
            )
            priors.setdefault(path, current)


__all__ = [
    "NativeModel",
    "PlannedFile",
    "Priors",
    "ProjectionConfigStore",
    "ProviderProjector",
    "binding_of",
    "projected_models",
    "projection_request",
]
