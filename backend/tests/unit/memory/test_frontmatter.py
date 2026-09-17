"""The fence every memory file goes through, and the two exactness rules that
are load-bearing rather than cosmetic (spec memory FR-008, FR-025).

``render_frontmatter``/``split_frontmatter`` are the only reader and writer of
the ``---``-fenced block under ``~/.coffer/memory/``, and two of their
properties decide whether the layer works at all:

* **A body comes back byte for byte**, whitespace and line endings included.
  A raw entry is an agent's own words carried verbatim, and "re-run the
  distillation without re-reading the agents" quietly stops meaning what it
  says the moment a round-trip rewrites one character.
* **The closing fence is recognised at column 0 only.** PyYAML writes a
  multi-line string as an *indented* continuation, so a retirement reason
  containing a horizontal rule puts ``    ---`` inside the block. A parser
  that stripped each line before comparing would end the frontmatter there,
  hand back an empty record, and — because ``RETIRED.md`` is the next pass's
  exclusion list — re-open every note retired for that reason, forever.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from coffer.infrastructure.memory.frontmatter import (
    atomic_write,
    read_text,
    render_frontmatter,
    split_frontmatter,
    text_list,
)


def test_a_body_survives_the_round_trip_byte_for_byte() -> None:
    body = "line one\r\nline two with trailing spaces   \r\n\r\n\t"
    fm, recovered = split_frontmatter(render_frontmatter({"title": "t"}, body))
    assert recovered == body
    assert fm == {"title": "t"}


def test_frontmatter_keys_keep_the_callers_order_not_the_alphabet() -> None:
    rendered = render_frontmatter({"title": "t", "description": "d", "created_at": "x"}, "body")
    block = rendered.split("---\n")[1]
    assert [line.split(":")[0] for line in block.strip().split("\n")] == [
        "title",
        "description",
        "created_at",
    ]


def test_a_value_containing_a_horizontal_rule_round_trips() -> None:
    """The indented-continuation trap, on the value that actually carries it.

    PyYAML writes this reason as an indented block, so the literal ``---``
    inside it is never at column 0 — which is exactly why the split compares
    the raw line rather than a stripped one.
    """
    reason = "The mechanism shipped.\n\n---\n\nThen it was removed; see the ADR.\n"
    rendered = render_frontmatter({"retired": [{"slug": "old", "reason": reason}]}, "prose below")

    # The trap itself: the rule inside the value is written indented, and the
    # only unindented fences in the file are the block's own two.
    assert [i for i, line in enumerate(rendered.split("\n")) if line == "---"] == [0, 12]
    assert "    ---" in rendered

    fm, body = split_frontmatter(rendered)
    assert fm["retired"][0]["reason"] == reason
    assert body == "prose below"


def test_an_indented_fence_does_not_end_the_frontmatter() -> None:
    text = "---\nreason: 'a\n\n    ---\n\n    b'\n---\nbody\n"
    fm, body = split_frontmatter(text)
    assert fm == {"reason": yaml.safe_load("'a\n\n    ---\n\n    b'")}
    assert body == "body\n"


def test_a_file_with_no_fence_is_all_body() -> None:
    assert split_frontmatter("no fence here\n") == ({}, "no fence here\n")


def test_an_unterminated_fence_degrades_to_all_body() -> None:
    """Nothing here is hand-authored and everything is rebuildable (FR-019),
    so one damaged file costs one thin entry, not the partition's listing."""
    text = "---\ntitle: t\nstill inside the block\n"
    assert split_frontmatter(text) == ({}, text)


def test_malformed_yaml_degrades_to_an_empty_mapping() -> None:
    fm, body = split_frontmatter("---\n: : not: yaml: at: all\n---\nbody\n")
    assert fm == {}
    assert body == "body\n"


def test_a_non_mapping_block_degrades_to_an_empty_mapping() -> None:
    fm, body = split_frontmatter("---\n- one\n- two\n---\nbody\n")
    assert fm == {}
    assert body == "body\n"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("worktree", ("worktree",)),
        (["worktree", "venv"], ("worktree", "venv")),
        ([1, 2], ("1", "2")),
        (None, ()),
        ({"a": 1}, ()),
    ],
)
def test_text_list_reads_a_scalar_or_a_sequence(value: object, expected: tuple[str, ...]) -> None:
    assert text_list(value) == expected


def test_atomic_write_creates_parents_and_leaves_no_temp_file(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "partition" / "notes" / "a.md"
    atomic_write(target, "content\n")
    assert target.read_text(encoding="utf-8") == "content\n"
    assert [p.name for p in target.parent.iterdir()] == ["a.md"]


def test_atomic_write_replaces_an_existing_file(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "a.md"
    atomic_write(target, "first")
    atomic_write(target, "second")
    assert target.read_bytes() == b"second"


def test_read_text_does_not_translate_line_endings(tmp_path: pathlib.Path) -> None:
    """``Path.read_text`` would fold ``\\r\\n`` to ``\\n`` and quietly break the
    verbatim rule one layer up."""
    target = tmp_path / "crlf.md"
    target.write_bytes(b"a\r\nb\r\n")
    assert read_text(target) == "a\r\nb\r\n"
