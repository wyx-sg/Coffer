"""The topic format, the text a session is handed, and the hook in an agent's
settings (spec memory "Keep memory in one place in the vault", "Hand a session
its project's memories at start")."""

from __future__ import annotations

import json

import pytest

from coffer.application.memory.hook_target import apply_hook, hook_command, installed_commands
from coffer.domain.memory.context import render_context
from coffer.domain.memory.errors import UnsafeMemoryPath
from coffer.domain.memory.hub import (
    MAX_LINE,
    Topic,
    check_file_name,
    hub_project_key,
    project_folder,
    read_topic,
)
from coffer.infrastructure.memory.legacy import BLOCK_BEGIN, BLOCK_END, strip_block


def _topic(name: str, kind: str, updated: str, body: str, title: str = "") -> Topic:
    return read_topic(
        "acme", name, {"title": title or name[:-3], "type": kind, "updated": updated}, body
    )


@pytest.mark.acceptance(
    spec="memory", scenario="a file that breaks the format is shown and flagged"
)
def test_a_file_that_breaks_the_format_is_read_and_flagged() -> None:
    ok = read_topic(
        "acme",
        "testing.md",
        {"title": "Testing", "type": "feedback", "updated": "2026-11-19"},
        "\nRun the unit tier before pushing.\nNever mock the vault.\n",
    )
    assert ok.problems == ()
    assert ok.body == "Run the unit tier before pushing.\nNever mock the vault."
    assert ok.path == "projects/acme/testing.md"

    bad = read_topic("acme", "notes.md", {"type": "reference"}, "x" * (MAX_LINE + 1))
    # Still read, so nothing an agent wrote is lost; the title falls back to the name.
    assert bad.title == "notes"
    assert bad.type == ""
    assert set(bad.problems) == {
        "no title",
        "type is not user, feedback or project",
        "no updated date",
        f"a line longer than {MAX_LINE} characters",
    }
    assert read_topic("acme", "e.md", {"title": "E", "type": "user"}, "").problems == (
        "no updated date",
        "no memories",
    )


def test_a_project_is_keyed_by_its_remote_and_filed_under_a_safe_folder() -> None:
    key = hub_project_key(remote_url="git@github.com:acme/payments.git", root_name="pay")
    assert key == "github.com/acme/payments"
    assert project_folder(key) == "github.com-acme-payments"
    assert hub_project_key(remote_url="", root_name="/work/scratch") == "scratch"
    for unsafe in ("..", ".hidden.md", "a/b.md", "notes.txt"):
        with pytest.raises(UnsafeMemoryPath):
            check_file_name(unsafe)


@pytest.mark.acceptance(
    spec="memory", scenario="a session is handed its project's memories within the cap"
)
def test_a_session_is_handed_its_memories_in_order_within_the_cap() -> None:
    topics = [
        _topic("state.md", "project", "2026-11-18", "Payments v2 is behind a flag."),
        _topic("old.md", "feedback", "2026-01-01", "Answer in Chinese."),
        _topic("new.md", "feedback", "2026-11-19", "Squash-merge once CI is green."),
        _topic("me.md", "user", "2026-05-01", "Backend developer."),
    ]
    text = render_context(project="github.com/acme/pay", folder="~/m/acme", topics=topics)
    assert text.startswith('<coffer-memory project="github.com/acme/pay">\n')
    assert text.endswith("</coffer-memory>\n")
    assert "~/m/acme/" in text and '"Memory" section' in text
    # The person first, then how to work with them (newest first), then the project.
    order = [text.index(t) for t in ("Backend", "Squash", "Chinese", "Payments")]
    assert order == sorted(order)
    assert "## new (feedback, updated 2026-11-19)" in text

    # Over the cap, what does not fit is named by path and title instead.
    big = [*topics, _topic("huge.md", "project", "2026-01-02", "y" * 300 + "\n" + "z" * 300)]
    capped = render_context(project="p", folder="~/m/acme", topics=big, cap=900)
    assert len(capped.encode()) <= 900
    assert "Not shown here; read a file when it is relevant:" in capped
    assert "- ~/m/acme/huge.md: huge" in capped
    assert "y" * 300 not in capped


def test_a_project_with_no_memories_is_still_told_where_to_write() -> None:
    text = render_context(project="p", folder="~/m/p", topics=[])
    assert "~/m/p/" in text and "Not shown" not in text


@pytest.mark.acceptance(
    spec="memory", scenario="the hook is added beside the agent's own hooks and removed alone"
)
def test_the_hook_is_added_beside_other_hooks_and_removed_alone() -> None:
    theirs = {
        "theme": "dark",
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "echo hi"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "say done"}]}],
        },
    }
    command = hook_command("/Applications/Coffer App/coffer")
    assert command == "'/Applications/Coffer App/coffer' memory session-start"

    added = apply_hook(json.dumps(theirs), "SessionStart", command)
    assert installed_commands(added, "SessionStart") == [command]
    doc = json.loads(added)
    assert doc["theme"] == "dark" and doc["hooks"]["Stop"] == theirs["hooks"]["Stop"]
    assert {"type": "command", "command": "echo hi"} in [
        h for g in doc["hooks"]["SessionStart"] for h in g["hooks"]
    ]
    # Applying again changes nothing; a moved CLI replaces the one hook.
    assert apply_hook(added, "SessionStart", command) == added
    moved = apply_hook(added, "SessionStart", "/opt/coffer memory session-start")
    assert installed_commands(moved, "SessionStart") == ["/opt/coffer memory session-start"]

    removed = json.loads(apply_hook(moved, "SessionStart", None))
    assert removed == theirs
    assert installed_commands(apply_hook(None, "SessionStart", command), "SessionStart") == [
        command
    ]


def test_only_coffers_block_is_taken_out_of_an_index() -> None:
    text = f"# Mine\n- a fact\n\n{BLOCK_BEGIN}\n- copied\n{BLOCK_END}\n\nafter\n"
    assert strip_block(text) == "# Mine\n- a fact\n\nafter\n"
    assert strip_block(f"{BLOCK_BEGIN}\n- copied\n{BLOCK_END}\n") == ""
    assert strip_block("# Mine\n") is None
