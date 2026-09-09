# backend/coffer/domain/memory/lane.py
"""The three memory lanes — Coffer's single classification axis (spec 007).

The lane names ARE the store subdir names. ``knowledge`` (semantic, recall) and
``rules`` (procedural, injected) are written by the organizer; ``handoff``
(working) is the per-branch scene.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["Lane"]


class Lane(StrEnum):
    KNOWLEDGE = "knowledge"
    RULES = "rules"
    HANDOFF = "handoff"
