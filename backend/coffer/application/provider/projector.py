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
from typing import Protocol as _Protocol

from coffer.application.provider.cli_path import default_coffer_cli_resolver
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.facets import AgentCatalog
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.agent_projection import (
    ProjectionPlan,
    ProviderProjection,
    ProviderProjectionRequest,
)
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.provider.modality import Modality
from coffer.domain.resource import Resource


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
    ) -> None:
        self._config_store = config_store
        self._catalog = agents
        # Where the ``coffer`` CLI is, for the ``apiKeyHelper`` line: asked at
        # each projection, so a CLI installed after the daemon started is found.
        self._resolve_cli = cli_resolver

    @staticmethod
    def agents_of_type(agents: list[Resource], agent_type: AgentType) -> list[Resource]:
        """The enabled agents of a given type among ``agents``."""
        return [
            a
            for a in agents
            if a.enabled and AgentConfig.model_validate(a.config).type == agent_type
        ]

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
    ) -> list[str]:
        """Project ``connection`` into every enabled agent of ``agent_type``;
        return the projected agent names (empty if the type is unprojectable or no
        such agent is registered).

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
            self._project(connection, cfg, agent, facet)
            projected.append(agent.name)
        return projected

    def deproject_type(self, agents: list[Resource], agent_type: AgentType) -> list[str]:
        """Remove Coffer's projection from every enabled agent of ``agent_type``
        so it falls back to its own built-in login; return the reverted names."""
        facet = self.projection_for(agent_type)
        if facet is None:
            return []
        reverted: list[str] = []
        for agent in self.agents_of_type(agents, agent_type):
            self._deproject(agent, facet)
            reverted.append(agent.name)
        return reverted

    # --- internals -----------------------------------------------------------

    def _project(
        self,
        connection: Resource,
        cfg: ProviderConfig,
        agent: Resource,
        facet: ProviderProjection,
    ) -> None:
        agent_cfg = AgentConfig.model_validate(agent.config)
        spec = spec_for(agent_cfg.type, facet.config_key, agent_cfg.resolved_config_dir())
        current = self._config_store.read_text(spec.path)
        request = ProviderProjectionRequest(
            connection_uid=connection.uid,
            connection_name=connection.name,
            base_url=cfg.base_url,
            # Model comes solely from the per-agent binding (spec
            # provider-switching "Take projected model keys from the agent's
            # binding"); an unbound agent projects no model.
            model=agent_cfg.model,
            fast_model=agent_cfg.fast_model,
            wire_api=agent_cfg.wire_api,
            # Only the `text` entries: a model catalogue is the agent's own
            # picker (spec provider-switching "Offer only text models to chat
            # pickers").
            text_models=tuple(cfg.model_ids(Modality.TEXT)),
            coffer_cli=self._resolve_cli(),
        )
        self._perform(spec.path, current, facet.apply(current or "", request, spec.path))

    def _deproject(self, agent: Resource, facet: ProviderProjection) -> None:
        agent_cfg = AgentConfig.model_validate(agent.config)
        spec = spec_for(agent_cfg.type, facet.config_key, agent_cfg.resolved_config_dir())
        current = self._config_store.read_text(spec.path)
        text = current or ""
        if not text.strip():
            return  # nothing was ever projected
        self._perform(spec.path, current, facet.remove(text, spec.path))

    def _perform(self, path: pathlib.Path, current: str | None, plan: ProjectionPlan) -> None:
        for side in plan.before:
            if side.text is not None:
                self._write_if_changed(
                    side.path, self._config_store.read_text(side.path), side.text
                )
        self._write_if_changed(path, current, plan.text)
        for side in plan.after:
            if side.text is None:
                self._config_store.delete_with_backup(side.path)
            else:
                self._write_if_changed(
                    side.path, self._config_store.read_text(side.path), side.text
                )

    def _write_if_changed(self, path: pathlib.Path, current: str | None, new: str) -> None:
        """Write only a real change, and only over the content that was read.

        The sync post-import reconcile re-derives the projection, and touching
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


__all__ = ["ProjectionConfigStore", "ProviderProjector"]
