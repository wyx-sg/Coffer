"""What a client SENDS to ``/api/v1/workflow/*``.

Split from ``schemas``, which holds what the daemon sends back. The two halves
change for opposite reasons — a request body changes when a command grows an
option, a response when the engine learns to say something new — and one file
holding both was the file that kept crossing the line ceiling.

Every model is named exactly as the contract names it, field for field, because
``make verify-contract`` compares the generated schema against that document in
both directions. ``schemas`` re-exports all of these, so no caller has to know
which half a model lives in.

Commands come in as the DOMAIN enum: validated at the boundary, and the enum IS
the contract's list, so there is nothing to keep in step.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from coffer.domain.workflow.run import NodeAction, RunInputKind, RunSignal


class RunInput(BaseModel):
    """One mounted input — a knowledge collection, a file or a link (spec
    workflow "List a run's mounted inputs to every node").

    ``size`` is bytes, and only an uploaded file has one: a collection's size is
    the collection's business and a link has none. It is on the same model in
    both directions because the contract has one ``RunInput`` — a client that
    sends one simply leaves it out, and the store answers with what it wrote.
    """

    kind: RunInputKind
    ref: str
    label: str | None = None
    size: int | None = None
    #: Where the run can reach it, relative to the run's working directory —
    #: set for a file and a repo, absent for a collection or a link.
    path: str | None = None
    #: What a ``link`` points at — ``confluence``, ``jira``, ``google_docs``
    #: … — or null when nothing is known beyond the address (spec workflow
    #: "Name what a mounted external reference points at"). DERIVED on every
    #: read rather than stored, so a link mounted before a provider was
    #: recognised is recognised now, with no migration. Never sent by a
    #: client: `RunInputIn` does not carry it.
    provider: str | None = None
    #: How a repo was given to the run: ``worktree`` (its own checkout on its
    #: own branch) or ``link`` (the source directory itself, which is what
    #: happens when the path is not a git repository). A node is TOLD which,
    #: because implying isolation it does not have is the one thing this must
    #: never do.
    mount: str | None = None


class RunInputIn(BaseModel):
    """What a client may say when mounting an input.

    Narrower than :class:`RunInput` on purpose: ``size``, ``path`` and ``mount``
    are what the server made of the request, not things a caller gets to assert
    about its own upload.

    The KIND is narrower too. A file and a note carry bytes and have routes of
    their own; naming one here would mount a row pointing at a file nobody
    wrote, which a node would meet as a broken run rather than a bad request.
    """

    kind: Literal["knowledge", "link", "repo"]
    ref: str
    label: str | None = None


class RunCreateIn(BaseModel):
    """A template and a title, and nothing else (spec workflow "Create a
    run from a template and a title alone").

    Two fields that were here are gone. ``workdir`` went because Coffer makes
    and owns a working directory per run ("Give each run a working directory of
    its own") — it is reported on ``RunOut`` and never asked for. ``inputs``
    went because they are mounted through ``/runs/{run_id}/inputs`` at any point
    in the run's life ("Add and remove inputs at any point in a run"), and a
    creation body that also accepted them would be a second way to do the same
    thing, available for one moment only.
    """

    #: The template resource's **uid**, not its name: the picker that fills
    #: this field has the uid already, and a run created from a label would be
    #: created from whatever that label pointed at when the request landed
    #: (ADR resource-identity-is-an-immutable-uid).
    template_uid: str
    title: str
    agent: str | None = None


class RunSignalIn(BaseModel):
    version: int
    signal: RunSignal
    reason: str | None = None


class NodeActionIn(BaseModel):
    version: int
    action: NodeAction
    #: Required for ``feedback``; the node service refuses an empty one, which
    #: is where that rule belongs — it is the same rule for the CLI.
    feedback: str | None = None
    waive_artifacts: bool = False


class AdhocTaskIn(BaseModel):
    version: int
    stage_key: str
    name: str
    instructions: str
    agent: str | None = None
    #: Overrides the run's working directory — how a task that touches a second
    #: repository is expressed.
    workdir: str | None = None


class RunNoteIn(BaseModel):
    """A note the developer wrote themselves (spec workflow "Keep the
    developer's own notes in a run's context")."""

    #: Becomes the note's filename and its label. An unusable one is refused by
    #: the path guard rather than repaired.
    title: str = Field(min_length=1)
    text: str = ""


class RunNoteEditIn(BaseModel):
    """A note's new contents. The ref it is written to is the path's."""

    text: str


class SayIn(BaseModel):
    """One sentence to one task (spec workflow "Let the developer speak
    to a task at any point, in one place").

    No ``version``: this is addressed to a named task and means the same
    wherever the run has got to, so it is outside the optimistic lock the way
    mounting an input is.
    """

    text: str


class PromotionIn(BaseModel):
    collection: str


class ApprovalDecisionIn(BaseModel):
    #: Narrowed to the two a person can make: ``expired`` and ``superseded``
    #: are outcomes the system reaches on its own, and a surface that accepted
    #: them could forge one.
    decision: Literal["approved", "rejected"]
    comment: str | None = None
    remember_tool_class: Literal["read", "write"] | None = None


class AssignmentIn(BaseModel):
    """Who runs a task's next attempt, on what, at what effort (spec
    workflow "Choose a task's agent, model and effort before it
    starts").

    All three are nullable and all three are written verbatim: null CLEARS the
    override and falls back to the template, which is a real choice rather than
    an omission. No ``version`` — this decides nothing about where the run is.
    """

    agent: str | None = None
    model: str | None = None
    effort: str | None = None


class RunLabelIn(BaseModel):
    """A run's title and description. No ``version``, and deliberately: this
    changes no state the optimistic lock guards (spec workflow "Edit a run's
    title and description as labels")."""

    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
