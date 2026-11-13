"""Reads Codex's memory: the topics of its v2 summary (spec memory "Read
Codex's memory from its v2 summary").

Codex keeps its consolidated memory in ``<config_dir>/memories_v2/
memory_summary.md``. Each bullet of its ``## What's in Memory`` section is one
topic: something Codex learned in one piece of work, with a pointer to the
rollout summary it came from. A topic is one memory. It is filed under the
working directory in the header of that rollout summary, the first lines of
that file and nothing else; the summaries' accounts and Codex's transcripts
are never read.

The rest of the summary is about the person rather than a project (the User
Profile, the preferences, the General Tips), and only memories learned in a
repository are synced, so it is not read.

Codex's older ``memories/`` folder (``MEMORY.md`` task groups) is not read
either: its bullets are working notes of single tasks, several hundred of
them, and what in them is worth carrying is what Codex consolidates into the
v2 summary (ADR sync-memories-not-task-notes).

A topic tagged ``[via Coffer]`` is what Codex derived from a memory Coffer
synced into it from another agent (spec memory "Never republish Coffer's own
copies") and is skipped; so is everything under ``extensions/``, which this
reader never lists.
"""

from __future__ import annotations

import hashlib
import pathlib
import re

from coffer.domain.agent.codex_memory import parse_codex_v2_topics
from coffer.domain.memory.errors import UnreadableMemory
from coffer.domain.memory.hub import TYPE_PROJECT
from coffer.domain.memory.reader import RawEntry, SourceFile
from coffer.infrastructure.agent_files.codex_rollout_summaries import rollout_cwd
from coffer.infrastructure.memory.writers.codex import VIA_COFFER

SUMMARY_NAME = "memory_summary.md"
V2_FOLDER = "memories_v2"
#: The heading part of a topic's anchor.
TOPICS_HEADING = "What's in Memory"


class CodexMemoryReader:
    """``MemoryReader`` for Codex's v2 ``memory_summary.md``."""

    agent_type = "codex"

    def sources(self, config_dir: str) -> tuple[SourceFile, ...]:
        file = pathlib.Path(config_dir) / V2_FOLDER / SUMMARY_NAME
        try:
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
        except OSError:
            return ()
        return (SourceFile(path=str(file), digest=digest),)

    def read(self, source: SourceFile) -> tuple[RawEntry, ...]:
        path = pathlib.Path(source.path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise UnreadableMemory(source.path, str(exc)) from exc
        entries: list[RawEntry] = []
        for topic in parse_codex_v2_topics(text):
            if VIA_COFFER in topic.body:
                continue
            # The topic's sentence and its indented details, without the
            # pointer and thread id Codex keeps for itself.
            body = "\n".join([topic.text, *topic.body.split("\n")[1:]])
            entries.append(
                RawEntry(
                    title=topic_title(topic.text),
                    description=topic.text,
                    type=TYPE_PROJECT,
                    body=body,
                    anchor=anchor(topic.scope or "memory", body),
                    project_root=rollout_cwd(path.parent, topic.rollout_file),
                )
            )
        return tuple(entries)


def topic_title(text: str) -> str:
    """A short title from a topic's first clause (up to the first ``->``,
    ``. `` or ``; ``): Codex's topics are prose with no title of their own."""
    clause = re.split(r"\s*->\s*|\.\s|;\s", text, maxsplit=1)[0].strip().rstrip(".")
    if not clause:
        clause = text.strip()
    if len(clause) > 100:
        clause = clause[:97].rstrip() + "..."
    return clause


def anchor(scope: str, body: str) -> str:
    """A topic's identity inside the summary: its scope and its text. The same
    topic re-read on a later sync has the same anchor; a topic Codex rewrote
    is a new memory."""
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{scope}::{TOPICS_HEADING}::{digest}"


__all__ = ["CodexMemoryReader", "anchor", "topic_title"]
