"""Where a provider model's context window comes from (spec provider-switching
"Resolve each provider model's context window"; ADR
context-windows-for-provider-models).

One order, used by the projection when it tells an agent the window and by the
Models section when it shows one, so the two never disagree:

1. **You set** — the window the person recorded for the model on the connection;
2. **endpoint** — what the endpoint reported when its models were listed;
3. **bundled** — the window the release's price list records for the model at
   the provider the endpoint belongs to;
4. otherwise unknown (``None``): nothing is written, nothing is guessed.

Pure: the bundled lookup is handed in.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from coffer.domain.provider.config import CuratedModel


class WindowSource(StrEnum):
    USER = "user"
    ENDPOINT = "endpoint"
    BUNDLED = "bundled"


@dataclass(frozen=True)
class ResolvedWindow:
    tokens: int
    source: WindowSource


def resolve_window(
    curated: CuratedModel | None, bundled: Callable[[], int | None]
) -> ResolvedWindow | None:
    """The window of one model: the curated entry's own facts first, then the
    bundled list (asked only when the entry has none)."""
    if curated is not None and curated.user_context_window is not None:
        return ResolvedWindow(curated.user_context_window, WindowSource.USER)
    if curated is not None and curated.context_window is not None:
        return ResolvedWindow(curated.context_window, WindowSource.ENDPOINT)
    tokens = bundled()
    return ResolvedWindow(tokens, WindowSource.BUNDLED) if tokens is not None else None


__all__ = ["ResolvedWindow", "WindowSource", "resolve_window"]
