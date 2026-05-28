"""Tracer port.

A minimal Span/Tracer surface that covers what KB + Memory services need:
- start a span with a stable name and an initial attribute set
- record extra attributes on the active span
- finish the span with a final status
- propagate exceptions: a span exits with status="error" if the context
  manager body raises

Adapters live under `coffer.infrastructure.observability/`. The default
adapter is a no-op; the LangFuse adapter activates when the LANGFUSE_*
environment variables are set.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Span(Protocol):
    def set_attribute(self, key: str, value: Any) -> None: ...
    def record_error(self, exc: BaseException) -> None: ...


@runtime_checkable
class SpanContext(Protocol):
    def __enter__(self) -> Span: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


@runtime_checkable
class Tracer(Protocol):
    """Open a span via a context manager.

    Adapters are expected to call `__enter__` / `__exit__` on a `Span`-like
    object whose lifetime represents the traced operation.
    """

    def span(self, name: str, *, attributes: Mapping[str, Any] | None = None) -> SpanContext: ...
