"""SessionStart rules-bundle assembly (Slice 6 FR-049/FR-050).

``assemble_session_context(cwd)`` resolves the recall scopes (project + global),
concatenates each store's rules (project first, then global), and ALWAYS appends
the two seeded built-in rules. Empty rules everywhere still yields the seeded
rules. The result is a single markdown string, bounded to <10k chars.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coffer.application.memory.rules_bundle import (
    SEEDED_RESUME_RULE,
    SEEDED_SOFTSTEER_RULE,
    RulesBundleAssembler,
)
from coffer.domain.memory.scope import MemoryScope, ResolvedScope

pytestmark = pytest.mark.asyncio

_PROJECT = ResolvedScope(scope=MemoryScope.PROJECT, project_id="P" * 26, store_dir=Path("/p"))
_GLOBAL = ResolvedScope(scope=MemoryScope.GLOBAL, project_id="global", store_dir=Path("/g"))


def _assembler(*, scopes, rules):
    async def resolve_recall_scopes(cwd):
        return scopes

    async def get_rules(store_name):
        return rules.get(store_name)

    return RulesBundleAssembler(
        resolve_recall_scopes=resolve_recall_scopes,
        get_rules=get_rules,
        store_name_for=lambda rs: "global" if rs.is_global else f"project-{rs.project_id}",
    )


async def test_seeded_rules_always_present_when_no_rules():
    a = _assembler(scopes=[_GLOBAL], rules={})
    out = await a.assemble_session_context(cwd=None)
    assert SEEDED_RESUME_RULE in out
    assert SEEDED_SOFTSTEER_RULE in out


async def test_global_only_rules_included():
    a = _assembler(scopes=[_GLOBAL], rules={"global": "Always run ruff."})
    out = await a.assemble_session_context(cwd=None)
    assert "Always run ruff." in out
    assert SEEDED_RESUME_RULE in out


async def test_project_first_then_global():
    a = _assembler(
        scopes=[_PROJECT, _GLOBAL],
        rules={f"project-{'P' * 26}": "PROJECT-RULE", "global": "GLOBAL-RULE"},
    )
    out = await a.assemble_session_context(cwd="/repo")
    assert out.index("PROJECT-RULE") < out.index("GLOBAL-RULE")
    assert out.index("GLOBAL-RULE") < out.index(SEEDED_RESUME_RULE)


async def test_empty_and_none_rules_skipped_cleanly():
    a = _assembler(
        scopes=[_PROJECT, _GLOBAL],
        rules={f"project-{'P' * 26}": "   ", "global": None},
    )
    out = await a.assemble_session_context(cwd="/repo")
    # No empty heading noise from the blank project rules, but seeded rules stay.
    assert SEEDED_RESUME_RULE in out
    assert SEEDED_SOFTSTEER_RULE in out


async def test_bundle_is_bounded_under_10k():
    a = _assembler(scopes=[_GLOBAL], rules={"global": "x" * 50_000})
    out = await a.assemble_session_context(cwd=None)
    assert len(out) <= 10_000
    # Seeded rules survive the truncation (appended-but-preserved contract).
    assert SEEDED_RESUME_RULE in out
    assert SEEDED_SOFTSTEER_RULE in out


async def test_scope_resolution_failure_degrades_to_seeded():
    """If scope resolution raises (e.g. not a git project), the bundle still
    returns the seeded rules — the hook must never block the agent."""

    async def boom(cwd):
        raise RuntimeError("no git root")

    async def get_rules(store_name):
        return None

    a = RulesBundleAssembler(
        resolve_recall_scopes=boom,
        get_rules=get_rules,
        store_name_for=lambda rs: "global",
    )
    out = await a.assemble_session_context(cwd="/not/a/repo")
    assert SEEDED_RESUME_RULE in out
