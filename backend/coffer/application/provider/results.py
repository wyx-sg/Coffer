"""Result value objects for :class:`ProviderService` switch operations (spec provider-switching)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActivateResult:
    """Outcome of switching one agent onto a connection."""

    activated: str
    protocol: str
    agent_type: str
    #: The agent's name.
    agent: str


@dataclass(frozen=True)
class DeactivateResult:
    """Outcome of switching an agent type back to its built-in login: which
    agents had Coffer's projection removed, and the connection it was on."""

    agent_type: str
    deprojected: list[str]
    previous: str | None
