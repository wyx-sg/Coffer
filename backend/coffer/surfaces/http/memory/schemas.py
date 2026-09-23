"""Wire models for ``/api/v1/memory/*``.

Mirrors ``surfaces/http/knowledge/schemas.py``: every model here describes what
a client is promised, kept deliberately separate from the domain values
(``domain.memory.note.Note``, ``domain.memory.retired.RetiredNote``,
``infrastructure.memory.files``) they mirror so trimming a domain field never
silently changes the wire contract.

That separation earned its keep in this redesign. ``Fact`` carried ``status``
and ``superseded_by``, and the wire carried them too; when retirement stopped
being a flag on a live record and became a file leaving ``notes/`` plus a line
in ``RETIRED.md`` ("Record retirements so they stick"), the two fields had to
go from both sides — and the
contract test comparing this module against
``openspec/specs/memory/contracts/api.openapi.yaml`` field name by field name is what
makes "both sides" checkable rather than remembered.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PartitionOut(BaseModel):
    """One partition, as the management surface lists it.

    Two repository fields rather than one ``project_root``, because a partition
    is keyed on a **repository** and a repository is two things: an identity two
    clones agree on (``repository_key``) and a place on this disk
    (``repository_path``). Both are empty for ``global``, which is no
    repository. The single working-directory root they replace is what split a
    worktree from its own checkout and turned six dated scratch folders into six
    permanent partitions ("Identify a partition by its repository", "Create no
    partition for a non-repository directory").
    """

    #: The partition Resource's immutable identity, and what every route under
    #: ``/partitions/{uid}/…`` takes. It is deliberately NOT the resolution
    #: key: a working directory resolves to a partition through
    #: ``repository_key``, which two clones of one repository derive
    #: identically on different machines. The uid answers "which row", the
    #: repository key answers "which partition is this directory in", and
    #: collapsing them would be one field answering two questions.
    uid: str
    #: A mutable label — ``global`` or a project slug — which is also the
    #: partition's directory name under the memory root, so a rename moves the
    #: directory with it. For display; anything that has to keep pointing at
    #: this partition holds ``uid``.
    name: str
    repository_key: str
    repository_path: str
    note_count: int
    #: True when ``repository_path`` is no longer a directory on this disk, so
    #: nothing can ever resolve to this partition again ("Report unresolvable
    #: partitions"). Surfaced
    #: rather than hidden: only the developer can decide it is not coming back.
    unresolvable: bool


class PartitionListOut(BaseModel):
    partitions: list[PartitionOut]


class OriginOut(BaseModel):
    """One raw entry a note was built from, and where it was read out of."""

    agent: str
    native_path: str
    anchor: str
    captured_at: str
    source_written_at: str


class NoteSummaryOut(BaseModel):
    """One note without its body — which is what an index line needs.

    There is no ``status`` and no ``superseded_by``. A retired note is not
    listed as dead: it has left ``notes/`` and is recorded in ``RETIRED.md``
    (``RetiredNoteOut`` below), so nothing on this shape has to be filtered by a
    client. The previous design left that filtering to the reader and 11 dead
    facts were served as current for weeks.
    """

    key: str
    slug: str
    partition: str
    title: str
    description: str
    #: ``user`` | ``feedback`` | ``project``. A plain ``str`` on purpose: the
    #: vocabulary lives in ``domain.memory.note``, and restating it as an enum
    #: here would be a second place to update.
    type: str
    #: What the source itself said to look this material up by, carried up from
    #: the entries that supplied it — Codex states them per task group, Claude
    #: Code states none ("Read Claude Code and Codex memory with their search
    #: terms").
    search_terms: list[str]
    created_at: str
    updated_at: str


class NoteListOut(BaseModel):
    notes: list[NoteSummaryOut]


class NoteOut(NoteSummaryOut):
    """One note, whole: Coffer's own text and the entries behind it.

    ``body`` is Coffer's writing, not a quote of any source ("Write notes in
    Coffer's own words") — the
    sources are named in ``origins`` and kept verbatim under the partition's
    ``.raw/``, which is what keeps a paraphrase traceable.
    """

    body: str
    origins: list[OriginOut]


class RetiredNoteOut(BaseModel):
    """One line of ``RETIRED.md``.

    ``entry_ids`` is deliberately not on the wire. It is the mechanism the next
    distil pass matches on, not something a reader of the record needs, and
    putting it here would invite a client to treat the retirement record as an
    index of raw entries rather than as the human-readable account it is.
    """

    #: The file name the note had under ``notes/``. Empty when the record
    #: accounts for entries a pass kept nothing from rather than for a note.
    slug: str
    title: str
    reason: str
    #: The slug of the note that replaced it, or empty when the subject was
    #: dropped rather than superseded.
    replaced_by: str
    retired_at: str


class RetiredListOut(BaseModel):
    retired: list[RetiredNoteOut]


class AggregationResultOut(BaseModel):
    """What one aggregation pass did.

    ``entries_written`` counts raw entries put under the partitions' ``.raw/``,
    and never notes: aggregation may not write one, and only aggregation may
    write ``.raw/`` ("Let only aggregation write raw entries"). A pass that
    found nothing new reports
    zero, which is the ordinary state of a machine whose agents have not
    written since the last pass.
    """

    partitions: list[str]
    entries_written: int
    sources_read: int
    sources_skipped: int
    #: Paths of native sources that would not parse ("Fail a broken reader
    #: loudly and in isolation") — left standing
    #: rather than deleted, so a later sync keeps retrying them.
    failures: list[str]


class DistilResultOut(BaseModel):
    """What one distil pass found, by the four actions of "Distil incrementally
    in two stages".

    ``dropped`` is a first-class outcome, not a failure: it is how a scratch
    directory's incidental material and an agent's transient observations stay
    out of the store. ``model_used`` is false when no internal connection is
    configured — each entry became a note of its own and the index was still
    written, from their frontmatter ("Distil mechanically with no internal
    connection").
    """

    partition: str
    merged: int
    opened: int
    retired: int
    dropped: int
    model_used: bool


class ComposedContextOut(BaseModel):
    """The session-start payload, and enough accounting to audit the ceiling.

    There is no ``layers`` field any more. Delivery is not a two-tier digest: it
    is the whole index of the current repository's partition plus what is known
    about the developer, so naming a layer would name a structure the payload no
    longer has ("Deliver the index and the notes path at session start").
    """

    text: str
    partition: str
    notes_included: int
    #: How many index lines the ceiling left out. The text names the count and
    #: the directory holding them, which is what makes a trim a small loss:
    #: every line that did not fit is still a file ("Bound delivery and prefer
    #: the current repository").
    notes_omitted: int


class FileNodeOut(BaseModel):
    """One entry in a partition's own directory ("Present partitions as a table
    and a file tree").

    Same shape as the skill kind's file tree so the two surfaces render through
    one component on the frontend. ``path`` is POSIX and relative to the
    partition directory (``""`` for the root); ``abs_path`` and
    ``folder_abs_path`` are what the viewer's open-in-editor and
    reveal-in-file-manager actions need, since a browser cannot resolve a path
    on the user's own disk but the loopback daemon can.
    """

    name: str
    path: str
    abs_path: str
    folder_abs_path: str
    type: str
    #: True for ``.raw/`` and everything under it: the verbatim entries
    #: aggregation read out of the agents. Flagged rather than hidden so the
    #: surface can show it as the distil pass's input rather than as Coffer's
    #: own writing ("Keep raw entries verbatim and hidden").
    derived: bool
    size: int | None = None
    #: True on a directory whose descendants were clipped at the walk bound.
    truncated: bool = False
    children: list[FileNodeOut] = Field(default_factory=list)


class FileTreeOut(BaseModel):
    root: FileNodeOut


class FileContentOut(BaseModel):
    """One file's content, read-only.

    No fingerprint, unlike the skill kind's equivalent: a fingerprint exists to
    make a later write conditional, and this family has no write. The tree under
    ``~/.coffer/memory/`` is derived ("Keep the memory tree derived and local") —
    an edit here would be overwritten
    by the next aggregation pass, so the surface does not offer one.
    """

    path: str
    abs_path: str
    folder_abs_path: str
    #: Empty when ``binary`` is true.
    content: str
    truncated: bool
    binary: bool
    size: int


class DeliveryStatusOut(BaseModel):
    """Installed or not, and nothing else.

    There is deliberately no last-fired field. A fire is an **event**, written
    to the audit log as ``memory_delivery_fired``; a hook installed a minute ago
    has legitimately never fired, so a status field flagging that would be
    crying wolf on its own normal state ("Audit every delivery fire", "Show
    delivery state on the agent's own page").
    """

    #: Which agent this row is about, and what the install and remove routes
    #: take — so a surface rendering this list acts on a row directly.
    agent_uid: str
    #: The same agent's label, for the row's heading. Beside the uid rather
    #: than instead of it, for the reason an audit row carries
    #: ``resource_name`` beside ``resource_id``: the list has to be both
    #: readable and actionable, and a client given only one of the two would
    #: have to fetch the agent list to recover the other.
    agent_name: str
    installed: bool
    command: str
    event: str


class DeliveryStatusListOut(BaseModel):
    delivery: list[DeliveryStatusOut]


class ContextQuery(BaseModel):
    """Body for composing a session-start context ("Deliver the index and the
    notes path at session start").

    A ``POST`` despite being a read, because the query is structured rather than
    a couple of scalar filters (knowledge's ``search`` is a ``POST`` for the same
    reason) — nothing here has a side effect on the memory tree itself.
    """

    cwd: str = Field(default="")
    #: The calling agent's uid — who fired, for ``record_fired`` below. It does
    #: not shape the payload: every enabled partition is composed for every
    #: agent.
    #:
    #: A uid rather than a name because of who sends it: the hook command
    #: Coffer wrote into that agent's settings file at install time and does
    #: not rewrite. A name baked into that command would attribute fires to
    #: nobody the first time the agent was relabelled, so there is one spelling
    #: here and it is the one that cannot change.
    agent_uid: str | None = None
    #: Omitted or null uses the server's default ceiling.
    ceiling_tokens: int | None = None
    #: Whether serving this payload counts as a real delivery ("Audit every
    #: delivery fire"). The
    #: installed hook always sets this; a management-surface preview must not,
    #: so it never records a fire that did not happen.
    record_fired: bool = False
