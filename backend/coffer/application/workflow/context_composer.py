"""The opening message every task of a run receives (FR-029).

Four parts, always in this order: the task's own brief with the exact path of
each deliverable it owes, its bound skill's instructions, an INDEX of the run's
earlier tasks and what they produced, and the run's mounted inputs.

One rule shapes all four: **name it, do not paste it.** Only the skill's
instructions are carried as content — they are what the task is being asked to
do, and they are bounded by the person who wrote them. Everything else is a
path, a collection or an address, with the message saying out loud that the
task may go and open it. A task not told it may read will answer from the
names alone.

That rule is why part 3 is an index rather than the earlier tasks'
conversations. Carrying those forward was tried: the opening message then grows
with every task that preceded it, and the fortieth task of a delivery cannot
start at all. So a task hands the next one its **deliverable**, not its
transcript (FR-072) — which also means a change of direction the developer
states inside a running task reaches the rest of the run by way of the file
that task writes (SC-004), and is worth stating while the task is still running
rather than after it has closed.

The whole message is bounded (FR-047), but the bound is a backstop: the index
costs a line per task, so a run would have to be hundreds of tasks long to
reach it. Every cut this module does make is stated in the message that carries
it — a task told nothing works from a hole it cannot see.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from coffer.application.workflow.catalogue import CATALOGUE_FILE, regenerate_catalogue
from coffer.application.workflow.context_budget import (
    BRIEF_SHARE,
    estimate_tokens,
    share_of,
)
from coffer.application.workflow.context_lines import (
    link_line,
    parse_inputs,
    repo_line,
)
from coffer.application.workflow.ports import (
    ArtifactStorePort,
    KnowledgeInputPort,
    SkillTextPort,
)
from coffer.application.workflow.task_index import (
    EarlierTask,
    EarlierTasksPort,
    render_index,
)
from coffer.domain.workflow.run import RunInput, RunInputKind
from coffer.domain.workflow.template import Node

__all__ = [
    "ContextComposer",
    "EarlierTask",
    "EarlierTasksPort",
    "NodeContextRequest",
    "parse_inputs",
]

#: How a node key is spelled as a directory name. Mirrors
#: ``infrastructure.workflow.paths.encode_node_key``, which this layer may not
#: import: only an ad-hoc key contains a colon, and a raw ``%`` never passes
#: that module's segment guard, so the escape is unambiguous on both sides. The
#: composer needs it because the message tells the agent the exact path to
#: write, and a path that is nearly right is a missing artifact (FR-023).
_COLON_ESCAPE = "%3A"

#: The directory an uploaded input lands in, relative to the run's own
#: directory. Mirrors ``infrastructure.workflow.paths.INPUTS_DIR_NAME`` for the
#: same reason as above: the node is told an absolute path it can open.
_INPUTS_DIR = "inputs"


@dataclass(frozen=True)
class NodeContextRequest:
    """Everything the composer needs for one attempt at one node.

    ``node`` is the template's own value object; an ad-hoc task arrives as one
    too, built from the developer's instructions (FR-028), so it is
    contextualised through exactly this path rather than a second one.

    ``attempt_id`` is what bounds the shared context: every task of this run
    that opened before this attempt is history, and this attempt's own
    conversation is where the reader already is.
    """

    run_id: str
    run_title: str
    workdir: str
    attempt_id: str
    node: Node
    attempt: int
    inputs: tuple[RunInput, ...] = field(default_factory=tuple)
    #: What the developer wrote for THIS attempt before it opened (FR-068) —
    #: the attempt row's own instructions. Separate from ``node.instructions``,
    #: which is the template's standing brief and is the same on every attempt.
    instructions: str | None = None


class ContextComposer:
    """Renders the shared opening message. Reads four ports, mutates nothing."""

    def __init__(
        self,
        *,
        skills: SkillTextPort,
        knowledge: KnowledgeInputPort,
        artifacts: ArtifactStorePort,
        earlier: EarlierTasksPort,
    ) -> None:
        self._skills = skills
        self._knowledge = knowledge
        self._artifacts = artifacts
        self._earlier = earlier

    async def compose(self, request: NodeContextRequest) -> str:
        """The whole message, in the four-part order FR-029 fixes."""
        sections = [
            self._preamble(request),
            self._brief(request),
            await self._skill(request),
            await self._earlier_tasks(request),
            await self._inputs(request),
        ]
        return "\n\n".join(section.rstrip() for section in sections) + "\n"

    # -- part 0: what this message is ---------------------------------------

    def _preamble(self, request: NodeContextRequest) -> str:
        return "\n".join(
            [
                f"# Workflow task: {request.node.name}",
                "",
                f'You are running one task of the Coffer workflow run "{request.run_title}".',
                "",
                "You will not be shown any other task's conversation, and no later task will be",
                "shown yours. What a task hands the rest of the run is the DELIVERABLE it writes",
                "— section 1 says which files you owe and exactly where to put them. Anything you",
                "work out that the tasks after you need, put in there; anything you leave only in",
                "this conversation stays here.",
                "",
                "Sections 3 and 4 are names, not contents: a path, a collection, a URL. Nothing is",
                "pasted, because any of them can be larger than this whole message. You have a",
                "filesystem and `coffer__search` / `coffer__read` — go and open what you need",
                "rather than answering from the names alone.",
            ]
        )

    # -- part 1: the node's own brief ---------------------------------------

    def _brief(self, request: NodeContextRequest) -> str:
        node = request.node
        lines = [
            "## 1. Your brief",
            "",
            f"- Task: `{node.key}` — {node.name}",
            f"- Type: `{node.type.value}`",
            f"- Attempt: {request.attempt}",
            f"- Working directory: `{request.workdir}`",
            f"- Skill: {f'`{node.skill}`' if node.skill else 'none bound'}",
        ]
        if node.instructions:
            lines.extend(["", node.instructions.strip()])
        added = (request.instructions or "").strip()
        # An ad-hoc task's brief IS its node instructions, so the two are the
        # same string there and printing it twice would read as emphasis.
        if added and added != (node.instructions or "").strip():
            lines.extend(["", "### What the developer added for this attempt", "", added])
        lines.extend(["", *self._deliverables(request)])
        return "\n".join(lines)

    def _deliverables(self, request: NodeContextRequest) -> list[str]:
        """The artifacts this task owes, each with the path to write it at.

        Never empty: a task whose workflow declared no deliverable is given a
        ``report.md`` (FR-072), because a deliverable is the only thing a task
        says to the tasks after it and one that owes nothing would leave its
        work behind when its conversation closes.

        The path is exact and absolute. A required artifact that is not at its
        path is not produced, and the task will not complete (FR-023) — so
        guessing at the location is the one mistake worth pre-empting here.
        """
        node = request.node
        attempt_dir = self._attempt_dir(request)
        lines = [
            "Deliverables — write each file at exactly this path. A required artifact that is",
            "not there when your turn ends blocks this task from completing. These files are",
            "what the rest of the run reads of your work, so write them for that reader.",
            "",
            "| Artifact | Required | Write to |",
            "| --- | --- | --- |",
        ]
        lines.extend(
            f"| `{spec.name}` | {'yes' if spec.required else 'no'} | `{attempt_dir}/{spec.name}` |"
            for spec in node.owed_artifacts
        )
        return lines

    def _run_dir(self, run_id: str) -> str:
        return self._artifacts.run_dir(run_id).rstrip("/")

    def _attempt_dir(self, request: NodeContextRequest) -> str:
        node_dir = request.node.key.replace(":", _COLON_ESCAPE)
        return f"{self._run_dir(request.run_id)}/artifacts/{node_dir}/{request.attempt}"

    # -- part 2: the bound skill --------------------------------------------

    async def _skill(self, request: NodeContextRequest) -> str:
        name = request.node.skill
        if not name:
            return "## 2. Skill\n\nNo skill is bound to this task."
        text = await self._skills.instructions(name)
        if text is None:
            # A template may name a skill that has since been deleted. The run
            # says so and carries on rather than stalling on a resource the
            # developer can re-add at any time.
            return (
                f"## 2. Skill: `{name}`\n\n"
                f"This task's skill is no longer registered in the vault, so its instructions "
                f"are unavailable. Proceed on the brief above and say so in your reply."
            )
        return f"## 2. Skill: `{name}`\n\n{_fit_skill(text.strip(), name)}"

    # -- part 3: what the run has done so far --------------------------------

    async def _earlier_tasks(self, request: NodeContextRequest) -> str:
        """Every task that ran before this attempt, and what it produced."""
        tasks = await self._earlier.earlier(request.run_id, request.attempt_id)
        run_dir = self._run_dir(request.run_id)
        # Written, not merely named. The index points at `CATALOG.md` for the
        # case where it is itself too long to render in full (FR-047), and a
        # path offered to an agent that resolves to nothing is worse than no
        # path at all. Regenerating is a directory read, and it keeps the file
        # honest on the same schedule the index is (FR-031).
        regenerate_catalogue(self._artifacts, request.run_id)
        lines = [
            "## 3. What this run has done so far",
            "",
            "Every task of this run that opened before yours, oldest first, with the files it",
            "produced. These files are the handover: open the ones that bear on your brief.",
            "You are not being shown their conversations — what a task decided is in what it",
            "wrote. If a deliverable does not answer a question you have, say so in your own",
            "rather than guessing at what was meant.",
            "",
            render_index(
                tasks,
                self._artifacts.list_artifacts(request.run_id),
                run_dir=run_dir,
                catalogue_path=f"{run_dir}/{CATALOGUE_FILE}",
            ),
        ]
        return "\n".join(lines)

    # -- part 4: what the developer mounted ----------------------------------

    async def _inputs(self, request: NodeContextRequest) -> str:
        lines = [
            "## 4. Mounted inputs",
            "",
            *await self._input_lines(request),
        ]
        return "\n".join(lines)

    async def _input_lines(self, request: NodeContextRequest) -> list[str]:
        inputs = request.inputs
        if not inputs:
            return ["Nothing is mounted on this run."]
        lines = [
            "These are the run's inputs. They are listed, never pasted — reach a",
            "collection with `coffer__search`, and open a file or a link yourself. An uploaded",
            f"file is on this machine under `{self._run_dir(request.run_id)}/{_INPUTS_DIR}/`.",
            "",
        ]
        for item in inputs:
            lines.append(await self._input_line(request, item))
        return lines

    async def _input_line(self, request: NodeContextRequest, item: RunInput) -> str:
        label = f" — {item.label}" if item.label else ""
        if item.kind is RunInputKind.REPO:
            return repo_line(item, label)
        if item.kind is RunInputKind.FILE:
            path = f"{self._run_dir(request.run_id)}/{_INPUTS_DIR}/{item.ref}"
            size = f" ({item.size} bytes)" if item.size is not None else ""
            return f"- file `{path}`{size}{label}"
        if item.kind is RunInputKind.NOTE:
            # Said to be the developer's own words, because that changes how it
            # should be read: an uploaded PRD is a document to work from, and a
            # note is the person who owns this run telling you something.
            path = f"{self._run_dir(request.run_id)}/{_INPUTS_DIR}/{item.ref}"
            return f"- note `{path}`{label} — written by the developer, in markdown"
        if item.kind is RunInputKind.LINK:
            return link_line(item, label)
        if item.kind is not RunInputKind.KNOWLEDGE:
            return f"- {item.kind.value} `{item.ref}`{label}"
        described = await self._knowledge.describe(item.ref)
        # A collection deleted since it was mounted is still worth listing: the
        # developer mounted it on purpose, and "it is gone" is the answer the
        # node needs rather than silence.
        detail = described or "not found in this vault"
        return f"- knowledge `{item.ref}`{label} — {detail}"


def _fit_skill(text: str, name: str) -> str:
    """The skill's instructions, capped at their share of the budget (FR-047).

    This is the one part of the message carried as CONTENT rather than as a
    name, so it is the one part that can overrun on its own — and a skill is a
    file the developer writes, with nothing stopping it being a hundred pages.
    Left uncapped the budget would be a number in a comment: every other part
    fits by construction, so the ceiling could only ever be breached here,
    which is precisely where nothing was checking.

    Cut from the END and said out loud, with the name of the whole. A skill
    opens with its purpose and its rules and closes with its examples, so
    keeping the head keeps the part the task cannot work without. A task told
    its skill was truncated can go and open the file; a task handed a silently
    short one follows rules it was never shown.
    """
    allowance = share_of(BRIEF_SHARE)
    if estimate_tokens(text) <= allowance:
        return text
    # On a line boundary rather than mid-sentence: a skill is markdown, and
    # half a heading reads as a corrupted document rather than a shortened one.
    kept: list[str] = []
    spent = 0
    for line in text.splitlines():
        spent += estimate_tokens(line)
        if spent > allowance and kept:
            break
        kept.append(line)
    return "\n".join(
        [
            *kept,
            "",
            f"_This skill's instructions are longer than a task's context budget allows, so "
            f"they are cut off here. Open `{name}` in the vault yourself before relying on "
            f"anything it says past this point._",
        ]
    )
