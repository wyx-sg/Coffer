"""Unit tests for AgentPluginService.

Uses a dict-backed fake ConfigFileStorePort, a fake _AgentLookup (claude_code
'cc' + codex 'cx'), and a fake AuditRepo — no real FS, DB, or keychain.

Covers:
 1. list_codex_groups_and_cache_flag — two plugins, cache present/absent
 2. list_codex_missing_config_empty — no config.toml → empty PluginsOut
 3. list_codex_parse_error_degrades — broken toml → parse_errors populated
 4. list_claude_inventory_and_enabled — inventory + settings enabled flags
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
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource

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

    async def repoint(self, kind, old_name, new_name) -> int:
        moved = [e for e in self._entries if e.resource_name == old_name]
        for e in moved:
            e.resource_name = new_name
        return len(moved)

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


def _make_svc(
    store: FakeStore,
    audit_svc: AuditService,
    *,
    cache_dirs: set[pathlib.Path] | None = None,
    rmtree_calls: list[pathlib.Path] | None = None,
    detail_reader: FakeDetailReader | None = None,
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


# ---------------------------------------------------------------------------
# 6. toggle_claude_writes_settings_only_internal_untouched
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 7. uninstall_claude — CLI-mediated (never hand-writes internal files)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 8. uninstall_codex_removes_entry_and_cache
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 9. uninstall_codex_cache_missing_ok
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 10. uninstall_codex_unknown_plugin_404
# ---------------------------------------------------------------------------
