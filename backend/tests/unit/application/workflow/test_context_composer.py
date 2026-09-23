"""The opening context every task receives (spec workflow "Open every task with
the same four parts")."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from coffer.application.workflow.context_budget import (
    NODE_CONTEXT_TOKEN_BUDGET,
    estimate_tokens,
)
from coffer.application.workflow.context_composer import (
    ContextComposer,
    NodeContextRequest,
    parse_inputs,
)
from coffer.application.workflow.task_index import EarlierTask
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

    def collect_run_files(
        self, run_id: str, destination: str, *, references: str | None = None
    ) -> int:
        return 0

    def delete_run_dir(self, run_id: str) -> None: ...


class FakeSkills:
    def __init__(self, texts: dict[str, str] | None = None) -> None:
        self.texts = texts or {}
        self.asked: list[str] = []

    async def instructions(self, skill_name: str) -> str | None:
        self.asked.append(skill_name)
        return self.texts.get(skill_name)


class FakeEarlierTasks:
    def __init__(self, items: Sequence[EarlierTask] = ()) -> None:
        self.items = list(items)
        self.asked: list[tuple[str, str]] = []

    async def earlier(self, run_id: str, before_attempt_id: str) -> Sequence[EarlierTask]:
        self.asked.append((run_id, before_attempt_id))
        return list(self.items)


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
    earlier: Sequence[EarlierTask] = (),
) -> tuple[ContextComposer, FakeStore, FakeSkills]:
    store = FakeStore(entries)
    skill_port = FakeSkills(skills)
    composer = ContextComposer(
        skills=skill_port,
        knowledge=FakeKnowledge(collections),
        artifacts=store,
        earlier=FakeEarlierTasks(earlier),
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


def task(
    node_key: str,
    *,
    attempt: int = 1,
    name: str = "An earlier task",
    status: str = "completed",
) -> EarlierTask:
    return EarlierTask(node_key=node_key, name=name, attempt=attempt, status=status)


@pytest.mark.acceptance(
    spec="workflow", scenario="a later task opens with an index of what the run produced"
)
async def test_the_four_parts_arrive_in_the_order_fr029_fixes() -> None:
    composer, _store, _skills = make_composer(skills={"coffer-writing-td": "Write it well."})

    text = await composer.compose(make_request())

    positions = [
        text.index("## 1. Your brief"),
        text.index("## 2. Skill"),
        text.index("## 3. What this run has done so far"),
        text.index("## 4. Mounted inputs"),
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
    assert "## 3. What this run has done so far" in text


@pytest.mark.acceptance(
    spec="workflow", scenario="a later task opens with an index of what the run produced"
)
async def test_the_earlier_tasks_are_indexed_oldest_first_by_what_they_produced() -> None:
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
    earlier = (
        task("draft_td", name="Draft the technical design"),
        task("write_code", name="Write the code"),
    )
    composer, _store, _skills = make_composer(entries=entries, earlier=earlier)

    text = await composer.compose(make_request())

    assert text.index("`draft_td`") < text.index("`write_code`")
    assert "`/vault/workflows/run-1/artifacts/draft_td/1/td.md`" in text


async def test_no_earlier_conversation_reaches_the_opening_message() -> None:
    """The change this module exists for, asserted as an absence.

    A task hands the next one its deliverable, not its transcript. The
    composer has no port that could reach a conversation any more, so what this
    pins is that nobody reintroduces one by putting a summary or an output on
    the index row — which is how the unbounded growth came back last time.
    """
    composer, _store, _skills = make_composer(
        earlier=(task("draft_td", name="Draft the technical design"),)
    )

    text = await composer.compose(make_request())

    assert "**developer**" not in text
    assert "You will not be shown any other task's conversation" in text


async def test_the_index_is_asked_for_by_the_attempt_now_opening() -> None:
    store = FakeStore()
    earlier = FakeEarlierTasks()
    composer = ContextComposer(
        skills=FakeSkills(),
        knowledge=FakeKnowledge(),
        artifacts=store,
        earlier=earlier,
    )

    await composer.compose(make_request(attempt_id="attempt-42"))

    assert earlier.asked == [("run-1", "attempt-42")]


async def test_a_run_whose_first_task_is_opening_says_nothing_ran_before_it() -> None:
    composer, _store, _skills = make_composer()

    text = await composer.compose(make_request())

    assert "No task of this run has run before yours." in text


async def test_the_message_says_what_carries_work_to_the_rest_of_the_run() -> None:
    """The handover rule, stated to the agent rather than assumed of it.

    A task that does not know its conversation is private will answer in the
    conversation and write nothing, and the run afterwards has a task that
    reported success and produced no deliverable to show for it.
    """
    composer, _store, _skills = make_composer()

    text = await composer.compose(make_request())

    assert "What a task hands the rest of the run is the DELIVERABLE it writes" in text


@pytest.mark.acceptance(
    spec="workflow", scenario="a later task opens with an index of what the run produced"
)
async def test_composing_regenerates_the_catalogue_the_index_points_at() -> None:
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
    composer, store, _skills = make_composer(
        entries=entries, earlier=(task("draft_td", name="Draft the technical design"),)
    )

    text = await composer.compose(make_request())

    # The index names `CATALOG.md` as where the whole of it can be read when it
    # is itself too long (spec workflow
    # "Keep a task's opening context within budget"), so the file has to exist
    # by then — a path offered to an agent that resolves to nothing is worse
    # than no path.
    assert store.written, "composing must regenerate CATALOG.md from the directory"
    assert "`/vault/workflows/run-1/artifacts/draft_td/1/td.md`" in text


@pytest.mark.acceptance(
    spec="workflow", scenario="a later task opens with an index of what the run produced"
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
    """An uploaded PRD is a document to work from; a note is the person
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


async def test_the_message_says_it_holds_names_and_invites_the_task_to_open_them() -> None:
    composer, _store, _skills = make_composer()

    text = await composer.compose(make_request())

    assert "Sections 3 and 4 are names, not contents" in text
    assert "go and open what you need" in text


async def test_two_tasks_of_one_run_get_the_same_run_level_parts() -> None:
    earlier = (task("draft_td", name="Draft the technical design"),)
    inputs = (RunInput(kind=RunInputKind.LINK, ref="https://example.invalid/x"),)
    composer, _store, _skills = make_composer(earlier=earlier)
    second_node = Node(key="review", name="Review it", type=NodeType.AI)

    first = await composer.compose(make_request(inputs=inputs))
    second = await composer.compose(make_request(second_node, inputs=inputs))

    def tail(text: str) -> str:
        return text[text.index("## 3. What this run has done so far") :]

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

    # A node told it has isolation it does not have will write into
    # the developer's directory believing it is its own.
    assert "a LINK to `/Users/dev/notes`" in text
    assert "anything you write there, you write in the original" in text


@pytest.mark.acceptance(
    spec="workflow", scenario="a task the developer gave no deliverable still owes one"
)
async def test_a_task_that_declared_no_artifacts_is_still_told_what_to_write() -> None:
    """Spec workflow "Give every task at least one deliverable", at the one place
    it has to be visible: the brief.

    The default is applied on READ, so the task's own declaration stays empty
    and round-trips through the editor unchanged — but the brief it opens with
    has to name a path anyway, or the task has nothing to hand the rest of the
    run and no way to know it was supposed to.
    """
    node = Node(key="verify", name="Run the checks", type=NodeType.AI)
    composer, _store, _skills = make_composer()

    text = await composer.compose(make_request(node))

    assert node.artifacts == ()
    assert "| `report.md` | yes | `/vault/workflows/run-1/artifacts/verify/1/report.md` |" in text
    # And said as an obligation, not as an option.
    assert "blocks this task from completing" in text


async def test_an_enormous_skill_is_cut_and_says_where_the_rest_is() -> None:
    """Spec workflow "Keep a task's opening context within budget", at the only
    place the budget can actually be breached.

    Every other part of the opening message is names — a path, a task key, a
    URL — and fits by construction. The skill's instructions are the one part
    carried as content, so they are the one part that can overrun, and for a
    while the share that was supposed to bound them was declared and never
    applied. What this catches is that regression returning: a budget nothing
    enforces is a number in a comment.
    """
    huge = "\n".join(["# Rules", "Follow them.", *(f"Example {i}." for i in range(60_000))])
    composer, _store, _skills = make_composer(skills={"coffer-writing-td": huge})

    text = await composer.compose(make_request())

    assert estimate_tokens(text) <= NODE_CONTEXT_TOKEN_BUDGET
    # Cut from the end, so the purpose and the rules survive and the examples go.
    assert "# Rules" in text
    assert "Example 59999." not in text
    # And never silently: the task is told, and told what to open.
    assert "cut off here" in text
    assert "coffer-writing-td" in text


async def test_a_skill_that_fits_is_carried_whole() -> None:
    composer, _store, _skills = make_composer(skills={"coffer-writing-td": "Ground identifiers."})

    text = await composer.compose(make_request())

    assert "Ground identifiers." in text
    assert "cut off here" not in text
