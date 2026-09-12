"""Dependency provider for the tidy pass.

Held behind a setter the way the other knowledge-side singletons are, so the
route module does not import the pass directly: tidy reaches an LLM through an
injected port, and keeping the wiring in the composition root is what stops
that port leaking into the surface layer.
"""

from __future__ import annotations

from typing import Any

_tidy_runner: Any | None = None


def set_tidy_runner(runner: Any) -> None:
    global _tidy_runner
    _tidy_runner = runner


def get_tidy_runner() -> Any:
    if _tidy_runner is None:
        raise RuntimeError("tidy runner not initialised")
    return _tidy_runner
