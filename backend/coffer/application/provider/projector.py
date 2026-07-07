"""Native-config projection orchestration for ``ProviderService`` (spec 011).

Extracted from the service so each file stays within its size budget. A
``ProviderProjector`` reads an agent's native config file, applies one of the
pure projection transforms, and writes it back through the atomic store. The
projection WRITER is chosen by the AGENT type the connection projects into — not
by the connection's ``protocol`` — so an openai-compatible endpoint routed to
Claude Code writes Claude's ``settings.json`` (anthropic shape), and vice versa.
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
    apply_hermes_provider,
    apply_opencode_provider,
    remove_anthropic_settings,
    remove_codex_provider,
    remove_hermes_provider,
    remove_opencode_provider,
    target_for_agent,
)
from coffer.domain.resource import Resource


class _ConfigFileStore(_Protocol):
    def read_text(self, path: pathlib.Path) -> str | None: ...
    def write_text_atomic(self, path: pathlib.Path, text: str) -> None: ...


class ProviderProjector:
    """Projects / de-projects a connection into agents' native config files."""

    def __init__(self, config_store: _ConfigFileStore) -> None:
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
        # Model comes solely from the per-agent binding (spec 011 E3/E4) — the
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
        elif agent_type is AgentType.OPENCODE:
            # opencode reads the key from COFFER_PROVIDER_KEY (injected into the
            # subprocess env at spawn time, same seam as Codex) via the
            # `{env:...}` reference in its provider block.
            new_text = apply_opencode_provider(
                text,
                base_url=cfg.base_url,
                model=agent_cfg.model,
            )
        elif agent_type is AgentType.HERMES:
            # Hermes reads the key from COFFER_PROVIDER_KEY too (config.yaml
            # providers.coffer.key_env), injected into the subprocess env.
            new_text = apply_hermes_provider(
                text,
                base_url=cfg.base_url,
                model=agent_cfg.model,
            )
        else:
            new_text = apply_codex_provider(
                text,
                base_url=cfg.base_url,
                model=agent_cfg.model,
                wire_api=agent_cfg.wire_api or "responses",
                display_name=f"Coffer ({name})",
            )
        self._config_store.write_text_atomic(spec.path, new_text)

    def _deproject(self, agent: Resource, config_key: str, agent_type: AgentType) -> None:
        agent_cfg = AgentConfig.model_validate(agent.config)
        spec = spec_for(agent_cfg.type, config_key, agent_cfg.resolved_config_dir())
        text = self._config_store.read_text(spec.path) or ""
        if not text.strip():
            return  # nothing was ever projected
        if agent_type is AgentType.CLAUDE_CODE:
            new_text = remove_anthropic_settings(text)
        elif agent_type is AgentType.OPENCODE:
            new_text = remove_opencode_provider(text)
        elif agent_type is AgentType.HERMES:
            new_text = remove_hermes_provider(text)
        else:
            new_text = remove_codex_provider(text)
        self._config_store.write_text_atomic(spec.path, new_text)


__all__ = ["ProviderProjector"]
