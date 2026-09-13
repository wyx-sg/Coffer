"""Dependency provider for the organise pass runner.

Mirrors ``surfaces/http/knowledge/tidy_state.py``: held behind a setter so
the route module never imports the internal-engine ports directly — organise
reaches a model through an injected port, and keeping that wiring in the
composition root (``memory_wiring.py``) is what stops the port leaking into
the surface layer. Unlike knowledge's ``TidyPass`` (a stateful object the
route calls with ``(svc, name, actor=actor)``), the runner here is a bare
``partition -> OrganiseResult`` coroutine: ``organise_partition`` is a plain
function, not a class, and the route supplies its own audit call (FR-063 —
``organise_partition`` itself never touches ``AuditService``, see
``memory_wiring.py``'s module docstring).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

OrganiseRunner = Callable[[str], Awaitable[Any]]

_organise_runner: OrganiseRunner | None = None


def set_organise_runner(runner: OrganiseRunner) -> None:
    global _organise_runner
    _organise_runner = runner


def get_organise_runner() -> OrganiseRunner:
    if _organise_runner is None:
        raise RuntimeError("organise runner not initialised")
    return _organise_runner
