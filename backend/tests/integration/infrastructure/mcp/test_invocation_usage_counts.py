"""Per-(server, tool) invocation counts — the ranking signal for tool tiering.

Tool tiering decides what the gateway lists from real usage, so this query is
the thing standing between the agent and a tool it uses every day. It counts
every status on purpose: an errored call still proves the agent reached for
that tool.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coffer.domain.mcp.capability import MCPInvocation
from coffer.infrastructure.mcp.invocation_writer import MCPInvocationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)


async def _make_repo(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return MCPInvocationRepo(session_maker(engine)), engine


def _inv(
    name: str,
    key: str,
    when: datetime,
    *,
    ctype: str = "tool",
    status: str = "ok",
) -> MCPInvocation:
    return MCPInvocation(
        id=None,
        timestamp=when,
        resource_name=name,
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
            await repo.insert(_inv("jira", "jira_get_issue", now))
        await repo.insert(_inv("jira", "jira_search", now))
        await repo.insert(_inv("confluence", "confluence_get_page", now))

        counts = await repo.usage_counts(since=now - timedelta(days=1))

        assert counts[("jira", "jira_get_issue")] == 3
        assert counts[("jira", "jira_search")] == 1
        assert counts[("confluence", "confluence_get_page")] == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_usage_counts_excludes_rows_before_the_window(tmp_path):
    repo, engine = await _make_repo(tmp_path)
    now = datetime.now(tz=UTC)
    try:
        await repo.insert(_inv("jira", "jira_get_issue", now - timedelta(days=200)))
        await repo.insert(_inv("jira", "jira_search", now))

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
        await repo.insert(_inv("jira", "some_prompt", now, ctype="prompt"))

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
        await repo.insert(_inv("jira", "jira_get_issue", now, status="error"))

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
