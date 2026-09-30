"""Who wrote a vault commit, and how a commit says so
(ADR every-vault-write-is-a-validated-commit-naming-its-writer).

Every accepted write to the vault is one commit whose author names the writer
and whose trailers carry the rest: the operation, the audit actor, the agent,
the machine, and — for a restore — the commit restored from. The knowledge
history wrote the same trailers before the vault was one repository, so its
commits read back through this module unchanged.

A commit Coffer did not write (a person's own ``git commit`` in the vault)
carries no trailers and reads as a ``disk`` write.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace

#: A person, through a Coffer surface — the web UI, the CLI, the API.
WRITER_USER = "user"
#: A change found in the working tree that no Coffer operation made: a
#: person's editor, a shell, an agent's own file tools, a hand ``git commit``.
WRITER_DISK = "disk"
#: An agent through a Coffer tool; ``agent`` names which (``Coffer-Agent``).
WRITER_AGENT = "agent"
#: The daemon on its own account: a uid minted for a hand-made file, a
#: machine descriptor, a layout upgrade, the migration.
WRITER_DAEMON = "daemon"
#: Coffer's curation pass over a knowledge collection.
WRITER_CURATION = "curation"
#: A sync round's merge: another machine's changes, applied here.
WRITER_SYNC = "sync"

WRITERS = (
    WRITER_USER,
    WRITER_DISK,
    WRITER_AGENT,
    WRITER_DAEMON,
    WRITER_CURATION,
    WRITER_SYNC,
)

#: The operations the vault core itself names; kinds add their own words.
OP_EDIT = "edit"
OP_BASELINE = "baseline"
OP_RESTORE = "restore"
OP_LAYOUT = "layout"
OP_SYNC = "sync"
OP_CREATE = "create"
OP_UPDATE = "update"
OP_DELETE = "delete"
OP_RENAME = "rename"
OP_MINT_UID = "mint-uid"


@dataclass(frozen=True)
class CommitMeta:
    """What one commit says about itself, written as its trailers.

    ``actor`` is the audit actor of the operation. ``agent`` names an agent —
    the writer itself when ``writer`` is ``agent``, and for a curation pass
    the author of the item it curated. ``collection`` / ``item`` / ``status``
    / ``undoes`` are the knowledge history's own fields.
    """

    writer: str
    operation: str
    summary: str
    actor: str | None = None
    agent: str | None = None
    machine: str | None = None
    collection: str | None = None
    item: str | None = None
    status: str | None = None
    restored_from: str | None = None
    undoes: str | None = None
    layout: str | None = None

    def with_machine(self, machine: str | None) -> CommitMeta:
        """This meta naming ``machine``, unless it already names one."""
        return self if self.machine or not machine else replace(self, machine=machine)


#: The trailer each ``CommitMeta`` field is written as.
TRAILERS = {
    "writer": "Coffer-Writer",
    "operation": "Coffer-Operation",
    "actor": "Coffer-Actor",
    "agent": "Coffer-Agent",
    "machine": "Coffer-Machine",
    "collection": "Coffer-Collection",
    "item": "Coffer-Item",
    "status": "Coffer-Status",
    "restored_from": "Coffer-Restored-From",
    "undoes": "Coffer-Undoes",
    "layout": "Coffer-Layout",
}
_FIELD_OF = {v.lower(): k for k, v in TRAILERS.items()}
_META_FIELDS = {f.name for f in fields(CommitMeta)}


def author_name(writer: str | None) -> str:
    """The commit author for ``writer`` (``Coffer (sync)``)."""
    return f"Coffer ({writer})" if writer else "Coffer"


def message(meta: CommitMeta) -> str:
    """The commit message: the summary, a blank line, one trailer per field set."""
    lines = [meta.summary.strip().replace("\n", " ") or meta.operation, ""]
    for name, trailer in TRAILERS.items():
        value = getattr(meta, name)
        if value:
            lines.append(f"{trailer}: {str(value).replace(chr(10), ' ')}")
    return "\n".join(lines) + "\n"


def parse_meta(body: str) -> CommitMeta:
    """Read a commit message back into its ``CommitMeta``.

    A commit with no ``Coffer-Writer`` trailer — one a person made by hand —
    reads as a ``disk`` edit, which is what it is.
    """
    lines = body.strip("\n").split("\n")
    summary = lines[0] if lines else ""
    values: dict[str, str] = {}
    for line in lines[1:]:
        key, sep, value = line.partition(": ")
        name = _FIELD_OF.get(key.strip().lower())
        if sep and name and name in _META_FIELDS:
            values[name] = value.strip()
    writer = values.pop("writer", WRITER_DISK)
    operation = values.pop("operation", OP_EDIT)
    return CommitMeta(writer=writer, operation=operation, summary=summary, **values)


def display_writer(meta: CommitMeta) -> str:
    """The short label a history row shows: ``agent:<type>`` for an agent."""
    if meta.writer == WRITER_AGENT and meta.agent:
        return f"agent:{meta.agent}"
    return meta.writer


__all__ = [
    "OP_BASELINE",
    "OP_CREATE",
    "OP_DELETE",
    "OP_EDIT",
    "OP_LAYOUT",
    "OP_MINT_UID",
    "OP_RENAME",
    "OP_RESTORE",
    "OP_SYNC",
    "OP_UPDATE",
    "TRAILERS",
    "WRITERS",
    "WRITER_AGENT",
    "WRITER_CURATION",
    "WRITER_DAEMON",
    "WRITER_DISK",
    "WRITER_SYNC",
    "WRITER_USER",
    "CommitMeta",
    "author_name",
    "display_writer",
    "message",
    "parse_meta",
]
