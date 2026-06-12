"""Unit tests for AgentMcpEntryService.

Uses a dict-backed fake ConfigFileStorePort, a fake _AgentLookup (claude_code
'cc' + codex 'cx'), a fake resource service that validates registered configs
against the real MCPServerConfig schema, and a fake keyring — no real FS, DB,
or keychain.

Covers:
  1. list merges entries from multiple sources + flags coffer
  2. list degrades an unparseable file to ParseErrorInfo, other sources intact
  3. list annotates matches_resource (stdio command+args equivalence)
  4. remove requires source when the name is ambiguous; targeted remove only
     touches the chosen file
  5. coffer entry is protected from remove and toggle
  6. toggle writes the codex enabled flag + audits; claude toggle is rejected
  7. adopt happy path: register BEFORE file write, secret moved to keychain +
     credential_refs (never plain env), audit recorded
  8. adopt with unmapped secret-like key → AdoptSecretUnresolved, no side effects
  9. adopt name conflict bubbles ResourceAlreadyExists, file unchanged, no rollback
 10. adopt rolls back the registered resource when the file write fails
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from coffer.application.agent.mcp_entry_service import AgentMcpEntryService
from coffer.application.audit_service import AuditService
from coffer.domain.agent.config_files import FileStat, spec_for
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceAlreadyExists, ResourceNotFound
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.workspace_errors import (
    AdoptSecretUnresolved,
    McpEntryProtected,
    McpEntrySourceAmbiguous,
    McpEntryToggleUnsupported,
)

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

_CLAUDE_CONFIG_DIR = pathlib.Path("/fake/home/.claude")
_CODEX_CONFIG_DIR = pathlib.Path("/fake/home/.codex")

# Resolve the same paths the service will (the claude 'global' spec anchors
# to $HOME, not the config dir, so compute it via spec_for).
_CLAUDE_GLOBAL = spec_for(AgentType.CLAUDE_CODE, "global", _CLAUDE_CONFIG_DIR).path
_CLAUDE_SETTINGS = spec_for(AgentType.CLAUDE_CODE, "settings", _CLAUDE_CONFIG_DIR).path
_CODEX_CONFIG = spec_for(AgentType.CODEX, "config", _CODEX_CONFIG_DIR).path


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
    """'cc' → claude_code agent, 'cx' → codex agent; anything else → 404."""

    async def get(self, name: str) -> Resource:
        if name == "cc":
            return _agent_resource("cc", "claude_code", _CLAUDE_CONFIG_DIR)
        if name == "cx":
            return _agent_resource("cx", "codex", _CODEX_CONFIG_DIR)
        raise ResourceNotFound("agent", name)


@dataclass
class FakeStore:
    """Dict-backed ConfigFileStorePort (only the methods this service uses)."""

    _files: dict[pathlib.Path, str] = field(default_factory=dict)
    _writes: list[tuple[pathlib.Path, str]] = field(default_factory=list)
    sequence: list[str] = field(default_factory=list)
    raise_on_write: Exception | None = None

    def read_text(self, path: pathlib.Path) -> str | None:
        return self._files.get(path)

    def stat(self, path: pathlib.Path) -> FileStat | None:
        text = self._files.get(path)
        if text is None:
            return None
        return FileStat(size=len(text.encode()), modified_at=_NOW)

    def write_text_atomic(self, path: pathlib.Path, text: str) -> None:
        if self.raise_on_write is not None:
            raise self.raise_on_write
        self.sequence.append("write")
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


@dataclass
class FakeResourceService:
    """Records register/get/list/delete; validates configs with the real schema."""

    resources: list[Resource] = field(default_factory=list)
    register_calls: list[tuple[str, str, dict, str]] = field(default_factory=list)
    delete_calls: list[tuple[ResourceRef, str]] = field(default_factory=list)
    sequence: list[str] = field(default_factory=list)
    raise_on_register: Exception | None = None
    raise_on_get: Exception | None = None

    async def register(
        self,
        kind: str,
        name: str,
        config: dict,
        actor: str,
        description: str | None = None,
        *,
        allow_lifecycle_kind: bool = False,
    ) -> Resource:
        if self.raise_on_register is not None:
            raise self.raise_on_register
        # The real service validates against the kind schema before persisting;
        # do the same so a wrong config shape fails these tests too.
        MCPServerConfig.model_validate(config)
        self.sequence.append("register")
        self.register_calls.append((kind, name, config, actor))
        r = Resource(
            id=len(self.resources) + 100,
            kind=kind,
            name=name,
            description=description,
            config=config,
            enabled=True,
            created_at=_NOW,
            updated_at=_NOW,
        )
        self.resources.append(r)
        return r

    async def get(self, ref: ResourceRef) -> Resource:
        if self.raise_on_get is not None:
            raise self.raise_on_get
        for r in self.resources:
            if r.kind == ref.kind and r.name == ref.name:
                return r
        raise ResourceNotFound(ref.kind, ref.name)

    async def list(self, kind: str | None = None, enabled: bool | None = None) -> list[Resource]:
        return [r for r in self.resources if kind is None or r.kind == kind]

    async def delete(self, ref: ResourceRef, actor: str) -> None:
        self.delete_calls.append((ref, actor))
        self.resources = [
            r for r in self.resources if not (r.kind == ref.kind and r.name == ref.name)
        ]


class FakeKeyring:
    def __init__(self) -> None:
        self.set_calls: list[tuple[str, str]] = []

    def set(self, ref: str, value: str) -> None:
        self.set_calls.append((ref, value))


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
async def rs() -> FakeResourceService:
    return FakeResourceService()


@pytest_asyncio.fixture
async def keyring() -> FakeKeyring:
    return FakeKeyring()


@pytest_asyncio.fixture
async def audit_svc() -> AuditService:
    return AuditService(FakeAuditRepo())


@pytest_asyncio.fixture
async def svc(store, audit_svc, rs, keyring) -> AgentMcpEntryService:
    # Share one sequence list so register-vs-write ordering is observable.
    rs.sequence = store.sequence
    return AgentMcpEntryService(
        agent_service=FakeAgentLookup(),
        audit=audit_svc,
        store=store,
        resource_service=rs,
        credentials=keyring,
    )


_CLAUDE_GLOBAL_JSON = """{
  "mcpServers": {
    "coffer": {"command": "/usr/local/bin/coffer-mcp-shim"},
    "alpha": {"command": "npx", "args": ["-y", "alpha-server"]}
  }
}
"""

_CLAUDE_SETTINGS_JSON = """{
  "mcpServers": {
    "beta": {"url": "https://beta.example.com/mcp"}
  }
}
"""

_CODEX_TOML = """[mcp_servers.jira]
command = "uvx"
args = ["mcp-jira"]

[mcp_servers.jira.env]
JIRA_URL = "https://jira.example.com"
JIRA_API_TOKEN = "tok-123"

[mcp_servers.coffer]
command = "/usr/local/bin/coffer-mcp-shim"
"""


# ---------------------------------------------------------------------------
# 1. list merges sources + marks coffer
# ---------------------------------------------------------------------------


async def test_list_merges_sources_and_marks_coffer(svc, store):
    store._files[_CLAUDE_GLOBAL] = _CLAUDE_GLOBAL_JSON
    store._files[_CLAUDE_SETTINGS] = _CLAUDE_SETTINGS_JSON

    view = await svc.list_entries("cc")

    assert view.parse_errors == []
    by_name = {e.name: e for e in view.items}
    assert set(by_name) == {"coffer", "alpha", "beta"}
    assert by_name["coffer"].is_coffer is True
    assert by_name["coffer"].source == "global"
    assert by_name["alpha"].is_coffer is False
    assert by_name["alpha"].source == "global"
    assert by_name["beta"].source == "settings"
    assert by_name["beta"].transport == "http"


# ---------------------------------------------------------------------------
# 2. list reports parse-error state, other sources still listed
# ---------------------------------------------------------------------------


async def test_list_reports_parse_error_state(svc, store):
    store._files[_CLAUDE_GLOBAL] = _CLAUDE_GLOBAL_JSON
    store._files[_CLAUDE_SETTINGS] = "{not valid json"

    view = await svc.list_entries("cc")

    assert len(view.parse_errors) == 1
    err = view.parse_errors[0]
    assert err.source == "settings"
    assert err.path == str(_CLAUDE_SETTINGS)
    assert err.error
    # Entries from the parseable global file survive.
    assert {e.name for e in view.items} == {"coffer", "alpha"}


# ---------------------------------------------------------------------------
# 3. list annotates matches_resource
# ---------------------------------------------------------------------------


async def test_list_annotates_matches_resource(svc, store, rs):
    store._files[_CLAUDE_GLOBAL] = """{
      "mcpServers": {
        "coffer": {"command": "/usr/local/bin/coffer-mcp-shim"},
        "same": {"command": "npx", "args": ["-y", "alpha-server"]},
        "diff-args": {"command": "npx", "args": ["-y", "other-server"]}
      }
    }
    """
    rs.resources.append(
        Resource(
            id=7,
            kind="mcp_server",
            name="alpha-registered",
            description=None,
            config={
                "transport": {
                    "type": "stdio",
                    "command": "npx",
                    "args": ["-y", "alpha-server"],
                }
            },
            enabled=True,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )

    view = await svc.list_entries("cc")
    by_name = {e.name: e for e in view.items}

    assert by_name["same"].matches_resource == "alpha-registered"
    assert by_name["diff-args"].matches_resource is None
    # The coffer entry is never annotated, even if a resource were equivalent.
    assert by_name["coffer"].matches_resource is None


# ---------------------------------------------------------------------------
# 4. remove: ambiguity requires source; targeted remove touches one file only
# ---------------------------------------------------------------------------


async def test_remove_requires_source_when_ambiguous(svc, store):
    dup_global = '{"mcpServers": {"dup": {"command": "a"}}}'
    dup_settings = '{"mcpServers": {"dup": {"command": "b"}}}'
    store._files[_CLAUDE_GLOBAL] = dup_global
    store._files[_CLAUDE_SETTINGS] = dup_settings

    with pytest.raises(McpEntrySourceAmbiguous):
        await svc.remove_entry("cc", "dup")
    assert store._writes == []  # nothing touched

    await svc.remove_entry("cc", "dup", source="settings")

    # settings rewritten without the entry; global untouched.
    assert "dup" not in store._files[_CLAUDE_SETTINGS]
    assert store._files[_CLAUDE_GLOBAL] == dup_global
    assert [p for p, _ in store._writes] == [_CLAUDE_SETTINGS]


async def test_remove_audits_with_source(svc, store, audit_svc):
    store._files[_CLAUDE_GLOBAL] = _CLAUDE_GLOBAL_JSON

    await svc.remove_entry("cc", "alpha", actor="cli")

    entries = await audit_svc.query(event_type=AuditEventType.AGENT_MCP_ENTRY_REMOVED.value)
    assert len(entries) == 1
    assert entries[0].details == {"entry": "alpha", "source": "global"}


# ---------------------------------------------------------------------------
# 5. coffer entry is protected
# ---------------------------------------------------------------------------


async def test_remove_coffer_protected(svc, store):
    store._files[_CLAUDE_GLOBAL] = _CLAUDE_GLOBAL_JSON

    with pytest.raises(McpEntryProtected):
        await svc.remove_entry("cc", "coffer")
    assert store._writes == []


async def test_toggle_coffer_protected(svc, store):
    store._files[_CODEX_CONFIG] = _CODEX_TOML

    with pytest.raises(McpEntryProtected):
        await svc.set_enabled("cx", "coffer", False)
    assert store._writes == []


# ---------------------------------------------------------------------------
# 6. toggle: codex writes enabled flag + audits; claude rejected
# ---------------------------------------------------------------------------


async def test_toggle_codex_writes_enabled_and_audits(svc, store, audit_svc):
    store._files[_CODEX_CONFIG] = _CODEX_TOML

    await svc.set_enabled("cx", "jira", False, actor="cli")

    new_text = store._files[_CODEX_CONFIG]
    assert "enabled = false" in new_text
    view = await svc.list_entries("cx")
    jira = next(e for e in view.items if e.name == "jira")
    assert jira.enabled is False

    entries = await audit_svc.query(event_type=AuditEventType.AGENT_CONFIG_FILE_WRITTEN.value)
    assert len(entries) == 1
    assert entries[0].details == {"key": "config", "entry": "jira", "enabled": False}


async def test_toggle_claude_rejected(svc, store):
    store._files[_CLAUDE_GLOBAL] = _CLAUDE_GLOBAL_JSON

    with pytest.raises(McpEntryToggleUnsupported):
        await svc.set_enabled("cc", "alpha", False)
    assert store._writes == []


# ---------------------------------------------------------------------------
# 7. adopt happy path
# ---------------------------------------------------------------------------


async def test_adopt_happy_path_order(svc, store, rs, keyring, audit_svc):
    store._files[_CODEX_CONFIG] = _CODEX_TOML
    secrets = {"JIRA_API_TOKEN": "mcp/jira/JIRA_API_TOKEN"}

    resource = await svc.adopt("cx", "jira", secrets=secrets, actor="cli")

    # Register happened BEFORE the config-file write (shared sequence log).
    assert store.sequence == ["register", "write"]

    # Entry removed from the written file; the coffer entry survives.
    new_text = store._files[_CODEX_CONFIG]
    assert "mcp_servers.jira" not in new_text
    assert "mcp_servers.coffer" in new_text

    # Secret went to the keychain under the given ref with the original value...
    assert keyring.set_calls == [("mcp/jira/JIRA_API_TOKEN", "tok-123")]
    # ...and into credential_refs, NOT the plain env of the registered config.
    (kind, name, config, actor) = rs.register_calls[0]
    assert (kind, name, actor) == ("mcp_server", "jira", "cli")
    transport = config["transport"]
    assert "JIRA_API_TOKEN" not in transport["env"]
    assert transport["env"] == {"JIRA_URL": "https://jira.example.com"}
    assert transport["credential_refs"] == {"JIRA_API_TOKEN": "mcp/jira/JIRA_API_TOKEN"}
    assert resource.name == "jira"

    # Audit recorded with the resource name and NO secret values anywhere.
    entries = await audit_svc.query(event_type=AuditEventType.AGENT_MCP_ENTRY_ADOPTED.value)
    assert len(entries) == 1
    assert entries[0].details == {"entry": "jira", "resource": "jira", "source": "config"}
    assert "tok-123" not in str(entries[0].details)


async def test_adopt_new_name_used_for_resource(svc, store, rs):
    store._files[_CODEX_CONFIG] = _CODEX_TOML

    resource = await svc.adopt(
        "cx",
        "jira",
        new_name="jira-prod",
        secrets={"JIRA_API_TOKEN": "mcp/jira-prod/JIRA_API_TOKEN"},
    )

    assert resource.name == "jira-prod"
    assert rs.register_calls[0][1] == "jira-prod"


# ---------------------------------------------------------------------------
# 8. adopt with unresolved secret keys
# ---------------------------------------------------------------------------


async def test_adopt_unresolved_secret_rejected(svc, store, rs, keyring):
    store._files[_CODEX_CONFIG] = _CODEX_TOML

    with pytest.raises(AdoptSecretUnresolved) as exc:
        await svc.adopt("cx", "jira")

    assert exc.value.keys == ["JIRA_API_TOKEN"]
    assert rs.register_calls == []
    assert keyring.set_calls == []
    assert store._writes == []
    assert store._files[_CODEX_CONFIG] == _CODEX_TOML


# ---------------------------------------------------------------------------
# 9. adopt name conflict bubbles, no side effects on the file, no rollback
# ---------------------------------------------------------------------------


async def test_adopt_name_conflict_bubbles(svc, store, rs):
    store._files[_CODEX_CONFIG] = _CODEX_TOML
    rs.raise_on_register = ResourceAlreadyExists("mcp_server", "jira")

    with pytest.raises(ResourceAlreadyExists):
        await svc.adopt("cx", "jira", secrets={"JIRA_API_TOKEN": "mcp/jira/T"})

    assert store._files[_CODEX_CONFIG] == _CODEX_TOML  # file unchanged
    assert store._writes == []
    assert rs.delete_calls == []  # nothing registered → nothing to roll back


# ---------------------------------------------------------------------------
# 10. adopt rolls back the resource when the file write fails
# ---------------------------------------------------------------------------


async def test_adopt_rollback_on_write_failure(svc, store, rs):
    store._files[_CODEX_CONFIG] = _CODEX_TOML
    store.raise_on_write = OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        await svc.adopt("cx", "jira", secrets={"JIRA_API_TOKEN": "mcp/jira/T"})

    # Registered resource was rolled back.
    assert rs.delete_calls == [(ResourceRef("mcp_server", "jira"), "api")]
    assert rs.resources == []
    # File unchanged (write raised before mutating).
    assert store._files[_CODEX_CONFIG] == _CODEX_TOML


# ---------------------------------------------------------------------------
# 11. adopt ignores bogus mapping keys (no dangling credential_refs)
# ---------------------------------------------------------------------------


async def test_adopt_bogus_mapping_key_ignored(svc, store, rs, keyring):
    """A secrets key that matches neither env nor headers must not reach keyring
    or credential_refs — otherwise the transport would reference a keychain entry
    that was never written."""
    store._files[_CODEX_CONFIG] = _CODEX_TOML
    secrets = {
        "JIRA_API_TOKEN": "mcp/jira/JIRA_API_TOKEN",
        "DOES_NOT_EXIST_TOKEN": "mcp/jira/ghost",  # bogus — not in env or headers
    }

    await svc.adopt("cx", "jira", secrets=secrets)

    # Keyring must NOT have been called for the bogus key.
    keyring_refs = [ref for ref, _ in keyring.set_calls]
    assert "mcp/jira/ghost" not in keyring_refs
    assert keyring_refs == ["mcp/jira/JIRA_API_TOKEN"]

    # credential_refs in the registered transport must NOT contain the bogus key.
    (_, _, config, _) = rs.register_calls[0]
    transport = config["transport"]
    assert "DOES_NOT_EXIST_TOKEN" not in transport["credential_refs"]
    assert transport["credential_refs"] == {"JIRA_API_TOKEN": "mcp/jira/JIRA_API_TOKEN"}


# ---------------------------------------------------------------------------
# 12. adopt codex http entry (gas) — headers/http branch + Authorization gate
# ---------------------------------------------------------------------------

_CODEX_TOML_WITH_GAS = """[mcp_servers.gas]
url = "https://gas.example/mcp"
enabled = false
[mcp_servers.gas.http_headers]
Authorization = "Bearer abc"

[mcp_servers.coffer]
command = "/usr/local/bin/coffer-mcp-shim"
"""


async def test_adopt_gas_without_secret_mapping_raises(svc, store):
    """Adopting the gas entry without mapping Authorization must fail — the
    Authorization header is now covered by the secret gate."""
    store._files[_CODEX_CONFIG] = _CODEX_TOML_WITH_GAS

    with pytest.raises(AdoptSecretUnresolved) as exc:
        await svc.adopt("cx", "gas")

    assert exc.value.keys == ["Authorization"]


async def test_adopt_gas_with_secret_mapping_happy_path(svc, store, rs, keyring):
    """Adopting the gas entry WITH Authorization mapped writes the keychain entry
    and produces a transport with empty headers + correct credential_refs."""
    store._files[_CODEX_CONFIG] = _CODEX_TOML_WITH_GAS

    resource = await svc.adopt("cx", "gas", secrets={"Authorization": "mcp/gas/auth"})

    # Keychain received the raw value.
    assert keyring.set_calls == [("mcp/gas/auth", "Bearer abc")]

    # Registered transport: headers empty, credential_refs set.
    (_, name, config, _) = rs.register_calls[0]
    assert name == "gas"
    transport = config["transport"]
    assert transport["type"] == "http"
    assert transport["url"] == "https://gas.example/mcp"
    assert transport["headers"] == {}
    assert transport["credential_refs"] == {"Authorization": "mcp/gas/auth"}

    # Entry removed from file; coffer survives.
    new_text = store._files[_CODEX_CONFIG]
    assert "mcp_servers.gas" not in new_text
    assert "mcp_servers.coffer" in new_text

    assert resource.name == "gas"


# ---------------------------------------------------------------------------
# 13. adopt verify-failure rolls back resource and re-raises
# ---------------------------------------------------------------------------


async def test_adopt_rollback_on_verify_failure(svc, store, rs):
    """When rs.get raises after registration, the resource must be deleted and
    the exception re-raised; the config file must remain unchanged."""
    store._files[_CODEX_CONFIG] = _CODEX_TOML
    rs.raise_on_get = RuntimeError("verify failed")

    with pytest.raises(RuntimeError, match="verify failed"):
        await svc.adopt("cx", "jira", secrets={"JIRA_API_TOKEN": "mcp/jira/T"})

    # Resource rolled back.
    assert rs.delete_calls == [(ResourceRef("mcp_server", "jira"), "api")]
    assert rs.resources == []
    # File untouched.
    assert store._files[_CODEX_CONFIG] == _CODEX_TOML
    assert store._writes == []
