"""The secret-notes document, published for the routes (spec secret "Label and describe")."""

from __future__ import annotations

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
