"""FastAPI dependency providers for the usage kind.

Module-global singletons, set once by the lifespan through ``wire_usage``; a
getter called before its setter raises.
"""

from __future__ import annotations

from coffer.application.usage.query import UsageQueryService

_query: UsageQueryService | None = None


def set_usage_query_service(service: UsageQueryService | None) -> None:
    global _query
    _query = service


def get_usage_query_service() -> UsageQueryService:
    if _query is None:
        raise RuntimeError("usage query service not initialised")
    return _query
