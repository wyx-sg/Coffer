"""``coffer__diagnose`` — Coffer's own history, read by the agent debugging it.

The audit log and the daemon log both lost their human reader: the audit page
is deleted, and nobody greps a log file by hand. The reader is an agent at the
moment something broke, so the surface is a tool it already holds.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.diagnostics import register_diagnostics_builtin_tools
from coffer.domain.audit import AuditEntry


class _FakeAuditRepo:
    def __init__(self, entries: list[AuditEntry]) -> None:
        self._entries = entries
        self.calls: list[dict] = []

    async def insert(self, entry: AuditEntry) -> None:  # pragma: no cover - unused
        raise AssertionError("diagnose must never write")

    async def repoint(self, kind, old_name, new_name) -> int:  # pragma: no cover - unused
        raise AssertionError("diagnose must never write")

    async def query(self, *, kind=None, name=None, event_type=None, since=None, limit=50):
        self.calls.append(
            {"kind": kind, "name": name, "event_type": event_type, "since": since, "limit": limit}
        )
        return self._entries[:limit]


def _entry(event: str, *, minutes_ago: int = 1) -> AuditEntry:
    return AuditEntry(
        id=1,
        timestamp=datetime.now(tz=UTC) - timedelta(minutes=minutes_ago),
        event_type=event,
        resource_kind="mcp_server",
        resource_name="jira",
        actor="cli",
        details={"ref": "jira.TOKEN"},
    )


def _log(tmp_path, lines: list[str]):
    path = tmp_path / "daemon.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lambda: path


def _tool(repo, log_path):
    registry = BuiltinToolRegistry()
    register_diagnostics_builtin_tools(registry, audit_repo=repo, log_path=log_path)
    [tool] = [t for t in registry.list() if t.name == "diagnose"]
    return tool


def _json_line(level: str, event: str, *, at: datetime | None = None) -> str:
    return json.dumps(
        {
            "timestamp": (at or datetime.now(tz=UTC)).isoformat(),
            "level": level,
            "event": event,
        }
    )


@pytest.mark.acceptance(
    spec="ui-shell", scenario="an agent reads recent changes and failures in one call"
)
@pytest.mark.asyncio
async def test_one_call_answers_from_both_records(tmp_path) -> None:
    """The point of the tool. An agent that hits a failure does not know whether
    it wants "what changed" or "what errored" — it wants what happened."""
    repo = _FakeAuditRepo([_entry("credential_read")])
    tool = _tool(repo, _log(tmp_path, [_json_line("error", "credential.missing")]))

    out = await tool.handler({})

    assert [c["event"] for c in out["changes"]] == ["credential_read"]
    assert [r["event"] for r in out["log"]] == ["credential.missing"]
    assert out["changes"][0]["resource"] == "mcp_server:jira"


@pytest.mark.asyncio
async def test_an_unparseable_line_is_kept_not_dropped(tmp_path) -> None:
    """A traceback is not JSON, and is usually the most interesting line in the
    file. Dropping it would hide exactly what the agent came for."""
    repo = _FakeAuditRepo([])
    tool = _tool(repo, _log(tmp_path, ["Traceback (most recent call last):", "  ValueError: x"]))

    out = await tool.handler({})

    assert [r["raw"] for r in out["log"]] == [
        "  ValueError: x",
        "Traceback (most recent call last):",
    ]


@pytest.mark.asyncio
async def test_errors_only_keeps_errors_and_unparseable_lines(tmp_path) -> None:
    repo = _FakeAuditRepo([_entry("resource_created")])
    tool = _tool(
        repo,
        _log(
            tmp_path,
            [
                _json_line("info", "coffer.resource_created"),
                _json_line("error", "mcp.upstream.spawn_failed"),
                "raw traceback line",
            ],
        ),
    )

    out = await tool.handler({"errors_only": True})

    assert [r.get("event") or r.get("raw") for r in out["log"]] == [
        "raw traceback line",
        "mcp.upstream.spawn_failed",
    ]
    # The audit side is deliberately unaffected — "what changed" has no level.
    assert len(out["changes"]) == 1


@pytest.mark.asyncio
async def test_newest_first_on_both_timelines(tmp_path) -> None:
    now = datetime.now(tz=UTC)
    repo = _FakeAuditRepo([])
    tool = _tool(
        repo,
        _log(
            tmp_path,
            [
                _json_line("info", "older", at=now - timedelta(minutes=2)),
                _json_line("info", "newer", at=now - timedelta(minutes=1)),
            ],
        ),
    )
    out = await tool.handler({})
    assert [r["event"] for r in out["log"]] == ["newer", "older"]


@pytest.mark.asyncio
async def test_the_window_bounds_both_sides(tmp_path) -> None:
    now = datetime.now(tz=UTC)
    repo = _FakeAuditRepo([])
    tool = _tool(
        repo,
        _log(
            tmp_path,
            [
                _json_line("info", "ancient", at=now - timedelta(days=3)),
                _json_line("info", "recent", at=now - timedelta(minutes=5)),
            ],
        ),
    )

    out = await tool.handler({"since_minutes": 30})

    assert [r["event"] for r in out["log"]] == ["recent"]
    assert repo.calls[0]["since"] is not None
    assert now - repo.calls[0]["since"] <= timedelta(minutes=31)


@pytest.mark.asyncio
async def test_filters_reach_the_audit_query(tmp_path) -> None:
    repo = _FakeAuditRepo([])
    tool = _tool(repo, _log(tmp_path, []))
    await tool.handler(
        {"event_type": "resource_deleted", "resource_kind": "skill", "resource_name": "x"}
    )
    assert repo.calls[0]["event_type"] == "resource_deleted"
    assert repo.calls[0]["kind"] == "skill"
    assert repo.calls[0]["name"] == "x"


@pytest.mark.asyncio
async def test_a_missing_log_file_still_answers_from_the_audit_side(tmp_path) -> None:
    """A fresh install has no daemon.log yet. Half an answer beats an error."""
    repo = _FakeAuditRepo([_entry("resource_created")])
    tool = _tool(repo, lambda: tmp_path / "absent.log")

    out = await tool.handler({})

    assert out["log"] == []
    assert len(out["changes"]) == 1


@pytest.mark.asyncio
async def test_limits_are_clamped_not_trusted(tmp_path) -> None:
    repo = _FakeAuditRepo([])
    tool = _tool(repo, _log(tmp_path, []))
    await tool.handler({"since_minutes": 10**9, "limit": 10**9})
    assert repo.calls[0]["limit"] == 200
