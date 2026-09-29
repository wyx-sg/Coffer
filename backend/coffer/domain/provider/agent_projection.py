"""The provider entry of each agent's projection facet (ADR
agent-mechanisms-are-optional-facets-on-the-descriptor).

One :class:`ProviderProjection` per agent that can be put on a connection. It
names the agent it serves, the allowlisted file the projection lands in, the
wire protocols the agent's native config speaks, and the translation: pure
functions from a connection plus the agent's binding to that file's new text.
Which agents a connection reaches is its scope; nothing here maps a protocol
to an agent.

Pure, like the transforms it composes: the application layer reads the file,
asks for a :class:`ProjectionPlan`, and performs its writes in order.
"""

from __future__ import annotations

import json
import pathlib
import tomllib
from dataclasses import dataclass
from typing import Protocol as _Protocol

from coffer.domain.agent.tiers import is_claude_model_id, suggest_tier_models
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.codex_projection import CodexAuthCommand
from coffer.domain.provider.codex_shell_env import CODEX_SHELL_ENV_POLICY_KEY
from coffer.domain.provider.config import Protocol
from coffer.domain.provider.model_binding import ModelBinding, ProjectedModel, find_model
from coffer.domain.provider.projection import (
    apply_anthropic_settings,
    apply_codex_provider,
    codex_model_catalog_json,
    codex_model_catalog_path,
    remove_anthropic_settings,
    remove_codex_provider,
)


@dataclass(frozen=True)
class ProviderProjectionRequest:
    """Everything a translation needs about one connection and one agent."""

    connection_uid: str
    connection_name: str
    agent_uid: str
    #: Where the agent sends its requests: the local model proxy's route for
    #: its wire.
    base_url: str
    #: Claude Code's ``apiKeyHelper`` command line.
    key_helper: str
    #: Codex's provider ``auth`` command; ``None`` falls back to ``env_key``.
    codex_auth: CodexAuthCommand | None
    #: The agent's own binding (spec provider-switching "Take projected model
    #: keys from the agent's binding").
    binding: ModelBinding
    wire_api: str | None
    #: The connection's curated text models, in order, with their facts.
    models: tuple[ProjectedModel, ...] = ()
    #: The connection is a model runtime on this machine.
    local: bool = False
    #: ``base_url`` is the loopback proxy (``NO_PROXY`` must cover it).
    loopback_proxy: bool = False

    @property
    def model_ids(self) -> tuple[str, ...]:
        return tuple(m.id for m in self.models)


@dataclass(frozen=True)
class ProjectedFile:
    """A file beside the main one: ``text`` to write, or ``None`` to delete."""

    path: pathlib.Path
    text: str | None


@dataclass(frozen=True)
class ProjectionPlan:
    """The main file's new text, plus files written before it and files
    removed after it — so the agent never reads a pointer to a file that is
    not there."""

    text: str
    before: tuple[ProjectedFile, ...] = ()
    after: tuple[ProjectedFile, ...] = ()


class ProviderProjection(_Protocol):
    """The provider capability of one agent's projection facet."""

    @property
    def agent_type(self) -> AgentType: ...

    @property
    def config_key(self) -> str:
        """The allowlisted file the projection lands in."""
        ...

    @property
    def protocols(self) -> tuple[str, ...]:
        """The wire protocols the agent's native config speaks."""
        ...

    def apply(
        self, text: str, req: ProviderProjectionRequest, config_file: pathlib.Path
    ) -> ProjectionPlan: ...

    def remove(
        self, text: str, config_file: pathlib.Path, binding: ModelBinding | None = None
    ) -> ProjectionPlan:
        """``binding`` is what Coffer projected: a model or effort still equal
        to it is Coffer's to remove, anything else is the user's."""
        ...

    def is_present(self, text: str) -> bool:
        """Whether Coffer's keys are in ``text``. Raises on a document that
        does not parse; the caller decides what that means."""
        ...


def claude_tiers(req: ProviderProjectionRequest) -> dict[str, str]:
    """The tier pins a projection writes: the binding's own, or — when the
    agent has none stored — Coffer's suggestion for its model, so no tier ever
    sends a Claude id to an endpoint that does not serve one."""
    if req.binding.tier_models:
        return dict(req.binding.tier_models)
    return suggest_tier_models(req.binding.model, req.model_ids, local=req.local)


@dataclass(frozen=True)
class ClaudeCodeProviderProjection:
    """``settings.json``: ``apiKeyHelper``, the base URL, the model keys."""

    agent_type: AgentType = AgentType.CLAUDE_CODE
    config_key: str = "settings"
    protocols: tuple[str, ...] = (Protocol.ANTHROPIC.value,)

    def apply(
        self, text: str, req: ProviderProjectionRequest, config_file: pathlib.Path
    ) -> ProjectionPlan:
        chosen = find_model(req.models, req.binding.model)
        return ProjectionPlan(
            apply_anthropic_settings(
                text,
                base_url=req.base_url,
                api_key_helper=req.key_helper,
                model=req.binding.model,
                effort=req.binding.effort,
                tier_models=claude_tiers(req),
                picker_models=req.model_ids,
                # Replace Claude Code's built-in rows only where they would
                # fail: an endpoint that serves no Claude ids.
                replace_builtin_picker=not any(is_claude_model_id(m) for m in req.model_ids),
                local=req.local,
                local_context_window=chosen.context_window if chosen else None,
                loopback_proxy=req.loopback_proxy,
            )
        )

    def remove(
        self, text: str, config_file: pathlib.Path, binding: ModelBinding | None = None
    ) -> ProjectionPlan:
        binding = binding or ModelBinding()
        return ProjectionPlan(
            remove_anthropic_settings(
                text, managed_model=binding.model, managed_effort=binding.effort
            )
        )

    def is_present(self, text: str) -> bool:
        if not text.strip():
            return False
        # Compared as parsed data: the remover re-serialises.
        return bool(json.loads(remove_anthropic_settings(text)) != json.loads(text))


@dataclass(frozen=True)
class CodexProviderProjection:
    """``config.toml``: a ``[model_providers.coffer]`` block, plus the
    Coffer-owned model catalogue beside it when the connection curates models."""

    agent_type: AgentType = AgentType.CODEX
    config_key: str = "config"
    protocols: tuple[str, ...] = (Protocol.OPENAI.value,)

    def apply(
        self, text: str, req: ProviderProjectionRequest, config_file: pathlib.Path
    ) -> ProjectionPlan:
        catalog_path = codex_model_catalog_path(config_file.parent)
        catalog = codex_model_catalog_json(req.models)
        chosen = find_model(req.models, req.binding.model)
        # Only a level the chosen model records: without levels Codex sends no
        # reasoning effort whatever the key says, so writing one would only
        # make the file claim something that is not happening.
        effort = req.binding.effort
        if chosen is None or effort not in chosen.effort_levels:
            effort = None
        new_text = apply_codex_provider(
            text,
            base_url=req.base_url,
            model=req.binding.model,
            wire_api=req.wire_api or "responses",
            # The label Codex shows in its own picker — the name, not the uid.
            display_name=f"Coffer ({req.connection_name})",
            effort=effort,
            auth=req.codex_auth,
            catalog_path=catalog_path if catalog is not None else None,
        )
        if catalog is not None:
            return ProjectionPlan(new_text, before=(ProjectedFile(catalog_path, catalog),))
        return ProjectionPlan(new_text, after=(ProjectedFile(catalog_path, None),))

    def remove(
        self, text: str, config_file: pathlib.Path, binding: ModelBinding | None = None
    ) -> ProjectionPlan:
        binding = binding or ModelBinding()
        return ProjectionPlan(
            remove_codex_provider(text, managed_effort=binding.effort),
            after=(ProjectedFile(codex_model_catalog_path(config_file.parent), None),),
        )

    def is_present(self, text: str) -> bool:
        """``shell_environment_policy`` is left out of the comparison: its
        ``exclude`` entry selects no provider."""
        if not text.strip():
            return False
        before = tomllib.loads(text)
        after = tomllib.loads(remove_codex_provider(text))
        before.pop(CODEX_SHELL_ENV_POLICY_KEY, None)
        after.pop(CODEX_SHELL_ENV_POLICY_KEY, None)
        return before != after


PROVIDER_PROJECTIONS: tuple[ClaudeCodeProviderProjection | CodexProviderProjection, ...] = (
    ClaudeCodeProviderProjection(),
    CodexProviderProjection(),
)

__all__ = [
    "PROVIDER_PROJECTIONS",
    "ClaudeCodeProviderProjection",
    "CodexProviderProjection",
    "ProjectedFile",
    "ProjectionPlan",
    "ProviderProjection",
    "ProviderProjectionRequest",
    "claude_tiers",
]
