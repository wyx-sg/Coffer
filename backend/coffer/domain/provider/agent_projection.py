"""The provider entry of each agent's projection facet (ADR
agent-mechanisms-are-optional-facets-on-the-descriptor).

One :class:`ProviderProjection` per agent that can be put on a connection. It
names the agent it serves, the allowlisted file the projection lands in, the
wire protocols the agent's native config speaks (which may be none), and the
translation: pure functions from a connection to that file's new text. Which
agents a connection reaches is its scope; nothing here maps a protocol to an
agent.

Pure, like the transforms it composes (``projection.py``): the application
layer reads the file, asks for a :class:`ProjectionPlan`, and performs its
writes in order.
"""

from __future__ import annotations

import json
import pathlib
import tomllib
from dataclasses import dataclass
from typing import Protocol as _Protocol

from coffer.domain.agent.types import AgentType
from coffer.domain.provider.api_key_helper import anthropic_api_key_helper
from coffer.domain.provider.codex_shell_env import CODEX_SHELL_ENV_POLICY_KEY
from coffer.domain.provider.config import Protocol
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
    base_url: str
    #: The agent's own binding (spec provider-switching "Take projected model
    #: keys from the agent's binding"); ``None`` projects no model.
    model: str | None
    fast_model: str | None
    wire_api: str | None
    #: The connection's curated text models, in order.
    text_models: tuple[str, ...]
    #: Where the ``coffer`` CLI is, for a key helper line.
    coffer_cli: str


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

    def remove(self, text: str, config_file: pathlib.Path) -> ProjectionPlan: ...

    def is_present(self, text: str) -> bool:
        """Whether Coffer's keys are in ``text``. Raises on a document that
        does not parse; the caller decides what that means."""
        ...


@dataclass(frozen=True)
class ClaudeCodeProviderProjection:
    """``settings.json``: an ``apiKeyHelper`` naming the connection by uid, and
    the ``ANTHROPIC_*`` env vars."""

    agent_type: AgentType = AgentType.CLAUDE_CODE
    config_key: str = "settings"
    protocols: tuple[str, ...] = (Protocol.ANTHROPIC.value,)

    def apply(
        self, text: str, req: ProviderProjectionRequest, config_file: pathlib.Path
    ) -> ProjectionPlan:
        return ProjectionPlan(
            apply_anthropic_settings(
                text,
                base_url=req.base_url,
                model=req.model,
                fast_model=req.fast_model,
                # The uid, so the helper keeps reading this connection's key
                # after a rename.
                api_key_helper=anthropic_api_key_helper(
                    req.connection_uid, coffer_cli=req.coffer_cli
                ),
            )
        )

    def remove(self, text: str, config_file: pathlib.Path) -> ProjectionPlan:
        return ProjectionPlan(remove_anthropic_settings(text))

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
        catalog = codex_model_catalog_json(req.text_models)
        new_text = apply_codex_provider(
            text,
            base_url=req.base_url,
            model=req.model,
            wire_api=req.wire_api or "responses",
            # The label Codex shows in its own picker — the name, not the uid.
            display_name=f"Coffer ({req.connection_name})",
            catalog_path=catalog_path if catalog is not None else None,
        )
        if catalog is not None:
            # Written before config.toml points at it.
            return ProjectionPlan(new_text, before=(ProjectedFile(catalog_path, catalog),))
        # No curated set: the pointer is gone, so retire the file too.
        return ProjectionPlan(new_text, after=(ProjectedFile(catalog_path, None),))

    def remove(self, text: str, config_file: pathlib.Path) -> ProjectionPlan:
        return ProjectionPlan(
            remove_codex_provider(text),
            after=(ProjectedFile(codex_model_catalog_path(config_file.parent), None),),
        )

    def is_present(self, text: str) -> bool:
        """``shell_environment_policy`` is left out of the comparison: its
        ``exclude`` entry only hides the key from shell commands and selects no
        provider, so one left behind by a hand-removed provider block is not a
        projection (a de-projection removes it)."""
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
]
