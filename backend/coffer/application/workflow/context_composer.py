"""The opening message every node of a run receives (FR-029).

Four parts, always in this order: the node's own brief, its bound skill's
instructions, the transcripts of the run's EARLIER TASKS, and the artifact
catalogue with the list of mounted inputs.

The last three are **run-level**. They are the same question asked at each
node — what has this run said, made and been given — which is the whole point:
a change of direction stated once inside one task's conversation is read by
everything that runs afterwards without being restated (SC-004, FR-030). There
is no main thread to state it in, and there does not need to be one: the
developer says it where the thing being decided is in front of them, and it is
part of that task's transcript from then on.

Nothing bulky is inlined (FR-032). A knowledge collection can be larger than a
context window, an artifact can be a hundred pages, and a repository is right
there on disk. So the message *names* them — path, collection, catalogue row —
and says so out loud, because a node that is not told it may go and read will
answer from the summary it was given instead of from the thing itself.

The whole message is bounded (FR-047). ``context_budget`` holds the ceiling and
each part's share of it; what overruns is summarised, and what could not even
be summarised is named. Every cut this module makes is stated in the message
that carries it — a node told nothing answers from a hole it cannot see.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from coffer.application.workflow.catalogue import CATALOGUE_TITLE, regenerate_catalogue
from coffer.application.workflow.context_budget import (
    TranscriptFitter,
)
from coffer.application.workflow.context_lines import (
    fit_catalogue,
    link_line,
    parse_inputs,
    repo_line,
)
from coffer.application.workflow.ports import (
    ArtifactStorePort,
    KnowledgeInputPort,
    SkillTextPort,
    SummariserPort,
)
from coffer.application.workflow.transcripts import (
    TaskTranscript,
    TaskTranscriptsPort,
    TranscriptMessage,
)
from coffer.domain.workflow.run import RunInput, RunInputKind
from coffer.domain.workflow.template import Node

__all__ = [
    "ContextComposer",
    "NodeContextRequest",
    "TaskTranscript",
    "TaskTranscriptsPort",
    "TranscriptMessage",
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
        transcripts: TaskTranscriptsPort,
        summariser: SummariserPort,
    ) -> None:
        self._skills = skills
        self._knowledge = knowledge
        self._artifacts = artifacts
        self._transcripts = transcripts
        self._fitter = TranscriptFitter(summariser=summariser)

    async def compose(self, request: NodeContextRequest) -> str:
        """The whole message, in the four-part order FR-029 fixes."""
        sections = [
            self._preamble(request),
            self._brief(request),
            await self._skill(request),
            await self._earlier_tasks(request),
            await self._artifacts_and_inputs(request),
        ]
        return "\n\n".join(section.rstrip() for section in sections) + "\n"

    # -- part 0: what this message is ---------------------------------------

    def _preamble(self, request: NodeContextRequest) -> str:
        return "\n".join(
            [
                f"# Workflow node: {request.node.name}",
                "",
                f'You are running one task of the Coffer workflow run "{request.run_title}".',
                "Sections 2 to 4 below are the run's shared context — every task of this run,",
                "planned or ad-hoc, opens with the same three, so what you read there is what",
                "the task before you read plus whatever it said and left behind.",
                "",
                "This run has no conversation of its own. Anything the developer wants the rest",
                "of the run to know, they say inside a task's conversation — including this one.",
                "",
                "Nothing here is inlined. Knowledge collections, artifacts and the repository are",
                "named, not pasted, because any of them can be larger than this message. You have",
                "a filesystem and `coffer__search` / `coffer__read` — go and open what you need",
                "rather than answering from the names alone.",
            ]
        )

    # -- part 1: the node's own brief ---------------------------------------

    def _brief(self, request: NodeContextRequest) -> str:
        node = request.node
        lines = [
            "## 1. Your brief",
            "",
            f"- Node: `{node.key}` — {node.name}",
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
        """The artifacts this node owes, each with the path to write it at.

        The path is exact and absolute. A required artifact that is not at its
        path is not produced, and the node will not complete (FR-023) — so
        guessing at the location is the one mistake worth pre-empting here.
        """
        node = request.node
        if not node.artifacts:
            return [
                "This node owes no artifact. Report what you did in your reply; "
                "that reply is what the developer reviews."
            ]
        attempt_dir = self._attempt_dir(request)
        lines = [
            "Deliverables — write each file at exactly this path. A required artifact that is",
            "not there when your turn ends blocks this node from completing.",
            "",
            "| Artifact | Required | Write to |",
            "| --- | --- | --- |",
        ]
        lines.extend(
            f"| `{spec.name}` | {'yes' if spec.required else 'no'} | `{attempt_dir}/{spec.name}` |"
            for spec in node.artifacts
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
            return "## 2. Skill\n\nNo skill is bound to this node."
        text = await self._skills.instructions(name)
        if text is None:
            # A template may name a skill that has since been deleted. The run
            # says so and carries on rather than stalling on a resource the
            # developer can re-add at any time.
            return (
                f"## 2. Skill: `{name}`\n\n"
                f"This node's skill is no longer registered in the vault, so its instructions "
                f"are unavailable. Proceed on the brief above and say so in your reply."
            )
        return f"## 2. Skill: `{name}`\n\n{text.strip()}"

    # -- part 3: what the earlier tasks said --------------------------------

    async def _earlier_tasks(self, request: NodeContextRequest) -> str:
        """Every task that ran before this attempt, cut to fit (FR-048)."""
        transcripts = await self._transcripts.transcripts(request.run_id, request.attempt_id)
        lines = [
            "## 3. What the earlier tasks said",
            "",
            "The conversations of every task of this run that opened before yours, oldest",
            "first. The developer steers this run by talking inside a task's conversation, so",
            "a correction they made in one of these is a correction to your brief above — read",
            "the newest of them as the current intent where they disagree.",
            "",
        ]
        if not transcripts:
            lines.append("No task has run before yours.")
            return "\n".join(lines)
        fitted = await self._fitter.fit(transcripts)
        notice = fitted.notice
        if notice:
            lines.extend([notice, ""])
        lines.append("\n\n".join(fitted.blocks))
        return "\n".join(lines)

    # -- part 4: artifacts and mounted inputs -------------------------------

    async def _artifacts_and_inputs(self, request: NodeContextRequest) -> str:
        catalogue = regenerate_catalogue(self._artifacts, request.run_id)
        # The file has its own H1; here it sits under an H3, and a second H1
        # mid-message reads as a new document rather than as a section.
        body = catalogue.removeprefix(CATALOGUE_TITLE).strip()
        lines = [
            "## 4. Artifacts and mounted inputs",
            "",
            "### Artifacts produced so far",
            "",
            "Every file below was written by a node of this run and is named with the node and",
            "attempt that produced it. Open the ones you need; they are on disk, not here.",
            "",
            fit_catalogue(body, f"{self._run_dir(request.run_id)}/CATALOG.md"),
            "",
            "### Mounted inputs",
            "",
        ]
        lines.extend(await self._input_lines(request))
        return "\n".join(lines)

    async def _input_lines(self, request: NodeContextRequest) -> list[str]:
        inputs = request.inputs
        if not inputs:
            return ["Nothing is mounted on this run."]
        lines = [
            "These are the run's inputs (FR-032). They are listed, never pasted — reach a",
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
