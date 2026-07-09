"""Unit tests for the instructions-block pure text transforms (ADR-042).

The INSTRUCTIONS_BLOCK injection mode: Coffer renders the session-context
payload into a marker-fenced block in the agent's instructions file. Install is
idempotent (replace in place), uninstall is a true inverse, and an unbalanced
marker is treated as "no Coffer block" rather than a guess at its extent.
"""

from __future__ import annotations

from coffer.domain.agent.instructions_block import (
    BLOCK_END,
    BLOCK_START,
    apply_block,
    has_block,
    remove_block,
)

USER_DOC = "# My agent notes\n\nAlways answer in French.\n"


def test_apply_to_empty_file_is_just_the_block() -> None:
    out = apply_block("", payload="RULES")
    assert out.startswith(BLOCK_START)
    assert out.rstrip("\n").endswith(BLOCK_END)
    assert "RULES" in out
    assert has_block(out)


def test_apply_appends_after_user_content_with_one_blank_line() -> None:
    out = apply_block(USER_DOC, payload="RULES")
    assert out.startswith(USER_DOC.rstrip("\n"))
    assert "\n\n" + BLOCK_START in out
    assert "Always answer in French." in out


def test_apply_replaces_existing_block_in_place() -> None:
    first = apply_block(USER_DOC, payload="OLD")
    # User appends their own section AFTER the block; a refresh must keep it.
    grown = first + "\n## Later notes\n"
    second = apply_block(grown, payload="NEW")
    assert "OLD" not in second
    assert "NEW" in second
    assert second.count(BLOCK_START) == 1
    assert "## Later notes" in second
    assert second.index(BLOCK_END) < second.index("## Later notes")


def test_apply_is_idempotent() -> None:
    once = apply_block(USER_DOC, payload="SAME")
    assert apply_block(once, payload="SAME") == once


def test_remove_is_true_inverse_of_apply() -> None:
    assert remove_block(apply_block(USER_DOC, payload="RULES")) == USER_DOC
    assert remove_block(apply_block("", payload="RULES")) == ""


def test_remove_preserves_user_content_on_both_sides() -> None:
    mid = apply_block("# Top\n", payload="RULES") + "\n# Bottom\n"
    out = remove_block(mid)
    assert out == "# Top\n\n# Bottom\n"


def test_remove_without_block_is_a_noop() -> None:
    assert remove_block(USER_DOC) == USER_DOC


def test_unbalanced_marker_is_not_ours() -> None:
    # A start fence whose end the user deleted: not a Coffer block. Install
    # appends a fresh balanced one; remove touches nothing; has_block is False.
    damaged = USER_DOC + "\n" + BLOCK_START + "\norphan\n"
    assert not has_block(damaged)
    assert remove_block(damaged) == damaged
    repaired = apply_block(damaged, payload="RULES")
    assert has_block(repaired)
    assert "orphan" in repaired


def test_payload_is_stripped_inside_the_block() -> None:
    out = apply_block("", payload="\n\nRULES\n\n")
    inner = out[out.index(BLOCK_START) : out.index(BLOCK_END)]
    assert "\n\n\n" not in inner
