"""Two-signal agent detection: the program, and the config directory.

A config directory alone is weak evidence that an agent is installed: it
survives an uninstall, and a dotfiles checkout can create it on a machine that
never had the program. So detection asks two questions — is the agent's
program on its real ``PATH`` (and which version), and does the config
directory exist — and names the combination:

- ``installed_active`` — program found, config directory present: the agent is
  installed and has been run here;
- ``installed_never_run`` — program found, no config directory yet: installed,
  never started (the agent creates its directory on first run);
- ``config_only`` — config directory present, program missing: what is left of
  an uninstalled agent. Shown as not installed, and not offered for adding;
- ``missing`` — neither. Never a discovery candidate; only a registered agent
  whose program and directory have both gone reads this.

Pure: the probe that answers the first question is the agent's dependency
probe facet (``facets.DependencyProbe``); the existence of the directory is
asked by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from coffer.domain.versions import parse_version


class DetectionState(StrEnum):
    INSTALLED_ACTIVE = "installed_active"
    INSTALLED_NEVER_RUN = "installed_never_run"
    CONFIG_ONLY = "config_only"
    MISSING = "missing"

    @property
    def installed(self) -> bool:
        """Whether the agent's program is on this machine."""
        return self in (DetectionState.INSTALLED_ACTIVE, DetectionState.INSTALLED_NEVER_RUN)


@dataclass(frozen=True)
class ProgramInfo:
    """What the dependency probe found. ``path`` is ``None`` when the program is
    not on the agent's ``PATH``; ``version`` is ``None`` when it is, but did not
    report a version the probe could read in time."""

    path: str | None = None
    version: str | None = None

    @property
    def found(self) -> bool:
        return self.path is not None


def classify(program: ProgramInfo, *, config_dir_exists: bool) -> DetectionState:
    if program.found:
        return (
            DetectionState.INSTALLED_ACTIVE
            if config_dir_exists
            else DetectionState.INSTALLED_NEVER_RUN
        )
    return DetectionState.CONFIG_ONLY if config_dir_exists else DetectionState.MISSING


__all__ = ["DetectionState", "ProgramInfo", "classify", "parse_version"]
