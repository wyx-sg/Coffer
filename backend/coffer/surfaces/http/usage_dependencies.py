"""FastAPI dependency providers for the usage kind.

Module-global singletons, set once by the lifespan through ``wire_usage``; a
getter called before its setter raises.
"""

from __future__ import annotations

from coffer.application.usage.query import UsageQueryService
from coffer.application.usage.quota import QuotaService

_query: UsageQueryService | None = None
_quota: QuotaService | None = None


def set_usage_query_service(service: UsageQueryService | None) -> None:
    global _query
    _query = service


def get_usage_query_service() -> UsageQueryService:
    if _query is None:
        raise RuntimeError("usage query service not initialised")
    return _query


def set_quota_service(service: QuotaService | None) -> None:
    global _quota
    _quota = service


def get_quota_service() -> QuotaService:
    if _quota is None:
        raise RuntimeError("quota service not initialised")
    return _quota
