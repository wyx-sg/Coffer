"""Observability adapters. Default = noop; LangFuse activates when env-vars set."""

import logging
import os

from coffer.application.observability.tracer import Tracer
from coffer.infrastructure.observability.langfuse_tracer import LangfuseTracer
from coffer.infrastructure.observability.noop_tracer import NoopTracer

__all__ = ["LangfuseTracer", "NoopTracer", "make_tracer"]

_logger = logging.getLogger(__name__)


def make_tracer() -> Tracer:
    """Pick the configured tracer adapter.

    LangFuse is enabled iff `LANGFUSE_PUBLIC_KEY` is set in the environment.
    Otherwise the no-op tracer is returned (zero overhead, zero outbound).

    If LangFuse init raises, fall back to the no-op tracer so the daemon
    still comes up, but log a warning with the traceback so the operator
    can see why traces are not flowing (CODE22-017).
    """
    if os.environ.get("LANGFUSE_PUBLIC_KEY"):
        try:
            return LangfuseTracer()
        except Exception:
            _logger.warning("langfuse.init_failed", exc_info=True)
            return NoopTracer()
    return NoopTracer()
