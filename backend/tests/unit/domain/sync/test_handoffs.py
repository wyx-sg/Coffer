"""The sync hand-off prompts' rules (``domain/sync/handoffs.py``): what they
never carry, and which conflicts an agent may merge."""

from __future__ import annotations

from coffer.domain.sync.handoffs import (
    agent_mergeable,
    display_remote,
    remote_failure_handoff,
    scrub_git_text,
)
from coffer.domain.sync.stops import ConflictFile, ConflictReason

TOKEN = "glpat-abcdefghijklmnop1234"


def _conflict(path: str, reason: ConflictReason = ConflictReason.BOTH_CHANGED) -> ConflictFile:
    return ConflictFile(path=path, area=path.split("/")[0], reason=reason, ours="a", theirs="b")


def test_git_text_loses_url_credentials_and_token_shapes() -> None:
    text = (
        f"fatal: unable to access 'https://oauth2:{TOKEN}@gitlab.com/g/r.git/'\n"
        "remote: ghp_abcdefghijklmnopqrstuvwxyz0123\n"
        "Authorization: Bearer abc.def.ghi\n"
        "using basic dXNlcjpwYXNzd29yZA=="
    )
    out = scrub_git_text(text)
    assert TOKEN not in out and "oauth2" not in out
    assert "ghp_" not in out and "abc.def.ghi" not in out and "dXNlcjpw" not in out
    assert "https://***@gitlab.com/g/r.git/" in out


def test_a_remote_is_shown_without_its_user_or_password() -> None:
    assert display_remote(f"https://oauth2:{TOKEN}@gitlab.com/g/r.git") == (
        "https://gitlab.com/g/r.git"
    )
    assert display_remote("git@github.com:me/vault.git") == "git@github.com:me/vault.git"


def test_a_refused_sign_in_hand_off_never_carries_or_asks_for_the_token() -> None:
    prompt = remote_failure_handoff(
        "auth_failed",
        url=f"https://oauth2:{TOKEN}@gitlab.com/g/r.git",
        branch="vault",
        detail=f"fatal: Authentication failed for 'https://oauth2:{TOKEN}@gitlab.com/g/r.git/'",
        secret_ref="sync/gitlab",
        username="oauth2",
    )
    assert prompt is not None
    assert TOKEN not in prompt
    assert "https://gitlab.com/g/r.git" in prompt and "Branch: vault" in prompt
    assert "sync/gitlab" in prompt and "user name oauth2" in prompt
    assert "Do not ask me for the token" in prompt


def test_an_unreachable_remote_has_a_hand_off_and_other_kinds_none() -> None:
    kwargs = {"url": "git@github.com:me/v.git", "branch": "main", "detail": "x"}
    assert remote_failure_handoff("unreachable", secret_ref=None, username=None, **kwargs)
    assert remote_failure_handoff("layout", secret_ref=None, username=None, **kwargs) is None


def test_only_edited_files_that_are_not_secrets_are_the_agents_to_merge() -> None:
    assert agent_mergeable(_conflict("knowledge/a.md"))
    assert agent_mergeable(_conflict("resources/mcp_server/x.json", ConflictReason.INVALID_MERGE))
    assert not agent_mergeable(_conflict("secret/token.enc"))
    assert not agent_mergeable(_conflict("knowledge/a.md", ConflictReason.CHANGED_AND_DELETED))
    assert not agent_mergeable(
        _conflict("resources/mcp_server/x.json", ConflictReason.SAME_NAME_DIFFERENT_UID)
    )
