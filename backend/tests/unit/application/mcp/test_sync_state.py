"""MCP capability preferences as a synced state area (spec vault-sync).

A server's document lists what is disabled on it and exists only while that
list is non-empty. So import makes one server's disabled set exactly the
document's, touches no other server (the applier hands over one document at a
time), and a deleted document re-enables everything on that server — the rows
stay, because enabled is their default and their seen-timestamps are this
machine's own.

Documents are addressed by the server's **uid**, which is the same value on
every machine in the fleet (ADR resource-identity-is-an-immutable-uid). The
uids below are written out as opaque hex so nothing in these tests can pass by
accidentally matching a name.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from coffer.application.mcp.sync_state import AREA, McpPreferenceSyncState
from coffer.domain.mcp.capability import CapabilityType, MCPCapabilityPreference

JIRA_UID = "aa11bb22cc33dd44ee55ff6677889900"
SMART_UID = "0099887766ff55ee44dd33cc22bb11aa"
ELSEWHERE_UID = "1234567890abcdef1234567890abcdef"


@dataclass
class _Resource:
    id: int
    uid: str
    name: str


class _Resources:
    def __init__(self, servers: dict[str, tuple[int, str]]) -> None:
        self._servers = servers

    async def list(self, kind: str | None = None) -> list[_Resource]:
        assert kind == "mcp_server"
        return [_Resource(i, uid, n) for n, (i, uid) in self._servers.items()]


class _Prefs:
    def __init__(self) -> None:
        self.rows: dict[tuple[int, str, str], MCPCapabilityPreference] = {}

    def seed(self, resource_id: int, cap_type: CapabilityType, key: str, enabled: bool) -> None:
        now = datetime.now(tz=UTC)
        self.rows[(resource_id, cap_type, key)] = MCPCapabilityPreference(
            id=len(self.rows) + 1,
            resource_id=resource_id,
            capability_type=cap_type,
            capability_key=key,
            enabled=enabled,
            first_seen_at=now,
            last_seen_at=now,
        )

    async def list_for(
        self, resource_id: int, capability_type: CapabilityType | None = None
    ) -> list[MCPCapabilityPreference]:
        return [p for (rid, _, _), p in self.rows.items() if rid == resource_id]

    async def set_enabled(
        self, resource_id: int, capability_type: CapabilityType, capability_key: str, enabled: bool
    ) -> MCPCapabilityPreference | None:
        pref = self.rows.get((resource_id, capability_type, capability_key))
        if pref is not None:
            pref.enabled = enabled
        return pref

    async def insert(
        self,
        resource_id: int,
        capability_type: CapabilityType,
        capability_key: str,
        enabled: bool,
        first_seen_at: datetime,
        last_seen_at: datetime,
    ) -> MCPCapabilityPreference:
        self.seed(resource_id, capability_type, capability_key, enabled)
        return self.rows[(resource_id, capability_type, capability_key)]

    def disabled(self, resource_id: int) -> set[str]:
        return {k for (rid, _, k), p in self.rows.items() if rid == resource_id and not p.enabled}

    def keys(self, resource_id: int) -> set[str]:
        return {k for (rid, _, k) in self.rows if rid == resource_id}


def _state() -> tuple[McpPreferenceSyncState, _Prefs]:
    prefs = _Prefs()
    prefs.seed(1, "tool", "search", enabled=False)
    prefs.seed(1, "tool", "write", enabled=True)
    prefs.seed(2, "prompt", "summarize", enabled=False)
    resources = _Resources({"jira": (1, JIRA_UID), "smart": (2, SMART_UID)})
    return McpPreferenceSyncState(resources, prefs), prefs  # type: ignore[arg-type]


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a state area decides what its own document's deletion means",
)
async def test_export_writes_a_doc_only_for_servers_with_something_disabled() -> None:
    state, _prefs = _state()
    await state.delete_docs([SMART_UID])
    docs = await state.export_docs()
    assert AREA == "mcp-preferences"
    assert docs == [
        (
            JIRA_UID,
            {"server_uid": JIRA_UID, "disabled": [{"type": "tool", "key": "search"}]},
        )
    ]


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a state area decides what its own document's deletion means",
)
async def test_deleting_a_servers_doc_re_enables_everything_on_that_server_only() -> None:
    state, prefs = _state()

    await state.delete_docs([JIRA_UID])

    assert prefs.disabled(1) == set()
    assert prefs.keys(1) == {"search", "write"}, "rows stay; only their state changes"
    assert prefs.disabled(2) == {"summarize"}, "another server's decision is untouched"


async def test_export_after_delete_no_longer_carries_the_server() -> None:
    state, _prefs = _state()
    await state.delete_docs([JIRA_UID])
    docs = await state.export_docs()
    assert [rel for rel, _ in docs] == [SMART_UID]


async def test_deleting_an_unknown_servers_doc_is_ignored() -> None:
    state, prefs = _state()
    await state.delete_docs([ELSEWHERE_UID])
    assert prefs.disabled(1) == {"search"}
    assert prefs.disabled(2) == {"summarize"}


async def test_import_of_one_doc_leaves_the_other_servers_alone() -> None:
    """The applier upserts one path at a time; a server absent from the batch
    has not been decided about."""
    state, prefs = _state()
    errors = await state.import_docs(
        [(JIRA_UID, {"server_uid": JIRA_UID, "disabled": [{"type": "tool", "key": "write"}]})]
    )
    assert errors == []
    assert prefs.disabled(1) == {"write"}
    assert prefs.disabled(2) == {"summarize"}


async def test_import_inserts_a_capability_this_machine_has_not_seen_yet() -> None:
    state, prefs = _state()
    await state.import_docs(
        [(SMART_UID, {"server_uid": SMART_UID, "disabled": [{"type": "tool", "key": "deploy"}]})]
    )
    assert prefs.disabled(2) == {"deploy"}


async def test_import_for_a_server_not_registered_here_is_skipped() -> None:
    state, prefs = _state()
    errors = await state.import_docs(
        [(ELSEWHERE_UID, {"server_uid": ELSEWHERE_UID, "disabled": [{"type": "tool", "key": "x"}]})]
    )
    assert errors == []
    assert prefs.disabled(1) == {"search"}
