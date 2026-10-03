"""Result value objects for :class:`ProviderService` switch operations (spec provider-switching)."""

from __future__ import annotations

from dataclasses import dataclass

from coffer.application.provider.line_diff import DiffRow


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


@dataclass(frozen=True)
class DeletePreviewFile:
    """One agent file that deleting a connection would change."""

    path: str
    #: ``modify`` or ``remove`` (the whole file goes).
    op: str
    diff: list[DiffRow]


@dataclass(frozen=True)
class DeletePreviewAgent:
    agent_uid: str
    agent_type: str
    agent_name: str
    files: list[DeletePreviewFile]


@dataclass(frozen=True)
class DeletePreview:
    """What deleting a connection would do to the agents running on it."""

    agents: list[DeletePreviewAgent]
