"""Unit tests for the Codex global-memory parser (spec 004 FR-040 revision).

Codex keeps a single global ``~/.codex/memories/MEMORY.md`` organised as
``# Task Group:`` blocks, each carrying one ``applies_to: cwd=...`` line that
routes the group to one or more project working directories. ``parse_codex_memory``
splits the doc into one :class:`CodexMemoryEntry` per Task Group, extracting the
group title, the routed cwd paths, and the verbatim block body.
"""

from __future__ import annotations

from coffer.domain.agent.codex_memory import CodexMemoryEntry, parse_codex_memory

_SAMPLE = """\
# Task Group: draw.io plus Confluence workflow

scope: practical diagram delivery
applies_to: cwd=/Users/x/Documents/codex-draw-io; reuse_rule=safe to reuse for /Users/x/other

## Task 1: explain how Codex generates draw.io, uncertain
### keywords
- draw.io, Confluence

# Task Group: account-gateway login debugging

scope: trace debugging
applies_to: cwd=/Users/x/WorkEnv/account-gateway; reuse_rule=safe

## Task 1: investigate AB-test path, success
## Task 2: debug missing channel, success

# Task Group: multi-repo work

scope: cross repo
applies_to: cwd=/Users/x/.codex/worktrees/*/account and /Users/x/WorkEnv/account; reuse_rule=x

## Task 1: do the thing, success

# Task Group: home-relative and prose

scope: messy
applies_to: cwd=/Users/x/Documents/skynet and ~/.agents/skills/skynet; reuse_rule=x

## Task 1: messy routing, partial
"""


def test_parses_one_entry_per_task_group() -> None:
    entries = parse_codex_memory(_SAMPLE)
    assert len(entries) == 4
    assert all(isinstance(e, CodexMemoryEntry) for e in entries)


def test_extracts_title_and_single_cwd() -> None:
    e = parse_codex_memory(_SAMPLE)[1]
    assert e.title == "account-gateway login debugging"
    assert e.cwds == ("/Users/x/WorkEnv/account-gateway",)
    # The body is the verbatim block, including its tasks.
    assert "## Task 2: debug missing channel" in e.body
    # reuse_rule text is not mistaken for a cwd.
    assert all("reuse_rule" not in c for c in e.cwds)


def test_splits_multi_path_cwd_on_and() -> None:
    e = parse_codex_memory(_SAMPLE)[2]
    assert e.cwds == (
        "/Users/x/.codex/worktrees/*/account",
        "/Users/x/WorkEnv/account",
    )


def test_extracts_home_relative_path_dropping_prose() -> None:
    e = parse_codex_memory(_SAMPLE)[3]
    assert e.cwds == ("/Users/x/Documents/skynet", "~/.agents/skills/skynet")


def test_first_group_body_stops_before_next_group() -> None:
    e = parse_codex_memory(_SAMPLE)[0]
    assert e.title == "draw.io plus Confluence workflow"
    assert e.cwds == ("/Users/x/Documents/codex-draw-io",)
    assert "account-gateway login debugging" not in e.body


def test_empty_or_groupless_text_yields_no_entries() -> None:
    assert parse_codex_memory("") == []
    assert parse_codex_memory("# User Profile\n\njust prose, no task groups\n") == []


def test_group_without_applies_to_has_no_cwds() -> None:
    text = "# Task Group: orphan\n\nscope: none\n\n## Task 1: x, success\n"
    e = parse_codex_memory(text)[0]
    assert e.title == "orphan"
    assert e.cwds == ()
