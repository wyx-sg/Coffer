"""No-op Tracer adapter — the default."""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import Any

from coffer.application.observability.tracer import Span, SpanContext, Tracer


class _NoopSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        return

    def record_error(self, exc: BaseException) -> None:
        return


class _NoopSpanContext:
    def __init__(self, span: _NoopSpan) -> None:
        self._span = span

    def __enter__(self) -> Span:
        return self._span

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return  # never swallow


class NoopTracer(Tracer):
    """Returns a no-op span; zero overhead beyond a few object creations."""

    def span(self, name: str, *, attributes: Mapping[str, Any] | None = None) -> SpanContext:
        return _NoopSpanContext(_NoopSpan())
