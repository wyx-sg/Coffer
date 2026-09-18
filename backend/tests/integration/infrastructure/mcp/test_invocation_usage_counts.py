"""Per-(server, tool) invocation counts — the ranking signal for tool tiering.

Tool tiering decides what the gateway lists from real usage, so this query is
the thing standing between the agent and a tool it uses every day. It counts
every status on purpose: an errored call still proves the agent reached for
that tool.

The rows are STORED by the server's uid and the counts come back keyed by its
name, because the tiering policy ranks the namespaced wire names a
``tools/list`` carries. The join that bridges the two lives in the repo, and the
tests below pin both of its consequences: a renamed server's whole history
counts under its current name, and a row that resolves to no server is left out.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from coffer.domain.mcp.capability import MCPInvocation
from coffer.infrastructure.mcp.invocation_writer import MCPInvocationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

JIRA_UID = "aa11bb22cc33dd44ee55ff6677889900"
CONFLUENCE_UID = "0099887766ff55ee44dd33cc22bb11aa"
GONE_UID = "1234567890abcdef1234567890abcdef"


async def _make_repo(tmp_path):
    """A repo plus the two ``mcp_server`` rows its counts join against."""
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    async with sm() as session:
        for uid, name in ((JIRA_UID, "jira"), (CONFLUENCE_UID, "confluence")):
            await session.execute(
                sa.text(
                    "INSERT INTO resources (uid, kind, name, config_json, enabled,"
                    " created_at, updated_at)"
                    " VALUES (:uid, 'mcp_server', :name, '{}', 1, :t, :t)"
                ),
                {"uid": uid, "name": name, "t": datetime.now(tz=UTC)},
            )
        await session.commit()
    return MCPInvocationRepo(sm), engine


async def _rename(engine, uid: str, new_name: str) -> None:
    async with session_maker(engine)() as session:
        await session.execute(
            sa.text("UPDATE resources SET name = :n WHERE uid = :uid"),
            {"n": new_name, "uid": uid},
        )
        await session.commit()


def _inv(
    uid: str,
    key: str,
    when: datetime,
    *,
    ctype: str = "tool",
    status: str = "ok",
) -> MCPInvocation:
    return MCPInvocation(
        id=None,
        timestamp=when,
        resource_uid=uid,
        capability_type=ctype,  # type: ignore[arg-type]
        capability_key=key,
        duration_ms=1,
        status=status,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_usage_counts_groups_by_server_and_tool(tmp_path):
    repo, engine = await _make_repo(tmp_path)
    now = datetime.now(tz=UTC)
    try:
        for _ in range(3):
            await repo.insert(_inv(JIRA_UID, "jira_get_issue", now))
        await repo.insert(_inv(JIRA_UID, "jira_search", now))
        await repo.insert(_inv(CONFLUENCE_UID, "confluence_get_page", now))

        counts = await repo.usage_counts(since=now - timedelta(days=1))

        assert counts[("jira", "jira_get_issue")] == 3
        assert counts[("jira", "jira_search")] == 1
        assert counts[("confluence", "confluence_get_page")] == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_renamed_servers_whole_history_counts_under_its_new_name(tmp_path):
    """The point of storing the uid. While the log keyed on the name, a rename
    split a server's usage in two: the tool the agent had called for months
    ranked as if it were brand new, and tiering could hide it on the very next
    session."""
    repo, engine = await _make_repo(tmp_path)
    now = datetime.now(tz=UTC)
    try:
        await repo.insert(_inv(JIRA_UID, "jira_get_issue", now - timedelta(days=30)))
        await repo.insert(_inv(JIRA_UID, "jira_get_issue", now))

        await _rename(engine, JIRA_UID, "issues")

        counts = await repo.usage_counts(since=now - timedelta(days=90))

        assert counts == {("issues", "jira_get_issue"): 2}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_row_that_resolves_to_no_server_is_left_out(tmp_path):
    """Coffer's own built-ins and servers deleted inside the window resolve to
    nothing. They are omitted rather than counted under some placeholder name:
    their tools are not in the catalogue being ranked, so a count for them could
    only displace a tool that IS."""
    repo, engine = await _make_repo(tmp_path)
    now = datetime.now(tz=UTC)
    try:
        await repo.insert(_inv(GONE_UID, "old_tool", now))
        await repo.insert(_inv("coffer", "recall", now))
        await repo.insert(_inv(JIRA_UID, "jira_search", now))

        counts = await repo.usage_counts(since=now - timedelta(days=1))

        assert counts == {("jira", "jira_search"): 1}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_usage_counts_excludes_rows_before_the_window(tmp_path):
    repo, engine = await _make_repo(tmp_path)
    now = datetime.now(tz=UTC)
    try:
        await repo.insert(_inv(JIRA_UID, "jira_get_issue", now - timedelta(days=200)))
        await repo.insert(_inv(JIRA_UID, "jira_search", now))

        counts = await repo.usage_counts(since=now - timedelta(days=90))

        assert ("jira", "jira_get_issue") not in counts
        assert counts[("jira", "jira_search")] == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_usage_counts_ignores_non_tool_capabilities(tmp_path):
    repo, engine = await _make_repo(tmp_path)
    now = datetime.now(tz=UTC)
    try:
        await repo.insert(_inv(JIRA_UID, "some_prompt", now, ctype="prompt"))

        counts = await repo.usage_counts(since=now - timedelta(days=1))

        assert counts == {}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_errored_calls_still_count_as_usage(tmp_path):
    """Reaching for a tool and failing is still evidence the agent wants it."""
    repo, engine = await _make_repo(tmp_path)
    now = datetime.now(tz=UTC)
    try:
        await repo.insert(_inv(JIRA_UID, "jira_get_issue", now, status="error"))

        counts = await repo.usage_counts(since=now - timedelta(days=1))

        assert counts[("jira", "jira_get_issue")] == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_empty_log_returns_an_empty_map(tmp_path):
    repo, engine = await _make_repo(tmp_path)
    try:
        counts = await repo.usage_counts(since=datetime.now(tz=UTC) - timedelta(days=90))
        assert counts == {}
    finally:
        await engine.dispose()
