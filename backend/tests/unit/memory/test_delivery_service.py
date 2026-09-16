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
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceNotFound
from coffer.domain.memory.delivery import MARKER, MalformedDeliveryConfig
from coffer.domain.resource import Resource

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

_CLAUDE_CONFIG_DIR = pathlib.Path("/fake/home/.claude")
_CODEX_CONFIG_DIR = pathlib.Path("/fake/home/.codex")

_CLAUDE_RESOURCE = Resource(
    id=1,
    kind="agent",
    name="cc",
    description=None,
    config={"type": "claude_code", "config_dir": str(_CLAUDE_CONFIG_DIR)},
    enabled=True,
    created_at=_NOW,
    updated_at=_NOW,
)

_CODEX_RESOURCE = Resource(
    id=2,
    kind="agent",
    name="codex",
    description=None,
    config={"type": "codex", "config_dir": str(_CODEX_CONFIG_DIR)},
    enabled=True,
    created_at=_NOW,
    updated_at=_NOW,
)


class FakeAgentLookup:
    def __init__(self, resources: list[Resource]) -> None:
        self._by_name = {r.name: r for r in resources}

    async def get(self, name: str) -> Resource:
        try:
            return self._by_name[name]
        except KeyError:
            raise ResourceNotFound("agent", name) from None

    async def list(self) -> list[Resource]:
        return list(self._by_name.values())


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

    def delete_with_backup(self, path: pathlib.Path) -> bool:  # pragma: no cover - unused
        raise NotImplementedError

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
    return DeliveryService(agent_service=agents, audit=audit, store=store)


_CC_SETTINGS_PATH = _CLAUDE_CONFIG_DIR / "settings.json"
_CODEX_HOOKS_PATH = _CODEX_CONFIG_DIR / "hooks.json"


# ---------------------------------------------------------------------------
# install: empty config, idempotency, foreign-entry preservation
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="memory", scenario="hook installation is marker-scoped and removable")
async def test_install_adds_one_marker_scoped_entry_to_an_empty_config(
    svc: DeliveryService, store: FakeStore
) -> None:
    status = await svc.install("cc", actor="tester")

    assert status.installed is True
    assert status.event == "SessionStart"
    assert MARKER in status.command

    written = json.loads(store._files[_CC_SETTINGS_PATH])
    entries = written["hooks"]["SessionStart"]
    assert len(entries) == 1
    assert entries[0]["hooks"][0]["command"] == status.command


@pytest.mark.acceptance(spec="memory", scenario="hook installation is marker-scoped and removable")
async def test_install_is_idempotent(svc: DeliveryService, store: FakeStore) -> None:
    await svc.install("cc", actor="tester")
    await svc.install("cc", actor="tester")

    written = json.loads(store._files[_CC_SETTINGS_PATH])
    assert len(written["hooks"]["SessionStart"]) == 1


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

    await svc.install("cc", actor="tester")

    written = json.loads(store._files[_CC_SETTINGS_PATH])
    assert written["env"] == {}
    assert written["theme"] == "dark"
    assert written["hooks"]["UserPromptSubmit"] == foreign["hooks"]["UserPromptSubmit"]
    assert written["hooks"]["PreToolUse"] == foreign["hooks"]["PreToolUse"]
    assert written["hooks"]["Stop"] == foreign["hooks"]["Stop"]
    assert len(written["hooks"]["SessionStart"]) == 1


async def test_install_records_an_audit_event_with_the_actor(
    svc: DeliveryService, audit: AuditService
) -> None:
    await svc.install("cc", actor="alice")
    repo: FakeAuditRepo = audit._repo  # type: ignore[attr-defined]
    assert len(repo.entries) == 1
    entry = repo.entries[0]
    assert entry.event_type == AuditEventType.MEMORY_DELIVERY_INSTALLED.value
    assert entry.actor == "alice"
    assert entry.resource_name == "cc"


@pytest.mark.acceptance(spec="memory", scenario="hook installation is marker-scoped and removable")
async def test_install_for_codex_writes_a_guarded_entry_into_hooks_json(
    svc: DeliveryService, store: FakeStore
) -> None:
    """Codex is delivered into its own file, on its own event, with a guard.

    Three things are per-agent-type, and all three have to hold at once or the
    hook is installed somewhere Codex never reads: the file is
    ``<config_dir>/hooks.json`` (not Claude Code's ``settings.json``), the
    event is ``UserPromptSubmit`` (Codex has no session-start event at all),
    and because that event fires on EVERY prompt the installed command carries
    a once-per-session lock-file guard keyed on the invoking process. Without
    the guard, Coffer's context would be prepended to every single prompt.
    """
    status = await svc.install("codex", actor="tester")

    assert [path for path, _ in store.writes] == [_CODEX_HOOKS_PATH]
    assert _CC_SETTINGS_PATH not in store._files

    written = json.loads(store._files[_CODEX_HOOKS_PATH])
    assert set(written["hooks"]) == {"UserPromptSubmit"}
    entries = written["hooks"]["UserPromptSubmit"]
    assert len(entries) == 1
    command = entries[0]["hooks"][0]["command"]
    assert command == status.command
    assert MARKER in command
    # The once-per-session guard: a $PPID-keyed lock file, tested before the
    # invocation runs and created on the first fire.
    assert "$PPID" in command
    assert "[ -e " in command


async def test_status_never_writes(svc: DeliveryService, store: FakeStore) -> None:
    await svc.status("cc")
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
    await svc.install("cc", actor="tester")

    status = await svc.remove("cc", actor="tester")

    assert status.installed is False
    written = json.loads(store._files[_CC_SETTINGS_PATH])
    assert written["hooks"]["SessionStart"] == foreign["hooks"]["SessionStart"]


@pytest.mark.acceptance(spec="memory", scenario="hook installation is marker-scoped and removable")
async def test_remove_with_nothing_installed_is_a_clean_no_op(
    svc: DeliveryService, store: FakeStore, audit: AuditService
) -> None:
    status = await svc.remove("cc", actor="tester")

    assert status.installed is False
    assert store.writes == []
    repo: FakeAuditRepo = audit._repo  # type: ignore[attr-defined]
    assert repo.entries == []


async def test_remove_records_an_audit_event(svc: DeliveryService, audit: AuditService) -> None:
    await svc.install("codex", actor="tester")
    await svc.remove("codex", actor="bob")
    repo: FakeAuditRepo = audit._repo  # type: ignore[attr-defined]
    event_types = [e.event_type for e in repo.entries]
    assert AuditEventType.MEMORY_DELIVERY_REMOVED.value in event_types
    removed = [
        e for e in repo.entries if e.event_type == AuditEventType.MEMORY_DELIVERY_REMOVED.value
    ]
    assert removed[0].actor == "bob"


# ---------------------------------------------------------------------------
# status: installed / not, per-agent, whole fleet
# ---------------------------------------------------------------------------


async def test_status_reports_not_installed_for_a_fresh_agent(svc: DeliveryService) -> None:
    (status,) = await svc.status("cc")
    assert status.installed is False
    assert status.agent == "cc"
    assert status.event == "SessionStart"


async def test_status_reports_installed_after_install(svc: DeliveryService) -> None:
    await svc.install("codex", actor="tester")
    (status,) = await svc.status("codex")
    assert status.installed is True
    assert status.event == "UserPromptSubmit"


async def test_status_with_no_agent_reports_every_registered_agent(
    svc: DeliveryService,
) -> None:
    await svc.install("cc", actor="tester")
    statuses = await svc.status()
    by_agent = {s.agent: s for s in statuses}
    assert set(by_agent) == {"cc", "codex"}
    assert by_agent["cc"].installed is True
    assert by_agent["codex"].installed is False


# ---------------------------------------------------------------------------
# record_fired: one audit entry per real fire (FR-026)
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="memory", scenario="every hook fire is recorded in the audit log")
async def test_record_fired_writes_one_audit_entry_naming_the_agent(
    svc: DeliveryService, audit: AuditService
) -> None:
    repo: FakeAuditRepo = audit._repo  # type: ignore[attr-defined]

    await svc.record_fired("cc")

    fires = [e for e in repo.entries if e.event_type == AuditEventType.MEMORY_DELIVERY_FIRED.value]
    assert len(fires) == 1
    assert fires[0].resource_name == "cc"
    # Nobody clicked anything: the agent whose session started is the actor.
    assert fires[0].actor == "cc"


async def test_record_fired_does_not_affect_installed_state(svc: DeliveryService) -> None:
    await svc.record_fired("cc")
    (status,) = await svc.status("cc")
    assert status.installed is False


async def test_neither_install_nor_status_records_a_fire(
    svc: DeliveryService, audit: AuditService
) -> None:
    repo: FakeAuditRepo = audit._repo  # type: ignore[attr-defined]

    await svc.install("cc", actor="tester")
    await svc.status("cc")

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
        await svc.install("cc", actor="tester")

    assert str(_CC_SETTINGS_PATH) in str(exc_info.value)
    # The broken file is never touched.
    assert store._files[_CC_SETTINGS_PATH] == "{not valid json"


async def test_unknown_agent_raises_resource_not_found(svc: DeliveryService) -> None:
    with pytest.raises(ResourceNotFound):
        await svc.install("does-not-exist", actor="tester")
