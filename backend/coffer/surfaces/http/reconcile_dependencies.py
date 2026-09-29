"""FastAPI dependency providers for the reconciler and the attention list.

Module-global singletons, set once by the lifespan like the kind-agnostic ones
in ``dependencies``; a getter called before its setter raises.
"""

from __future__ import annotations

from coffer.application.attention import AttentionService
from coffer.application.reconcile.reconciler import Reconciler

_reconciler: Reconciler | None = None
_attention: AttentionService | None = None


def set_reconciler(reconciler: Reconciler | None) -> None:
    global _reconciler
    _reconciler = reconciler


def get_reconciler() -> Reconciler:
    if _reconciler is None:
        raise RuntimeError("reconciler not initialised")
    return _reconciler


def set_attention_service(service: AttentionService | None) -> None:
    global _attention
    _attention = service


def get_attention_service() -> AttentionService:
    if _attention is None:
        raise RuntimeError("attention service not initialised")
    return _attention
