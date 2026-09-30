"""AgentService integration: DB + audit + suppression."""

from __future__ import annotations

import os
import pathlib
import stat

import pytest

from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.service import assert_skill_dir_usable
from coffer.application.platform_port import PrivilegedPaths
from coffer.domain.agent.detection import DetectionState
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import (
    AgentConfigDirRegistered,
    AgentTypeRegistered,
    PrivilegedPath,
    SkillDirNotWritable,
)
from coffer.infrastructure.platform import HostPlatform
from tests.support.facets import agent_catalog, installed


def _rules() -> PrivilegedPaths:
    """This host's privileged-path rules, read when the test runs."""
    return HostPlatform().privileged_paths()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="agent-registry", scenario="register an agent with a custom config dir"
)
async def test_register_with_custom_config_dir(agent_bundle, tmp_path):
    custom = tmp_path / "cfg"
    custom.mkdir()
    r = await agent_bundle.svc.register(
        agent_type=AgentType.CODEX,
        config_dir=str(custom),
        actor="cli",
    )
    assert r.kind == "agent"
    assert r.name == "codex"  # named by its type, never chosen
    assert r.config["type"] == "codex"
    # Registration auto-creates <config_dir>/skills.
    assert (custom / "skills").is_dir()
    entries = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_CREATED.value)
    assert len(entries) == 1


@pytest.mark.acceptance(
    spec="agent-registry", scenario="reject registration with an invalid config dir"
)
async def test_register_rejects_unhostable_config_dir(agent_bundle, tmp_path):
    # config_dir points at an existing regular file, so <file>/skills cannot be
    # created and the resolved skill dir is unusable.
    bogus_file = tmp_path / "a-file"
    bogus_file.write_text("not a dir")
    with pytest.raises(SkillDirNotWritable):
        await agent_bundle.svc.register(
            agent_type=AgentType.CODEX,
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
            config_dir=str(missing),
            actor="cli",
        )
    assert not missing.exists()
    assert (await agent_bundle.svc.list()) == []


@pytest.mark.acceptance(spec="agent-registry", scenario="reject duplicate agent name")
async def test_register_rejects_a_second_agent_of_the_type(agent_bundle, tmp_path):
    """The name is the type's, so a second agent of a type would duplicate it:
    refused even on a distinct, writable directory, with nothing persisted."""
    first = tmp_path / "cfg1"
    second = tmp_path / "cfg2"
    first.mkdir()
    second.mkdir()
    kept = await agent_bundle.svc.register(
        agent_type=AgentType.CODEX, config_dir=str(first), actor="cli"
    )
    with pytest.raises(AgentTypeRegistered):
        await agent_bundle.svc.register(
            agent_type=AgentType.CODEX, config_dir=str(second), actor="cli"
        )
    assert [(a.uid, a.name) for a in await agent_bundle.svc.list()] == [(kept.uid, "codex")]
    assert not (second / "skills").exists()


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="reject a second agent for an already-registered config dir",
)
async def test_register_rejects_duplicate_config_dir(agent_bundle, tmp_path):
    custom = tmp_path / "cfg"
    custom.mkdir()
    await agent_bundle.svc.register(agent_type=AgentType.CODEX, config_dir=str(custom), actor="cli")
    # An agent of another type on the same config_dir is rejected — one agent
    # per config directory.
    with pytest.raises(AgentConfigDirRegistered):
        await agent_bundle.svc.register(
            agent_type=AgentType.CLAUDE_CODE, config_dir=str(custom), actor="cli"
        )
    assert len(await agent_bundle.svc.list()) == 1


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="agent-registry", scenario="update an existing agent")
async def test_update_config_dir(agent_bundle, tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    agent = await agent_bundle.svc.register(
        agent_type=AgentType.CODEX, config_dir=str(old), actor="cli"
    )
    updated = await agent_bundle.svc.update_config_dir(
        uid=agent.uid, new_config_dir=str(new), actor="cli"
    )
    assert updated.config["config_dir"] == str(new)
    # The new config dir's skills subdir is auto-created on update.
    assert (new / "skills").is_dir()
    updates = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_UPDATED.value)
    assert len(updates) == 1


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="agent-registry", scenario="remove an agent")
async def test_remove_deletes_agent(agent_bundle, tmp_path):
    """Removing an agent deletes it and audits the deletion. A removal is never
    permanent — the next scan re-surfaces it as a candidate (no suppression)."""
    custom = tmp_path / "cfg"
    custom.mkdir()
    agent = await agent_bundle.svc.register(
        agent_type=AgentType.CODEX,
        config_dir=str(custom),
        actor="system",
    )
    await agent_bundle.svc.remove(uid=agent.uid, actor="cli")
    assert (await agent_bundle.svc.list()) == []
    rows = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_DELETED.value)
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Discovery — detection is discovery + confirm (no auto-registration)
# ---------------------------------------------------------------------------


def _detect(bundle, programs=None, environ=None):
    """The bundle's registry with probes answering from ``programs``."""
    return AutoDetectService(
        agent_service=bundle.svc,
        catalog=agent_catalog(programs),
        environ=lambda: dict(environ or {}),
    )


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="discover installed agents as candidates",
)
async def test_discover_returns_installed_candidate(agent_bundle, tmp_path, monkeypatch):
    """An installed agent (program on PATH, config dir present) is reported as
    a candidate with its state and version, and discovery is read-only."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".codex").mkdir()

    candidates = await _detect(agent_bundle, {AgentType.CODEX: installed("0.155.1")}).discover()
    codex = next(c for c in candidates if c.type is AgentType.CODEX)
    assert (codex.name, codex.display_name) == ("codex", "OpenAI Codex")
    assert codex.config_dir == str(tmp_path / ".codex")
    assert codex.state is DetectionState.INSTALLED_ACTIVE
    assert codex.version == "0.155.1"
    assert codex.addable
    # Read-only: discovery must not register anything.
    assert (await agent_bundle.svc.list()) == []


async def test_discover_skips_types_with_neither_signal(agent_bundle, tmp_path, monkeypatch):
    """No program and no config dir → the type is not offered."""
    monkeypatch.setenv("HOME", str(tmp_path))
    assert await _detect(agent_bundle).discover() == []


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="offer an installed agent that has never run",
)
async def test_an_installed_agent_without_a_config_dir_is_never_run(
    agent_bundle, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    candidates = await _detect(
        agent_bundle, {AgentType.CLAUDE_CODE: installed("2.1.281")}
    ).discover()
    assert [(c.type, c.state, c.config_dir) for c in candidates] == [
        (AgentType.CLAUDE_CODE, DetectionState.INSTALLED_NEVER_RUN, str(tmp_path / ".claude"))
    ]
    assert candidates[0].version == "2.1.281"
    assert not (tmp_path / ".claude").exists()
    # Offered for adding: registering it creates the standard directory.
    assert candidates[0].addable


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="show a leftover config directory as config left behind",
)
async def test_a_config_dir_without_its_program_is_config_only(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir()
    candidates = await _detect(agent_bundle).discover()
    assert [(c.type, c.state, c.version) for c in candidates] == [
        (AgentType.CLAUDE_CODE, DetectionState.CONFIG_ONLY, None)
    ]
    assert not candidates[0].addable


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="offer the directory named by the agent's environment variable",
)
async def test_the_env_named_dir_is_offered_on_the_one_candidate(
    agent_bundle, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    standard = tmp_path / ".claude"
    standard.mkdir()
    work = tmp_path / ".claude-work"
    work.mkdir()
    found = {AgentType.CLAUDE_CODE: installed("2.1.281")}
    env = {"CLAUDE_CONFIG_DIR": str(work)}

    candidates = await _detect(agent_bundle, found, env).discover()

    # One candidate for the type, at the standard directory, the variable's
    # directory offered beside it — never a second agent.
    assert [(c.config_dir, c.other_config_dir, c.name) for c in candidates] == [
        (str(standard), str(work), "claude-code")
    ]
    assert candidates[0].state is DetectionState.INSTALLED_ACTIVE
    # Without the standard directory the variable's directory is the candidate.
    standard.rmdir()
    [only] = await _detect(agent_bundle, found, env).discover()
    assert (only.config_dir, only.other_config_dir) == (str(work), None)
    assert only.state is DetectionState.INSTALLED_ACTIVE
    # The variable naming the standard directory adds nothing.
    standard.mkdir()
    [same] = await _detect(agent_bundle, found, {"CLAUDE_CONFIG_DIR": str(standard)}).discover()
    assert (same.config_dir, same.other_config_dir) == (str(standard), None)


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="skip already-registered config directories on subsequent scan",
)
async def test_discover_skips_already_registered(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".codex").mkdir()
    custom = tmp_path / "cfg"
    custom.mkdir()
    await agent_bundle.svc.register(agent_type=AgentType.CODEX, config_dir=None, actor="cli")

    # CODEX_HOME names another existing directory: still no codex candidate,
    # for either directory, because the type already has its agent.
    candidates = await _detect(
        agent_bundle, {AgentType.CODEX: installed()}, {"CODEX_HOME": str(custom)}
    ).discover()
    assert "codex" not in [c.type.value for c in candidates]


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="re-surface removed agents on subsequent scan",
)
async def test_discover_re_surfaces_removed_agent(agent_bundle, tmp_path, monkeypatch):
    """A removed agent is NOT permanently suppressed — the next scan offers it
    again as a candidate (the removal might have been accidental)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".codex").mkdir()
    agent = await agent_bundle.svc.register(
        agent_type=AgentType.CODEX, config_dir=None, actor="system"
    )
    detect = _detect(agent_bundle, {AgentType.CODEX: installed()})
    assert await detect.discover() == []
    await agent_bundle.svc.remove(uid=agent.uid, actor="cli")

    candidates = await detect.discover()
    assert "codex" in [c.type.value for c in candidates]


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="report a registered agent's detection state",
)
async def test_detect_reports_a_registered_agents_state(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".codex").mkdir()
    detect = _detect(agent_bundle, {AgentType.CODEX: installed("0.155.1")})
    got = await detect.detect(AgentType.CODEX, tmp_path / ".codex")
    assert (got.state, got.version) == (DetectionState.INSTALLED_ACTIVE, "0.155.1")
    gone = await _detect(agent_bundle).detect(AgentType.CODEX, tmp_path / "nowhere")
    assert gone.state is DetectionState.MISSING


# ---------------------------------------------------------------------------
# Privileged-path defence — TEST25-103
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="agent-registry", scenario="reject registration into privileged system path"
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
        assert_skill_dir_usable(pathlib.Path(privileged), _rules())


def test_privileged_path_symlink_traversal_rejected(tmp_path):
    """A symlink pointing at /etc is rejected because resolve() is privileged.

    Spec agent-registry "Validate the config directory at registration": even
    if the user-supplied path is harmless-looking, the *resolved*
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
        assert_skill_dir_usable(link, _rules())


# ---------------------------------------------------------------------------
# assert_skill_dir_usable negative branches — TEST25-102
# ---------------------------------------------------------------------------


def test_assert_skill_dir_usable_directory_missing(tmp_path):
    """A non-existent skill_dir is rejected with `directory_missing`.

    "Validate the config directory at registration" requires the skill_dir to
    exist before registration — we don't silently accept a parent-writable +
    missing-dir case because skill loading would later fail in obscure ways.
    """
    target = tmp_path / "no-such-dir"
    with pytest.raises(SkillDirNotWritable) as ei:
        assert_skill_dir_usable(target, _rules())
    assert ei.value.reason == "directory_missing"


def test_assert_skill_dir_usable_not_a_directory(tmp_path):
    """A path that exists but is a file (not a dir) is rejected."""
    f = tmp_path / "skills"
    f.write_text("not a dir")
    with pytest.raises(SkillDirNotWritable) as ei:
        assert_skill_dir_usable(f, _rules())
    assert ei.value.reason == "not_a_directory"


def test_assert_skill_dir_usable_existing_dir_not_writable(tmp_path):
    """An existing dir without the write bit is rejected."""
    d = tmp_path / "skills"
    d.mkdir()
    orig_mode = d.stat().st_mode
    os.chmod(d, stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(SkillDirNotWritable) as ei:
            assert_skill_dir_usable(d, _rules())
        assert ei.value.reason == "not_writable"
    finally:
        os.chmod(d, orig_mode)


def test_assert_skill_dir_usable_tilde_expansion(tmp_path, monkeypatch):
    """TEST25-110: `~` in skill_dir expands against HOME before validation."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "skills").mkdir()
    # Should not raise; the path expands to <tmp_path>/skills which exists.
    assert_skill_dir_usable(pathlib.Path("~/skills"), _rules())


def test_firmlink_is_left_alone_where_the_host_has_none():
    """Without a firmlink root (Linux, Windows) ``/private`` is an ordinary path."""
    from coffer.application.agent.service import _strip_firmlink

    rules = PrivilegedPaths(prefixes=(), carve_outs=(), separator="/", firmlink_root=None)
    assert _strip_firmlink("/private/var/x", rules) == "/private/var/x"


def test_firmlink_root_itself_collapses_to_slash():
    """Bare ``/private`` on macOS collapses to ``/`` (covers the equality branch)."""
    from coffer.application.agent.service import _strip_firmlink

    rules = PrivilegedPaths(prefixes=(), carve_outs=(), separator="/", firmlink_root="/private")
    assert _strip_firmlink("/private", rules) == "/"
    assert _strip_firmlink("/private/etc/x", rules) == "/etc/x"
    assert _strip_firmlink("/privatefoo", rules) == "/privatefoo"


async def test_register_invalid_config_raises_config_validation_error(agent_bundle):
    """A config_dir that fails pydantic field validation surfaces as ConfigValidationError."""
    from coffer.domain.errors import ConfigValidationError

    with pytest.raises(ConfigValidationError):
        await agent_bundle.svc.register(
            agent_type=AgentType.CODEX,
            config_dir="   ",  # whitespace-only → rejected by AgentConfig
            actor="cli",
        )


async def test_update_config_dir_invalid_raises_config_validation_error(agent_bundle, tmp_path):
    """An update with an invalid (relative) config_dir surfaces as ConfigValidationError."""
    from coffer.domain.errors import ConfigValidationError

    custom = tmp_path / "cfg"
    custom.mkdir()
    agent = await agent_bundle.svc.register(
        agent_type=AgentType.CODEX, config_dir=str(custom), actor="cli"
    )
    with pytest.raises(ConfigValidationError):
        await agent_bundle.svc.update_config_dir(
            uid=agent.uid, new_config_dir="relative/path", actor="cli"
        )


# ---------------------------------------------------------------------------
# Audit lifecycle — pre-existing scenario, kept for spec coverage
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="agent-registry", scenario="audit lifecycle events")
async def test_audit_records_lifecycle_events(agent_bundle, tmp_path):
    custom = tmp_path / "cfg"
    custom.mkdir()
    new = tmp_path / "cfg2"
    new.mkdir()
    agent = await agent_bundle.svc.register(
        agent_type=AgentType.CODEX, config_dir=str(custom), actor="cli"
    )
    # The lifecycle is create, update, remove (each via the kind-agnostic
    # resource_* events); the enable/disable toggle is audited the same way and
    # covered by test_skill_delivery.py.
    await agent_bundle.svc.update_config_dir(uid=agent.uid, new_config_dir=str(new), actor="cli")
    await agent_bundle.svc.remove(uid=agent.uid, actor="cli")

    created = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_CREATED.value)
    updated = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_UPDATED.value)
    deleted = await agent_bundle.audit.query(event_type=AuditEventType.RESOURCE_DELETED.value)
    assert len(created) == len(updated) == len(deleted) == 1
