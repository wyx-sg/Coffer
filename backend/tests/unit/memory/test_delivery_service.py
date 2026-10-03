"""Unit tests for `coffer.application.memory.delivery.DeliveryService`.

Fakes throughout (dict-backed store, hard-coded agent lookup, in-memory audit
repo) — same shape as `tests/unit/application/agent/test_config_file_service.py`
and `test_mcp_service.py`. No filesystem, no database, no subprocess.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from coffer.application.audit_service import AuditService
from coffer.application.memory.delivery import DeliveryService
from coffer.domain.agent.config_files import FileStat
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceNotFound
from coffer.domain.memory.delivery import (
    DELIVERY_EVENTS,
    MARKER,
    MalformedDeliveryConfig,
    events_label,
)
from coffer.domain.resource import Resource
from tests.support.facets import agent_catalog

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

#: The events every installed hook sits on, as a status spells them.
_ALL_EVENTS = events_label(DELIVERY_EVENTS)

_CLAUDE_CONFIG_DIR = pathlib.Path("/fake/home/.claude")
_CODEX_CONFIG_DIR = pathlib.Path("/fake/home/.codex")

#: The uids the tests address the two agents by. Opaque on purpose: nothing in
#: this module may work because a uid happens to look like its agent's name.
_CC_UID = "9f3c1b0a4d5e4f7b8c1d2e3f40516273"
_CODEX_UID = "1a2b3c4d5e6f708192a3b4c5d6e7f809"

_CLAUDE_RESOURCE = Resource(
    uid=_CC_UID,
    kind="agent",
    name="cc",
    description=None,
    config={"type": "claude_code", "config_dir": str(_CLAUDE_CONFIG_DIR)},
    enabled=True,
    created_at=_NOW,
    updated_at=_NOW,
)

_CODEX_RESOURCE = Resource(
    uid=_CODEX_UID,
    kind="agent",
    name="codex",
    description=None,
    config={"type": "codex", "config_dir": str(_CODEX_CONFIG_DIR)},
    enabled=True,
    created_at=_NOW,
    updated_at=_NOW,
)


class FakeAgentLookup:
    """Keyed by uid, like the real agent service: a name gets you nothing."""

    def __init__(self, resources: list[Resource]) -> None:
        self._by_uid = {r.uid: r for r in resources}

    async def get(self, uid: str) -> Resource:
        try:
            return self._by_uid[uid]
        except KeyError:
            raise ResourceNotFound(uid) from None

    async def list(self) -> list[Resource]:
        return list(self._by_uid.values())


@dataclass
class FakeStore:
    """In-memory `ConfigFileStorePort`. Only the two methods delivery uses."""

    _files: dict[pathlib.Path, str] = field(default_factory=dict)
    writes: list[tuple[pathlib.Path, str]] = field(default_factory=list)

    def read_text(self, path: pathlib.Path) -> str | None:
        return self._files.get(path)

    def stat(self, path: pathlib.Path) -> FileStat | None:  # pragma: no cover - unused
        raise NotImplementedError

    def write_text_atomic(self, path: pathlib.Path, text: str) -> None:
        self.writes.append((path, text))
        self._files[path] = text

    def list_dir(self, root: pathlib.Path):  # pragma: no cover - unused
        raise NotImplementedError

    deletes: list[pathlib.Path] = field(default_factory=list)

    def delete_with_backup(self, path: pathlib.Path) -> bool:
        self.deletes.append(path)
        return self._files.pop(path, None) is not None

    def remove_tree(self, path: pathlib.Path) -> bool:  # pragma: no cover - unused
        raise NotImplementedError

    def fingerprint(self, text: str | None) -> str:  # pragma: no cover - unused
        return ""

    def resolved_within(self, path: pathlib.Path, root: pathlib.Path) -> bool:
        return True


class FakeAuditRepo:
    def __init__(self) -> None:
        self.entries: list = []

    async def insert(self, entry) -> None:
        self.entries.append(entry)

    async def repoint(self, kind, old_name, new_name) -> int:  # pragma: no cover - unused
        return 0

    async def query(self, **kwargs):  # pragma: no cover - unused
        return []


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest_asyncio.fixture
async def audit() -> AuditService:
    return AuditService(FakeAuditRepo())


@pytest_asyncio.fixture
async def svc(store: FakeStore, audit: AuditService) -> DeliveryService:
    agents = FakeAgentLookup([_CLAUDE_RESOURCE, _CODEX_RESOURCE])
    return DeliveryService(agent_service=agents, audit=audit, store=store, catalog=agent_catalog())


_CC_SETTINGS_PATH = _CLAUDE_CONFIG_DIR / "settings.json"
_CODEX_HOOKS_PATH = _CODEX_CONFIG_DIR / "hooks.json"


# ---------------------------------------------------------------------------
# install: empty config, idempotency, foreign-entry preservation
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="memory", scenario="hook installation is marker-scoped and removable")
async def test_install_adds_one_marker_scoped_entry_to_an_empty_config(
    svc: DeliveryService, store: FakeStore
) -> None:
    status = await svc.install(_CC_UID, actor="tester")

    assert status.installed is True
    assert status.event == _ALL_EVENTS
    assert MARKER in status.command

    written = json.loads(store._files[_CC_SETTINGS_PATH])
    assert set(written["hooks"]) == set(DELIVERY_EVENTS)
    for event in DELIVERY_EVENTS:
        entries = written["hooks"][event]
        assert len(entries) == 1
        assert entries[0]["hooks"][0]["command"] == status.command


@pytest.mark.acceptance(spec="memory", scenario="hook installation is marker-scoped and removable")
async def test_install_is_idempotent(svc: DeliveryService, store: FakeStore) -> None:
    await svc.install(_CC_UID, actor="tester")
    await svc.install(_CC_UID, actor="tester")

    written = json.loads(store._files[_CC_SETTINGS_PATH])
    for event in DELIVERY_EVENTS:
        assert len(written["hooks"][event]) == 1


@pytest.mark.acceptance(spec="memory", scenario="hook installation is marker-scoped and removable")
async def test_install_into_a_config_holding_foreign_hooks_leaves_them_untouched(
    svc: DeliveryService, store: FakeStore
) -> None:
    foreign = {
        "env": {},
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "/skynet/beforeSubmitPrompt.sh"}]}
            ],
            "PreToolUse": [
                {
                    "matcher": "mcp__.*",
                    "hooks": [{"type": "command", "command": "/skynet/beforeMCP.sh"}],
                }
            ],
            "Stop": [{"hooks": [{"type": "command", "command": "/skynet/stop.sh"}]}],
        },
        "theme": "dark",
    }
    store._files[_CC_SETTINGS_PATH] = json.dumps(foreign)

    await svc.install(_CC_UID, actor="tester")

    written = json.loads(store._files[_CC_SETTINGS_PATH])
    assert written["env"] == {}
    assert written["theme"] == "dark"
    # Foreign entries stay first and unchanged; Coffer's one is appended after.
    event = "UserPromptSubmit"
    assert written["hooks"][event][:-1] == foreign["hooks"][event]
    assert MARKER in written["hooks"][event][-1]["hooks"][0]["command"]
    # A foreign hook on an event Coffer does not install on is left alone, and
    # Coffer adds nothing there.
    assert written["hooks"]["PreToolUse"] == foreign["hooks"]["PreToolUse"]
    assert written["hooks"]["Stop"] == foreign["hooks"]["Stop"]
    assert len(written["hooks"]["SessionStart"]) == 1
    assert "PostToolUse" not in written["hooks"]


@pytest.mark.acceptance(spec="memory", scenario="hook installation is marker-scoped and removable")
async def test_the_installed_command_names_the_agent_by_uid_not_by_name(
    svc: DeliveryService, store: FakeStore
) -> None:
    """The hook outlives every rename the agent will ever have.

    An installed entry sits in somebody else's settings file for months. If it
    spelled the agent's registry name, renaming the agent would leave a hook
    reporting a name nothing answers to — and with no name fallback on the
    reading side, a session that silently delivered no memory. So the command
    carries the uid, and the agent's name appears nowhere in it.
    """
    status = await svc.install(_CC_UID, actor="tester")

    assert f"--agent-uid {_CC_UID}" in status.command
    assert "--agent " not in status.command
    assert "cc" not in status.command.replace(_CC_UID, "")

    written = json.loads(store._files[_CC_SETTINGS_PATH])
    assert written["hooks"]["SessionStart"][0]["hooks"][0]["command"] == status.command


async def test_install_records_an_audit_event_with_the_actor(
    svc: DeliveryService, audit: AuditService
) -> None:
    await svc.install(_CC_UID, actor="alice")
    repo: FakeAuditRepo = audit._repo  # type: ignore[attr-defined]
    assert len(repo.entries) == 1
    entry = repo.entries[0]
    assert entry.event_type == AuditEventType.MEMORY_DELIVERY_INSTALLED.value
    assert entry.actor == "alice"
    assert entry.resource_name == "cc"


@pytest.mark.acceptance(spec="memory", scenario="hook installation is marker-scoped and removable")
async def test_install_for_codex_writes_a_session_start_entry_into_hooks_json(
    svc: DeliveryService, store: FakeStore
) -> None:
    """Codex is delivered into its own file, on all four events, as JSON.

    The file is ``<config_dir>/hooks.json`` (not Claude Code's
    ``settings.json``); session start is its own event (once per session, so
    no guard — the old ``$PPID`` guard let only the first session of a shared
    app-server fire); and every entry runs ``coffer memory hook``, which reads
    the event from stdin and prints that event's JSON ``hookSpecificOutput``.
    """
    status = await svc.install(_CODEX_UID, actor="tester")

    assert [path for path, _ in store.writes] == [_CODEX_HOOKS_PATH]
    assert _CC_SETTINGS_PATH not in store._files

    written = json.loads(store._files[_CODEX_HOOKS_PATH])
    assert set(written["hooks"]) == set(DELIVERY_EVENTS)
    assert written["hooks"]["SessionStart"][0]["matcher"] == "startup|resume|clear|compact"
    for event in DELIVERY_EVENTS:
        entries = written["hooks"][event]
        assert len(entries) == 1
        command = entries[0]["hooks"][0]["command"]
        assert command == status.command
    assert MARKER in status.command
    assert " memory hook " in status.command
    assert "--hook-event" not in status.command
    assert "$PPID" not in status.command


async def test_status_never_writes(svc: DeliveryService, store: FakeStore) -> None:
    await svc.status(_CC_UID)
    assert store.writes == []


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="memory", scenario="hook installation is marker-scoped and removable")
async def test_remove_takes_out_only_coffers_entry(svc: DeliveryService, store: FakeStore) -> None:
    foreign = {
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "/usr/local/bin/other.sh"}]}]
        }
    }
    store._files[_CC_SETTINGS_PATH] = json.dumps(foreign)
    await svc.install(_CC_UID, actor="tester")

    status = await svc.remove(_CC_UID, actor="tester")

    assert status.installed is False
    written = json.loads(store._files[_CC_SETTINGS_PATH])
    assert written["hooks"]["SessionStart"] == foreign["hooks"]["SessionStart"]


@pytest.mark.acceptance(spec="memory", scenario="hook installation is marker-scoped and removable")
async def test_remove_with_nothing_installed_is_a_clean_no_op(
    svc: DeliveryService, store: FakeStore, audit: AuditService
) -> None:
    status = await svc.remove(_CC_UID, actor="tester")

    assert status.installed is False
    assert store.writes == []
    repo: FakeAuditRepo = audit._repo  # type: ignore[attr-defined]
    assert repo.entries == []


async def test_remove_records_an_audit_event(svc: DeliveryService, audit: AuditService) -> None:
    await svc.install(_CODEX_UID, actor="tester")
    await svc.remove(_CODEX_UID, actor="bob")
    repo: FakeAuditRepo = audit._repo  # type: ignore[attr-defined]
    event_types = [e.event_type for e in repo.entries]
    assert AuditEventType.MEMORY_DELIVERY_REMOVED.value in event_types
    removed = [
        e for e in repo.entries if e.event_type == AuditEventType.MEMORY_DELIVERY_REMOVED.value
    ]
    assert removed[0].actor == "bob"


# ---------------------------------------------------------------------------
# status: installed / not, per agent
# ---------------------------------------------------------------------------


async def test_status_reports_not_installed_for_a_fresh_agent(svc: DeliveryService) -> None:
    status = await svc.status(_CC_UID)
    assert status.installed is False
    assert status.agent_uid == _CC_UID
    # The label travels beside the identity so a surface has something to show.
    assert status.agent_name == "cc"
    assert status.event == _ALL_EVENTS


async def test_status_reports_installed_after_install(svc: DeliveryService) -> None:
    await svc.install(_CODEX_UID, actor="tester")
    status = await svc.status(_CODEX_UID)
    assert status.installed is True
    assert status.event == _ALL_EVENTS


async def test_supports_exactly_the_types_with_a_hook_adapter(svc: DeliveryService) -> None:
    assert svc.supports(AgentType.CLAUDE_CODE) is True
    assert svc.supports(AgentType.CODEX) is True


async def test_an_agent_without_a_delivery_hook_is_unsupported() -> None:
    """The adapter is the projection facet's; an agent whose projection has no
    delivery hook is refused rather than guessed at."""
    import dataclasses

    from coffer.domain.agent.facets import AgentCatalog
    from coffer.domain.memory.delivery import DeliveryUnsupported

    bound = agent_catalog()
    bare = AgentCatalog(
        {
            d.type: dataclasses.replace(
                d, projection=dataclasses.replace(d.projection, delivery_hook=None)
            )
            for d in bound
            if d.projection is not None
        }
    )
    svc = DeliveryService(
        agent_service=FakeAgentLookup([_CLAUDE_RESOURCE]),
        audit=AuditService(FakeAuditRepo()),
        store=FakeStore(),
        catalog=bare,
    )
    assert svc.supports(AgentType.CLAUDE_CODE) is False
    with pytest.raises(DeliveryUnsupported):
        await svc.status(_CC_UID)


# ---------------------------------------------------------------------------
# record_fired: one audit entry per real fire ("Audit every delivery fire")
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="memory", scenario="every hook fire is recorded in the audit log")
async def test_record_fired_writes_one_audit_entry_naming_the_agent(
    svc: DeliveryService, audit: AuditService
) -> None:
    repo: FakeAuditRepo = audit._repo  # type: ignore[attr-defined]

    await svc.record_fired(_CC_UID)

    fires = [e for e in repo.entries if e.event_type == AuditEventType.MEMORY_DELIVERY_FIRED.value]
    assert len(fires) == 1
    assert fires[0].resource_name == "cc"
    # Nobody clicked anything: the agent whose session started is the actor.
    assert fires[0].actor == "cc"


async def test_record_fired_does_not_affect_installed_state(svc: DeliveryService) -> None:
    await svc.record_fired(_CC_UID)
    status = await svc.status(_CC_UID)
    assert status.installed is False


async def test_neither_install_nor_status_records_a_fire(
    svc: DeliveryService, audit: AuditService
) -> None:
    repo: FakeAuditRepo = audit._repo  # type: ignore[attr-defined]

    await svc.install(_CC_UID, actor="tester")
    await svc.status(_CC_UID)

    assert not [
        e for e in repo.entries if e.event_type == AuditEventType.MEMORY_DELIVERY_FIRED.value
    ]


# ---------------------------------------------------------------------------
# Malformed config fails loudly, with the path
# ---------------------------------------------------------------------------


async def test_malformed_config_fails_loudly_with_the_path(
    svc: DeliveryService, store: FakeStore
) -> None:
    store._files[_CC_SETTINGS_PATH] = "{not valid json"

    with pytest.raises(MalformedDeliveryConfig) as exc_info:
        await svc.install(_CC_UID, actor="tester")

    assert str(_CC_SETTINGS_PATH) in str(exc_info.value)
    # The broken file is never touched.
    assert store._files[_CC_SETTINGS_PATH] == "{not valid json"


async def test_unknown_agent_raises_resource_not_found(svc: DeliveryService) -> None:
    with pytest.raises(ResourceNotFound):
        await svc.install("00000000000000000000000000000000", actor="tester")


@pytest.mark.acceptance(
    spec="memory", scenario="an install clears marked entries on events it no longer uses"
)
async def test_install_clears_marked_entries_on_events_it_no_longer_uses(
    svc: DeliveryService, store: FakeStore
) -> None:
    first = await svc.install(_CC_UID, actor="tester")
    command = first.command
    marked = {"hooks": [{"type": "command", "command": command, "timeout": 5}]}
    foreign = {"hooks": [{"type": "command", "command": "/skynet/beforeShell.sh"}]}
    doc = json.loads(store._files[_CC_SETTINGS_PATH])
    # An earlier build also hung Coffer's entry on the two shell-tool events.
    doc["hooks"]["PreToolUse"] = [foreign, {"matcher": "Bash", **marked}]
    doc["hooks"]["PostToolUse"] = [{"matcher": "Bash", **marked}]
    store._files[_CC_SETTINGS_PATH] = json.dumps(doc)

    await svc.install(_CC_UID, actor="tester")

    written = json.loads(store._files[_CC_SETTINGS_PATH])
    assert written["hooks"]["PreToolUse"] == [foreign]
    assert "PostToolUse" not in written["hooks"]
    for event in ("SessionStart", "UserPromptSubmit"):
        entries = written["hooks"][event]
        assert len(entries) == 1
        assert entries[0]["hooks"][0]["command"] == command
