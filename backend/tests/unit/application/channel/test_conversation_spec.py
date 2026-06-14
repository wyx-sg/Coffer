"""The conversation-spec resolver: how a peer's sticky choices + channel
defaults + workspace allowlist become (agent_key, agent_config)."""

from __future__ import annotations

import pytest
from coffer.application.channel.conversation_spec import (
    ConversationSpec,
    resolve_conversation_spec,
    validate_workspaces,
)


def _resolve(**overrides):  # type: ignore[no-untyped-def]
    kwargs = {
        "default_agent": "builtin",
        "default_agent_config": None,
        "workspaces": {},
        "default_workspace": None,
        "preferred_agent": None,
        "preferred_workspace": None,
    }
    kwargs.update(overrides)
    return resolve_conversation_spec(**kwargs)


def test_builtin_default_yields_no_config():
    spec = _resolve()
    assert spec == ConversationSpec(agent_key="builtin", agent_config=None)


def test_preferred_agent_overrides_default():
    spec = _resolve(preferred_agent="codex")
    assert spec.agent_key == "codex"


def test_preferred_workspace_injects_cwd():
    spec = _resolve(
        preferred_agent="codex",
        workspaces={"proj": "/srv/proj", "docs": "/srv/docs"},
        preferred_workspace="proj",
    )
    assert spec.agent_key == "codex"
    assert spec.agent_config == {"cwd": "/srv/proj"}


def test_default_workspace_used_when_no_preference():
    spec = _resolve(
        preferred_agent="claude_code",
        workspaces={"proj": "/srv/proj"},
        default_workspace="proj",
    )
    assert spec.agent_config == {"cwd": "/srv/proj"}


def test_unknown_preferred_workspace_falls_back_to_default():
    spec = _resolve(
        preferred_agent="codex",
        workspaces={"proj": "/srv/proj"},
        preferred_workspace="gone",
        default_workspace="proj",
    )
    assert spec.agent_config == {"cwd": "/srv/proj"}


def test_default_agent_config_merged_with_cwd():
    spec = _resolve(
        preferred_agent="claude_code",
        default_agent_config={"permission_mode": "plan"},
        workspaces={"proj": "/srv/proj"},
        default_workspace="proj",
    )
    assert spec.agent_config == {"permission_mode": "plan", "cwd": "/srv/proj"}


def test_no_workspace_resolved_keeps_default_config():
    spec = _resolve(preferred_agent="codex", default_agent_config={"k": "v"})
    assert spec.agent_config == {"k": "v"}


# -- validate_workspaces (registration-time fs check) --------------------------


def test_validate_workspaces_accepts_existing_dirs(tmp_path):  # type: ignore[no-untyped-def]
    a = tmp_path / "a"
    a.mkdir()
    validate_workspaces([("a", str(a))], default="a")  # no raise


def test_validate_workspaces_rejects_missing_dir(tmp_path):  # type: ignore[no-untyped-def]
    missing = tmp_path / "nope"
    with pytest.raises(ValueError, match="not a directory"):
        validate_workspaces([("a", str(missing))], default=None)


def test_validate_workspaces_rejects_default_not_present(tmp_path):  # type: ignore[no-untyped-def]
    a = tmp_path / "a"
    a.mkdir()
    with pytest.raises(ValueError, match="default_workspace"):
        validate_workspaces([("a", str(a))], default="b")
