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
