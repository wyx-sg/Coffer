"""Composition of the unified reconciler (ADR
one-level-triggered-reconciler-compares-parameters).

The reconciler is built before any kind, because the resource repository it
hints from is built before any kind: every write through ``ResourceService``
announces itself (``HintingResourceRepo``). Each kind's wiring registers the
targets it supplies; the lifespan then runs the boot pass, starts the periodic
loop, and cancels it on shutdown.

A sync round's checkout tells the vault writer's listeners what changed, and
each changed resource is hinted exactly like an API write. The round also
holds the reconciler (``Reconciler.hold``) from its first git call to its
import pass, so no pass judges the vault in between.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence

from coffer.application.attention import AttentionService, AttentionSource, IgnoreStore
from coffer.application.audit_service import AuditService
from coffer.application.reconcile.attention_source import DriftAttentionSource
from coffer.application.reconcile.reconciler import Reconciler
from coffer.application.runtime.supervisor import spawn_restarting
from coffer.domain.reconcile import Outcome, Trigger
from coffer.surfaces.http.reconcile_dependencies import set_attention_service, set_reconciler

_log = logging.getLogger(__name__)


def build_reconciler(audit: AuditService) -> Reconciler:
    """The one reconciler, registered for the routes."""
    reconciler = Reconciler(audit=audit)
    set_reconciler(reconciler)
    return reconciler


async def run_boot_pass(reconciler: Reconciler) -> None:
    """The boot pass: best-effort, never allowed to fail startup. What it
    repairs is audited; what it only reports is logged by the pass."""
    try:
        report = await reconciler.run(trigger=Trigger.BOOT)
    except Exception:
        _log.exception("reconcile.boot_pass_failed")
        return
    _log.info(
        "reconcile.boot_pass",
        extra={
            "applied": report.count(Outcome.APPLIED),
            "failed": report.count(Outcome.FAILED),
            "open": report.count(Outcome.PLANNED),
        },
    )


def wire_attention(
    reconciler: Reconciler,
    feature_enabled: Callable[[str], bool],
    sources: Sequence[AttentionSource],
    *,
    ignores: IgnoreStore | None = None,
    audit: AuditService | None = None,
) -> AttentionService:
    """The "needs you" list: the reconciler's open drift first, then each
    kind's own signals; a source behind a switched-off feature is not asked.
    ``ignores`` holds what a person ignored on this machine."""
    service = AttentionService(
        [DriftAttentionSource(reconciler), *sources],
        feature_enabled=feature_enabled,
        ignores=ignores,
        audit=audit,
    )
    set_attention_service(service)
    return service


def start_reconciler(reconciler: Reconciler) -> asyncio.Task[None]:
    """The periodic loop, as a task the shutdown cancels."""
    return spawn_restarting(reconciler.serve, name="reconciler")


__all__ = [
    "build_reconciler",
    "run_boot_pass",
    "start_reconciler",
    "wire_attention",
]
