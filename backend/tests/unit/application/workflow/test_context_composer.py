"""The shared opening context every node receives (FR-029, FR-031, FR-032)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from coffer.application.workflow.context_composer import (
    ContextComposer,
    NodeContextRequest,
    parse_inputs,
)
from coffer.application.workflow.transcripts import TaskTranscript, TranscriptMessage
from coffer.domain.workflow.run import (
    REPO_MOUNT_LINK,
    REPO_MOUNT_WORKTREE,
    RunInput,
    RunInputKind,
)
from coffer.domain.workflow.template import ArtifactSpec, Node, NodeType


@dataclass(frozen=True)
class FakeEntry:
    name: str
    node_key: str
    attempt: int
    path: str
    size: int
    modified_at: datetime


class FakeStore:
    def __init__(self, entries: Sequence[FakeEntry] = ()) -> None:
        self.entries = list(entries)
        self.written: list[str] = []

    def run_dir(self, run_id: str) -> str:
        return f"/vault/workflows/{run_id}"

    def workspace_dir(self, run_id: str) -> str:
        return f"/vault/workflows/{run_id}/workspace"

    def ensure_run_dirs(self, run_id: str) -> None: ...

    def list_artifacts(self, run_id: str) -> Sequence[FakeEntry]:
        return list(self.entries)

    def write_catalogue(self, run_id: str, markdown: str) -> None:
        self.written.append(markdown)

    def read_catalogue(self, run_id: str) -> str:
        return self.written[-1] if self.written else ""

    def collect_artifacts(self, run_id: str, destination: str) -> int:
        return 0

    def delete_run_dir(self, run_id: str) -> None: ...


class FakeSkills:
    def __init__(self, texts: dict[str, str] | None = None) -> None:
        self.texts = texts or {}
        self.asked: list[str] = []

    async def instructions(self, skill_name: str) -> str | None:
        self.asked.append(skill_name)
        return self.texts.get(skill_name)


class FakeTranscripts:
    def __init__(self, items: Sequence[TaskTranscript] = ()) -> None:
        self.items = list(items)
        self.asked: list[tuple[str, str]] = []

    async def transcripts(self, run_id: str, before_attempt_id: str) -> Sequence[TaskTranscript]:
        self.asked.append((run_id, before_attempt_id))
        return list(self.items)


class FakeSummariser:
    def __init__(self, text: str | None = "The design settled on the retry ceiling.") -> None:
        self.text = text
        self.asked: list[str] = []

    async def summarise(self, text: str, *, hint: str) -> str | None:
        self.asked.append(text)
        return self.text


class FakeKnowledge:
    def __init__(self, descriptions: dict[str, str] | None = None) -> None:
        self.descriptions = descriptions or {}

    async def describe(self, collection: str) -> str | None:
        return self.descriptions.get(collection)

    async def create_collection(self, name: str) -> str:
        return name


def make_composer(
    *,
    entries: Sequence[FakeEntry] = (),
    skills: dict[str, str] | None = None,
    collections: dict[str, str] | None = None,
    transcripts: Sequence[TaskTranscript] = (),
    summary: str | None = "The design settled on the retry ceiling.",
) -> tuple[ContextComposer, FakeStore, FakeSkills]:
    store = FakeStore(entries)
    skill_port = FakeSkills(skills)
    composer = ContextComposer(
        skills=skill_port,
        knowledge=FakeKnowledge(collections),
        artifacts=store,
        transcripts=FakeTranscripts(transcripts),
        summariser=FakeSummariser(summary),
    )
    return composer, store, skill_port


def make_request(node: Node | None = None, **overrides: object) -> NodeContextRequest:
    base: dict[str, object] = {
        "run_id": "run-1",
        "run_title": "Ship the retry fix",
        "workdir": "/repo",
        "attempt_id": "attempt-9",
        "node": node
        or Node(
            key="draft_td",
            name="Draft the technical design",
            type=NodeType.AI,
            skill="coffer-writing-td",
            instructions="Ground every identifier in this repository.",
            artifacts=(ArtifactSpec(name="td.md"), ArtifactSpec(name="notes.md", required=False)),
        ),
        "attempt": 1,
    }
    base.update(overrides)
    return NodeContextRequest(**base)  # type: ignore[arg-type]


def task(node_key: str, *texts: str, attempt: int = 1, name: str | None = None) -> TaskTranscript:
    return TaskTranscript(
        node_key=node_key,
        attempt=attempt,
        name=name,
        messages=tuple(TranscriptMessage(role="developer", text=text) for text in texts),
    )


@pytest.mark.acceptance(
    spec="workflow", scenario="a later task opens with what the earlier ones said"
)
async def test_the_four_parts_arrive_in_the_order_fr029_fixes() -> None:
    composer, _store, _skills = make_composer(skills={"coffer-writing-td": "Write it well."})

    text = await composer.compose(make_request())

    positions = [
        text.index("## 1. Your brief"),
        text.index("## 2. Skill"),
        text.index("## 3. What the earlier tasks said"),
        text.index("## 4. Artifacts and mounted inputs"),
    ]
    assert positions == sorted(positions)


async def test_the_brief_names_the_node_its_skill_and_where_to_write_each_artifact() -> None:
    composer, _store, _skills = make_composer(skills={"coffer-writing-td": "Write it well."})

    text = await composer.compose(make_request())

    assert "Draft the technical design" in text
    assert "`/vault/workflows/run-1/artifacts/draft_td/1/td.md`" in text
    assert "| `notes.md` | no |" in text
    assert "| `td.md` | yes |" in text


@pytest.mark.acceptance(
    spec="workflow", scenario="an ad-hoc task joins a stage and carries the same context"
)
async def test_an_adhoc_task_is_told_a_path_it_can_actually_write() -> None:
    node = Node(
        key="adhoc:hotfix",
        name="Patch the staging config",
        type=NodeType.AI,
        instructions="The developer wrote this one.",
        artifacts=(ArtifactSpec(name="patch.md"),),
    )
    composer, _store, _skills = make_composer()

    text = await composer.compose(make_request(node, attempt=2))

    # The colon is not a legal path segment; the run directory spells it %3A.
    assert "`/vault/workflows/run-1/artifacts/adhoc%3Ahotfix/2/patch.md`" in text
    assert "The developer wrote this one." in text


async def test_the_bound_skills_instructions_are_the_second_part() -> None:
    composer, _store, skills = make_composer(skills={"coffer-writing-td": "Cite the repository."})

    text = await composer.compose(make_request())

    assert skills.asked == ["coffer-writing-td"]
    assert "Cite the repository." in text


async def test_a_skill_deleted_since_the_template_was_written_does_not_stall_the_node() -> None:
    composer, _store, _skills = make_composer(skills={})

    text = await composer.compose(make_request())

    assert "no longer registered" in text
    assert "## 3. What the earlier tasks said" in text


@pytest.mark.acceptance(
    spec="workflow", scenario="a later task opens with what the earlier ones said"
)
async def test_the_earlier_tasks_transcripts_are_quoted_oldest_first() -> None:
    transcripts = (
        task("draft_td", "Target friday."),
        task("write_code", "Actually, drop the migration."),
    )
    composer, _store, _skills = make_composer(transcripts=transcripts)

    text = await composer.compose(make_request())

    assert text.index("Target friday.") < text.index("Actually, drop the migration.")
    assert "**developer**" in text
    assert "`draft_td` attempt 1" in text


async def test_the_transcripts_are_asked_for_by_the_attempt_now_opening() -> None:
    store = FakeStore()
    transcripts = FakeTranscripts()
    composer = ContextComposer(
        skills=FakeSkills(),
        knowledge=FakeKnowledge(),
        artifacts=store,
        transcripts=transcripts,
        summariser=FakeSummariser(),
    )

    await composer.compose(make_request(attempt_id="attempt-42"))

    assert transcripts.asked == [("run-1", "attempt-42")]


async def test_a_run_whose_first_task_is_opening_says_nothing_ran_before_it() -> None:
    composer, _store, _skills = make_composer()

    text = await composer.compose(make_request())

    assert "No task has run before yours." in text


async def test_the_message_says_the_run_has_no_conversation_of_its_own() -> None:
    composer, _store, _skills = make_composer()

    text = await composer.compose(make_request())

    assert "This run has no conversation of its own." in text


@pytest.mark.acceptance(
    spec="workflow", scenario="a later task opens with what the earlier ones said"
)
async def test_the_catalogue_is_regenerated_into_the_context_naming_node_and_attempt() -> None:
    entries = [
        FakeEntry(
            name="td.md",
            node_key="draft_td",
            attempt=1,
            path="draft_td/1/td.md",
            size=64,
            modified_at=datetime(2026, 9, 17, 8, 0, tzinfo=UTC),
        )
    ]
    composer, store, _skills = make_composer(entries=entries)

    text = await composer.compose(make_request())

    assert store.written, "composing must regenerate CATALOG.md from the directory"
    assert "`artifacts/draft_td/1/td.md`" in text
    assert "`draft_td`" in text


@pytest.mark.acceptance(
    spec="workflow", scenario="a later task opens with what the earlier ones said"
)
async def test_mounted_inputs_are_listed_and_never_inlined() -> None:
    inputs = (
        RunInput(kind=RunInputKind.KNOWLEDGE, ref="account-service"),
        RunInput(kind=RunInputKind.FILE, ref="prd.pdf", label="The PRD", size=2048),
        RunInput(kind=RunInputKind.LINK, ref="https://example.invalid/ticket/1"),
    )
    composer, _store, _skills = make_composer(
        collections={"account-service": "13 services, owners and links"}
    )

    text = await composer.compose(make_request(inputs=inputs))

    assert "- knowledge `account-service` — 13 services, owners and links" in text
    assert "- file `/vault/workflows/run-1/inputs/prd.pdf` (2048 bytes) — The PRD" in text
    assert "- link `https://example.invalid/ticket/1`" in text
    assert "coffer__search" in text


@pytest.mark.acceptance(
    spec="workflow", scenario="a note the developer wrote is part of the run's context"
)
async def test_a_note_is_listed_as_the_developers_own_words() -> None:
    """FR-069: an uploaded PRD is a document to work from; a note is the person
    who owns this run telling you something, and the two should not read the
    same to a node deciding what to believe."""
    inputs = (
        RunInput(kind=RunInputKind.NOTE, ref="what ops told me.md", label="what ops told me"),
    )
    composer, _store, _skills = make_composer()

    text = await composer.compose(make_request(inputs=inputs))

    assert (
        "- note `/vault/workflows/run-1/inputs/what ops told me.md` — what ops told me "
        "— written by the developer, in markdown" in text
    )


async def test_a_collection_deleted_since_it_was_mounted_is_still_listed() -> None:
    composer, _store, _skills = make_composer(collections={})
    inputs = (RunInput(kind=RunInputKind.KNOWLEDGE, ref="gone"),)

    text = await composer.compose(make_request(inputs=inputs))

    assert "- knowledge `gone` — not found in this vault" in text


async def test_the_message_says_the_context_is_shared_and_may_be_read_further() -> None:
    composer, _store, _skills = make_composer()

    text = await composer.compose(make_request())

    assert "every task of this run" in text
    assert "Nothing here is inlined" in text


async def test_two_tasks_of_one_run_get_the_same_three_run_level_parts() -> None:
    transcripts = (task("draft_td", "Keep it small."),)
    inputs = (RunInput(kind=RunInputKind.LINK, ref="https://example.invalid/x"),)
    composer, _store, _skills = make_composer(transcripts=transcripts)
    second_node = Node(key="review", name="Review it", type=NodeType.AI)

    first = await composer.compose(make_request(inputs=inputs))
    second = await composer.compose(make_request(second_node, inputs=inputs))

    def tail(text: str) -> str:
        return text[text.index("## 3. What the earlier tasks said") :]

    assert tail(first) == tail(second)


def test_run_inputs_are_parsed_from_the_runs_json_column_and_the_junk_skipped() -> None:
    parsed = parse_inputs(
        [
            {"kind": "knowledge", "ref": "account-service", "label": "the KB"},
            {"kind": "file", "ref": "prd.pdf", "size": 12},
            {"kind": "not-a-kind", "ref": "x"},
            {"kind": "link"},
        ]
    )

    assert parsed == (
        RunInput(kind=RunInputKind.KNOWLEDGE, ref="account-service", label="the KB"),
        RunInput(kind=RunInputKind.FILE, ref="prd.pdf", size=12),
    )


def test_a_boolean_size_is_not_a_size() -> None:
    # ``isinstance(True, int)`` is true in Python, and a JSON column written by
    # something other than this layer is exactly where that bites.
    parsed = parse_inputs([{"kind": "file", "ref": "prd.pdf", "size": True}])

    assert parsed[0].size is None


async def test_the_embedded_catalogue_does_not_open_a_second_h1() -> None:
    entries = [
        FakeEntry(
            name="td.md",
            node_key="draft_td",
            attempt=1,
            path="draft_td/1/td.md",
            size=64,
            modified_at=datetime(2026, 9, 17, 8, 0, tzinfo=UTC),
        )
    ]
    composer, _store, _skills = make_composer(entries=entries)

    text = await composer.compose(make_request())

    assert text.count("\n# ") == 0
    assert "Edits are overwritten" in text


@pytest.mark.acceptance(
    spec="workflow", scenario="earlier tasks are summarised when they exceed the budget"
)
async def test_the_oldest_transcripts_are_summarised_and_the_context_says_which() -> None:
    # 200k ASCII characters is ~50k tokens — over the transcripts' 33k share.
    huge = "x" * 200_000
    transcripts = (
        task("draft_td", huge, name="Draft the technical design"),
        task("write_code", "Kept verbatim."),
    )
    composer, _store, _skills = make_composer(transcripts=transcripts)

    text = await composer.compose(make_request())

    assert "summaries, not transcripts" in text
    assert "`draft_td` attempt 1 — Draft the technical design" in text
    assert "The design settled on the retry ceiling." in text
    assert "Kept verbatim." in text
    assert huge not in text


async def test_with_no_summariser_the_omitted_transcripts_are_named_not_dropped() -> None:
    # 200k ASCII characters is ~50k tokens — over the transcripts' 33k share.
    huge = "x" * 200_000
    transcripts = (
        task("draft_td", huge, name="Draft the technical design"),
        task("write_code", "Kept verbatim."),
    )
    composer, _store, _skills = make_composer(transcripts=transcripts, summary=None)

    text = await composer.compose(make_request())

    assert "no internal model connection is configured" in text
    assert "`draft_td` attempt 1 — Draft the technical design" in text
    assert huge not in text
    assert "Kept verbatim." in text


async def test_a_catalogue_larger_than_its_share_is_cut_and_points_at_the_file() -> None:
    entries = [
        FakeEntry(
            name=f"artifact-{index}.md",
            node_key=f"node_{index}",
            attempt=1,
            path=f"node_{index}/1/artifact-{index}.md",
            size=64,
            modified_at=datetime(2026, 9, 17, 8, 0, tzinfo=UTC),
        )
        for index in range(4000)
    ]
    composer, store, _skills = make_composer(entries=entries)

    text = await composer.compose(make_request())

    assert "older catalogue line(s) are omitted here" in text
    assert "`/vault/workflows/run-1/CATALOG.md`" in text
    # The file on disk still holds every row — only the embedded copy is cut.
    assert "artifact-0.md" in store.written[-1]


async def test_a_mounted_worktree_is_named_as_the_runs_own_checkout() -> None:
    inputs = (
        RunInput(
            kind=RunInputKind.REPO,
            ref="/Users/dev/work/account",
            label="the service",
            path="/vault/workflows/run-1/workspace/account",
            mount=REPO_MOUNT_WORKTREE,
        ),
    )
    composer, _store, _skills = make_composer()

    text = await composer.compose(make_request(inputs=inputs))

    assert "- repo `/vault/workflows/run-1/workspace/account` — the service" in text
    assert "your own git worktree of `/Users/dev/work/account`" in text
    assert "the developer's own checkout is untouched" in text.lower()


async def test_a_linked_directory_is_not_dressed_up_as_a_checkout() -> None:
    inputs = (
        RunInput(
            kind=RunInputKind.REPO,
            ref="/Users/dev/notes",
            path="/vault/workflows/run-1/workspace/notes",
            mount=REPO_MOUNT_LINK,
        ),
    )
    composer, _store, _skills = make_composer()

    text = await composer.compose(make_request(inputs=inputs))

    # FR-057: a node told it has isolation it does not have will write into
    # the developer's directory believing it is its own.
    assert "a LINK to `/Users/dev/notes`" in text
    assert "anything you write there, you write in the original" in text
