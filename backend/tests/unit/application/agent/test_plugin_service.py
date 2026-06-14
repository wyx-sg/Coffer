"""Unit tests for AgentPluginService.

Uses a dict-backed fake ConfigFileStorePort, a fake _AgentLookup (claude_code
'cc' + codex 'cx'), and a fake AuditRepo — no real FS, DB, or keychain.

Covers:
 1. list_codex_groups_and_cache_flag — two plugins, cache present/absent
 2. list_codex_missing_config_empty — no config.toml → empty PluginsOut
 3. list_codex_parse_error_degrades — broken toml → parse_errors populated
 4. list_claude_inventory_and_enabled — inventory + settings enabled flags
 5. toggle_codex_writes_config_only — enabled flag flipped; audit pinned
 6. toggle_claude_writes_settings_only_internal_untouched — internal files untouched
 7. uninstall_claude_rejected — PluginUninstallUnsupported, zero writes
 8. uninstall_codex_removes_entry_and_cache — entry gone; rmtree called; audit
 9. uninstall_codex_cache_missing_ok — no rmtree; cache_removed: False
10. uninstall_codex_unknown_plugin_404 — PluginNotFound, no write/rmtree
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar

import pytest
import pytest_asyncio

from coffer.application.agent.plugin_service import AgentPluginService
from coffer.application.audit_service import AuditService
from coffer.domain.agent.config_files import FileStat, spec_for
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource
from coffer.domain.workspace_errors import (
    PluginNotFound,
    PluginToggleUnsupported,
    PluginUninstallUnsupported,
)

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

_CLAUDE_CONFIG_DIR = pathlib.Path("/fake/home/.claude")
_CODEX_CONFIG_DIR = pathlib.Path("/fake/home/.codex")

_CLAUDE_SETTINGS = spec_for(AgentType.CLAUDE_CODE, "settings", _CLAUDE_CONFIG_DIR).path
_CODEX_CONFIG = spec_for(AgentType.CODEX, "config", _CODEX_CONFIG_DIR).path

_CLAUDE_INSTALLED = _CLAUDE_CONFIG_DIR / "plugins" / "installed_plugins.json"
_CLAUDE_MARKETPLACES = _CLAUDE_CONFIG_DIR / "plugins" / "known_marketplaces.json"

_CURSOR_CONFIG_DIR = pathlib.Path("/fake/home/.cursor")
_OPENCODE_CONFIG_DIR = pathlib.Path("/fake/home/.config/opencode")
_OPENCLAW_CONFIG_DIR = pathlib.Path("/fake/home/.openclaw")
_HERMES_CONFIG_DIR = pathlib.Path("/fake/home/.hermes")

_CURSOR_EXTENSIONS = _CURSOR_CONFIG_DIR / "extensions" / "extensions.json"
_OPENCODE_CONFIG = spec_for(AgentType.OPENCODE, "config", _OPENCODE_CONFIG_DIR).path
_OPENCLAW_CONFIG = spec_for(AgentType.OPENCLAW, "config", _OPENCLAW_CONFIG_DIR).path

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _agent_resource(name: str, agent_type: str, config_dir: pathlib.Path) -> Resource:
    return Resource(
        id=1,
        kind="agent",
        name=name,
        description=None,
        config={"type": agent_type, "config_dir": str(config_dir)},
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


class FakeAgentLookup:
    """Map fixture names to agents of each supported type; else 404."""

    _AGENTS: ClassVar[dict[str, tuple[str, pathlib.Path]]] = {
        "cc": ("claude_code", _CLAUDE_CONFIG_DIR),
        "cx": ("codex", _CODEX_CONFIG_DIR),
        "cu": ("cursor", _CURSOR_CONFIG_DIR),
        "oc": ("opencode", _OPENCODE_CONFIG_DIR),
        "ow": ("openclaw", _OPENCLAW_CONFIG_DIR),
        "he": ("hermes", _HERMES_CONFIG_DIR),
    }

    async def get(self, name: str) -> Resource:
        if name in self._AGENTS:
            agent_type, config_dir = self._AGENTS[name]
            return _agent_resource(name, agent_type, config_dir)
        raise ResourceNotFound("agent", name)


@dataclass
class FakeStore:
    """Dict-backed ConfigFileStorePort (only the methods this service uses)."""

    _files: dict[pathlib.Path, str] = field(default_factory=dict)
    _writes: list[tuple[pathlib.Path, str]] = field(default_factory=list)

    def read_text(self, path: pathlib.Path) -> str | None:
        return self._files.get(path)

    def stat(self, path: pathlib.Path) -> FileStat | None:
        text = self._files.get(path)
        if text is None:
            return None
        return FileStat(size=len(text.encode()), modified_at=_NOW)

    def write_text_atomic(self, path: pathlib.Path, text: str) -> None:
        self._writes.append((path, text))
        self._files[path] = text

    def list_dir(self, root: pathlib.Path):
        return None

    def delete_with_backup(self, path: pathlib.Path) -> bool:
        if path not in self._files:
            return False
        del self._files[path]
        return True

    def fingerprint(self, text: str | None) -> str:
        return "" if text is None else f"fp:{hash(text)}"

    def resolved_within(self, path: pathlib.Path, root: pathlib.Path) -> bool:
        return True


class FakeAuditRepo:
    def __init__(self) -> None:
        self._entries: list = []

    async def insert(self, entry) -> None:
        self._entries.append(entry)

    async def query(self, *, kind=None, name=None, event_type=None, since=None, limit=50):
        results = self._entries
        if event_type is not None:
            results = [e for e in results if e.event_type == event_type]
        return results[:limit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def store() -> FakeStore:
    return FakeStore()


@pytest_asyncio.fixture
async def audit_svc() -> AuditService:
    return AuditService(FakeAuditRepo())


def _make_svc(
    store: FakeStore,
    audit_svc: AuditService,
    *,
    cache_dirs: set[pathlib.Path] | None = None,
    rmtree_calls: list[pathlib.Path] | None = None,
) -> AgentPluginService:
    _cache_dirs: set[pathlib.Path] = cache_dirs if cache_dirs is not None else set()
    _rmtree_calls: list[pathlib.Path] = rmtree_calls if rmtree_calls is not None else []

    def _dir_exists(p: pathlib.Path) -> bool:
        return p in _cache_dirs

    def _rmtree(p: pathlib.Path) -> None:
        _rmtree_calls.append(p)
        _cache_dirs.discard(p)

    return AgentPluginService(
        agent_service=FakeAgentLookup(),
        audit=audit_svc,
        store=store,
        dir_exists=_dir_exists,
        rmtree=_rmtree,
    )


# ---------------------------------------------------------------------------
# TOML / JSON fixtures
# ---------------------------------------------------------------------------

_CODEX_TOML_WITH_PLUGINS = """\
[marketplaces.npm]
source_type = "npm"
source = "https://registry.npmjs.org"

[marketplaces.pypi]
source_type = "pypi"
source = "https://pypi.org"

[plugins."lint-tool@npm"]
enabled = true

[plugins."format-tool@pypi"]
enabled = false
"""

_INSTALLED_JSON = """\
{
  "version": 2,
  "plugins": {
    "plugin-a@npm": [],
    "plugin-b@pypi": []
  }
}
"""

_MARKETPLACES_JSON = """\
{
  "npm": {"source": {"source": "npm", "repo": "https://registry.npmjs.org"}}
}
"""

_SETTINGS_JSON_DISABLED_B = """\
{
  "enabledPlugins": {
    "plugin-b@pypi": false
  }
}
"""

# ---------------------------------------------------------------------------
# 1. list_codex_groups_and_cache_flag
# ---------------------------------------------------------------------------


async def test_list_codex_groups_and_cache_flag(store, audit_svc):
    store._files[_CODEX_CONFIG] = _CODEX_TOML_WITH_PLUGINS
    # Only the first plugin has a cache directory.
    cache_dirs: set[pathlib.Path] = {_CODEX_CONFIG_DIR / "plugins" / "cache" / "npm" / "lint-tool"}
    svc = _make_svc(store, audit_svc, cache_dirs=cache_dirs)

    out = await svc.list_plugins("cx")

    assert out.parse_errors == []
    by_id = {v.id: v for v in out.items}
    assert set(by_id) == {"lint-tool@npm", "format-tool@pypi"}

    assert by_id["lint-tool@npm"].cache_present is True
    assert by_id["lint-tool@npm"].enabled is True
    assert by_id["format-tool@pypi"].cache_present is False
    assert by_id["format-tool@pypi"].enabled is False

    mkt_names = {m.name for m in out.marketplaces}
    assert mkt_names == {"npm", "pypi"}


# ---------------------------------------------------------------------------
# 2. list_codex_missing_config_empty
# ---------------------------------------------------------------------------


async def test_list_codex_missing_config_empty(store, audit_svc):
    # No config.toml in the store.
    svc = _make_svc(store, audit_svc)

    out = await svc.list_plugins("cx")

    assert out.items == []
    assert out.marketplaces == []
    assert out.parse_errors == []


# ---------------------------------------------------------------------------
# 3. list_codex_parse_error_degrades
# ---------------------------------------------------------------------------


async def test_list_codex_parse_error_degrades(store, audit_svc):
    store._files[_CODEX_CONFIG] = "[[[[broken toml"
    svc = _make_svc(store, audit_svc)

    out = await svc.list_plugins("cx")

    assert out.items == []
    assert len(out.parse_errors) == 1
    err = out.parse_errors[0]
    assert err.source == "config"
    assert err.path == str(_CODEX_CONFIG)
    assert err.error


# ---------------------------------------------------------------------------
# 4. list_claude_inventory_and_enabled
# ---------------------------------------------------------------------------


async def test_list_claude_inventory_and_enabled(store, audit_svc):
    store._files[_CLAUDE_INSTALLED] = _INSTALLED_JSON
    store._files[_CLAUDE_MARKETPLACES] = _MARKETPLACES_JSON
    store._files[_CLAUDE_SETTINGS] = _SETTINGS_JSON_DISABLED_B
    svc = _make_svc(store, audit_svc)

    out = await svc.list_plugins("cc")

    assert out.parse_errors == []
    by_id = {v.id: v for v in out.items}
    # Both installed plugins should appear.
    assert "plugin-a@npm" in by_id
    assert "plugin-b@pypi" in by_id
    # plugin-a not in enabledPlugins → enabled=True (default)
    assert by_id["plugin-a@npm"].enabled is True
    # plugin-b explicitly disabled in settings
    assert by_id["plugin-b@pypi"].enabled is False
    # cache_present = "was in installed inventory"
    assert by_id["plugin-a@npm"].cache_present is True
    assert by_id["plugin-b@pypi"].cache_present is True
    # marketplaces come from known_marketplaces.json
    assert any(m.name == "npm" for m in out.marketplaces)


async def test_list_claude_settings_only_orphan_gets_false_cache(store, audit_svc):
    """A plugin that only appears in settings (not inventory) gets cache_present=False."""
    # No installed_plugins.json; settings references a phantom id.
    store._files[_CLAUDE_SETTINGS] = '{"enabledPlugins": {"orphan@npm": false}}'
    svc = _make_svc(store, audit_svc)

    out = await svc.list_plugins("cc")

    assert out.parse_errors == []
    by_id = {v.id: v for v in out.items}
    assert "orphan@npm" in by_id
    assert by_id["orphan@npm"].cache_present is False


# ---------------------------------------------------------------------------
# 5. toggle_codex_writes_config_only
# ---------------------------------------------------------------------------


async def test_toggle_codex_writes_config_only(store, audit_svc):
    store._files[_CODEX_CONFIG] = _CODEX_TOML_WITH_PLUGINS
    svc = _make_svc(store, audit_svc)

    await svc.set_enabled("cx", "lint-tool@npm", False, actor="cli")

    # Only config.toml was written.
    written_paths = [p for p, _ in store._writes]
    assert written_paths == [_CODEX_CONFIG]

    # The updated file should have enabled = false for the toggled plugin.
    new_text = store._files[_CODEX_CONFIG]
    assert "enabled = false" in new_text

    # Audit event
    entries = await audit_svc.query(event_type=AuditEventType.AGENT_PLUGIN_TOGGLED.value)
    assert len(entries) == 1
    assert entries[0].details == {"plugin": "lint-tool@npm", "enabled": False}
    assert entries[0].actor == "cli"


# ---------------------------------------------------------------------------
# 6. toggle_claude_writes_settings_only_internal_untouched
# ---------------------------------------------------------------------------


async def test_toggle_claude_writes_settings_only_internal_untouched(store, audit_svc):
    store._files[_CLAUDE_INSTALLED] = _INSTALLED_JSON
    store._files[_CLAUDE_MARKETPLACES] = _MARKETPLACES_JSON
    store._files[_CLAUDE_SETTINGS] = _SETTINGS_JSON_DISABLED_B
    svc = _make_svc(store, audit_svc)

    # Toggle plugin-a to disabled.
    await svc.set_enabled("cc", "plugin-a@npm", False, actor="test")

    # Only settings.json was written; internal files untouched.
    written_paths = [p for p, _ in store._writes]
    assert written_paths == [_CLAUDE_SETTINGS]
    # Internal files are byte-identical.
    assert store._files[_CLAUDE_INSTALLED] == _INSTALLED_JSON
    assert store._files[_CLAUDE_MARKETPLACES] == _MARKETPLACES_JSON

    # New settings content should have the plugin disabled.
    import json as _json

    new_settings = _json.loads(store._files[_CLAUDE_SETTINGS])
    assert new_settings["enabledPlugins"]["plugin-a@npm"] is False

    # Audit pinned
    entries = await audit_svc.query(event_type=AuditEventType.AGENT_PLUGIN_TOGGLED.value)
    assert len(entries) == 1
    assert entries[0].details == {"plugin": "plugin-a@npm", "enabled": False}


# ---------------------------------------------------------------------------
# 7. uninstall_claude_rejected
# ---------------------------------------------------------------------------


async def test_uninstall_claude_rejected(store, audit_svc):
    store._files[_CLAUDE_INSTALLED] = _INSTALLED_JSON
    svc = _make_svc(store, audit_svc)

    with pytest.raises(PluginUninstallUnsupported):
        await svc.uninstall("cc", "plugin-a@npm")

    # No writes, no audit events.
    assert store._writes == []
    entries = await audit_svc.query(event_type=AuditEventType.AGENT_PLUGIN_UNINSTALLED.value)
    assert entries == []


# ---------------------------------------------------------------------------
# 8. uninstall_codex_removes_entry_and_cache
# ---------------------------------------------------------------------------


async def test_uninstall_codex_removes_entry_and_cache(store, audit_svc):
    store._files[_CODEX_CONFIG] = _CODEX_TOML_WITH_PLUGINS
    cache_dir = _CODEX_CONFIG_DIR / "plugins" / "cache" / "npm" / "lint-tool"
    rmtree_calls: list[pathlib.Path] = []
    cache_dirs: set[pathlib.Path] = {cache_dir}
    svc = _make_svc(store, audit_svc, cache_dirs=cache_dirs, rmtree_calls=rmtree_calls)

    await svc.uninstall("cx", "lint-tool@npm", actor="cli")

    # Config was written.
    assert len(store._writes) == 1
    new_text = store._files[_CODEX_CONFIG]
    assert "lint-tool@npm" not in new_text
    # The other plugin and marketplaces survive.
    assert "format-tool@pypi" in new_text

    # Cache removed.
    assert rmtree_calls == [cache_dir]

    # Audit event with cache_removed=True.
    entries = await audit_svc.query(event_type=AuditEventType.AGENT_PLUGIN_UNINSTALLED.value)
    assert len(entries) == 1
    assert entries[0].details == {"plugin": "lint-tool@npm", "cache_removed": True}


# ---------------------------------------------------------------------------
# 9. uninstall_codex_cache_missing_ok
# ---------------------------------------------------------------------------


async def test_uninstall_codex_cache_missing_ok(store, audit_svc):
    store._files[_CODEX_CONFIG] = _CODEX_TOML_WITH_PLUGINS
    rmtree_calls: list[pathlib.Path] = []
    # No cache directories exist.
    svc = _make_svc(store, audit_svc, cache_dirs=set(), rmtree_calls=rmtree_calls)

    await svc.uninstall("cx", "format-tool@pypi")

    # Entry removed.
    new_text = store._files[_CODEX_CONFIG]
    assert "format-tool@pypi" not in new_text

    # No rmtree call.
    assert rmtree_calls == []

    entries = await audit_svc.query(event_type=AuditEventType.AGENT_PLUGIN_UNINSTALLED.value)
    assert len(entries) == 1
    assert entries[0].details == {"plugin": "format-tool@pypi", "cache_removed": False}


# ---------------------------------------------------------------------------
# 10. uninstall_codex_unknown_plugin_404
# ---------------------------------------------------------------------------


async def test_uninstall_codex_unknown_plugin_404(store, audit_svc):
    store._files[_CODEX_CONFIG] = _CODEX_TOML_WITH_PLUGINS
    rmtree_calls: list[pathlib.Path] = []
    svc = _make_svc(store, audit_svc, cache_dirs=set(), rmtree_calls=rmtree_calls)

    with pytest.raises(PluginNotFound):
        await svc.uninstall("cx", "nonexistent@npm")

    # No writes, no rmtree, no audit events.
    assert store._writes == []
    assert rmtree_calls == []
    entries = await audit_svc.query(event_type=AuditEventType.AGENT_PLUGIN_UNINSTALLED.value)
    assert entries == []


# ---------------------------------------------------------------------------
# Cursor (read-only)
# ---------------------------------------------------------------------------

_CURSOR_EXTENSIONS_JSON = json.dumps(
    [
        {"identifier": {"id": "ms-python.python"}, "version": "1.0.0"},
        {"identifier": {"id": "esbenp.prettier-vscode"}, "version": "2.0.0"},
    ]
)


async def test_list_cursor_extensions(store, audit_svc):
    store._files[_CURSOR_EXTENSIONS] = _CURSOR_EXTENSIONS_JSON
    svc = _make_svc(store, audit_svc)

    out = await svc.list_plugins("cu")

    assert out.parse_errors == []
    assert {v.id for v in out.items} == {"ms-python.python", "esbenp.prettier-vscode"}
    assert all(v.enabled for v in out.items)
    assert out.marketplaces == []


async def test_list_cursor_missing_empty(store, audit_svc):
    svc = _make_svc(store, audit_svc)
    out = await svc.list_plugins("cu")
    assert out.items == [] and out.parse_errors == []


async def test_toggle_cursor_unsupported(store, audit_svc):
    store._files[_CURSOR_EXTENSIONS] = _CURSOR_EXTENSIONS_JSON
    svc = _make_svc(store, audit_svc)
    with pytest.raises(PluginToggleUnsupported):
        await svc.set_enabled("cu", "ms-python.python", False)
    assert store._writes == []


async def test_uninstall_cursor_unsupported(store, audit_svc):
    store._files[_CURSOR_EXTENSIONS] = _CURSOR_EXTENSIONS_JSON
    svc = _make_svc(store, audit_svc)
    with pytest.raises(PluginUninstallUnsupported):
        await svc.uninstall("cu", "ms-python.python")
    assert store._writes == []


# ---------------------------------------------------------------------------
# OpenCode (toggle/uninstall = membership in the "plugin" array)
# ---------------------------------------------------------------------------

_OPENCODE_JSON = json.dumps({"plugin": ["alpha", "beta"], "other": 1})


async def test_list_opencode_plugins(store, audit_svc):
    store._files[_OPENCODE_CONFIG] = _OPENCODE_JSON
    svc = _make_svc(store, audit_svc)

    out = await svc.list_plugins("oc")

    assert out.parse_errors == []
    assert {v.id for v in out.items} == {"alpha", "beta"}
    assert all(v.enabled for v in out.items)


async def test_toggle_opencode_writes_config(store, audit_svc):
    store._files[_OPENCODE_CONFIG] = _OPENCODE_JSON
    svc = _make_svc(store, audit_svc)

    await svc.set_enabled("oc", "alpha", False, actor="cli")

    written = [p for p, _ in store._writes]
    assert written == [_OPENCODE_CONFIG]
    data = json.loads(store._files[_OPENCODE_CONFIG])
    assert "alpha" not in data["plugin"]
    assert data["other"] == 1  # siblings survive

    entries = await audit_svc.query(event_type=AuditEventType.AGENT_PLUGIN_TOGGLED.value)
    assert len(entries) == 1
    assert entries[0].details == {"plugin": "alpha", "enabled": False}


async def test_uninstall_opencode_removes_entry(store, audit_svc):
    store._files[_OPENCODE_CONFIG] = _OPENCODE_JSON
    rmtree_calls: list[pathlib.Path] = []
    svc = _make_svc(store, audit_svc, rmtree_calls=rmtree_calls)

    await svc.uninstall("oc", "beta", actor="cli")

    data = json.loads(store._files[_OPENCODE_CONFIG])
    assert "beta" not in data["plugin"]
    # OpenCode has no plugin cache directory to remove.
    assert rmtree_calls == []
    entries = await audit_svc.query(event_type=AuditEventType.AGENT_PLUGIN_UNINSTALLED.value)
    assert len(entries) == 1
    assert entries[0].details["plugin"] == "beta"


async def test_uninstall_opencode_unknown_404(store, audit_svc):
    store._files[_OPENCODE_CONFIG] = _OPENCODE_JSON
    svc = _make_svc(store, audit_svc)
    with pytest.raises(PluginNotFound):
        await svc.uninstall("oc", "ghost")


# ---------------------------------------------------------------------------
# OpenClaw (the plugins{} block)
# ---------------------------------------------------------------------------

_OPENCLAW_JSON = json.dumps(
    {"plugins": {"entries": ["alpha", "beta"], "enabled": ["alpha"], "deny": ["beta"]}}
)


async def test_list_openclaw_plugins(store, audit_svc):
    store._files[_OPENCLAW_CONFIG] = _OPENCLAW_JSON
    svc = _make_svc(store, audit_svc)

    out = await svc.list_plugins("ow")

    assert out.parse_errors == []
    by_id = {v.id: v.enabled for v in out.items}
    assert by_id == {"alpha": True, "beta": False}


async def test_toggle_openclaw_writes_config(store, audit_svc):
    store._files[_OPENCLAW_CONFIG] = _OPENCLAW_JSON
    svc = _make_svc(store, audit_svc)

    await svc.set_enabled("ow", "beta", True, actor="cli")

    written = [p for p, _ in store._writes]
    assert written == [_OPENCLAW_CONFIG]
    out = await svc.list_plugins("ow")
    assert {v.id: v.enabled for v in out.items}["beta"] is True


async def test_uninstall_openclaw_removes_entry(store, audit_svc):
    store._files[_OPENCLAW_CONFIG] = _OPENCLAW_JSON
    svc = _make_svc(store, audit_svc)

    await svc.uninstall("ow", "alpha", actor="cli")

    out = await svc.list_plugins("ow")
    assert "alpha" not in {v.id for v in out.items}
    entries = await audit_svc.query(event_type=AuditEventType.AGENT_PLUGIN_UNINSTALLED.value)
    assert len(entries) == 1


# ---------------------------------------------------------------------------
# Hermes (N/A — MCP is the plugin mechanism)
# ---------------------------------------------------------------------------


async def test_list_hermes_empty(store, audit_svc):
    svc = _make_svc(store, audit_svc)
    out = await svc.list_plugins("he")
    assert out.items == [] and out.marketplaces == [] and out.parse_errors == []


async def test_toggle_hermes_unsupported(store, audit_svc):
    svc = _make_svc(store, audit_svc)
    with pytest.raises(PluginToggleUnsupported):
        await svc.set_enabled("he", "anything", True)
    assert store._writes == []


async def test_uninstall_hermes_unsupported(store, audit_svc):
    svc = _make_svc(store, audit_svc)
    with pytest.raises(PluginUninstallUnsupported):
        await svc.uninstall("he", "anything")
    assert store._writes == []
