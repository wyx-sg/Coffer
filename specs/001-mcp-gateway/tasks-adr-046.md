# ADR-046 Tool Tiering — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Coffer's aggregated tools reliably discoverable by the connecting agent — list a usage-ranked budgeted slice instead of the whole catalogue, tell the agent what Coffer is at `initialize`, and make a failed upstream discovery recover mid-session instead of vanishing for the session.

**Architecture:** A pure ranking/selection function in `domain/mcp/tool_tiering.py` (no I/O, mirrors `domain/mcp/tool_search.py`) is fed invocation counts read through a new `MCPInvocationRepoPort.usage_counts` method and applied as the last step of `MCPGatewaySession._handle_tools_list`. `handle_initialize` gains an `instructions` string. `gateway_aggregate_lists._one` reports which server failed instead of silently returning `None`, and the session schedules a background re-discovery that emits `notifications/tools/list_changed` on recovery.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, pytest / pytest-asyncio, React + TypeScript + Vitest (Task 8 only).

**Spec:** [`docs/decisions/ADR-046-budget-driven-tool-tiering.md`](../../docs/decisions/ADR-046-budget-driven-tool-tiering.md), amending [`docs/decisions/ADR-018-tool-retrieval-for-overload.md`](../../docs/decisions/ADR-018-tool-retrieval-for-overload.md) and [`specs/001-mcp-gateway/spec.md`](./spec.md).

## Global Constraints

- Backend files stay **under 400 LOC**; `make lint` enforces it. `gateway.py` is at 398 — do not grow it. New logic goes in new modules that `gateway.py` calls.
- **Layering (importlinter):** `domain/` imports nothing from `application/`, `infrastructure/`, or `surfaces/`. The tiering policy is pure and lives in `domain/`. Application code depends on Protocol ports from `application/mcp/ports.py`, never on infrastructure classes.
- **Wire-contract rule:** any change to an HTTP response model must be mirrored in `specs/001-mcp-gateway/contracts/` and pass `make verify-contract`.
- **Bilingual docs:** every `docs/decisions/*.md` and `specs/**/*.md` edit has a matching `.zh.md` edit. Does not apply to code comments or tests.
- **Conventional Commits**, scope `mcp-gateway`. Every commit ends with:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- Default tuning values, all overridable by env var (existing repo pattern, cf. `COFFER_MCP_SESSION_IDLE_S`):
  - `COFFER_TOOL_TIERING` — `auto` (default) | `off`
  - `COFFER_TOOL_TIERING_BUDGET` — `50` (upstream tools only; Coffer built-ins sit on top)
  - `COFFER_TOOL_TIERING_WINDOW_DAYS` — `90`
- Run `make verify` before opening the PR. It runs lint + unit + integration + contract + acceptance audit.

---

### Task 1: Usage counts on the invocation repo

**Files:**
- Modify: `backend/coffer/application/mcp/ports.py` (append to `MCPInvocationRepoPort`)
- Modify: `backend/coffer/infrastructure/mcp/invocation_writer.py` (append a method to `MCPInvocationRepo`)
- Test: `backend/tests/integration/infrastructure/mcp/test_invocation_usage_counts.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `MCPInvocationRepoPort.usage_counts(*, since: datetime) -> dict[tuple[str, str], int]` — maps `(resource_name, capability_key)` to the number of `capability_type == "tool"` invocations at or after `since`. Every status counts; an errored call still proves the agent reached for the tool.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/infrastructure/mcp/test_invocation_usage_counts.py
from datetime import UTC, datetime, timedelta

import pytest

from coffer.domain.mcp.capability import MCPInvocation
from coffer.infrastructure.mcp.invocation_writer import MCPInvocationRepo


def _inv(name: str, key: str, when: datetime, *, ctype: str = "tool") -> MCPInvocation:
    return MCPInvocation(
        id=None,
        timestamp=when,
        resource_name=name,
        capability_type=ctype,  # type: ignore[arg-type]
        capability_key=key,
        duration_ms=1,
        status="ok",
        error_message=None,
        session_id="s1",
    )


@pytest.mark.asyncio
async def test_usage_counts_groups_by_server_and_tool(session_maker):
    repo = MCPInvocationRepo(session_maker)
    now = datetime.now(tz=UTC)
    for _ in range(3):
        await repo.insert(_inv("jira", "jira_get_issue", now))
    await repo.insert(_inv("jira", "jira_search", now))
    await repo.insert(_inv("confluence", "confluence_get_page", now))

    counts = await repo.usage_counts(since=now - timedelta(days=1))

    assert counts[("jira", "jira_get_issue")] == 3
    assert counts[("jira", "jira_search")] == 1
    assert counts[("confluence", "confluence_get_page")] == 1


@pytest.mark.asyncio
async def test_usage_counts_excludes_rows_before_the_window(session_maker):
    repo = MCPInvocationRepo(session_maker)
    now = datetime.now(tz=UTC)
    await repo.insert(_inv("jira", "jira_get_issue", now - timedelta(days=200)))
    await repo.insert(_inv("jira", "jira_search", now))

    counts = await repo.usage_counts(since=now - timedelta(days=90))

    assert ("jira", "jira_get_issue") not in counts
    assert counts[("jira", "jira_search")] == 1


@pytest.mark.asyncio
async def test_usage_counts_ignores_non_tool_capabilities(session_maker):
    repo = MCPInvocationRepo(session_maker)
    now = datetime.now(tz=UTC)
    await repo.insert(_inv("jira", "some_prompt", now, ctype="prompt"))

    counts = await repo.usage_counts(since=now - timedelta(days=1))

    assert counts == {}
```

Check `backend/tests/integration/conftest.py` for the exact name of the async session-maker fixture and use that name; if it differs from `session_maker`, rename the parameter in all three tests.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/integration/infrastructure/mcp/test_invocation_usage_counts.py -v`
Expected: FAIL — `AttributeError: 'MCPInvocationRepo' object has no attribute 'usage_counts'`

- [ ] **Step 3: Add the port method**

In `backend/coffer/application/mcp/ports.py`, inside `class MCPInvocationRepoPort`, after `query`:

```python
    async def usage_counts(
        self,
        *,
        since: datetime,
    ) -> dict[tuple[str, str], int]: ...
```

- [ ] **Step 4: Implement it on the repo**

In `backend/coffer/infrastructure/mcp/invocation_writer.py`, append to `class MCPInvocationRepo` (import `func` from `sqlalchemy` and `select` if not already imported; reuse whatever ORM model `query` uses — read that method first and mirror its table reference):

```python
    async def usage_counts(
        self,
        *,
        since: datetime,
    ) -> dict[tuple[str, str], int]:
        """Tool-invocation counts per (server, tool) at or after ``since``.

        Feeds ADR-046 tool tiering. Every status counts — an errored call still
        proves the agent reached for that tool.
        """
        async with self._sm() as session:
            stmt = (
                select(
                    MCPInvocationRow.resource_name,
                    MCPInvocationRow.capability_key,
                    func.count().label("n"),
                )
                .where(MCPInvocationRow.capability_type == "tool")
                .where(MCPInvocationRow.timestamp >= since)
                .group_by(
                    MCPInvocationRow.resource_name,
                    MCPInvocationRow.capability_key,
                )
            )
            rows = (await session.execute(stmt)).all()
        return {(r.resource_name, r.capability_key): int(r.n) for r in rows}
```

Replace `MCPInvocationRow` with the actual ORM class name used by `query` in this file.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/integration/infrastructure/mcp/test_invocation_usage_counts.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/coffer/application/mcp/ports.py backend/coffer/infrastructure/mcp/invocation_writer.py backend/tests/integration/infrastructure/mcp/test_invocation_usage_counts.py
git commit -m "feat(mcp-gateway): read per-tool invocation counts for tiering

ADR-046 ranks the listed tool slice by real usage. Adds
MCPInvocationRepoPort.usage_counts(since=...) returning
{(server, tool): count} over tool invocations inside the window.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Pure tiering policy

**Files:**
- Create: `backend/coffer/domain/mcp/tool_tiering.py`
- Test: `backend/tests/unit/domain/mcp/test_tool_tiering.py`

**Interfaces:**
- Consumes: nothing (pure domain, no I/O).
- Produces:
  - `DEFAULT_BUDGET: int = 50`
  - `DEFAULT_WINDOW_DAYS: int = 90`
  - `TieringResult` — frozen dataclass with `listed: list[dict[str, Any]]` and `hidden_count: int`
  - `select_listed_tools(tools, usage, *, builtin_prefix, budget) -> TieringResult`
    - `tools`: the aggregated `tools/list` entries, each `{"name", "description", "inputSchema"}`, `name` already prefixed (`jira__jira_get_issue`, `coffer__recall`), in catalogue order.
    - `usage`: `dict[tuple[str, str], int]` from Task 1.
    - `builtin_prefix`: `"coffer__"`.
    - Returns the entries to list, built-ins first in their original order, then the selected upstream tools in catalogue order.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/domain/mcp/test_tool_tiering.py
from coffer.domain.mcp.tool_tiering import (
    DEFAULT_BUDGET,
    select_listed_tools,
)

PREFIX = "coffer__"


def _tool(name: str) -> dict:
    return {"name": name, "description": f"does {name}", "inputSchema": {}}


def _catalogue(server: str, n: int, start: int = 0) -> list[dict]:
    return [_tool(f"{server}__t{i}") for i in range(start, start + n)]


def _names(result) -> list[str]:
    return [t["name"] for t in result.listed]


def test_under_budget_lists_everything():
    tools = [_tool("coffer__recall"), *_catalogue("jira", 10)]

    result = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=DEFAULT_BUDGET)

    assert _names(result) == [t["name"] for t in tools]
    assert result.hidden_count == 0


def test_builtins_are_always_listed_even_over_budget():
    tools = [_tool("coffer__search_tools"), _tool("coffer__recall"), *_catalogue("jira", 80)]

    result = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=10)

    assert "coffer__search_tools" in _names(result)
    assert "coffer__recall" in _names(result)
    # 2 builtins + 10 upstream
    assert len(result.listed) == 12
    assert result.hidden_count == 70


def test_builtins_do_not_consume_the_upstream_budget():
    tools = [_tool("coffer__recall"), *_catalogue("jira", 20)]

    result = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=5)

    upstream = [n for n in _names(result) if not n.startswith(PREFIX)]
    assert len(upstream) == 5


def test_used_tools_outrank_unused_ones():
    tools = _catalogue("jira", 30)
    usage = {("jira", "t29"): 10, ("jira", "t28"): 5}

    result = select_listed_tools(tools, usage, builtin_prefix=PREFIX, budget=3)

    listed = _names(result)
    assert "jira__t29" in listed
    assert "jira__t28" in listed


def test_every_server_keeps_at_least_one_tool():
    tools = [*_catalogue("jira", 40), *_catalogue("seatalk", 5)]
    usage = {("jira", f"t{i}"): 100 - i for i in range(40)}

    result = select_listed_tools(tools, usage, builtin_prefix=PREFIX, budget=10)

    listed = _names(result)
    assert any(n.startswith("seatalk__") for n in listed)


def test_selection_is_deterministic_and_keeps_catalogue_order():
    tools = _catalogue("jira", 30)

    first = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=5)
    second = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=5)

    assert _names(first) == _names(second)
    assert _names(first) == sorted(_names(first), key=lambda n: [t["name"] for t in tools].index(n))


def test_zero_usage_falls_back_to_catalogue_order():
    tools = _catalogue("jira", 30)

    result = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=3)

    assert _names(result) == ["jira__t0", "jira__t1", "jira__t2"]


def test_hidden_count_counts_only_upstream_tools():
    tools = [_tool("coffer__recall"), *_catalogue("jira", 60)]

    result = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=50)

    assert result.hidden_count == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/unit/domain/mcp/test_tool_tiering.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'coffer.domain.mcp.tool_tiering'`

- [ ] **Step 3: Write the implementation**

```python
# backend/coffer/domain/mcp/tool_tiering.py
"""Budget-driven selection of the tools the gateway lists (ADR-046).

Pure: no I/O, no infra import, kind-agnostic (importlinter Contracts 2b/5/6).
Given the aggregated ``tools/list`` entries and per-(server, tool) invocation
counts, decides which entries to list. Everything not listed stays callable —
tiering is a listing-side policy only, and ``coffer__search_tools`` keeps
ranking the full catalogue.

Deterministic by construction: usage rank first, catalogue order as the tie
break, so an unchanged catalogue yields an identical slice every session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_BUDGET = 50
DEFAULT_WINDOW_DAYS = 90

# Separator between the server namespace and the upstream tool name, as
# applied by ``domain.mcp.namespace.prefix_tool``.
_NAMESPACE_SEP = "__"


@dataclass(frozen=True)
class TieringResult:
    """The listing decision. ``hidden_count`` counts upstream tools only."""

    listed: list[dict[str, Any]]
    hidden_count: int


def split_prefixed(name: str) -> tuple[str, str]:
    """``"jira__jira_get_issue"`` -> ``("jira", "jira_get_issue")``.

    Splits on the FIRST separator: server names never contain it, upstream
    tool names may.
    """
    server, sep, tool = name.partition(_NAMESPACE_SEP)
    if not sep:
        return "", name
    return server, tool


def select_listed_tools(
    tools: list[dict[str, Any]],
    usage: dict[tuple[str, str], int],
    *,
    builtin_prefix: str,
    budget: int,
) -> TieringResult:
    """Pick the tools to advertise in ``tools/list``.

    Coffer's own ``builtin_prefix`` tools are always listed and never consume
    the budget. Upstream tools at or under budget are all listed; over budget
    they are ranked by ``usage`` (descending) with catalogue order as the tie
    break, then trimmed to ``budget`` — after reserving one slot for each
    server so none disappears entirely.
    """
    builtins = [t for t in tools if str(t.get("name", "")).startswith(builtin_prefix)]
    upstream = [t for t in tools if not str(t.get("name", "")).startswith(builtin_prefix)]

    if len(upstream) <= budget:
        return TieringResult(listed=[*builtins, *upstream], hidden_count=0)

    order = {id(t): i for i, t in enumerate(upstream)}

    def _rank(tool: dict[str, Any]) -> tuple[int, int]:
        server, bare = split_prefixed(str(tool.get("name", "")))
        return (-usage.get((server, bare), 0), order[id(tool)])

    by_rank = sorted(upstream, key=_rank)

    # Reserve the best-ranked tool of each server first, so a server whose
    # tools are all unused still reaches the agent.
    chosen: list[dict[str, Any]] = []
    seen_servers: set[str] = set()
    for tool in by_rank:
        server, _ = split_prefixed(str(tool.get("name", "")))
        if server not in seen_servers:
            seen_servers.add(server)
            chosen.append(tool)
        if len(chosen) == budget:
            break

    # Fill the remaining budget in pure rank order.
    if len(chosen) < budget:
        picked = {id(t) for t in chosen}
        for tool in by_rank:
            if id(tool) in picked:
                continue
            chosen.append(tool)
            if len(chosen) == budget:
                break

    picked = {id(t) for t in chosen}
    listed_upstream = [t for t in upstream if id(t) in picked]
    return TieringResult(
        listed=[*builtins, *listed_upstream],
        hidden_count=len(upstream) - len(listed_upstream),
    )


__all__ = [
    "DEFAULT_BUDGET",
    "DEFAULT_WINDOW_DAYS",
    "TieringResult",
    "select_listed_tools",
    "split_prefixed",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/unit/domain/mcp/test_tool_tiering.py -v`
Expected: 8 passed

- [ ] **Step 5: Check layering and file size**

Run: `make lint`
Expected: PASS — the new module is pure domain and well under 400 LOC.

- [ ] **Step 6: Commit**

```bash
git add backend/coffer/domain/mcp/tool_tiering.py backend/tests/unit/domain/mcp/test_tool_tiering.py
git commit -m "feat(mcp-gateway): pure budget-driven tool tiering policy

ADR-046. Usage rank first, catalogue order as the tie break, one
reserved slot per server so no server disappears, and built-ins always
listed outside the budget. Pure and deterministic so the slice is
stable across sessions for an unchanged catalogue.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Tiering config from the environment

**Files:**
- Create: `backend/coffer/application/mcp/tiering_config.py`
- Test: `backend/tests/unit/application/mcp/test_tiering_config.py`

**Interfaces:**
- Consumes: `DEFAULT_BUDGET`, `DEFAULT_WINDOW_DAYS` from Task 2.
- Produces: `TieringConfig` frozen dataclass with `enabled: bool`, `budget: int`, `window_days: int`; and `load_tiering_config(env: Mapping[str, str] | None = None) -> TieringConfig`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/application/mcp/test_tiering_config.py
from coffer.application.mcp.tiering_config import load_tiering_config


def test_defaults_when_env_is_empty():
    cfg = load_tiering_config({})
    assert cfg.enabled is True
    assert cfg.budget == 50
    assert cfg.window_days == 90


def test_mode_off_disables_tiering():
    assert load_tiering_config({"COFFER_TOOL_TIERING": "off"}).enabled is False
    assert load_tiering_config({"COFFER_TOOL_TIERING": "OFF"}).enabled is False


def test_overrides_are_read():
    cfg = load_tiering_config(
        {"COFFER_TOOL_TIERING_BUDGET": "12", "COFFER_TOOL_TIERING_WINDOW_DAYS": "7"}
    )
    assert cfg.budget == 12
    assert cfg.window_days == 7


def test_unparseable_or_nonpositive_values_fall_back_to_defaults():
    for raw in ("abc", "0", "-5", ""):
        cfg = load_tiering_config({"COFFER_TOOL_TIERING_BUDGET": raw})
        assert cfg.budget == 50


def test_unknown_mode_keeps_tiering_on():
    # Only the explicit "off" disables it; a typo must not silently
    # re-expose the full catalogue.
    assert load_tiering_config({"COFFER_TOOL_TIERING": "auto"}).enabled is True
    assert load_tiering_config({"COFFER_TOOL_TIERING": "banana"}).enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/unit/application/mcp/test_tiering_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'coffer.application.mcp.tiering_config'`

- [ ] **Step 3: Write the implementation**

```python
# backend/coffer/application/mcp/tiering_config.py
"""Environment-sourced knobs for ADR-046 tool tiering.

Follows the repo's existing env-var tuning pattern (cf.
``COFFER_MCP_SESSION_IDLE_S``). No DB table and no CRUD surface: these are
operator escape hatches, not user-facing settings.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from coffer.domain.mcp.tool_tiering import DEFAULT_BUDGET, DEFAULT_WINDOW_DAYS

MODE_ENV = "COFFER_TOOL_TIERING"
BUDGET_ENV = "COFFER_TOOL_TIERING_BUDGET"
WINDOW_ENV = "COFFER_TOOL_TIERING_WINDOW_DAYS"


@dataclass(frozen=True)
class TieringConfig:
    enabled: bool
    budget: int
    window_days: int


def _positive_int(raw: str | None, default: int) -> int:
    """Parse a positive int, falling back to ``default`` on anything else.

    A malformed knob must never be able to shrink the listed catalogue to
    nothing — misconfiguration degrades to the documented default.
    """
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def load_tiering_config(env: Mapping[str, str] | None = None) -> TieringConfig:
    source: Mapping[str, str] = os.environ if env is None else env
    # Only the explicit "off" disables tiering: a typo must not silently
    # restore the pre-ADR-046 full-catalogue listing.
    enabled = source.get(MODE_ENV, "auto").strip().lower() != "off"
    return TieringConfig(
        enabled=enabled,
        budget=_positive_int(source.get(BUDGET_ENV), DEFAULT_BUDGET),
        window_days=_positive_int(source.get(WINDOW_ENV), DEFAULT_WINDOW_DAYS),
    )


__all__ = ["BUDGET_ENV", "MODE_ENV", "WINDOW_ENV", "TieringConfig", "load_tiering_config"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/unit/application/mcp/test_tiering_config.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/coffer/application/mcp/tiering_config.py backend/tests/unit/application/mcp/test_tiering_config.py
git commit -m "feat(mcp-gateway): env knobs for tool tiering

COFFER_TOOL_TIERING (auto|off), _BUDGET, _WINDOW_DAYS. Only an explicit
'off' disables tiering, and unparseable values fall back to defaults, so
a typo can never silently change what the gateway lists.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Apply tiering in the gateway session

**Files:**
- Create: `backend/coffer/application/mcp/gateway_tiering.py`
- Modify: `backend/coffer/application/mcp/gateway.py` (`__init__` signature; `_handle_tools_list`)
- Modify: `backend/coffer/surfaces/http/app_mcp_composition.py` (pass the new constructor arg at all three `MCPGatewaySession(...)` call sites — grep for `machine_id=_local_machine_id`, they are on lines 119, 134, 161)
- Test: `backend/tests/integration/application/mcp/test_gateway_tiering.py`

**Interfaces:**
- Consumes: `select_listed_tools`, `TieringResult` (Task 2); `TieringConfig`, `load_tiering_config` (Task 3); `MCPInvocationRepoPort.usage_counts` (Task 1).
- Produces:
  - `apply_tiering(tools, *, invocations, config, clock) -> TieringResult` in `gateway_tiering.py`.
  - `MCPGatewaySession.last_hidden_count: int` — the most recent `tools/list`'s hidden upstream count, read by Task 5's `instructions`. Starts at `0`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/application/mcp/test_gateway_tiering.py
from datetime import UTC, datetime

import pytest

from coffer.application.mcp.gateway_tiering import apply_tiering
from coffer.application.mcp.tiering_config import TieringConfig


class _Invocations:
    def __init__(self, counts=None, fail=False):
        self._counts = counts or {}
        self._fail = fail
        self.since_seen = None

    async def usage_counts(self, *, since):
        if self._fail:
            raise RuntimeError("db is down")
        self.since_seen = since
        return self._counts


def _tools(n: int, server: str = "jira") -> list[dict]:
    return [{"name": f"{server}__t{i}", "description": "", "inputSchema": {}} for i in range(n)]


def _clock():
    return datetime(2026, 9, 9, tzinfo=UTC)


@pytest.mark.asyncio
async def test_tiering_trims_to_budget():
    tools = [{"name": "coffer__recall", "description": "", "inputSchema": {}}, *_tools(80)]
    cfg = TieringConfig(enabled=True, budget=10, window_days=90)

    result = await apply_tiering(tools, invocations=_Invocations(), config=cfg, clock=_clock)

    assert len(result.listed) == 11  # 1 builtin + 10 upstream
    assert result.hidden_count == 70


@pytest.mark.asyncio
async def test_disabled_config_lists_everything():
    tools = _tools(80)
    cfg = TieringConfig(enabled=False, budget=10, window_days=90)

    result = await apply_tiering(tools, invocations=_Invocations(), config=cfg, clock=_clock)

    assert len(result.listed) == 80
    assert result.hidden_count == 0


@pytest.mark.asyncio
async def test_usage_query_failure_degrades_to_listing_everything():
    """A broken statistics layer must never make tools disappear (ADR-046)."""
    tools = _tools(80)
    cfg = TieringConfig(enabled=True, budget=10, window_days=90)

    result = await apply_tiering(
        tools, invocations=_Invocations(fail=True), config=cfg, clock=_clock
    )

    assert len(result.listed) == 80
    assert result.hidden_count == 0


@pytest.mark.asyncio
async def test_window_is_derived_from_config():
    tools = _tools(80)
    cfg = TieringConfig(enabled=True, budget=10, window_days=7)
    inv = _Invocations()

    await apply_tiering(tools, invocations=inv, config=cfg, clock=_clock)

    assert (_clock() - inv.since_seen).days == 7


@pytest.mark.asyncio
async def test_usage_counts_drive_the_selection():
    tools = _tools(80)
    cfg = TieringConfig(enabled=True, budget=2, window_days=90)
    inv = _Invocations({("jira", "t70"): 9, ("jira", "t71"): 8})

    result = await apply_tiering(tools, invocations=inv, config=cfg, clock=_clock)

    assert [t["name"] for t in result.listed] == ["jira__t70", "jira__t71"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/integration/application/mcp/test_gateway_tiering.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'coffer.application.mcp.gateway_tiering'`

- [ ] **Step 3: Write the tiering application helper**

```python
# backend/coffer/application/mcp/gateway_tiering.py
"""Applies the ADR-046 tiering policy to an aggregated tools/list result.

Kept out of ``gateway.py`` so that file stays under its 400-LOC ceiling. The
policy itself is pure and lives in ``domain.mcp.tool_tiering``; this module
only supplies it with usage counts and enforces the fail-open rule.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from coffer.application.builtin_tools import COFFER_TOOL_PREFIX
from coffer.application.mcp.ports import MCPInvocationRepoPort
from coffer.application.mcp.tiering_config import TieringConfig
from coffer.domain.mcp.tool_tiering import TieringResult, select_listed_tools

_logger = logging.getLogger(__name__)


async def apply_tiering(
    tools: list[dict[str, Any]],
    *,
    invocations: MCPInvocationRepoPort,
    config: TieringConfig,
    clock: Callable[[], datetime],
) -> TieringResult:
    """Return the slice of ``tools`` to list, per ADR-046.

    Fails open: when tiering is off, or the usage query raises, every tool is
    listed. A broken statistics layer must never be able to hide tools.
    """
    if not config.enabled:
        return TieringResult(listed=list(tools), hidden_count=0)

    since = clock() - timedelta(days=config.window_days)
    try:
        usage = await invocations.usage_counts(since=since)
    except Exception:
        _logger.warning("mcp.gateway.tiering.usage_query_failed", exc_info=True)
        return TieringResult(listed=list(tools), hidden_count=0)

    return select_listed_tools(
        tools,
        usage,
        builtin_prefix=COFFER_TOOL_PREFIX,
        budget=config.budget,
    )


__all__ = ["apply_tiering"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/integration/application/mcp/test_gateway_tiering.py -v`
Expected: 5 passed

- [ ] **Step 5: Wire it into the session**

In `backend/coffer/application/mcp/gateway.py`:

Add to the imports:

```python
from coffer.application.mcp.gateway_tiering import apply_tiering
from coffer.application.mcp.tiering_config import TieringConfig, load_tiering_config
```

Add a keyword-only parameter at the end of `__init__`'s signature:

```python
        tiering: TieringConfig | None = None,
```

and in the body, next to `self._builtin = ...`:

```python
        # ADR-046: how much of the aggregated catalogue this session lists.
        # Resolved once per session; None means "read the environment".
        self._tiering = tiering or load_tiering_config()
        # Upstream tools left unlisted by the most recent tools/list. Read by
        # handle_initialize's instructions text (Task 5) — it is 0 until the
        # client has listed at least once, which is the honest value: nothing
        # has been hidden yet.
        self.last_hidden_count = 0
```

Replace `_handle_tools_list` with:

```python
    async def _handle_tools_list(self) -> dict[str, Any]:
        result = await list_tools_across(
            self._discovery, self._ensure_subscribed, await self._enabled_mcp_servers()
        )
        append_builtin_tools(result["tools"], self._builtin)
        tiered = await apply_tiering(
            result["tools"],
            invocations=self._invocations,
            config=self._tiering,
            clock=self._clock,
        )
        self.last_hidden_count = tiered.hidden_count
        return {"tools": tiered.listed}
```

- [ ] **Step 6: Verify the file-size ceiling still holds**

Run: `make lint`
Expected: PASS. If `gateway.py` now exceeds 400 LOC, move the three added `__init__` lines' comments into `gateway_tiering.py`'s module docstring rather than deleting logic.

- [ ] **Step 7: Run the full MCP test suite**

Run: `.venv/bin/python -m pytest backend/tests/unit/application/mcp backend/tests/integration/application/mcp -v`
Expected: all pass. Existing `tools/list` tests that assert on the full catalogue should still pass because their fixtures list far fewer than 50 upstream tools; if one fails because it exceeds the budget, pass `tiering=TieringConfig(enabled=False, budget=50, window_days=90)` when constructing the session in that test rather than changing the production default.

- [ ] **Step 8: Commit**

```bash
git add backend/coffer/application/mcp/gateway_tiering.py backend/coffer/application/mcp/gateway.py backend/coffer/surfaces/http/app_mcp_composition.py backend/tests/integration/application/mcp/test_gateway_tiering.py
git commit -m "feat(mcp-gateway): list a budgeted tool slice

ADR-046. tools/list now returns built-ins plus the usage-ranked upstream
slice. Fails open in both directions: tiering off, or a failing usage
query, lists everything. tools/call is untouched, so unlisted tools stay
callable and search_tools keeps ranking the full catalogue.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: `initialize` instructions

**Files:**
- Create: `backend/coffer/application/mcp/gateway_instructions.py`
- Modify: `backend/coffer/application/mcp/gateway.py` (`handle_initialize`)
- Test: `backend/tests/contract/mcp/test_initialize_instructions.py`

**Interfaces:**
- Consumes: `MCPGatewaySession.last_hidden_count` (Task 4).
- Produces: `build_instructions(*, hidden_count: int) -> str` — at most 800 characters.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/contract/mcp/test_initialize_instructions.py
from coffer.application.mcp.gateway_instructions import (
    MAX_INSTRUCTIONS_CHARS,
    build_instructions,
)


def test_instructions_fit_the_system_prompt_budget():
    # It lands in every session's system prompt; ADR-046 caps it.
    assert len(build_instructions(hidden_count=0)) <= MAX_INSTRUCTIONS_CHARS
    assert len(build_instructions(hidden_count=9999)) <= MAX_INSTRUCTIONS_CHARS


def test_instructions_name_the_escape_hatch():
    text = build_instructions(hidden_count=70)
    assert "coffer__search_tools" in text


def test_instructions_report_the_hidden_count():
    assert "70" in build_instructions(hidden_count=70)


def test_no_hidden_tools_means_no_misleading_claim():
    text = build_instructions(hidden_count=0)
    # Must not tell the agent tools are hidden when none are.
    assert "not listed" not in text
```

And the wiring check, in the same file:

```python
import pytest

from coffer.application.mcp.gateway_instructions import MAX_INSTRUCTIONS_CHARS


@pytest.mark.asyncio
async def test_initialize_returns_instructions(gateway_session):
    result = await gateway_session.handle_initialize(
        {"protocolVersion": "2025-06-18", "capabilities": {}}
    )

    assert "instructions" in result
    assert 0 < len(result["instructions"]) <= MAX_INSTRUCTIONS_CHARS
    assert result["protocolVersion"] == "2025-06-18"
```

Reuse whatever session-construction fixture the existing gateway tests use — grep `backend/tests/` for `MCPGatewaySession(` and copy that fixture, naming it `gateway_session` in a local `conftest.py` if one does not already provide it.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/contract/mcp/test_initialize_instructions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'coffer.application.mcp.gateway_instructions'`

- [ ] **Step 3: Write the implementation**

```python
# backend/coffer/application/mcp/gateway_instructions.py
"""The MCP ``instructions`` string Coffer returns at ``initialize`` (ADR-046).

This is the only channel a server has into the client's system prompt, so it
is the one place the tiering contract can actually reach the agent that has to
follow it. It is charged against every session's context, so it is capped and
deliberately terse — the context it spends must stay far below what tiering
saves.
"""

from __future__ import annotations

MAX_INSTRUCTIONS_CHARS = 800

_BASE = (
    "Coffer is this machine's local vault: it aggregates the user's MCP servers "
    "behind one endpoint and adds its own coffer__* tools for memory (recall, "
    "remember), knowledge (search_knowledge, ask) and skills (list_skills, "
    "load_skill). Prefer coffer__recall before asking the user something they "
    "may have already told Coffer."
)

_TIERED = (
    " The tools listed here are the ones used most on this machine; {n} further "
    "upstream tools are not listed. Call coffer__search_tools with a plain-language "
    "description of what you need to find them — it searches the full catalogue, "
    "and every tool it returns is callable by name straight away."
)


def build_instructions(*, hidden_count: int) -> str:
    """Build the per-session instructions text.

    ``hidden_count`` is the number of upstream tools the last ``tools/list``
    left unlisted. When it is 0 nothing is hidden, so the tiering paragraph is
    omitted rather than making a claim that is not true for this session.
    """
    text = _BASE
    if hidden_count > 0:
        text += _TIERED.format(n=hidden_count)
    return text[:MAX_INSTRUCTIONS_CHARS]


__all__ = ["MAX_INSTRUCTIONS_CHARS", "build_instructions"]
```

- [ ] **Step 4: Wire it into `handle_initialize`**

In `backend/coffer/application/mcp/gateway.py`, add the import:

```python
from coffer.application.mcp.gateway_instructions import build_instructions
```

and change the `return` of `handle_initialize` to:

```python
        return {
            "protocolVersion": "2025-06-18",
            "capabilities": _COFFER_SERVER_CAPABILITIES,
            "serverInfo": {
                "name": "coffer",
                "version": "0.1.0",
            },
            # ADR-046: the only channel into the client's system prompt. On the
            # first handshake nothing has been listed yet, so hidden_count is 0
            # and the tiering paragraph is omitted; a client that re-initializes
            # after listing gets the real number.
            "instructions": build_instructions(hidden_count=self.last_hidden_count),
        }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/contract/mcp/test_initialize_instructions.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add backend/coffer/application/mcp/gateway_instructions.py backend/coffer/application/mcp/gateway.py backend/tests/contract/mcp/test_initialize_instructions.py
git commit -m "feat(mcp-gateway): return MCP instructions at initialize

ADR-046. The gateway never used the one channel it has into the client's
system prompt, so no agent was ever told what Coffer is or that
search_tools reaches the rest of the catalogue. Capped at 800 chars and
it omits the tiering paragraph when nothing is actually hidden.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Recoverable upstream-discovery degradation

**Files:**
- Modify: `backend/coffer/application/mcp/gateway_aggregate_lists.py` (`_one`, `_aggregate`, the three `list_*_across` functions)
- Modify: `backend/coffer/application/mcp/gateway.py` (`_handle_tools_list`, plus a background recovery task)
- Test: `backend/tests/integration/application/mcp/test_gateway_degraded_recovery.py`

**Interfaces:**
- Consumes: nothing from earlier tasks beyond Task 4's `_handle_tools_list` shape.
- Produces: `AggregateOutcome` frozen dataclass in `gateway_aggregate_lists.py` with `items: list[dict[str, Any]]` and `failed_servers: list[str]`; `list_tools_across` returns it. `list_resources_across` / `list_prompts_across` keep returning plain dicts — only the tools path needs recovery.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/application/mcp/test_gateway_degraded_recovery.py
import asyncio

import pytest

from coffer.application.mcp.gateway_aggregate_lists import list_tools_across
from coffer.domain.errors import UpstreamUnavailable


class _Discovery:
    """Fails for 'jira' until ``heal()`` is called; 'seatalk' always works."""

    def __init__(self):
        self.healed = False

    async def list_tools(self, server: str):
        if server == "jira" and not self.healed:
            raise UpstreamUnavailable("cold spawn too slow")
        return [_FakeTool(f"{server}__t1")]

    def heal(self):
        self.healed = True


class _FakeTool:
    def __init__(self, prefixed: str):
        self.prefixed_name = prefixed
        self.description = ""
        self.input_schema = {}


async def _noop(_server: str) -> None:
    return None


@pytest.mark.asyncio
async def test_failed_server_is_reported_not_silently_dropped():
    outcome = await list_tools_across(_Discovery(), _noop, ["jira", "seatalk"])

    assert [t["name"] for t in outcome.items] == ["seatalk__t1"]
    assert outcome.failed_servers == ["jira"]


@pytest.mark.asyncio
async def test_recovered_server_returns_on_the_next_list():
    discovery = _Discovery()
    first = await list_tools_across(discovery, _noop, ["jira", "seatalk"])
    assert first.failed_servers == ["jira"]

    discovery.heal()
    second = await list_tools_across(discovery, _noop, ["jira", "seatalk"])

    assert second.failed_servers == []
    assert {t["name"] for t in second.items} == {"jira__t1", "seatalk__t1"}


@pytest.mark.asyncio
async def test_all_healthy_reports_no_failures():
    discovery = _Discovery()
    discovery.heal()

    outcome = await list_tools_across(discovery, _noop, ["jira", "seatalk"])

    assert outcome.failed_servers == []
    assert len(outcome.items) == 2
```

Add the session-level recovery test in the same file:

```python
@pytest.mark.asyncio
async def test_session_emits_list_changed_when_a_degraded_server_recovers(
    gateway_session_factory,
):
    """The defect ADR-046 fixes: without this the client's cached tools/list
    keeps the server's tools missing for the whole session, because no
    notification can arrive from a server that never connected."""
    discovery = _Discovery()
    sent: list[dict] = []

    session = gateway_session_factory(discovery=discovery, servers=["jira", "seatalk"])
    session.set_downstream_sink(lambda payload: sent.append(payload) or asyncio.sleep(0))

    await session.handle_request("tools/list")
    assert session.degraded_servers == {"jira"}

    discovery.heal()
    await session.recover_degraded_now()

    assert any(
        p.get("method") == "notifications/tools/list_changed" for p in sent
    )
    assert session.degraded_servers == set()
```

Build `gateway_session_factory` in this file (or a local `conftest.py`) by copying the session construction used by the existing integration tests — grep `backend/tests/integration/application/mcp/` for `MCPGatewaySession(`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/integration/application/mcp/test_gateway_degraded_recovery.py -v`
Expected: FAIL — `list_tools_across` returns a `dict`, so `outcome.items` raises `AttributeError`.

- [ ] **Step 3: Report the failing server and fix the logging**

In `backend/coffer/application/mcp/gateway_aggregate_lists.py`, add to the imports:

```python
from dataclasses import dataclass
```

Add after `EnsureSubscribed`:

```python
@dataclass(frozen=True)
class AggregateOutcome:
    """One aggregate list plus the servers that could not be reached.

    ADR-046: a caller that knows WHICH servers failed can retry them and tell
    the client to re-list. Silently returning only the survivors made a slow
    cold spawn cost the client that server for the whole session.
    """

    items: list[dict[str, Any]]
    failed_servers: list[str]
```

Replace `_one` with a version that names the server and renders the error — the current `extra=` call never reaches the configured log format, which is why the 180 warnings in the daemon log say nothing:

```python
async def _one(
    server: str,
    fetcher: Callable[[str], Awaitable[Any]],
    ensure_subscribed: EnsureSubscribed,
    failure_event: str,
) -> Any:
    try:
        result = await asyncio.wait_for(fetcher(server), timeout=PER_SERVER_LIST_TIMEOUT)
        await ensure_subscribed(server)
    except (
        UpstreamUnavailable,
        UpstreamTimeout,
        TimeoutError,
        # Unresolvable credentials (locked OS keychain, missing ref) surface
        # when the fetch cold-spawns the upstream; they are that server's
        # problem alone and must not take down the whole aggregate.
        CredentialLocked,
        CredentialMissing,
    ) as e:
        _logger.warning(
            "%s server=%s error=%s: %s",
            failure_event,
            server,
            type(e).__name__,
            e,
        )
        return None
    return result
```

Change `_aggregate` to track which servers failed and return an `AggregateOutcome`:

```python
async def _aggregate(
    fetcher: Callable[[str], Awaitable[Any]],
    ensure_subscribed: EnsureSubscribed,
    servers: list[str],
    *,
    failure_event: str,
    project: Callable[[Any], dict[str, Any]],
) -> AggregateOutcome:
    """Shared parallel fan-out: discover each server under the per-server
    budget, record failed batches, then flatten via ``project`` into one list."""
    results = await asyncio.gather(
        *(_one(s, fetcher, ensure_subscribed, failure_event) for s in servers)
    )
    items: list[dict[str, Any]] = []
    failed: list[str] = []
    for server, batch in zip(servers, results, strict=True):
        if batch is None:
            failed.append(server)
            continue
        items.extend(project(x) for x in batch)
    return AggregateOutcome(items=items, failed_servers=failed)
```

Change the three public functions. `list_tools_across` returns the outcome; the other two keep their existing `dict` shape so their callers are untouched:

```python
async def list_tools_across(
    discovery: CapabilityDiscovery,
    ensure_subscribed: EnsureSubscribed,
    servers: list[str],
) -> AggregateOutcome:
    return await _aggregate(
        discovery.list_tools,
        ensure_subscribed,
        servers,
        failure_event="mcp.gateway.list_tools.upstream_failed",
        project=_tool_entry,
    )


async def list_resources_across(
    discovery: CapabilityDiscovery,
    ensure_subscribed: EnsureSubscribed,
    servers: list[str],
) -> dict[str, Any]:
    outcome = await _aggregate(
        discovery.list_resources,
        ensure_subscribed,
        servers,
        failure_event="mcp.gateway.list_resources.upstream_failed",
        project=_resource_entry,
    )
    return {"resources": outcome.items}


async def list_prompts_across(
    discovery: CapabilityDiscovery,
    ensure_subscribed: EnsureSubscribed,
    servers: list[str],
) -> dict[str, Any]:
    outcome = await _aggregate(
        discovery.list_prompts,
        ensure_subscribed,
        servers,
        failure_event="mcp.gateway.list_prompts.upstream_failed",
        project=_prompt_entry,
    )
    return {"prompts": outcome.items}
```

Add `AggregateOutcome` to the module's `__all__` if it defines one.

- [ ] **Step 4: Update the two `list_tools_across` call sites in the session**

In `backend/coffer/application/mcp/gateway.py`, `_handle_tools_list` becomes:

```python
    async def _handle_tools_list(self) -> dict[str, Any]:
        outcome = await list_tools_across(
            self._discovery, self._ensure_subscribed, await self._enabled_mcp_servers()
        )
        self._degraded = set(outcome.failed_servers)
        if self._degraded:
            self._schedule_degraded_recovery()
        tools = list(outcome.items)
        append_builtin_tools(tools, self._builtin)
        tiered = await apply_tiering(
            tools,
            invocations=self._invocations,
            config=self._tiering,
            clock=self._clock,
        )
        self.last_hidden_count = tiered.hidden_count
        return {"tools": tiered.listed}
```

And in `_handle_tools_call`, the `TOOL_SEARCH_NAME` branch, replace `listed["tools"]` with the outcome's items so search still ranks the FULL catalogue (this is what keeps unlisted tools discoverable):

```python
        if name == TOOL_SEARCH_NAME:
            outcome = await list_tools_across(
                self._discovery, self._ensure_subscribed, await self._enabled_mcp_servers()
            )
            embedder = await self._embedder_provider() if self._embedder_provider else None
            return await dispatch_tool_search(
                params=params,
                aggregated_tools=outcome.items,
                invocations=self._invocations,
                session_id=self.id,
                clock=self._clock,
                embedder=embedder,
            )
```

- [ ] **Step 5: Add the recovery machinery to the session**

In `gateway.py`'s `__init__`, next to `self._notification_tasks`:

```python
        # ADR-046: servers whose discovery failed on the last tools/list. A
        # client caches tools/list, and no list_changed can arrive from a
        # server that never connected — so the session retries them itself and
        # tells the client to re-list once one comes back.
        self._degraded: set[str] = set()
        self._recovery_task: asyncio.Task[None] | None = None
```

Add a public read-only view plus the recovery methods (place them right after `_ensure_subscribed`):

```python
    @property
    def degraded_servers(self) -> set[str]:
        """Servers whose tools are missing from the last listing."""
        return set(self._degraded)

    def _schedule_degraded_recovery(self) -> None:
        """Start one background recovery pass, if none is already running."""
        if self._recovery_task is not None and not self._recovery_task.done():
            return
        task = asyncio.ensure_future(self._recover_degraded_loop())
        self._recovery_task = task
        self._notification_tasks.add(task)
        task.add_done_callback(self._notification_tasks.discard)

    async def _recover_degraded_loop(self) -> None:
        """Retry degraded servers on a widening delay, up to three attempts.

        Bounded on purpose: the supervisor already owns sticky background
        recovery, and this exists only to un-stick the client's cached list.
        """
        for delay in (2.0, 8.0, 30.0):
            await asyncio.sleep(delay)
            if not self._degraded:
                return
            if await self.recover_degraded_now():
                return

    async def recover_degraded_now(self) -> bool:
        """Re-discover degraded servers once. Returns True if any recovered.

        On recovery the discovery cache slice is invalidated and the client is
        told to re-list, which is the step that actually puts the tools back
        in front of the agent mid-session.
        """
        recovered = False
        for server in sorted(self._degraded):
            try:
                await self._discovery.list_tools(server)
            except Exception:
                continue
            self._discovery.invalidate(server, "tool")
            self._degraded.discard(server)
            recovered = True
        if recovered:
            await self._send_downstream(
                {"method": "notifications/tools/list_changed", "params": {}}
            )
        return recovered
```

In `dispose`, before `self._notification_subscriptions.clear()`:

```python
        if self._recovery_task is not None:
            self._recovery_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._recovery_task
            self._recovery_task = None
        self._degraded.clear()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/integration/application/mcp/test_gateway_degraded_recovery.py -v`
Expected: 4 passed

- [ ] **Step 7: Run the whole MCP suite and lint**

Run: `.venv/bin/python -m pytest backend/tests/unit/application/mcp backend/tests/integration/application/mcp -v && make lint`
Expected: all pass. Any existing test asserting `list_tools_across(...)["tools"]` must be updated to `.items` — that is the intended contract change.

- [ ] **Step 8: Commit**

```bash
git add backend/coffer/application/mcp/gateway_aggregate_lists.py backend/coffer/application/mcp/gateway.py backend/tests/integration/application/mcp/test_gateway_degraded_recovery.py
git commit -m "fix(mcp-gateway): recover from a failed upstream tool listing

A per-server discovery timeout dropped that server's whole tool list for
the life of the session: the client caches tools/list and no
list_changed can arrive from a server that never connected. The session
now tracks which servers failed, retries them in the background, and
emits list_changed on recovery so the client re-lists.

The failure log also gains the server name and error — the previous
extra= call never reached the configured format, so 180 warnings in the
daemon log said only that something, somewhere, had failed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Fix the search corpus

**Files:**
- Modify: `backend/coffer/application/mcp/gateway_tool_search.py` (`execute_tool_search`, `_semantic_rank`)
- Test: `backend/tests/unit/application/mcp/test_gateway_tool_search.py` (add cases)

**Interfaces:**
- Consumes: `split_prefixed` from Task 2's `domain/mcp/tool_tiering.py`.
- Produces: no new public names; the ranking corpus text changes from `"<prefixed_name>: <desc>"` to `"<server> <bare_name>: <desc>"`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/application/mcp/test_gateway_tool_search.py`:

```python
from coffer.application.mcp.gateway_tool_search import _search_corpus


def test_corpus_drops_the_duplicated_server_token():
    """`jira__jira_get_issue` tokenizes as jira, jira, get, issue — the server
    name lands twice at name weight and crowds out the intent tokens."""
    corpus = _search_corpus(
        [{"name": "jira__jira_get_issue", "description": "Fetch an issue"}]
    )

    assert corpus == [("jira jira_get_issue", "Fetch an issue")]


def test_corpus_handles_a_tool_name_containing_the_separator():
    corpus = _search_corpus(
        [{"name": "srv__weird__tool", "description": "d"}]
    )

    assert corpus == [("srv weird__tool", "d")]


@pytest.mark.asyncio
async def test_ranking_still_finds_the_right_tool_after_the_corpus_change():
    result = await execute_tool_search({"query": "create an issue", "top_k": 1}, _agg())

    assert result["tools"][0]["name"] == "github__create_issue"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/unit/application/mcp/test_gateway_tool_search.py -v`
Expected: FAIL — `ImportError: cannot import name '_search_corpus'`

- [ ] **Step 3: Write the implementation**

In `backend/coffer/application/mcp/gateway_tool_search.py`, add the import:

```python
from coffer.domain.mcp.tool_tiering import split_prefixed
```

Add the helper next to `_clamp_top_k`:

```python
def _search_corpus(tools: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Build the (name_text, description) pairs the rankers score.

    The listed name is doubly namespaced — ``jira__jira_get_issue`` tokenizes
    as jira, jira, get, issue — so the server token lands twice at the ranker's
    name weight and crowds out the tokens that actually carry the intent.
    Splitting the namespace off collapses it to one occurrence.
    """
    corpus: list[tuple[str, str]] = []
    for tool in tools:
        server, bare = split_prefixed(str(tool.get("name", "")))
        text = f"{server} {bare}".strip() if server else bare
        corpus.append((text, str(tool.get("description", ""))))
    return corpus
```

In `execute_tool_search`, replace the `catalogue = [...]` line with:

```python
    catalogue = _search_corpus(candidates)
```

`_semantic_rank` already consumes `catalogue`, so it picks the change up unchanged. Add `_search_corpus` to `__all__`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/unit/application/mcp/test_gateway_tool_search.py -v`
Expected: all pass, including the pre-existing cases.

- [ ] **Step 5: Commit**

```bash
git add backend/coffer/application/mcp/gateway_tool_search.py backend/tests/unit/application/mcp/test_gateway_tool_search.py
git commit -m "fix(mcp-gateway): stop double-counting the server name when ranking

jira__jira_get_issue tokenized as jira, jira, get, issue, so the server
token landed twice at the ranker's name weight and diluted the intent
tokens. Both the BM25 and the semantic path now score '<server>
<bare_name>'.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Surface tiering in the management UI and update the docs

The ADR records "why can't the agent see tool X" as a real cost of tiering. This task pays it down: the capabilities page says which tools are currently listed.

**Files:**
- Modify: `backend/coffer/surfaces/http/schemas.py` (`MCPToolView`, `CapabilityListOut`)
- Modify: `backend/coffer/surfaces/http/mcp/capability_views.py` (`live_capability_list`)
- Modify: `specs/001-mcp-gateway/contracts/` (the capabilities response schema)
- Modify: `frontend/src/kinds/mcp/CapabilityList.tsx`
- Modify: `specs/001-mcp-gateway/spec.md` and `spec.zh.md`
- Test: `backend/tests/contract/` (existing capabilities contract test), `frontend/src/kinds/mcp/CapabilityList.test.tsx`

**Interfaces:**
- Consumes: `select_listed_tools` (Task 2), `load_tiering_config` (Task 3).
- Produces: `MCPToolView.listed: bool` (default `True`) and `CapabilityListOut.hidden_count: int` (default `0`).

- [ ] **Step 1: Write the failing frontend test**

Append to `frontend/src/kinds/mcp/CapabilityList.test.tsx`, matching the render helpers already in that file:

```tsx
it("marks tools that are not listed to agents", () => {
  renderCapabilityList({
    tools: [
      { name: "jira_get_issue", enabled: true, listed: true },
      { name: "jira_rare_tool", enabled: true, listed: false },
    ],
  });

  expect(screen.getByText("jira_rare_tool").closest("tr")).toHaveTextContent(
    /search only/i,
  );
  expect(screen.getByText("jira_get_issue").closest("tr")).not.toHaveTextContent(
    /search only/i,
  );
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/kinds/mcp/CapabilityList.test.tsx`
Expected: FAIL — no "search only" text is rendered.

- [ ] **Step 3: Add `listed` to the backend view**

In `backend/coffer/surfaces/http/schemas.py`, add to `MCPToolView`:

```python
    # ADR-046: false when tiering leaves this tool out of tools/list. It stays
    # callable and searchable — this flag is only about what agents see listed.
    listed: bool = True
```

and to `CapabilityListOut`:

```python
    hidden_count: int = 0
```

In `backend/coffer/surfaces/http/mcp/capability_views.py`, inside `live_capability_list`, compute the flag by running the same policy the gateway runs. Read the function first and follow its existing construction of `MCPToolView`; the addition is:

```python
    from coffer.application.mcp.tiering_config import load_tiering_config
    from coffer.domain.mcp.tool_tiering import select_listed_tools

    config = load_tiering_config()
    entries = [
        {"name": t.prefixed_name, "description": t.description, "inputSchema": t.input_schema}
        for t in tools
    ]
    if config.enabled:
        # usage counts are not available on this read-only management path;
        # an empty map degrades to catalogue order, which matches what a
        # never-used server would see anyway.
        result = select_listed_tools(entries, {}, builtin_prefix="coffer__", budget=config.budget)
        listed_names = {t["name"] for t in result.listed}
        hidden_count = result.hidden_count
    else:
        listed_names = {e["name"] for e in entries}
        hidden_count = 0
```

then pass `listed=(t.prefixed_name in listed_names)` when building each `MCPToolView`, and `hidden_count=hidden_count` on the `CapabilityListOut`.

- [ ] **Step 4: Render the badge**

In `frontend/src/kinds/mcp/CapabilityList.tsx`, add `listed?: boolean` to the tool row type, and in the row render, next to the existing enabled control, add:

```tsx
{tool.listed === false && (
  <span className="badge badge-muted" title={t("mcp.capabilities.searchOnlyHint")}>
    {t("mcp.capabilities.searchOnly")}
  </span>
)}
```

Add both keys to the i18n resource files this component already reads (follow the neighbouring keys in `frontend/src/lib/i18n/`):
- `mcp.capabilities.searchOnly` — EN `"search only"`, ZH `"仅搜索可见"`
- `mcp.capabilities.searchOnlyHint` — EN `"Not listed to agents; reachable via coffer__search_tools and still callable by name."`, ZH `"不出现在 agent 的工具列表中；可经 coffer__search_tools 发现，仍可按名调用。"`

- [ ] **Step 5: Run frontend and contract tests**

Run: `cd frontend && npx vitest run src/kinds/mcp/CapabilityList.test.tsx`
Expected: PASS

Run: `make verify-contract`
Expected: PASS. If it fails on the openapi↔model check, update the capabilities response schema under `specs/001-mcp-gateway/contracts/` to include `listed` and `hidden_count`.

- [ ] **Step 6: Update the spec prose**

In `specs/001-mcp-gateway/spec.md`, find the section describing `tools/list` aggregation and add:

```markdown
Listing is budgeted (see [ADR-046](../../docs/decisions/ADR-046-budget-driven-tool-tiering.md)).
Coffer's own `coffer__*` tools are always listed; upstream tools are listed in
full while they fit the budget (default 50), and beyond it the gateway lists the
most-used ones plus at least one per server. Unlisted tools are **not** disabled:
`tools/call` still routes them and `coffer__search_tools` still ranks the full
catalogue. `COFFER_TOOL_TIERING=off` restores unbudgeted listing.

The `initialize` response carries an MCP `instructions` string stating this
contract, so the connecting agent learns it without the user configuring
anything.
```

Mirror it in `specs/001-mcp-gateway/spec.zh.md`:

```markdown
列表是有预算的（见 [ADR-046](../../docs/decisions/ADR-046-budget-driven-tool-tiering.zh.md)）。
Coffer 自己的 `coffer__*` 工具恒定列出；上游工具在预算（默认 50）之内全部列出，
超出后网关列出使用最多的那些，并保证每台服务器至少一个。未列出的工具**并未被禁用**：
`tools/call` 照常路由，`coffer__search_tools` 照常检索完整目录。
`COFFER_TOOL_TIERING=off` 可恢复不设预算的列表行为。

`initialize` 应答携带一个 MCP `instructions` 字符串来陈述该契约，使接入的 agent
无需用户做任何配置即可获知它。
```

- [ ] **Step 7: Run the full verification**

Run: `make verify`
Expected: PASS — lint, unit, integration, contract, acceptance audit.

- [ ] **Step 8: Commit**

```bash
git add backend/coffer/surfaces/http/schemas.py backend/coffer/surfaces/http/mcp/capability_views.py specs/001-mcp-gateway/ frontend/src/kinds/mcp/CapabilityList.tsx frontend/src/kinds/mcp/CapabilityList.test.tsx frontend/src/lib/i18n/
git commit -m "feat(mcp-gateway): show which tools agents actually see

ADR-046 makes tools/list policy-dependent, so 'why can't the agent see
tool X' gains a layer. The capabilities page now marks unlisted tools
'search only' and the spec states the tiering contract.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage.** ADR-046 decision part 1 (tiering policy) → Tasks 2, 3, 4. Part 2 (hidden is not disabled) → Task 6 Step 4 keeps `search_tools` on the full catalogue; no task touches `tools/call` gating, which is the point. Part 3 (instructions) → Task 5. Part 4 (recoverable degradation + real logging) → Task 6. Escape hatch and fail-open → Task 3 and Task 4's `test_usage_query_failure_degrades_to_listing_everything`. Documented negative consequence "one more layer to check" → Task 8.

**Determinism claim.** ADR-046 says the slice is stable across sessions for an unchanged catalogue. Task 2's `_rank` sorts on `(-usage, catalogue_index)` with no other input, and `test_selection_is_deterministic_and_keeps_catalogue_order` covers it.

**Type consistency.** `TieringResult(listed, hidden_count)` is produced in Task 2 and consumed unchanged in Tasks 4 and 8. `AggregateOutcome(items, failed_servers)` is produced in Task 6 and consumed in the same task's `gateway.py` edits. `split_prefixed` is defined in Task 2 and reused in Task 7. `last_hidden_count` is set in Task 4 and read in Task 5.

**Ordering constraint.** Task 6 rewrites the same `_handle_tools_list` that Task 4 introduces, so Task 4 must land first. Task 7 imports from Task 2. Task 8 imports from Tasks 2 and 3. Tasks 1→2→3→4→6 are strictly ordered; Task 5 needs Task 4; Task 7 needs Task 2.
