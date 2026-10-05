"""What a person said about a secret, as one vault document.

``state/secret-notes/notes.json`` is ``{"notes": {<ref>: {"label": "…",
"description": "…", "created_for": "<uid>", "origin": "page|dialog"}}}`` — a vault state
document, so it carries the format version, is written as one validated commit
and travels with sync. It sits beside no ciphertext: these are the person's
words, not secrets.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from coffer.domain.secrets import SecretNote
from coffer.infrastructure.vault.state_documents import StateDocument

AREA = "secret-notes"
DOC = "notes"
_KNOWN = ("label", "description", "created_for", "origin")


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _note(entry: Any) -> SecretNote | None:
    if not isinstance(entry, dict):
        return None
    note = SecretNote(
        label=_text(entry.get("label")),
        description=_text(entry.get("description")),
        created_for=_text(entry.get("created_for")),
        origin=_text(entry.get("origin")),
    )
    return None if note.empty else note


def _entry(note: SecretNote) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if note.label:
        out["label"] = note.label
    if note.description:
        out["description"] = note.description
    if note.created_for:
        out["created_for"] = note.created_for
    if note.origin:
        out["origin"] = note.origin
    return out


#: Every change to the one notes document is read-modify-write; one lock per
#: process keeps two of them from reading the same version and the second
#: being refused (or losing the first's change).
_WRITE = threading.RLock()


class VaultSecretNotes:
    """``SecretNotesPort`` over the vault's ``secret-notes`` state document."""

    def __init__(self, *, home: Path | None = None) -> None:
        self._doc = StateDocument(AREA, DOC, home=home)

    def _raw(self) -> dict[str, Any]:
        notes = (self._doc.get() or {}).get("notes")
        return dict(notes) if isinstance(notes, dict) else {}

    def all(self) -> dict[str, SecretNote]:
        out: dict[str, SecretNote] = {}
        for ref, entry in self._raw().items():
            note = _note(entry)
            if note is not None:
                out[ref] = note
        return out

    def get(self, ref: str) -> SecretNote | None:
        return _note(self._raw().get(ref))

    def put(self, ref: str, note: SecretNote | None, *, summary: str, actor: str | None) -> None:
        """Set ``ref``'s note; an empty or absent one removes the entry. Entries
        for other refs, and any key of the entry this build does not know, stay."""
        with _WRITE:
            self._put(ref, note, summary=summary, actor=actor)

    def update(
        self,
        ref: str,
        change: Callable[[SecretNote | None], SecretNote | None],
        *,
        summary: str,
        actor: str | None,
    ) -> SecretNote | None:
        with _WRITE:
            before = self.get(ref)
            after = change(before)
            if after != before:
                self._put(ref, after, summary=summary, actor=actor)
            return None if after is None or after.empty else after

    def _put(self, ref: str, note: SecretNote | None, *, summary: str, actor: str | None) -> None:
        raw = self._raw()
        if note is None or note.empty:
            if ref not in raw:
                return
            raw.pop(ref)
        else:
            kept = dict(raw[ref]) if isinstance(raw.get(ref), dict) else {}
            for key in _KNOWN:
                kept.pop(key, None)
            raw[ref] = {**_entry(note), **kept}
        if not raw:
            self._doc.remove(summary=summary, actor=actor)
        else:
            self._doc.put({"notes": raw}, summary=summary, actor=actor)
