"""The agents guide's support table says what the daemon reports.

ADR what-coffer-does-for-an-agent-follows-from-its-facets: the table in
``docs-site/guides/agents.md`` (and its Chinese twin) is the one place a gap is
explained, so a ✓ must stand exactly where a type has the feature, and every
other cell must name one of the reason categories.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.agent.features import FEATURES, agent_features
from coffer.domain.agent.types import AgentType
from coffer.infrastructure.agent.native_session_sources import native_session_sources
from coffer.surfaces.http.agent_facet_wiring import build_agent_catalog

DOCS = pathlib.Path(__file__).resolve().parents[4] / "docs-site"

#: Guide → the words a gap may give as its reason.
GUIDES = {
    DOCS / "guides" / "agents.md": {"not offered", "terms", "not yet"},
    DOCS / "zh" / "guides" / "agents.md": {"产品不支持", "条款不允许", "尚未支持"},
}

#: Table columns after the type, in order: a feature name, or ``memory`` for
#: the session-start hook memory rides on.
COLUMNS = ("mcp", "skills", "provider", "chat", "sessions", "plugins", "hooks", "memory")


def _table(guide: pathlib.Path) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in guide.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == len(COLUMNS) + 1 and cells[0].startswith("`") and "✓" in line:
            rows[cells[0].strip("`")] = cells[1:]
    return rows


def _reported() -> dict[str, set[str]]:
    catalog = build_agent_catalog()
    sessions = native_session_sources(None).keys()  # type: ignore[arg-type]
    out = {}
    for t in AgentType:
        have = set(agent_features(catalog, t, session_types=sessions))
        if catalog.get(t).session_hook is not None:
            have.add("memory")
        out[t.value] = have
    return out


def test_columns_cover_every_feature() -> None:
    assert set(FEATURES) <= set(COLUMNS)


@pytest.mark.parametrize("guide", list(GUIDES), ids=lambda p: str(p.relative_to(DOCS)))
@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="the agents guide's support table matches what the daemon reports",
)
def test_support_table_matches_features(guide: pathlib.Path) -> None:
    table = _table(guide)
    reported = _reported()
    assert set(table) == set(reported), "one row per agent type"
    for agent, cells in table.items():
        for column, cell in zip(COLUMNS, cells, strict=True):
            where = f"{agent} / {column}"
            if column in reported[agent]:
                assert cell == "✓", f"{where}: Coffer does this, the table says {cell!r}"
            else:
                assert cell in GUIDES[guide], f"{where}: a gap needs a reason, got {cell!r}"
