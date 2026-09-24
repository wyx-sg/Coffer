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
from coffer.domain.resource import Resource


class _FakeAuditRepo:
    def __init__(self, entries: list[AuditEntry]) -> None:
        self._entries = entries
        self.calls: list[dict] = []

    async def insert(self, entry: AuditEntry) -> None:  # pragma: no cover - unused
        raise AssertionError("diagnose must never write")

    async def query(
        self,
        *,
        kind=None,
        resource_id=None,
        event_type=None,
        event_prefix=None,
        since=None,
        limit=50,
    ):
        self.calls.append(
            {
                "kind": kind,
                "resource_id": resource_id,
                "event_type": event_type,
                "since": since,
                "limit": limit,
            }
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


def _resource(kind: str, name: str, *, row_id: int = 7) -> Resource:
    now = datetime.now(tz=UTC)
    return Resource(
        id=row_id,
        uid="a1b2c3d4e5f60718293a4b5c6d7e8f90",
        kind=kind,
        name=name,
        description=None,
        config={},
        enabled=True,
        created_at=now,
        updated_at=now,
    )


def _tool(repo, log_path, find_resource=None):
    registry = BuiltinToolRegistry()
    register_diagnostics_builtin_tools(
        registry, audit_repo=repo, log_path=log_path, find_resource=find_resource
    )
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
    spec="web-ui", scenario="an agent reads recent changes and failures in one call"
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
    assert (out["changes"][0]["resource_kind"], out["changes"][0]["resource"]) == (
        "mcp_server",
        "jira",
    )


@pytest.mark.asyncio
async def test_an_unparseable_line_is_kept_not_dropped(tmp_path) -> None:
    """A traceback matches no writer's format, and is usually the most
    interesting thing in the file. Dropping it would hide exactly what the
    agent came for — and its frames stay with the line they continue."""
    repo = _FakeAuditRepo([])
    tool = _tool(repo, _log(tmp_path, ["Traceback (most recent call last):", "  ValueError: x"]))

    out = await tool.handler({})

    assert [r["raw"] for r in out["log"]] == ["Traceback (most recent call last):"]
    assert out["log"][0]["continuation"] == ["  ValueError: x"]


@pytest.mark.asyncio
async def test_a_traceback_is_returned_with_the_record_that_raised(tmp_path) -> None:
    """One failure is one record. Returning its frames as records of their own
    would push the line that explains them off the end of the window."""
    repo = _FakeAuditRepo([])
    tool = _tool(
        repo,
        _log(
            tmp_path,
            [
                _json_line("error", "consolidate.store.failed"),
                "Traceback (most recent call last):",
                '  File "coffer/application/memory/consolidate.py", line 159, in run',
                "openai.RateLimitError: Error code: 429",
            ],
        ),
    )

    out = await tool.handler({})

    [record] = out["log"]
    assert record["event"] == "consolidate.store.failed"
    assert record["continuation"][-1] == "openai.RateLimitError: Error code: 429"


@pytest.mark.asyncio
async def test_every_writers_format_reaches_the_agent_parsed(tmp_path) -> None:
    """``daemon.log`` interleaves Coffer's structlog with the stdlib formatter
    and an upstream MCP server's dashed lines. An agent must get the level and
    the logger from all of them, not a wall of unparsed text."""
    repo = _FakeAuditRepo([])
    tool = _tool(
        repo,
        _log(
            tmp_path,
            [
                "ERROR - mcp_atlassian.utils.toolsets - failed to serve incoming request",
                "WARNI [coffer.infrastructure.chat.codex_app_server] \x1b[31mERROR\x1b[0m cache",
            ],
        ),
    )

    out = await tool.handler({})

    codex, upstream = out["log"]
    assert codex["level"] == "warning"
    assert codex["logger"] == "coffer.infrastructure.chat.codex_app_server"
    assert codex["event"] == "ERROR cache"  # the colour escapes are gone
    assert (upstream["level"], upstream["logger"]) == ("error", "mcp_atlassian.utils.toolsets")


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
async def test_a_named_resource_is_resolved_to_its_row_before_the_query(tmp_path) -> None:
    """The audit log is filtered by a resource's id, not its label — that is
    what makes a renamed resource's trail read as one trail. The agent asking
    only ever has a name, so the name is resolved here and the id is what
    reaches the query."""
    repo = _FakeAuditRepo([])
    asked: list[tuple[str, str]] = []

    async def _find(kind, name):
        asked.append((kind, name))
        return _resource(kind, name, row_id=42)

    tool = _tool(repo, _log(tmp_path, []), find_resource=_find)
    await tool.handler(
        {"event_type": "resource_deleted", "resource_kind": "skill", "resource_name": "x"}
    )

    assert asked == [("skill", "x")]
    assert repo.calls[0]["event_type"] == "resource_deleted"
    assert repo.calls[0]["resource_id"] == 42
    # The kind is implied by the row; re-applying it would only narrow the
    # resource's own trail.
    assert repo.calls[0]["kind"] is None


@pytest.mark.asyncio
async def test_kind_alone_still_filters_by_kind(tmp_path) -> None:
    repo = _FakeAuditRepo([])
    tool = _tool(repo, _log(tmp_path, []))
    await tool.handler({"resource_kind": "skill"})
    assert (repo.calls[0]["kind"], repo.calls[0]["resource_id"]) == ("skill", None)


@pytest.mark.asyncio
async def test_a_name_that_resolves_to_nothing_is_refused_not_ignored(tmp_path) -> None:
    """Dropping an unresolvable filter would answer "what happened to X" with
    every resource's history — which an agent reads as "X was involved in all
    of this", the opposite of the truth at the one moment it is establishing
    what actually happened."""
    repo = _FakeAuditRepo([_entry("resource_created")])

    async def _find(kind, name):
        return None

    tool = _tool(repo, _log(tmp_path, []), find_resource=_find)

    with pytest.raises(ValueError, match="no skill named 'gone'"):
        await tool.handler({"resource_kind": "skill", "resource_name": "gone"})
    assert repo.calls == []


@pytest.mark.asyncio
async def test_a_name_without_a_kind_is_refused(tmp_path) -> None:
    """A name is unique only within a kind, so a bare name names nothing."""
    repo = _FakeAuditRepo([])

    async def _find(kind, name):  # pragma: no cover - must not be reached
        raise AssertionError("resolution must not be attempted without a kind")

    tool = _tool(repo, _log(tmp_path, []), find_resource=_find)

    with pytest.raises(ValueError, match="needs 'resource_kind'"):
        await tool.handler({"resource_name": "x"})
    assert repo.calls == []


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
