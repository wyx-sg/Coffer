"""The memory sync's pure parts: project keys, paths, absorption and the copy
state machine (spec memory)."""

from __future__ import annotations

import pytest

from coffer.domain.memory import absorption
from coffer.domain.memory.errors import UnsafeMemoryPath
from coffer.domain.memory.hub import (
    HubEntry,
    Origin,
    check_segment,
    entry_id,
    hub_project_key,
    project_folder,
)
from coffer.domain.memory.portable import from_portable, to_portable
from coffer.domain.memory.sync_plan import (
    ACTION_REMOVE,
    ACTION_UPDATE,
    ACTION_WRITE,
    STATE_EDITED,
    STATE_REMOVED,
    STATE_WRITTEN,
    CopyRecord,
    Target,
    digest_text,
    plan_copies,
)
from coffer.infrastructure.memory.hub_store import parse_entry, render_entry
from coffer.infrastructure.memory.readers import MEMORY_READERS
from coffer.infrastructure.memory.writers import MEMORY_WRITERS


def _entry(eid: str = "3f2a91c4de55b071", updated: str = "2026-10-09T06:00:00Z") -> HubEntry:
    return HubEntry(
        id=eid,
        origin=Origin(machine="m", agent="codex", source="MEMORY.md::g::h::0"),
        project="github.com/acme/payments",
        type="project",
        title="Retry is idempotent",
        description="Ledger retries are idempotent",
        body="See <repo>/ledger/retry.py",
        created_at="2026-10-09T06:00:00Z",
        updated_at=updated,
        search_terms=("retry",),
    )


def test_hub_project_key_prefers_the_remote() -> None:
    assert (
        hub_project_key(remote_url="git@github.com:acme/payments.git", root_name="pay")
        == "github.com/acme/payments"
    )
    assert hub_project_key(remote_url="", root_name="/Users/a/src/notes") == "notes"
    assert project_folder("github.com/acme/payments") == "github.com-acme-payments"


def test_entry_id_is_stable_and_machine_specific() -> None:
    a = entry_id("m1", "claude_code", "projects/x/memory/feedback")
    assert a == entry_id("m1", "claude_code", "projects/x/memory/feedback")
    assert a != entry_id("m2", "claude_code", "projects/x/memory/feedback")
    assert len(a) == 16


def test_a_hub_entry_round_trips() -> None:
    entry = _entry()
    assert parse_entry(render_entry(entry)) == entry


@pytest.mark.acceptance(spec="memory", scenario="a path follows the repository to another machine")
def test_paths_are_made_portable_and_expanded_on_boundaries() -> None:
    text = (
        "Edit /Users/a/src/payments/ledger/retry.py, not /Users/a/src/payments-old/x.py; "
        "config in /Users/a/.config/tool.toml."
    )
    portable = to_portable(text, repo_roots=["/Users/a/src/payments"], home="/Users/a")
    assert "<repo>/ledger/retry.py" in portable
    assert "~/src/payments-old/x.py" in portable
    assert "~/.config/tool.toml" in portable
    back = from_portable(portable, repo_root="/home/b/work/pay", home="/home/b")
    assert "/home/b/work/pay/ledger/retry.py" in back
    assert "/home/b/.config/tool.toml" in back


@pytest.mark.acceptance(
    spec="memory",
    scenario="refuse a path segment built from source contents that escapes",
)
@pytest.mark.parametrize("segment", ["..", ".", "", ".hidden", "a/b", "a\\b"])
def test_an_unsafe_segment_is_refused(segment: str) -> None:
    with pytest.raises(UnsafeMemoryPath):
        check_segment(segment)
    with pytest.raises(UnsafeMemoryPath):
        _ = _entry(eid=segment).path
    if "/" in segment or "\\" in segment:
        # A project key's separators become ``-``: it cannot climb out.
        assert "/" not in project_folder(segment) and "\\" not in project_folder(segment)
    else:
        with pytest.raises(UnsafeMemoryPath):
            project_folder(segment)


def test_only_delivered_sentences_count_as_absorbed() -> None:
    delivered = absorption.fingerprints("Run uv sync --frozen before every test run.")
    assert absorption.only_delivered(
        "Mine.", "Mine.\nRun uv sync --frozen before every test run.", delivered
    )
    assert not absorption.only_delivered(
        "Mine.", "Mine.\nRun uv sync --frozen before every test run.\nA new lesson here.", delivered
    )
    assert not absorption.only_delivered("Mine. Other.", "Mine.", delivered)


def _plan(targets: list[Target], records: dict[str, CopyRecord], disk: dict[str, str]):  # type: ignore[no-untyped-def]
    return plan_copies(
        "claude_code",
        targets,
        records,
        path_for=lambda t, taken: (
            f"/m/coffer_{t.entry.id}{'-2' if any(t.entry.id in p for p in taken) else ''}.md"
        ),
        render=lambda t: f"{t.entry.updated_at}:{t.body}",
        digest_of=lambda p: digest_text(disk[p]) if p in disk else None,
    )


def test_a_new_target_is_written_and_an_unchanged_copy_is_left() -> None:
    target = Target(_entry(), "/r", "body")
    plan = _plan([target], {}, {})
    assert [(op.action, op.path) for op in plan.ops] == [
        (ACTION_WRITE, f"/m/coffer_{target.entry.id}.md")
    ]

    path = plan.ops[0].path
    content = plan.ops[0].content
    rec = CopyRecord(path, target.entry.id, target.entry.updated_at, digest_text(content))
    assert _plan([target], {path: rec}, {path: content}).ops == []


def test_an_edited_copy_is_left_until_the_entry_changes_then_a_new_copy_goes_beside() -> None:
    target = Target(_entry(), "/r", "body")
    path = f"/m/coffer_{target.entry.id}.md"
    rec = CopyRecord(path, target.entry.id, target.entry.updated_at, digest_text("old"))
    plan = _plan([target], {path: rec}, {path: "the agent's edit"})
    assert plan.ops == [] and plan.records[path].state == STATE_EDITED

    newer = Target(_entry(updated="2026-10-10T00:00:00Z"), "/r", "body2")
    plan = _plan([newer], {path: plan.records[path]}, {path: "the agent's edit"})
    (op,) = plan.ops
    assert op.action == ACTION_WRITE and op.path != path


def test_a_removed_copy_stays_removed_until_the_entry_changes() -> None:
    target = Target(_entry(), "/r", "body")
    path = f"/m/coffer_{target.entry.id}.md"
    rec = CopyRecord(path, target.entry.id, target.entry.updated_at, digest_text("x"))
    plan = _plan([target], {path: rec}, {})
    assert plan.ops == [] and plan.records[path].state == STATE_REMOVED
    newer = Target(_entry(updated="2026-10-10T00:00:00Z"), "/r", "body2")
    (op,) = _plan([newer], {path: plan.records[path]}, {}).ops
    assert (op.action, op.path) == (ACTION_WRITE, path)


def test_a_copy_whose_entry_left_is_removed_only_when_unchanged() -> None:
    target = Target(_entry(), "/r", "body")
    content = f"{target.entry.updated_at}:body"
    path = "/m/coffer_x.md"
    rec = CopyRecord(
        path, target.entry.id, target.entry.updated_at, digest_text(content), STATE_WRITTEN
    )
    (op,) = _plan([], {path: rec}, {path: content}).ops
    assert op.action == ACTION_REMOVE
    assert _plan([], {path: rec}, {path: "edited"}).ops == []
    changed = Target(_entry(updated="2026-10-11T00:00:00Z"), "/r", "body")
    (op,) = _plan([changed], {path: rec}, {path: content}).ops
    assert op.action == ACTION_UPDATE


@pytest.mark.acceptance(spec="memory", scenario="register exactly the two readers and two writers")
def test_register_exactly_the_two_readers_and_two_writers() -> None:
    assert sorted(r.agent_type for r in MEMORY_READERS) == ["claude_code", "codex"]
    assert sorted(w.agent_type for w in MEMORY_WRITERS) == ["claude_code", "codex"]
