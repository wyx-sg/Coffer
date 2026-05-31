"""AgentService integration: DB + audit + suppression."""

from __future__ import annotations

import os
import pathlib
import stat

import pytest

from coffer.application.agent.service import assert_skill_dir_usable
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import (
    AgentConfigDirRegistered,
    PrivilegedPath,
    ResourceAlreadyExists,
    SkillDirNotWritable,
)

# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="register an agent with a custom config dir"
)
async def test_register_with_custom_config_dir(agent_bundle, tmp_path):
    custom = tmp_path / "cfg"
    custom.mkdir()
    r = await agent_bundle.svc.register(
        agent_type=AgentType.CODEX,
        name="codex-work",
        config_dir=str(custom),
        actor="cli",
    )
    assert r.kind == "agent"
    assert r.name == "codex-work"
    assert r.config["type"] == "codex"
    # Registration auto-creates <config_dir>/skills.
    assert (custom / "skills").is_dir()
    entries = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_CREATED.value)
    assert len(entries) == 1


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="reject registration with an invalid config dir"
)
async def test_register_rejects_unhostable_config_dir(agent_bundle, tmp_path):
    # config_dir points at an existing regular file, so <file>/skills cannot be
    # created and the resolved skill dir is unusable.
    bogus_file = tmp_path / "a-file"
    bogus_file.write_text("not a dir")
    with pytest.raises(SkillDirNotWritable):
        await agent_bundle.svc.register(
            agent_type=AgentType.CODEX,
            name="bad",
            config_dir=str(bogus_file),
            actor="cli",
        )
    assert (await agent_bundle.svc.list()) == []


async def test_register_rejects_missing_config_dir(agent_bundle, tmp_path):
    # A mistyped / non-existent config_dir must be REJECTED, not silently
    # materialised via mkdir -p (which would deliver skills to a dir the agent
    # never reads). Only the skills/ leaf is auto-created, under an existing dir.
    missing = tmp_path / "does-not-exist" / ".codex"
    with pytest.raises(SkillDirNotWritable):
        await agent_bundle.svc.register(
            agent_type=AgentType.CODEX,
            name="typo",
            config_dir=str(missing),
            actor="cli",
        )
    assert not missing.exists()
    assert (await agent_bundle.svc.list()) == []


@pytest.mark.acceptance(spec="004-agent-registry", scenario="reject duplicate agent name")
async def test_register_rejects_duplicate_name(agent_bundle, tmp_path):
    # Distinct config dirs so the only collision is on the name (not the
    # one-agent-per-config-dir rule).
    first = tmp_path / "cfg1"
    second = tmp_path / "cfg2"
    first.mkdir()
    second.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CODEX, name="a", config_dir=str(first), actor="cli"
    )
    with pytest.raises(ResourceAlreadyExists):
        await agent_bundle.svc.register(
            agent_type=AgentType.CLAUDE_CODE, name="a", config_dir=str(second), actor="cli"
        )


@pytest.mark.acceptance(
    spec="004-agent-registry",
    scenario="reject a second agent for an already-registered config dir",
)
async def test_register_rejects_duplicate_config_dir(agent_bundle, tmp_path):
    custom = tmp_path / "cfg"
    custom.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CODEX, name="codex-one", config_dir=str(custom), actor="cli"
    )
    # A second Codex agent that resolves to the same config_dir is rejected even
    # with a different name — one agent per config directory.
    with pytest.raises(AgentConfigDirRegistered):
        await agent_bundle.svc.register(
            agent_type=AgentType.CODEX, name="codex-two", config_dir=str(custom), actor="cli"
        )
    assert len(await agent_bundle.svc.list()) == 1


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="004-agent-registry", scenario="update an existing agent")
async def test_update_config_dir(agent_bundle, tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CODEX, name="a", config_dir=str(old), actor="cli"
    )
    updated = await agent_bundle.svc.update_config_dir(
        name="a", new_config_dir=str(new), actor="cli"
    )
    assert updated.config["config_dir"] == str(new)
    # The new config dir's skills subdir is auto-created on update.
    assert (new / "skills").is_dir()
    updates = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_UPDATED.value)
    assert len(updates) == 1


async def test_update_config_dir_description_only(agent_bundle, tmp_path):
    """TEST25-108: a description-only change does not mutate config_dir.

    Calling `update_config_dir(name, new_config_dir=current, description=new)`
    is the service-layer counterpart of the HTTP PATCH-description-only route.
    """
    old = tmp_path / "old"
    old.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CODEX,
        name="a",
        config_dir=str(old),
        description="before",
        actor="cli",
    )
    updated = await agent_bundle.svc.update_config_dir(
        name="a",
        new_config_dir=str(old),  # unchanged
        actor="cli",
        description="after",
    )
    assert updated.config["config_dir"] == str(old)
    assert updated.description == "after"


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="004-agent-registry", scenario="remove an agent")
async def test_remove_deletes_agent(agent_bundle, tmp_path):
    """Removing an agent deletes it and audits the deletion. A removal is never
    permanent — the next scan re-surfaces it as a candidate (no suppression)."""
    custom = tmp_path / "cfg"
    custom.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CODEX,
        name="cur",
        config_dir=str(custom),
        actor="system",
    )
    await agent_bundle.svc.remove(name="cur", actor="cli")
    assert (await agent_bundle.svc.list()) == []
    rows = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_DELETED.value)
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Discovery — detection is discovery + confirm (no auto-registration)
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="004-agent-registry",
    scenario="discover installed agents as candidates",
)
async def test_discover_returns_installed_candidate(agent_bundle, tmp_path, monkeypatch):
    """An installed agent (marker dir present) is reported as a candidate, and
    discovery is read-only — nothing is registered."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".codex").mkdir()

    candidates = await agent_bundle.detect.discover()
    types = [c.type.value for c in candidates]
    assert "codex" in types
    # Read-only: discovery must not register anything.
    assert (await agent_bundle.svc.list()) == []


async def test_discover_skips_types_without_marker(agent_bundle, tmp_path, monkeypatch):
    """No marker dir on disk → the type is not offered as a candidate."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Neither ~/.codex nor ~/.claude exists.
    candidates = await agent_bundle.detect.discover()
    assert candidates == []


@pytest.mark.acceptance(
    spec="004-agent-registry",
    scenario="skip already-registered types on subsequent scan",
)
async def test_discover_skips_already_registered(agent_bundle, tmp_path, monkeypatch):
    custom = tmp_path / "cfg"
    custom.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CODEX,
        name="manual-codex",
        config_dir=str(custom),
        actor="cli",
    )

    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".codex").mkdir()

    candidates = await agent_bundle.detect.discover()
    assert "codex" not in [c.type.value for c in candidates]


@pytest.mark.acceptance(
    spec="004-agent-registry",
    scenario="re-surface removed agents on subsequent scan",
)
async def test_discover_re_surfaces_removed_agent(agent_bundle, tmp_path, monkeypatch):
    """A removed agent is NOT permanently suppressed — the next scan offers it
    again as a candidate (the removal might have been accidental)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".codex").mkdir()
    custom = tmp_path / "cfg"
    custom.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CODEX,
        name="x",
        config_dir=str(custom),
        actor="system",
    )
    await agent_bundle.svc.remove(name="x", actor="cli")

    candidates = await agent_bundle.detect.discover()
    assert "codex" in [c.type.value for c in candidates]


# ---------------------------------------------------------------------------
# Privileged-path defence — TEST25-103
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="reject registration into privileged system path"
)
@pytest.mark.parametrize(
    "privileged",
    [
        "/etc/skills",
        "/bin/skills",
        "/sbin/skills",
        "/usr/local/skills",
        "/System/Library/skills",
    ],
)
def test_privileged_path_rejected(privileged):
    """assert_skill_dir_usable rejects every privileged POSIX prefix."""
    with pytest.raises(PrivilegedPath):
        assert_skill_dir_usable(pathlib.Path(privileged))


def test_privileged_path_symlink_traversal_rejected(tmp_path):
    """A symlink pointing at /etc is rejected because resolve() is privileged.

    SC-005: even if the user-supplied path is harmless-looking, the *resolved*
    path is what we host the skill files at — and that must not be /etc.
    """
    link = tmp_path / "skills"
    # /etc exists on POSIX hosts. Skip on Windows where the prefix set differs.
    import sys

    if sys.platform == "win32":
        pytest.skip("symlink-traversal test is POSIX-only")
    try:
        link.symlink_to("/etc")
    except OSError:  # pragma: no cover — sandbox without symlink perms
        pytest.skip("symlink creation not permitted in this sandbox")
    with pytest.raises(PrivilegedPath):
        assert_skill_dir_usable(link)


# ---------------------------------------------------------------------------
# assert_skill_dir_usable negative branches — TEST25-102
# ---------------------------------------------------------------------------


def test_assert_skill_dir_usable_directory_missing(tmp_path):
    """A non-existent skill_dir is rejected with `directory_missing`.

    FR-007 requires the skill_dir to exist before registration — we don't
    silently accept a parent-writable + missing-dir case because skill loading
    would later fail in obscure ways.
    """
    target = tmp_path / "no-such-dir"
    with pytest.raises(SkillDirNotWritable) as ei:
        assert_skill_dir_usable(target)
    assert ei.value.reason == "directory_missing"


def test_assert_skill_dir_usable_not_a_directory(tmp_path):
    """A path that exists but is a file (not a dir) is rejected."""
    f = tmp_path / "skills"
    f.write_text("not a dir")
    with pytest.raises(SkillDirNotWritable) as ei:
        assert_skill_dir_usable(f)
    assert ei.value.reason == "not_a_directory"


def test_assert_skill_dir_usable_existing_dir_not_writable(tmp_path):
    """An existing dir without the write bit is rejected."""
    d = tmp_path / "skills"
    d.mkdir()
    orig_mode = d.stat().st_mode
    os.chmod(d, stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(SkillDirNotWritable) as ei:
            assert_skill_dir_usable(d)
        assert ei.value.reason == "not_writable"
    finally:
        os.chmod(d, orig_mode)


def test_assert_skill_dir_usable_tilde_expansion(tmp_path, monkeypatch):
    """TEST25-110: `~` in skill_dir expands against HOME before validation."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "skills").mkdir()
    # Should not raise; the path expands to <tmp_path>/skills which exists.
    assert_skill_dir_usable(pathlib.Path("~/skills"))


def test_strip_macos_private_non_darwin_passthrough(monkeypatch):
    """`_strip_macos_private` is a no-op on non-darwin (covers the platform guard)."""
    from coffer.application.agent.service import _strip_macos_private

    monkeypatch.setattr("sys.platform", "linux")
    assert _strip_macos_private("/private/var/x") == "/private/var/x"


def test_strip_macos_private_handles_exact_private(monkeypatch):
    """Bare ``/private`` on darwin collapses to ``/`` (covers the equality branch)."""
    from coffer.application.agent.service import _strip_macos_private

    monkeypatch.setattr("sys.platform", "darwin")
    assert _strip_macos_private("/private") == "/"


async def test_register_invalid_config_raises_config_validation_error(agent_bundle):
    """A config_dir that fails pydantic field validation surfaces as ConfigValidationError."""
    from coffer.domain.errors import ConfigValidationError

    with pytest.raises(ConfigValidationError):
        await agent_bundle.svc.register(
            agent_type=AgentType.CODEX,
            name="bad",
            config_dir="   ",  # whitespace-only → rejected by AgentConfig
            actor="cli",
        )


async def test_update_config_dir_invalid_raises_config_validation_error(agent_bundle, tmp_path):
    """An update with an invalid (relative) config_dir surfaces as ConfigValidationError."""
    from coffer.domain.errors import ConfigValidationError

    custom = tmp_path / "cfg"
    custom.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CODEX, name="a", config_dir=str(custom), actor="cli"
    )
    with pytest.raises(ConfigValidationError):
        await agent_bundle.svc.update_config_dir(
            name="a", new_config_dir="relative/path", actor="cli"
        )


# ---------------------------------------------------------------------------
# Audit lifecycle — pre-existing scenario, kept for spec coverage
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="004-agent-registry", scenario="audit lifecycle events")
async def test_audit_records_lifecycle_events(agent_bundle, tmp_path):
    custom = tmp_path / "cfg"
    custom.mkdir()
    new = tmp_path / "cfg2"
    new.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CODEX, name="a", config_dir=str(custom), actor="cli"
    )
    # Agents have no enable/disable concept — the lifecycle is create, update,
    # remove (each via the kind-agnostic resource_* events).
    await agent_bundle.svc.update_config_dir(name="a", new_config_dir=str(new), actor="cli")
    await agent_bundle.svc.remove(name="a", actor="cli")

    created = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_CREATED.value)
    updated = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_UPDATED.value)
    deleted = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_DELETED.value)
    assert len(created) == len(updated) == len(deleted) == 1
