"""Tests for the curate hop: captured traces -> golden cases (ADR-019, slice 3).

The interactive shell is thin; the logic lives in pure functions (load, dedup,
parse a selection, build a case) plus a ``curate`` driver that takes an injected
labeler. These tests pin that logic without any terminal I/O.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals import _io
from evals._io import append_jsonl, load_jsonl
from evals.curate import (
    _interactive_labeler,
    build_case,
    curate,
    load_captures,
    parse_selection,
)


def _write(path: Path, rows: list[dict | str]) -> None:
    lines = [r if isinstance(r, str) else json.dumps(r) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- load_captures ---------------------------------------------------------


def test_load_captures_keeps_only_valid_tool_search(tmp_path: Path) -> None:
    cap = tmp_path / "cap.jsonl"
    _write(
        cap,
        [
            {
                "kind": "tool_search",
                "query": "make a ticket",
                "results": ["jira__create"],
            },
            {
                "kind": "retrieval",
                "query": "kafka offsets",
                "results": ["kafka"],
            },  # other kind
            {"kind": "tool_search", "query": "", "results": ["x__y"]},  # empty query
            {
                "kind": "tool_search",
                "query": "no results",
                "results": [],
            },  # empty results
            "not json at all",  # malformed line — skipped, not fatal
            "",  # blank line
        ],
    )
    rows = load_captures(cap)
    assert [r["query"] for r in rows] == ["make a ticket"]


def test_load_captures_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_captures(tmp_path / "nope.jsonl") == []


# --- parse_selection -------------------------------------------------------


def test_parse_selection_indices() -> None:
    results = ["a__one", "b__two", "c__three"]
    assert parse_selection("1,3", results) == ["a__one", "c__three"]


def test_parse_selection_all() -> None:
    results = ["a__one", "b__two"]
    assert parse_selection("all", results) == ["a__one", "b__two"]


def test_parse_selection_skip_and_none_and_blank() -> None:
    results = ["a__one"]
    assert parse_selection("skip", results) is None  # explicit skip
    assert parse_selection("none", results) == []  # seen but nothing relevant
    assert parse_selection("", results) == []


def test_parse_selection_ignores_out_of_range_and_dupes() -> None:
    results = ["a__one", "b__two"]
    assert parse_selection("2,2,9,0", results) == ["b__two"]


# --- build_case ------------------------------------------------------------


def test_interactive_labeler_treats_eof_as_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Piping an empty stdin (or Ctrl-D) must skip the record cleanly, not crash
    the session with an EOFError traceback."""

    def _raise_eof(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", _raise_eof)
    assert _interactive_labeler({"query": "q", "results": ["a__b"]}) is None


# --- build_case ------------------------------------------------------------


def test_build_case_shape() -> None:
    case = build_case("make a ticket", ["jira__create"])
    assert case == {
        "query": "make a ticket",
        "expected": ["jira__create"],
        "source": "captured",
    }


# --- curate (dedup + label) ------------------------------------------------


def test_curate_dedups_against_dataset_and_within_batch(tmp_path: Path) -> None:
    captures = [
        {"kind": "tool_search", "query": "make a ticket", "results": ["jira__create"]},
        {
            "kind": "tool_search",
            "query": "make a ticket",
            "results": ["jira__create"],
        },  # dupe
        {
            "kind": "tool_search",
            "query": "open a PR",
            "results": ["gh__pr", "gh__push"],
        },
    ]
    seen = {"make a ticket"}  # already in the dataset

    # Labeler picks the first result for whatever it is asked about.
    asked: list[str] = []

    def labeler(record: dict) -> list[str]:
        asked.append(record["query"])
        return [record["results"][0]]

    cases = curate(captures, seen, labeler)

    # "make a ticket" is in the dataset -> never presented; the in-batch dupe is
    # also collapsed. Only "open a PR" reaches the labeler.
    assert asked == ["open a PR"]
    assert cases == [
        {"query": "open a PR", "expected": ["gh__pr"], "source": "captured"}
    ]


def test_curate_skips_when_labeler_returns_none() -> None:
    captures = [{"kind": "tool_search", "query": "vague", "results": ["a__b"]}]
    assert curate(captures, set(), lambda _r: None) == []


def test_curate_skips_empty_label() -> None:
    captures = [
        {"kind": "tool_search", "query": "nothing relevant", "results": ["a__b"]}
    ]
    assert curate(captures, set(), lambda _r: []) == []


# --- append_jsonl + end-to-end ---------------------------------------------


def test_append_jsonl_round_trips_and_keeps_newline_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_io, "DATASETS", tmp_path)
    # Seed a file WITHOUT a trailing newline to prove append inserts one.
    (tmp_path / "ds.jsonl").write_text(
        '{"query": "seed", "expected": ["s__t"]}', encoding="utf-8"
    )

    append_jsonl(
        "ds.jsonl", [{"query": "new", "expected": ["n__w"], "source": "captured"}]
    )

    rows = load_jsonl("ds.jsonl")
    assert [r["query"] for r in rows] == ["seed", "new"]
    assert rows[1]["source"] == "captured"


def test_curate_then_append_grows_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_io, "DATASETS", tmp_path)
    (tmp_path / "tool_search.jsonl").write_text(
        '{"query": "make a ticket", "expected": ["jira__create"]}\n', encoding="utf-8"
    )
    captures = [
        {
            "kind": "tool_search",
            "query": "make a ticket",
            "results": ["jira__create"],
        },  # known
        {
            "kind": "tool_search",
            "query": "open a PR",
            "results": ["gh__pr", "gh__push"],
        },
    ]
    seen = {row["query"] for row in load_jsonl("tool_search.jsonl")}

    cases = curate(captures, seen, lambda rec: [rec["results"][0]])
    append_jsonl("tool_search.jsonl", cases)

    rows = load_jsonl("tool_search.jsonl")
    assert [r["query"] for r in rows] == ["make a ticket", "open a PR"]
    assert rows[1] == {
        "query": "open a PR",
        "expected": ["gh__pr"],
        "source": "captured",
    }
