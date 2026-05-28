"""LangFuse Tracer adapter. Optional; activated only when LANGFUSE_* env-vars set.

The `langfuse` package is imported lazily so the module loads cleanly when
it isn't installed.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from types import TracebackType
from typing import Any

from coffer.application.observability.tracer import Span, SpanContext, Tracer

_logger = logging.getLogger(__name__)


class _LFSpan:
    def __init__(self, lf_span: Any) -> None:
        self._lf_span = lf_span

    def set_attribute(self, key: str, value: Any) -> None:
        try:
            self._lf_span.update(metadata={key: value})
        except Exception:
            _logger.debug("langfuse span.update failed", exc_info=True)

    def record_error(self, exc: BaseException) -> None:
        try:
            self._lf_span.update(level="ERROR", status_message=str(exc))
        except Exception:
            _logger.debug("langfuse error record failed", exc_info=True)


class _LFContext:
    def __init__(self, lf: Any, name: str, attributes: Mapping[str, Any] | None) -> None:
        self._lf = lf
        self._name = name
        self._attrs = dict(attributes or {})
        self._span: Any = None

    def __enter__(self) -> Span:
        try:
            self._span = self._lf.span(name=self._name, metadata=self._attrs)
        except Exception:
            _logger.debug("langfuse span create failed", exc_info=True)
            self._span = None
        return _LFSpan(self._span) if self._span is not None else _NullSpan()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._span is not None:
            try:
                if exc is not None:
                    self._span.update(level="ERROR", status_message=str(exc))
                self._span.end()
            except Exception:
                _logger.debug("langfuse span end failed", exc_info=True)
        return


class _NullSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        return

    def record_error(self, exc: BaseException) -> None:
        return


class LangfuseTracer(Tracer):
    """LangFuse-backed tracer.

    Requires `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and (typically)
    `LANGFUSE_HOST` in the environment. Falls back gracefully if the SDK
    can't initialise.
    """

    def __init__(self) -> None:
        try:
            from langfuse import Langfuse  # type: ignore
        except ImportError as exc:
            raise RuntimeError("langfuse SDK not installed; pip install langfuse") from exc
        self._lf = Langfuse()

    def span(self, name: str, *, attributes: Mapping[str, Any] | None = None) -> SpanContext:
        return _LFContext(self._lf, name, attributes)
