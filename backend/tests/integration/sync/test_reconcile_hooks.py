"""The real per-kind reconcile hooks (spec 010 import reconciliation):
provider projection and agent side-effects, driven against tmp config dirs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from coffer.application.agent.sync_reconcile import AgentImportGate, AgentSideEffectsReconcile
from coffer.application.provider.projector import ProviderProjector
from coffer.application.provider.sync_reconcile import ProviderProjectionReconcile
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.config_file_store import ConfigFileStore


def _resource(kind: str, name: str, config: dict) -> Resource:  # type: ignore[type-arg]
    now = datetime.now(tz=UTC)
    return Resource(
        id=1,
        kind=kind,
        name=name,
        description=None,
        enabled=True,
        config=config,
        created_at=now,
        updated_at=now,
    )


class _Rows:
    def __init__(self, rows: list[Resource]) -> None:
        self._rows = rows

    async def list(self) -> list[Resource]:
        return self._rows


def _claude_agent(tmp_path: Path, *, disable_native_memory: bool = False) -> Resource:
    config_dir = tmp_path / ".claude"
    (config_dir / "skills").mkdir(parents=True, exist_ok=True)
    return _resource(
        "agent",
        "claude-code",
        {
            "type": "claude_code",
            "config_dir": str(config_dir),
            "disable_native_memory": disable_native_memory,
        },
    )


def _provider(name: str, *, is_active: bool) -> Resource:
    return _resource(
        "provider",
        name,
        {
            "protocol": "anthropic",
            "base_url": "https://api.example.com",
            "credential_ref": f"provider/{name}/key",
            "is_active": is_active,
            "internal_default": False,
        },
    )


@pytest.mark.acceptance(
    spec="010-sync", scenario="imported config re-applies its side-effects on this machine"
)
async def test_provider_hook_projects_and_deprojects(tmp_path) -> None:  # type: ignore[no-untyped-def]
    agent = _claude_agent(tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    projector = ProviderProjector(ConfigFileStore())

    # An active connection arriving via import projects into the local agent.
    hook = ProviderProjectionReconcile(
        providers=_Rows([_provider("acme", is_active=True)]),
        agents=_Rows([agent]),
        projector=projector,
    )
    assert await hook.reconcile() == []
    assert "apiKeyHelper" in json.loads(settings.read_text())

    # The deactivation arriving via import converges back to built-in.
    hook = ProviderProjectionReconcile(
        providers=_Rows([_provider("acme", is_active=False)]),
        agents=_Rows([agent]),
        projector=projector,
    )
    assert await hook.reconcile() == []
    assert "apiKeyHelper" not in json.loads(settings.read_text())


async def test_agent_hook_applies_native_memory_transform(tmp_path) -> None:  # type: ignore[no-untyped-def]
    agent = _claude_agent(tmp_path, disable_native_memory=True)
    settings = tmp_path / ".claude" / "settings.json"
    hook = AgentSideEffectsReconcile(_Rows([agent]), ConfigFileStore())  # type: ignore[arg-type]

    assert await hook.reconcile() == []
    assert json.loads(settings.read_text())["autoMemoryEnabled"] is False

    # Idempotent: a second pass leaves the file byte-identical.
    before = settings.read_text()
    assert await hook.reconcile() == []
    assert settings.read_text() == before

    # The flag flipping back (imported from another machine) restores.
    restored = _claude_agent(tmp_path, disable_native_memory=False)
    hook = AgentSideEffectsReconcile(_Rows([restored]), ConfigFileStore())  # type: ignore[arg-type]
    assert await hook.reconcile() == []
    assert json.loads(settings.read_text()).get("autoMemoryEnabled") is not False


async def test_agent_gate_requires_installed_config_dir(tmp_path) -> None:  # type: ignore[no-untyped-def]
    gate = AgentImportGate()
    # Installed: config dir exists → passes (and creates the skills leaf).
    installed = tmp_path / ".claude"
    installed.mkdir()
    await gate.validate({"type": "claude_code", "config_dir": str(installed)})

    # Not installed here: quarantining CofferError.
    from coffer.domain.error_base import CofferError

    with pytest.raises(CofferError):
        await gate.validate({"type": "claude_code", "config_dir": str(tmp_path / "missing")})


async def test_agent_hook_never_rewrites_converged_files(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Semantic convergence (review #291 finding 1): an already-correct file
    is never rewritten (no reformat), and a missing file with the flag off is
    never created."""
    agent = _claude_agent(tmp_path, disable_native_memory=False)
    settings = tmp_path / ".claude" / "settings.json"
    hook = AgentSideEffectsReconcile(_Rows([agent]), ConfigFileStore())  # type: ignore[arg-type]

    # Missing file + flag off: nothing to restore — no `{}` file appears.
    assert await hook.reconcile() == []
    assert not settings.exists()

    # A user-formatted (4-space) file that is already semantically correct
    # stays byte-identical — no normalization, no .bak churn.
    settings.write_text('{\n    "model": "opus"\n}\n', encoding="utf-8")
    before = settings.read_text()
    assert await hook.reconcile() == []
    assert settings.read_text() == before


async def test_agent_hook_skips_vanished_config_dir(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A stale row whose config dir vanished is reported and left alone —
    never resurrected by a reconcile write (review #291 findings 1/5)."""
    agent = _resource(
        "agent",
        "gone",
        {
            "type": "claude_code",
            "config_dir": str(tmp_path / "vanished"),
            "disable_native_memory": True,
        },
    )
    hook = AgentSideEffectsReconcile(_Rows([agent]), ConfigFileStore())  # type: ignore[arg-type]
    errors = await hook.reconcile()
    assert errors and "config dir missing" in errors[0]
    assert not (tmp_path / "vanished").exists()


async def test_provider_hook_double_active_is_deterministic(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Two active connections for one type (transient merge state, review
    #291 finding 2): the first NAME wins on every machine, and the anomaly is
    surfaced."""
    agent = _claude_agent(tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    projector = ProviderProjector(ConfigFileStore())
    rows = [_provider("zeta", is_active=True), _provider("acme", is_active=True)]

    for ordering in (rows, list(reversed(rows))):
        hook = ProviderProjectionReconcile(
            providers=_Rows(ordering), agents=_Rows([agent]), projector=projector
        )
        errors = await hook.reconcile()
        assert any("multiple active connections" in e for e in errors)
        helper = json.loads(settings.read_text())["apiKeyHelper"]
        assert "acme" in helper and "zeta" not in helper
