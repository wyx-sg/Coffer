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
from coffer.domain.agent.plugin_bundle import PluginDetail
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource
from coffer.domain.workspace_errors import (
    PluginNotFound,
    PluginUninstallFailed,
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


class FakeDetailReader:
    """Maps install paths to PluginDetail and records which paths were read."""

    def __init__(self, by_path: dict[str, PluginDetail]) -> None:
        self._by_path = by_path
        self.calls: list[str] = []

    def read(self, install_path: str) -> PluginDetail | None:
        self.calls.append(install_path)
        return self._by_path.get(install_path)


class FakeCliRunner:
    """Stands in for the agent's plugin CLI (Claude). Records uninstall calls."""

    def __init__(self, *, available: bool = True, fail: Exception | None = None) -> None:
        self._available = available
        self._fail = fail
        self.calls: list[str] = []

    def available(self) -> bool:
        return self._available

    def uninstall(self, plugin_id: str) -> None:
        self.calls.append(plugin_id)
        if self._fail is not None:
            raise self._fail


def _make_svc(
    store: FakeStore,
    audit_svc: AuditService,
    *,
    cache_dirs: set[pathlib.Path] | None = None,
    rmtree_calls: list[pathlib.Path] | None = None,
    detail_reader: FakeDetailReader | None = None,
    cli_runner: FakeCliRunner | None = None,
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
        detail_reader=detail_reader,
        cli_runner=cli_runner,
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


async def test_list_codex_surfaces_detail_from_reader(store, audit_svc):
    """Codex plugins get the same bundled detail as Claude: the service hands
    the reader the cache <marketplace>/<name> dir (Codex records no path)."""
    store._files[_CODEX_CONFIG] = _CODEX_TOML_WITH_PLUGINS
    name_dir = str(_CODEX_CONFIG_DIR / "plugins" / "cache" / "npm" / "lint-tool")
    reader = FakeDetailReader(
        {
            name_dir: PluginDetail(
                version="1.0.0",
                description="Lints things",
                author="OpenAI",
                skills=("lint",),
            )
        }
    )
    svc = _make_svc(store, audit_svc, detail_reader=reader)

    out = await svc.list_plugins("cx")

    by_id = {v.id: v for v in out.items}
    lint = by_id["lint-tool@npm"]
    assert lint.version == "1.0.0"
    assert lint.description == "Lints things"
    assert lint.author == "OpenAI"
    assert lint.skills == ("lint",)
    # The reader was asked using the cache <marketplace>/<name> path.
    assert name_dir in reader.calls
    # The other plugin has no mapped detail → empty, no crash.
    assert by_id["format-tool@pypi"].description is None


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


async def test_list_claude_surfaces_detail_from_reader(store, audit_svc):
    """Claude listing carries version + bundled detail from the install path;
    a plugin with no install path (empty inventory record) reads nothing."""
    installed = json.dumps(
        {
            "version": 2,
            "plugins": {
                "plugin-a@npm": [{"installPath": "/cache/npm/plugin-a/1.2.3", "version": "1.2.3"}],
                "plugin-b@pypi": [],
            },
        }
    )
    store._files[_CLAUDE_INSTALLED] = installed
    reader = FakeDetailReader(
        {
            "/cache/npm/plugin-a/1.2.3": PluginDetail(
                description="Does A",
                author="Ada",
                homepage="https://example/a",
                skills=("alpha", "beta"),
                commands=("doit",),
                mcp_servers=(),
            )
        }
    )
    svc = _make_svc(store, audit_svc, detail_reader=reader)

    out = await svc.list_plugins("cc")

    by_id = {v.id: v for v in out.items}
    a = by_id["plugin-a@npm"]
    assert a.version == "1.2.3"
    assert a.description == "Does A"
    assert a.author == "Ada"
    assert a.homepage == "https://example/a"
    assert a.skills == ("alpha", "beta")
    assert a.commands == ("doit",)
    # plugin-b has no install path → reader never asked, detail empty.
    b = by_id["plugin-b@pypi"]
    assert b.version is None
    assert b.description is None
    assert b.skills == ()
    assert reader.calls == ["/cache/npm/plugin-a/1.2.3"]


async def test_list_claude_without_reader_has_no_detail(store, audit_svc):
    """With no detail reader wired, the listing carries only config-derived
    fields — the bundled-detail fields stay empty (no crash)."""
    store._files[_CLAUDE_INSTALLED] = _INSTALLED_JSON
    svc = _make_svc(store, audit_svc)  # detail_reader=None

    out = await svc.list_plugins("cc")

    assert out.parse_errors == []
    for v in out.items:
        assert v.version is None
        assert v.description is None
        assert v.skills == () and v.commands == () and v.mcp_servers == ()


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
# 7. uninstall_claude — CLI-mediated (never hand-writes internal files)
# ---------------------------------------------------------------------------


async def test_uninstall_claude_via_cli_calls_runner(store, audit_svc):
    store._files[_CLAUDE_INSTALLED] = _INSTALLED_JSON
    runner = FakeCliRunner(available=True)
    svc = _make_svc(store, audit_svc, cli_runner=runner)

    await svc.uninstall("cc", "plugin-a@npm", actor="cli")

    # Delegated to `claude plugin uninstall`; Coffer wrote no config files itself.
    assert runner.calls == ["plugin-a@npm"]
    assert store._writes == []
    entries = await audit_svc.query(event_type=AuditEventType.AGENT_PLUGIN_UNINSTALLED.value)
    assert len(entries) == 1
    assert entries[0].details == {"plugin": "plugin-a@npm", "cache_removed": True, "via": "cli"}


async def test_uninstall_claude_without_cli_runner_rejected(store, audit_svc):
    # No runner wired → uninstall is unavailable (the listing hides the button).
    svc = _make_svc(store, audit_svc)
    with pytest.raises(PluginUninstallUnsupported):
        await svc.uninstall("cc", "plugin-a@npm")
    assert store._writes == []
    entries = await audit_svc.query(event_type=AuditEventType.AGENT_PLUGIN_UNINSTALLED.value)
    assert entries == []


async def test_uninstall_claude_cli_unavailable_rejected(store, audit_svc):
    runner = FakeCliRunner(available=False)
    svc = _make_svc(store, audit_svc, cli_runner=runner)
    with pytest.raises(PluginUninstallUnsupported):
        await svc.uninstall("cc", "plugin-a@npm")
    assert runner.calls == []  # never attempted when the CLI is absent


async def test_uninstall_claude_cli_failure_propagates(store, audit_svc):
    runner = FakeCliRunner(available=True, fail=PluginUninstallFailed("plugin-a@npm", "boom"))
    svc = _make_svc(store, audit_svc, cli_runner=runner)
    with pytest.raises(PluginUninstallFailed):
        await svc.uninstall("cc", "plugin-a@npm")
    # A failed uninstall records no success audit event.
    entries = await audit_svc.query(event_type=AuditEventType.AGENT_PLUGIN_UNINSTALLED.value)
    assert entries == []


async def test_list_can_uninstall_gating(store, audit_svc):
    # Claude (CLI strategy): can_uninstall follows the CLI's availability.
    store._files[_CLAUDE_INSTALLED] = _INSTALLED_JSON
    with_cli = await _make_svc(
        store, audit_svc, cli_runner=FakeCliRunner(available=True)
    ).list_plugins("cc")
    assert with_cli.can_uninstall is True
    without_cli = await _make_svc(store, audit_svc).list_plugins("cc")
    assert without_cli.can_uninstall is False

    # Codex (config-edit strategy): always available, no CLI needed.
    store._files[_CODEX_CONFIG] = _CODEX_TOML_WITH_PLUGINS
    codex = await _make_svc(store, audit_svc).list_plugins("cx")
    assert codex.can_uninstall is True


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
