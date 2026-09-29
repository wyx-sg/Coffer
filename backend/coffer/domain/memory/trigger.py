"""A memory trigger: a person's mark that one note is a known trap tied to a
command (spec memory "Guard a known trap once per session").

A trigger names a note and a pattern. A ``block`` trigger holds the first
shell command in a session whose **executing** segment matches ``command`` —
the agent is told the note as the reason and its next attempt passes. A
``context`` trigger adds the note after a command whose output matches
``error``, and never blocks.

Triggers are authored content, not derived memory: they live in the vault
(``vault/memory-triggers/<id>.md``) beside the derived notes and survive a
rebuild of the memory tree. Distil may **propose** one; a proposal does
nothing until a person arms it (``armed_by``).

Pure: parsing a command into segments and matching a trigger against it.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, replace

from coffer.domain.error_base import CofferError

KIND_BLOCK = "block"
KIND_CONTEXT = "context"
TRIGGER_KINDS = frozenset({KIND_BLOCK, KIND_CONTEXT})

#: The partition and slug a trigger's note is named by: ``<partition>/<slug>``.
_NOTE_REF = re.compile(r"^[A-Za-z0-9._\- 一-鿿]+/[A-Za-z0-9._\-一-鿿]+$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")

#: What separates two shell segments: ``&&``, ``||``, ``;``, ``|``, a newline,
#: ``$(``, ``(``, ``)`` and a backtick.
_SEPARATOR = re.compile(r"&&|\|\||\$\(|[;|\n()`]")
#: One segment: its ``VAR=value`` prefixes, the program, and the rest.
_SEGMENT = re.compile(r"^\s*((?:\w+=\S*\s+)*)(\S+)(.*)$", re.S)


#: Programs that execute the script named by their first argument.
_INTERPRETERS = frozenset(
    {"bash", "sh", "zsh", "dash", "fish", "python", "python3", "node", "ruby", "perl"}
)


class TriggerInvalid(CofferError):  # noqa: N818
    """A trigger whose fields cannot be used: an unknown kind, a pattern that
    does not compile, a missing pattern for its kind, or a malformed note ref."""

    code = "MEMORY_TRIGGER_INVALID"


class TriggerNotFound(CofferError):  # noqa: N818
    code = "MEMORY_TRIGGER_NOT_FOUND"


@dataclass(frozen=True)
class Segment:
    """One shell segment of a command: the ``VAR=value`` prefixes, the program
    as it executes (its base name), and its arguments."""

    env: str
    program: str
    args: str

    @property
    def text(self) -> str:
        """What a ``command`` pattern is matched against, **from its start**:
        the command that executes, without the ``VAR=value`` prefixes.

        That is the program and its arguments — ``make verify`` — except when the
        program is an interpreter running a script (``bash scripts/e2e.sh``,
        ``python3 tool.py``): then the script executes, and the text starts at
        its base name (``e2e.sh``). A file a program only reads is an argument,
        never the start, so ``cat scripts/e2e.sh`` starts with ``cat``.
        """
        args = self.args.strip()
        if self.program in _INTERPRETERS and args:
            words = args.split()
            flags = 0
            while flags < len(words) and words[flags].startswith("-"):
                if words[flags] in ("-c", "-m", "-e"):
                    # An inline program or a module, not a script file.
                    return f"{self.program} {args}".strip()
                flags += 1
            if flags < len(words):
                script = os.path.basename(words[flags])
                return " ".join([script, *words[flags + 1 :]])
        return f"{self.program} {args}".strip()


def segments(command: str) -> Iterator[Segment]:
    """Every segment of ``command`` that executes a program, subshells and
    command substitutions included."""
    for piece in _SEPARATOR.split(command or ""):
        m = _SEGMENT.match(piece)
        if m is not None:
            yield Segment(m.group(1) or "", os.path.basename(m.group(2)), m.group(3) or "")


@dataclass(frozen=True)
class Trigger:
    """One trigger, as its file holds it."""

    id: str
    #: ``<partition>/<slug>`` — the note whose description is the reason.
    note: str
    kind: str
    #: Regex matched from the start of each executing segment (``program
    #: args``, or the script an interpreter runs), for ``block``.
    command: str = ""
    #: Regex over the whole command; when it matches, the trigger stays quiet —
    #: the command already does what the note asks (``PATH=...v20... make verify``).
    unless: str = ""
    #: Regex over a command's output, for ``context``.
    error: str = ""
    #: Who armed it; empty for a proposal nobody has accepted.
    armed_by: str = ""
    armed_at: str = ""
    #: Who proposed it (``distil``), or empty when a person wrote it.
    proposed_by: str = ""
    created: str = ""
    #: Free text below the frontmatter; the reason when the note is gone.
    body: str = ""

    @property
    def armed(self) -> bool:
        return bool(self.armed_by)

    @property
    def partition(self) -> str:
        return self.note.split("/", 1)[0]

    @property
    def slug(self) -> str:
        return self.note.split("/", 1)[1] if "/" in self.note else ""

    def arm(self, actor: str, at: str) -> Trigger:
        return replace(self, armed_by=actor, armed_at=at)

    def disarm(self) -> Trigger:
        return replace(self, armed_by="", armed_at="")


@dataclass(frozen=True)
class TriggerProposal:
    """A trigger distil suggests for the note it just wrote, unarmed until a
    person accepts it."""

    slug: str
    kind: str
    command: str = ""
    unless: str = ""
    error: str = ""


def _compiles(pattern: str, field: str) -> None:
    try:
        re.compile(pattern)
    except re.error as e:
        raise TriggerInvalid(f"{field}: {e}") from e


def validate(trigger: Trigger) -> Trigger:
    """``trigger`` unchanged, or :class:`TriggerInvalid` naming what is wrong."""
    if not _ID.match(trigger.id):
        raise TriggerInvalid(f"id {trigger.id!r} is not a safe file name")
    if not _NOTE_REF.match(trigger.note) or ".." in trigger.note:
        raise TriggerInvalid(f"note {trigger.note!r} is not <partition>/<slug>")
    if trigger.kind not in TRIGGER_KINDS:
        raise TriggerInvalid(f"kind {trigger.kind!r} is not one of {sorted(TRIGGER_KINDS)}")
    if trigger.kind == KIND_BLOCK and not trigger.command:
        raise TriggerInvalid("a block trigger needs a command pattern")
    if trigger.kind == KIND_CONTEXT and not trigger.error:
        raise TriggerInvalid("a context trigger needs an error pattern")
    for field in ("command", "unless", "error"):
        value = getattr(trigger, field)
        if value:
            _compiles(value, field)
    return trigger


def matches_command(trigger: Trigger, command: str) -> bool:
    """Whether ``command`` executes what ``trigger.command`` names.

    Matched per segment, **anchored at the start** of what executes
    (:attr:`Segment.text`): the pattern names the command, and a word that only
    appears in a later argument does not match — ``cat scripts/e2e.sh`` does
    not trip a trigger on ``e2e``, ``bash scripts/e2e.sh`` does. ``unless`` is
    searched anywhere in the whole command, prefixes included.
    """
    if not trigger.command or not command:
        return False
    if trigger.unless and re.search(trigger.unless, command):
        return False
    pattern = re.compile(trigger.command)
    return any(pattern.match(seg.text) for seg in segments(command))


def matches_error(trigger: Trigger, command: str, output: str) -> bool:
    """Whether a finished command's ``output`` shows what ``trigger.error``
    names (and, when the trigger also has a ``command``, the command matched)."""
    if not trigger.error or not output:
        return False
    if trigger.command and not matches_command(trigger, command):
        return False
    return re.search(trigger.error, output) is not None


__all__ = [
    "KIND_BLOCK",
    "KIND_CONTEXT",
    "TRIGGER_KINDS",
    "Segment",
    "Trigger",
    "TriggerInvalid",
    "TriggerNotFound",
    "TriggerProposal",
    "matches_command",
    "matches_error",
    "segments",
    "validate",
]
