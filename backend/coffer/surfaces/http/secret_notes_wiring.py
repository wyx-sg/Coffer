"""The secret-notes document, published for the routes (spec secret "Label and
describe a secret without changing its reference")."""

from __future__ import annotations

from typing import Any

from coffer.infrastructure.secret.notes_store import VaultSecretNotes

_notes: VaultSecretNotes | None = None


def set_secret_notes(notes: VaultSecretNotes) -> None:
    """Called once on startup, by the secret store's init."""
    global _notes
    _notes = notes


def optional_secret_notes() -> VaultSecretNotes | None:
    return _notes


def get_secret_notes() -> VaultSecretNotes:
    """FastAPI Depends() target."""
    if _notes is None:
        raise RuntimeError("secret notes not initialised")
    return _notes


def name_secret_refs(details: dict[str, Any]) -> dict[str, Any]:
    """An audit row's details with the secret its ``ref`` names also carrying
    ``ref_label``, the name a person gave it right now: the trail reads by
    that name, and it still does once the secret is renamed or deleted. A
    secret nobody named, or a row that already says, is left as it is."""
    ref = details.get("ref")
    if _notes is None or "ref_label" in details or not isinstance(ref, str):
        return details
    note = _notes.get(ref) if ref.startswith("secret/") else None
    return {**details, "ref_label": note.label} if note and note.label else details
