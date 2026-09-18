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
from coffer.domain.provider.modality import Modality
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
        target = target_for_agent(agent_type)
        if target is None:
            return []
        projected: list[str] = []
        for agent in self.agents_of_type(agents, agent_type):
            self._project(connection, cfg, agent, target.config_key, agent_type)
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
        connection: Resource,
        cfg: ProviderConfig,
        agent: Resource,
        config_key: str,
        agent_type: AgentType,
    ) -> None:
        agent_cfg = AgentConfig.model_validate(agent.config)
        spec = spec_for(agent_cfg.type, config_key, agent_cfg.resolved_config_dir())
        current = self._config_store.read_text(spec.path)
        text = current or ""
        # Model comes solely from the per-agent binding (spec provider-switching E3/E4) — the
        # connection no longer carries one. An unbound agent projects no model so
        # it runs on its OWN default model.
        if agent_type is AgentType.CLAUDE_CODE:
            # apiKeyHelper names THIS connection by uid, so the projected agent
            # always reads exactly its key regardless of wire (the agnes case)
            # — and goes on reading it after the connection is renamed, which is
            # why a rename no longer re-projects anything.
            new_text = apply_anthropic_settings(
                text,
                base_url=cfg.base_url,
                model=agent_cfg.model,
                fast_model=agent_cfg.fast_model,
                api_key_helper=anthropic_api_key_helper(connection.uid),
            )
            self._write_if_changed(spec.path, current, new_text)
            return

        # Codex additionally gets a model catalogue so its OWN picker lists the
        # endpoint's models. The catalogue file is written BEFORE config.toml
        # points at it (and, below, the pointer is dropped before the file is
        # deleted) so Codex never reads a `model_catalog_json` path that is not
        # there. `None` ⇒ the connection curates no models; see
        # `codex_model_catalog_json` for why guessing one is not allowed.
        # Only the `text` entries: this catalogue IS Codex's model picker, and an
        # embedding or image model offered there could only be rejected by the
        # turn that picked it (spec provider-switching FR-032).
        catalog_path = codex_model_catalog_path(spec.path.parent)
        catalog = codex_model_catalog_json(cfg.model_ids(Modality.TEXT))
        if catalog is not None:
            self._write_if_changed(
                catalog_path, self._config_store.read_text(catalog_path), catalog
            )
        new_text = apply_codex_provider(
            text,
            base_url=cfg.base_url,
            model=agent_cfg.model,
            wire_api=agent_cfg.wire_api or "responses",
            # DELIBERATELY the name, not the uid. This is the label Codex shows
            # in its own provider picker, so it has to be the word the user
            # chose; "Coffer (a3f1…)" would be unreadable. Nothing resolves it —
            # Coffer's ownership of the block is the ``coffer`` provider id, and
            # the key comes from ``env_key`` — so a rename leaves this line
            # cosmetically stale until the next projection rewrites it, and
            # nothing breaks in the meantime. That is the whole reason a rename
            # needs no re-projection: the only OTHER place a connection's name
            # reached into another tool's file was the ``apiKeyHelper``, and
            # that now carries the uid.
            display_name=f"Coffer ({connection.name})",
            catalog_path=catalog_path if catalog is not None else None,
        )
        self._write_if_changed(spec.path, current, new_text)
        if catalog is None:
            # The curated set was cleared since the last projection: the pointer
            # is already gone from config.toml, so retire the file too rather than
            # leave a catalogue nothing describes.
            self._config_store.delete_with_backup(catalog_path)

    def _deproject(self, agent: Resource, config_key: str, agent_type: AgentType) -> None:
        agent_cfg = AgentConfig.model_validate(agent.config)
        spec = spec_for(agent_cfg.type, config_key, agent_cfg.resolved_config_dir())
        current = self._config_store.read_text(spec.path)
        text = current or ""
        if not text.strip():
            return  # nothing was ever projected
        if agent_type is AgentType.CLAUDE_CODE:
            new_text = remove_anthropic_settings(text)
            self._write_if_changed(spec.path, current, new_text)
            return
        new_text = remove_codex_provider(text)
        self._write_if_changed(spec.path, current, new_text)
        # `remove_codex_provider` has dropped the pointer (iff it was ours), so the
        # file is now unreferenced — delete it so Codex's built-in model list is
        # what its picker shows again. Absent is a no-op.
        self._config_store.delete_with_backup(codex_model_catalog_path(spec.path.parent))

    def _write_if_changed(self, path: pathlib.Path, current: str | None, new: str) -> None:
        """Write only a real change, and only over the content that was read.

        The boot sweep re-derives the projection on every start, and touching
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
