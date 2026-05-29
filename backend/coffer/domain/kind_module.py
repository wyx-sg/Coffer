"""KindModule — the composition-root data carrier.

Held outside `domain/resource.py` on purpose: it references surface-layer
artefacts (HTTP routers, Typer groups) via `Any`-typed fields so the
domain layer can't accidentally import them at the call site. Composition
roots in surfaces/http/app.py and surfaces/cli/main.py construct these
and wire them into the running daemon.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class KindModule:
    """Bundle of references a composition root needs to register a kind."""

    name: str
    display_name: str
    config_schema: type  # Pydantic BaseModel subclass
    on_delete: Callable[..., None] | None = None
    http_routers: Sequence[Any] = field(default_factory=tuple)
    cli_groups: Sequence[Any] = field(default_factory=tuple)
