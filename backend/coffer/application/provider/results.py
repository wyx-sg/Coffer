"""Result value objects for :class:`ProviderService` switch operations (spec 011)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActivateResult:
    """Outcome of a switch: which agents were written, which wire had none."""

    activated: str
    wire_format: str
    projected: list[str]
    skipped: list[str]


@dataclass(frozen=True)
class DeactivateResult:
    """Outcome of switching a wire back to the agent's built-in login: which
    agents had Coffer's projection removed, and the connection that was active."""

    wire_format: str
    deprojected: list[str]
    previous: str | None
