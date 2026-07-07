"""AgentService.set_disable_native_memory — persist field + on-disk transform.

Slice 6 opt-in toggle: enabling writes the AgentConfig field AND the native
write-side memory disable into the agent's config file (Claude settings.json
``autoMemoryEnabled=false``; Codex config.toml ``features.memories`` +
``memories.generate_memories``). Disabling restores both.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType

pytestmark = pytest.mark.asyncio


async def _register_claude(bundle, home: pathlib.Path):
    (home / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    await bundle.svc.register(agent_type=AgentType.CLAUDE_CODE, name="cc", actor="cli")


async def _register_codex(bundle, home: pathlib.Path):
    (home / ".codex" / "skills").mkdir(parents=True, exist_ok=True)
    await bundle.svc.register(agent_type=AgentType.CODEX, name="cx", actor="cli")


async def _register_opencode(bundle, home: pathlib.Path):
    (home / ".config" / "opencode" / "skills").mkdir(parents=True, exist_ok=True)
    await bundle.svc.register(agent_type=AgentType.OPENCODE, name="oc", actor="cli")


async def test_opencode_native_memory_disable_is_unsupported(agent_bundle, tmp_path, monkeypatch):
    # opencode has no native write-side memory (ADR-040): the toggle is an absent
    # facet, so the service rejects it (422) rather than raising AssertionError/500.
    from coffer.domain.workspace_errors import NativeMemoryDisableUnsupported

    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_opencode(agent_bundle, tmp_path)

    with pytest.raises(NativeMemoryDisableUnsupported):
        await agent_bundle.svc.set_disable_native_memory(name="oc", enabled=True, actor="ui")


async def test_enable_persists_field_and_writes_claude_settings(
    agent_bundle, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")

    r = await agent_bundle.svc.set_disable_native_memory(name="cc", enabled=True, actor="ui")
    cfg = AgentConfig.model_validate(r.config)
    assert cfg.disable_native_memory is True

    data = json.loads(settings.read_text())
    assert data["autoMemoryEnabled"] is False
    assert data["theme"] == "dark"  # preserved
    assert (tmp_path / ".claude" / "settings.json.bak").exists()

    rows = await agent_bundle.audit.query(
        kind="agent", name="cc", event_type=AuditEventType.AGENT_NATIVE_MEMORY_DISABLED.value
    )
    assert len(rows) == 1


@pytest.mark.acceptance(
    spec="007-memory", scenario="disable_native_memory turns native memory off and restores it"
)
async def test_disable_restores_claude_settings(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    await agent_bundle.svc.set_disable_native_memory(name="cc", enabled=True, actor="ui")

    r = await agent_bundle.svc.set_disable_native_memory(name="cc", enabled=False, actor="ui")
    assert AgentConfig.model_validate(r.config).disable_native_memory is False
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "autoMemoryEnabled" not in data

    rows = await agent_bundle.audit.query(
        kind="agent", name="cc", event_type=AuditEventType.AGENT_NATIVE_MEMORY_RESTORED.value
    )
    assert len(rows) == 1


async def test_enable_writes_codex_toml(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_codex(agent_bundle, tmp_path)
    cfg_file = tmp_path / ".codex" / "config.toml"
    cfg_file.write_text('model = "o1"\n', encoding="utf-8")

    await agent_bundle.svc.set_disable_native_memory(name="cx", enabled=True, actor="ui")
    text = cfg_file.read_text()
    assert 'model = "o1"' in text  # preserved
    assert "memories = false" in text
    assert "generate_memories = false" in text


async def test_idempotent_enable(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    await agent_bundle.svc.set_disable_native_memory(name="cc", enabled=True, actor="ui")
    r = await agent_bundle.svc.set_disable_native_memory(name="cc", enabled=True, actor="ui")
    assert AgentConfig.model_validate(r.config).disable_native_memory is True
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert data["autoMemoryEnabled"] is False
