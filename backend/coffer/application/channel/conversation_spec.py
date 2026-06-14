"""Resolve a channel peer's sticky choices + channel defaults + workspace
allowlist into the (agent_key, agent_config) a new conversation is created with.

Structural dimensions only: the agent and the working directory are fixed when
a conversation is created (a conversation cannot be re-keyed), so switching
either opens a fresh conversation built from this spec. The model is parametric
(re-read each turn) and is not handled here.

Pure functions — no I/O except the registration-time directory check in
``validate_workspaces``.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConversationSpec:
    """The inputs to ``create_conversation`` for a channel-driven conversation."""

    agent_key: str
    agent_config: dict[str, Any] | None


def resolve_conversation_spec(
    *,
    default_agent: str,
    default_agent_config: dict[str, Any] | None,
    workspaces: dict[str, str],
    default_workspace: str | None,
    preferred_agent: str | None,
    preferred_workspace: str | None,
) -> ConversationSpec:
    """Combine the peer's sticky preferences with the channel defaults.

    ``workspaces`` maps a workspace name to its absolute path (the allowlist).
    The chosen workspace's path is injected as ``cwd`` so a bridged agent runs
    there; an unknown preferred workspace falls back to the default. An empty
    resulting config is normalized to ``None`` (matching the historical
    pass-through of an absent ``default_agent_config``).
    """
    agent_key = preferred_agent or default_agent
    config: dict[str, Any] = dict(default_agent_config) if default_agent_config else {}

    ws_name = preferred_workspace if preferred_workspace in workspaces else default_workspace
    if ws_name is not None and ws_name in workspaces:
        config["cwd"] = workspaces[ws_name]

    return ConversationSpec(agent_key=agent_key, agent_config=config or None)


def validate_workspaces(workspaces: Iterable[tuple[str, str]], *, default: str | None) -> None:
    """Registration-time check: every workspace path must be an existing
    directory, and ``default`` (if set) must name one of them.

    Raises ``ValueError`` so the resource framework rejects the registration
    with nothing persisted.
    """
    names: list[str] = []
    for name, path in workspaces:
        names.append(name)
        if not pathlib.Path(path).expanduser().is_dir():
            raise ValueError(f"workspace '{name}' path is not a directory: {path}")
    if default is not None and default not in names:
        raise ValueError(f"default_workspace '{default}' must name a declared workspace")
