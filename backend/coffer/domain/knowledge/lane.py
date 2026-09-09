"""The three knowledge lanes — Coffer's single classification axis.

The lane names ARE the scope-dir subdir names. ``knowledge`` (semantic, recall)
and ``rules`` (procedural, injected) are written by the organizer; ``handoff``
(working) is the per-branch scene.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["Lane"]


class Lane(StrEnum):
    KNOWLEDGE = "knowledge"
    RULES = "rules"
    HANDOFF = "handoff"
