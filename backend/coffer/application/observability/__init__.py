"""Cross-cutting observability port — extracted per constitution rule once a
second feature (memory, spec 007) needs traces alongside knowledge_base (006).

The default adapter is a no-op; the LangFuse adapter (infrastructure/) only
activates when the relevant environment variables are set.
"""

from coffer.application.observability.tracer import Span, Tracer

__all__ = ["Span", "Tracer"]
