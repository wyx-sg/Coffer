"""Native-config projection orchestration for ``ProviderService`` (spec provider-switching).

Extracted from the service so each file stays within its size budget. A
``ProviderProjector`` reads an agent's native config file, applies one of the
pure projection transforms, and writes it back through the atomic store. The
projection WRITER is chosen by the AGENT type the connection projects into — not
by the connection's ``protocol`` — so an openai-compatible endpoint routed to
Claude Code writes Claude's ``settings.json`` (anthropic shape), and vice versa.

A Codex projection is TWO files, not one: ``config.toml`` plus the Coffer-owned
model catalogue it points at via ``model_catalog_json``. The catalogue is the only
thing that makes Codex's own model picker list the endpoint's models instead of
OpenAI's, and it is written/removed here (the document itself is built by the pure
``codex_model_catalog_json``).
"""

from __future__ import annotations

import pathlib
from typing import Protocol as _Protocol

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.provider.projection import (
    anthropic_api_key_helper,
    apply_anthropic_settings,
    apply_codex_provider,
    codex_model_catalog_json,
    codex_model_catalog_path,
    remove_anthropic_settings,
    remove_codex_provider,
    target_for_agent,
)
from coffer.domain.resource import Resource


class ProjectionConfigStore(_Protocol):
    def read_text(self, path: pathlib.Path) -> str | None: ...
    def write_text_atomic(self, path: pathlib.Path, text: str) -> None: ...
    # Needed only for the Codex model catalogue: de-projection must REMOVE the
    # file, not blank it, or Codex keeps reading a catalogue that no longer
    # describes anything. ``delete_with_backup`` already existed on the store for
    # agent config files, so the projector's narrow view of it just widened by one
    # method — no new infrastructure.
    def delete_with_backup(self, path: pathlib.Path) -> bool: ...


class ProviderProjector:
    """Projects / de-projects a connection into agents' native config files."""

    def __init__(self, config_store: ProjectionConfigStore) -> None:
        self._config_store = config_store

    @staticmethod
    def agents_of_type(agents: list[Resource], agent_type: AgentType) -> list[Resource]:
        """The enabled agents of a given type among ``agents``."""
        return [
            a
            for a in agents
            if a.enabled and AgentConfig.model_validate(a.config).type == agent_type
        ]

    def project_type(
        self, name: str, cfg: ProviderConfig, agents: list[Resource], agent_type: AgentType
    ) -> list[str]:
        """Project connection ``name`` into every enabled agent of ``agent_type``;
        return the projected agent names (empty if the type is unprojectable or no
        such agent is registered)."""
        target = target_for_agent(agent_type)
        if target is None:
            return []
        projected: list[str] = []
        for agent in self.agents_of_type(agents, agent_type):
            self._project(name, cfg, agent, target.config_key, agent_type)
            projected.append(agent.name)
        return projected

    def deproject_type(self, agents: list[Resource], agent_type: AgentType) -> list[str]:
        """Remove Coffer's projection from every enabled agent of ``agent_type``
        so it falls back to its own built-in login; return the reverted names."""
        target = target_for_agent(agent_type)
        if target is None:
            return []
        reverted: list[str] = []
        for agent in self.agents_of_type(agents, agent_type):
            self._deproject(agent, target.config_key, agent_type)
            reverted.append(agent.name)
        return reverted

    # --- internals -----------------------------------------------------------

    def _project(
        self,
        name: str,
        cfg: ProviderConfig,
        agent: Resource,
        config_key: str,
        agent_type: AgentType,
    ) -> None:
        agent_cfg = AgentConfig.model_validate(agent.config)
        spec = spec_for(agent_cfg.type, config_key, agent_cfg.resolved_config_dir())
        text = self._config_store.read_text(spec.path) or ""
        # Model comes solely from the per-agent binding (spec provider-switching E3/E4) — the
        # connection no longer carries one. An unbound agent projects no model so
        # it runs on its OWN default model.
        if agent_type is AgentType.CLAUDE_CODE:
            # apiKeyHelper names THIS connection, so the projected agent always
            # reads exactly its key regardless of wire (the agnes case).
            new_text = apply_anthropic_settings(
                text,
                base_url=cfg.base_url,
                model=agent_cfg.model,
                fast_model=agent_cfg.fast_model,
                api_key_helper=anthropic_api_key_helper(name),
            )
            self._write_if_changed(spec.path, text, new_text)
            return

        # Codex additionally gets a model catalogue so its OWN picker lists the
        # endpoint's models. The catalogue file is written BEFORE config.toml
        # points at it (and, below, the pointer is dropped before the file is
        # deleted) so Codex never reads a `model_catalog_json` path that is not
        # there. `None` ⇒ the connection curates no models; see
        # `codex_model_catalog_json` for why guessing one is not allowed.
        catalog_path = codex_model_catalog_path(spec.path.parent)
        catalog = codex_model_catalog_json(cfg.models)
        if catalog is not None:
            self._write_if_changed(
                catalog_path, self._config_store.read_text(catalog_path) or "", catalog
            )
        new_text = apply_codex_provider(
            text,
            base_url=cfg.base_url,
            model=agent_cfg.model,
            wire_api=agent_cfg.wire_api or "responses",
            display_name=f"Coffer ({name})",
            catalog_path=catalog_path if catalog is not None else None,
        )
        self._write_if_changed(spec.path, text, new_text)
        if catalog is None:
            # The curated set was cleared since the last projection: the pointer
            # is already gone from config.toml, so retire the file too rather than
            # leave a catalogue nothing describes.
            self._config_store.delete_with_backup(catalog_path)

    def _deproject(self, agent: Resource, config_key: str, agent_type: AgentType) -> None:
        agent_cfg = AgentConfig.model_validate(agent.config)
        spec = spec_for(agent_cfg.type, config_key, agent_cfg.resolved_config_dir())
        text = self._config_store.read_text(spec.path) or ""
        if not text.strip():
            return  # nothing was ever projected
        if agent_type is AgentType.CLAUDE_CODE:
            new_text = remove_anthropic_settings(text)
            self._write_if_changed(spec.path, text, new_text)
            return
        new_text = remove_codex_provider(text)
        self._write_if_changed(spec.path, text, new_text)
        # `remove_codex_provider` has dropped the pointer (iff it was ours), so the
        # file is now unreferenced — delete it so Codex's built-in model list is
        # what its picker shows again. Absent is a no-op.
        self._config_store.delete_with_backup(codex_model_catalog_path(spec.path.parent))

    def _write_if_changed(self, path: pathlib.Path, current: str, new: str) -> None:
        """Write only a real change. The boot sweep re-derives the projection on
        every start, and touching an agent's config file when nothing differs
        would churn its mtime — and hide, in any file audit, the one case that
        matters: a projection that had actually gone missing."""
        if new != current:
            self._config_store.write_text_atomic(path, new)


__all__ = ["ProjectionConfigStore", "ProviderProjector"]
