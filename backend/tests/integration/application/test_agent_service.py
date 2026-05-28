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
    PrivilegedPath,
    ResourceAlreadyExists,
    SkillDirNotWritable,
)

# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="register an agent with custom skill_dir"
)
async def test_register_with_custom_skill_dir(agent_bundle, tmp_path):
    custom = tmp_path / "skills"
    custom.mkdir()
    r = await agent_bundle.svc.register(
        agent_type=AgentType.CURSOR,
        name="cursor-work",
        skill_dir=str(custom),
        actor="cli",
    )
    assert r.kind == "agent"
    assert r.name == "cursor-work"
    assert r.config["type"] == "cursor"
    entries = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_CREATED.value)
    assert len(entries) == 1


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="reject registration with invalid skill_dir"
)
async def test_register_rejects_nonexistent_skill_dir(agent_bundle, tmp_path):
    nonexistent = tmp_path / "no-such-dir" / "nested" / "deep"
    with pytest.raises(SkillDirNotWritable):
        await agent_bundle.svc.register(
            agent_type=AgentType.CURSOR,
            name="bad",
            skill_dir=str(nonexistent),
            actor="cli",
        )
    assert (await agent_bundle.svc.list()) == []


@pytest.mark.acceptance(spec="004-agent-registry", scenario="reject duplicate agent name")
async def test_register_rejects_duplicate_name(agent_bundle, tmp_path):
    custom = tmp_path / "skills"
    custom.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CURSOR, name="a", skill_dir=str(custom), actor="cli"
    )
    with pytest.raises(ResourceAlreadyExists):
        await agent_bundle.svc.register(
            agent_type=AgentType.CLAUDE_CODE, name="a", skill_dir=str(custom), actor="cli"
        )


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="004-agent-registry", scenario="update an existing agent")
async def test_update_skill_dir(agent_bundle, tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CURSOR, name="a", skill_dir=str(old), actor="cli"
    )
    updated = await agent_bundle.svc.update_skill_dir(name="a", new_skill_dir=str(new), actor="cli")
    assert updated.config["skill_dir"] == str(new)
    updates = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_UPDATED.value)
    assert len(updates) == 1


async def test_update_skill_dir_description_only(agent_bundle, tmp_path):
    """TEST25-108: a description-only change does not mutate skill_dir.

    Calling `update_skill_dir(name, new_skill_dir=current, description=new)` is
    the service-layer counterpart of the HTTP PATCH-description-only route.
    """
    old = tmp_path / "old"
    old.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CURSOR,
        name="a",
        skill_dir=str(old),
        description="before",
        actor="cli",
    )
    updated = await agent_bundle.svc.update_skill_dir(
        name="a",
        new_skill_dir=str(old),  # unchanged
        actor="cli",
        description="after",
    )
    assert updated.config["skill_dir"] == str(old)
    assert updated.description == "after"


# ---------------------------------------------------------------------------
# Enable/disable
# ---------------------------------------------------------------------------


async def test_set_enabled_idempotent_no_audit(agent_bundle, tmp_path):
    """TEST25-107: setting enabled=True on an already-enabled agent emits no event."""
    custom = tmp_path / "skills"
    custom.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CURSOR, name="a", skill_dir=str(custom), actor="cli"
    )
    # Re-enable on an already-enabled agent. The resource-service path is
    # idempotent — it must not record an audit row.
    await agent_bundle.svc.set_enabled(name="a", enabled=True, actor="cli")
    enabled = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_ENABLED.value)
    disabled = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_DISABLED.value)
    assert enabled == []
    assert disabled == []


# ---------------------------------------------------------------------------
# Remove + suppression
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="004-agent-registry", scenario="remove an agent")
async def test_remove_auto_detected_agent_suppresses_type(agent_bundle, tmp_path):
    """TEST25-104: removing an auto-detected agent both suppresses + audits."""
    custom = tmp_path / "skills"
    custom.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CURSOR,
        name="cur",
        skill_dir=str(custom),
        actor="system",
        auto_detected=True,
    )
    await agent_bundle.svc.remove(name="cur", actor="cli")
    assert await agent_bundle.suppression.is_suppressed("cursor")
    assert (await agent_bundle.svc.list()) == []
    # The AGENT_TYPE_SUPPRESSED audit row must be present.
    rows = await agent_bundle.audit.query(event_type=AuditEventType.AGENT_TYPE_SUPPRESSED.value)
    assert len(rows) == 1
    assert rows[0].details.get("agent_type") == "cursor"


async def test_remove_manual_agent_does_not_suppress(agent_bundle, tmp_path):
    custom = tmp_path / "skills"
    custom.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CURSOR,
        name="cur",
        skill_dir=str(custom),
        actor="cli",
        auto_detected=False,
    )
    await agent_bundle.svc.remove(name="cur", actor="cli")
    assert not await agent_bundle.suppression.is_suppressed("cursor")


async def test_register_lifts_suppression(agent_bundle, tmp_path):
    await agent_bundle.suppression.suppress("cursor")
    custom = tmp_path / "skills"
    custom.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CURSOR,
        name="cur",
        skill_dir=str(custom),
        actor="cli",
    )
    assert not await agent_bundle.suppression.is_suppressed("cursor")


async def test_suppress_twice_is_idempotent(agent_bundle):
    """TEST25-205: calling `suppress()` twice does not duplicate state or raise."""
    await agent_bundle.suppression.suppress("cursor")
    await agent_bundle.suppression.suppress("cursor")
    assert await agent_bundle.suppression.is_suppressed("cursor")
    listed = await agent_bundle.suppression.list_all()
    assert listed.count("cursor") == 1


# ---------------------------------------------------------------------------
# Auto-detect
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="004-agent-registry",
    scenario="skip already-registered types on subsequent launch",
)
async def test_auto_detect_skips_already_registered(agent_bundle, tmp_path, monkeypatch):
    custom = tmp_path / "skills"
    custom.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CURSOR,
        name="manual-cursor",
        skill_dir=str(custom),
        actor="cli",
    )

    home = tmp_path
    monkeypatch.setenv("HOME", str(home))
    (home / ".cursor").mkdir()

    new = await agent_bundle.detect.run_once()
    types = [r.config["type"] for r in new]
    assert "cursor" not in types


@pytest.mark.acceptance(
    spec="004-agent-registry",
    scenario="respect user removal across launches",
)
async def test_auto_detect_respects_suppression(agent_bundle, tmp_path, monkeypatch):
    home = tmp_path
    monkeypatch.setenv("HOME", str(home))
    (home / ".cursor").mkdir()
    custom = tmp_path / "skills"
    custom.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CURSOR,
        name="x",
        skill_dir=str(custom),
        actor="system",
        auto_detected=True,
    )
    await agent_bundle.svc.remove(name="x", actor="cli")

    new = await agent_bundle.detect.run_once()
    types = [r.config["type"] for r in new]
    assert "cursor" not in types


async def test_detect_endpoint_emits_auto_registered_audit(agent_bundle, tmp_path, monkeypatch):
    """TEST25-104: AGENT_AUTO_REGISTERED is recorded for each marker-detected agent."""
    home = tmp_path
    monkeypatch.setenv("HOME", str(home))
    # FR-007 requires the actual skill_dir to exist for register() to succeed,
    # so mkdir the default ~/.cursor/skills (not just the marker .cursor/).
    (home / ".cursor" / "skills").mkdir(parents=True)

    new = await agent_bundle.detect.run_once()
    types = [r.config["type"] for r in new]
    assert "cursor" in types
    rows = await agent_bundle.audit.query(event_type=AuditEventType.AGENT_AUTO_REGISTERED.value)
    assert len(rows) == 1
    assert rows[0].details.get("agent_type") == "cursor"


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="concurrent detect requests are serialized"
)
async def test_auto_detect_concurrent_calls_serialized(agent_bundle, tmp_path, monkeypatch):
    """Two overlapping `run_once()` calls must register each marker exactly once.

    Without the `asyncio.Lock` inside `AutoDetectService`, both calls would
    observe "not registered yet" and race to register the same type — the
    second one would then hit `ResourceAlreadyExists`. The serialised
    behaviour we assert here is the spec scenario "concurrent detect
    requests are serialized".
    """
    import asyncio

    home = tmp_path
    monkeypatch.setenv("HOME", str(home))
    (home / ".cursor" / "skills").mkdir(parents=True)

    results = await asyncio.gather(
        agent_bundle.detect.run_once(),
        agent_bundle.detect.run_once(),
    )
    # Across both calls the cursor type is registered exactly once.
    flat = [r.config["type"] for batch in results for r in batch]
    assert flat.count("cursor") == 1
    # The list contains exactly one cursor row.
    items = [r for r in await agent_bundle.svc.list() if r.config["type"] == "cursor"]
    assert len(items) == 1


async def test_auto_detect_swallows_register_exception(agent_bundle, tmp_path, monkeypatch):
    """TEST25-105: auto-detect must not crash startup if `register` raises.

    `assert_skill_dir_usable` is patched to raise — every register attempt fails.
    `run_once()` must return [] (or a partial list) without re-raising, and the
    type must stay unregistered.
    """
    home = tmp_path
    monkeypatch.setenv("HOME", str(home))
    (home / ".cursor").mkdir()

    def _boom(path: pathlib.Path) -> None:
        raise SkillDirNotWritable(str(path), "monkeypatched")

    monkeypatch.setattr("coffer.application.agent.service.assert_skill_dir_usable", _boom)

    registered = await agent_bundle.detect.run_once()
    types = [r.config["type"] for r in registered]
    assert "cursor" not in types
    # And no auto-register audit row got recorded.
    rows = await agent_bundle.audit.query(event_type=AuditEventType.AGENT_AUTO_REGISTERED.value)
    assert rows == []


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
    """A skill_dir that fails pydantic field validation surfaces as ConfigValidationError."""
    from coffer.domain.errors import ConfigValidationError

    with pytest.raises(ConfigValidationError):
        await agent_bundle.svc.register(
            agent_type=AgentType.CURSOR,
            name="bad",
            skill_dir="   ",  # whitespace-only → rejected by AgentConfig
            actor="cli",
        )


async def test_update_skill_dir_invalid_raises_config_validation_error(agent_bundle, tmp_path):
    """An update with an invalid (relative) skill_dir surfaces as ConfigValidationError."""
    from coffer.domain.errors import ConfigValidationError

    custom = tmp_path / "skills"
    custom.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CURSOR, name="a", skill_dir=str(custom), actor="cli"
    )
    with pytest.raises(ConfigValidationError):
        await agent_bundle.svc.update_skill_dir(
            name="a", new_skill_dir="relative/path", actor="cli"
        )


# ---------------------------------------------------------------------------
# Audit lifecycle — pre-existing scenario, kept for spec coverage
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="004-agent-registry", scenario="audit lifecycle events")
async def test_audit_records_lifecycle_events(agent_bundle, tmp_path):
    custom = tmp_path / "skills"
    custom.mkdir()
    await agent_bundle.svc.register(
        agent_type=AgentType.CURSOR, name="a", skill_dir=str(custom), actor="cli"
    )
    await agent_bundle.svc.set_enabled(name="a", enabled=False, actor="cli")
    await agent_bundle.svc.set_enabled(name="a", enabled=True, actor="cli")
    await agent_bundle.svc.remove(name="a", actor="cli")

    created = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_CREATED.value)
    disabled = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_DISABLED.value)
    enabled = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_ENABLED.value)
    deleted = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_DELETED.value)
    assert len(created) == len(disabled) == len(enabled) == len(deleted) == 1
