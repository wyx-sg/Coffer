"""Shared async-operation primitives.

A lightweight, cross-cutting layer (justified by the features that need it:
KB ingest and native-memory import) for running time-consuming operations off
the request path and surfacing their in-flight state to the UI.

- ``AsyncOpRegistry`` — in-memory map of transient states (queued/running/error).
- ``AsyncOpRunner`` — a bounded worker pool draining a queue of work items.

Durable "done"/"unchanged" outcomes are NOT stored here; each operation derives
them from its own data (sha ledgers, content hashes), so nothing in this layer
needs to survive a daemon restart.
"""

from coffer.application.async_ops.registry import (
    AsyncOpRegistry,
    InflightEntry,
    OpState,
)
from coffer.application.async_ops.runner import AsyncOpRunner, WorkFactory

__all__ = [
    "AsyncOpRegistry",
    "AsyncOpRunner",
    "InflightEntry",
    "OpState",
    "WorkFactory",
]
