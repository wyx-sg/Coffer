"""Wiring for the built-in workflow seed (spec workflow "Seed one
built-in template").

Two lines of joinery the application layer is not allowed to do for itself: a
``SeedRecord`` backed by a file, and the boot call that runs the seed once the
``workflow`` kind is registered.

The marker sits under ``~/.coffer/state/``, beside the one
``removed_agent_notice`` writes, for the same reason that one exists: a boot
action that must happen exactly once needs somewhere to say it happened, and
that somewhere has to outlive the thing it created. It is machine-local and
not part of the synced vault, which is correct — a converge round carries the
template itself, and a second machine reading the row as already present
records its own bit without writing anything.

Its own module rather than a few more lines in ``workflow_wiring``: that file
builds the engine, and this is the one piece of workflow startup that touches
neither a repository nor a port the engine holds.
"""

from __future__ import annotations

import logging
import os
import pathlib

from coffer.application.resource_service import ResourceService
from coffer.application.workflow.builtin_seed import BuiltinWorkflowSeed

_log = logging.getLogger(__name__)

#: Home-relative marker whose presence means this machine has already seen the
#: built-in template. Deleting it makes the next boot seed it again, which is
#: the only way back to the shipped template once it has been edited away.
SEED_MARKER = pathlib.Path(".coffer") / "state" / "workflow-builtin-template.done"


class FileSeedRecord:
    """``SeedRecord`` over one file under the vault's state directory.

    ``home`` is passed in rather than read here so nothing constructs a record
    pointed at the developer's real vault by default — the same reason the
    workflow file layer refuses to resolve its root without being told.
    """

    def __init__(self, home: pathlib.Path) -> None:
        self._marker = home / SEED_MARKER

    def seen(self) -> bool:
        return self._marker.exists()

    def mark(self) -> None:
        """Best-effort. A marker that cannot be written means the seed is
        re-attempted next boot and finds the row it wrote already there, which
        is a wasted read rather than a second template."""
        try:
            self._marker.parent.mkdir(parents=True, exist_ok=True)
            self._marker.write_text("seeded\n", encoding="utf-8")
        except OSError:
            _log.debug("workflow.builtin_seed.marker_unwritable", exc_info=True)


async def run_builtin_workflow_seed(resources: ResourceService) -> None:
    """Boot hook, mirroring ``run_builtin_guide_refresh``.

    Runs after the workflow kind is wired, because the write goes through the
    framework and the framework refuses a kind it does not know.
    """
    home = pathlib.Path(os.environ.get("HOME", "~")).expanduser()
    seed = BuiltinWorkflowSeed(resources=resources, record=FileSeedRecord(home))
    if await seed.seed():
        _log.info("workflow.builtin_template.seeded")


__all__ = ["SEED_MARKER", "FileSeedRecord", "run_builtin_workflow_seed"]
