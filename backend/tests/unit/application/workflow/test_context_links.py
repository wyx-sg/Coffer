"""A mounted link names its provider in the node's context (FR-065)."""

from __future__ import annotations

import pytest

from coffer.application.workflow.context_composer import _link_line
from coffer.domain.workflow.run import RunInput, RunInputKind


def _link(ref: str) -> RunInput:
    return RunInput(kind=RunInputKind.LINK, ref=ref)


@pytest.mark.acceptance(
    spec="workflow", scenario="a mounted link tells the task which tool opens it"
)
def test_a_recognised_link_says_what_it_is_and_an_ordinary_one_does_not() -> None:
    confluence = _link_line(_link("https://mycorp.atlassian.net/wiki/spaces/ENG/pages/1/TD"), "")
    ordinary = _link_line(_link("https://example.com/notes"), "")

    # The point of the line: the task knows which tool opens it.
    assert "confluence" in confluence
    assert "read it with that tool" in confluence
    # …and is told nothing it would have to un-learn about the other one.
    assert ordinary == "- link `https://example.com/notes`"
    assert "tool" not in ordinary


def test_a_label_the_developer_gave_survives_either_way() -> None:
    assert "— the PRD" in _link_line(_link("https://example.com/prd"), " — the PRD")
    assert "— the PRD" in _link_line(_link("https://jira.internal/browse/COF-1"), " — the PRD")
