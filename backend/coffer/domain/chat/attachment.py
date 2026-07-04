"""A user-supplied attachment referenced by local path (spec 009 — channel media).

The bytes live on disk (downloaded from the channel into a Coffer-managed cache),
never inline in the chat DB — so conversation history stays small and the same
reference works for any modality. Each agent adapter *materialises* the reference
in its own native shape at send time: a vision agent inlines an image/document
content block (base64 read from ``path``), a path-native agent (Codex) receives
the path. See ADR-038.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Attachment:
    """One file handed to an agent for a turn — a path plus how to read it."""

    path: str  # absolute local path to the downloaded bytes
    mime: str  # e.g. "image/jpeg", "application/pdf", "audio/ogg"
    filename: str  # best-effort original name, for display / the agent's benefit

    @property
    def is_image(self) -> bool:
        return self.mime.startswith("image/")

    @property
    def is_pdf(self) -> bool:
        return self.mime == "application/pdf"


__all__ = ["Attachment"]
