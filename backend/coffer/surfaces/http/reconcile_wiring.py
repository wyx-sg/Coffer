"""Composition of the unified reconciler (ADR
one-level-triggered-reconciler-compares-parameters).

The reconciler is built before any kind, because the resource repository it
hints from is built before any kind: every write through ``ResourceService``
announces itself (``HintingResourceRepo``). Each kind's wiring registers the
targets it supplies; the lifespan then runs the boot pass, starts the periodic
loop, and cancels it on shutdown.

A sync import no longer carries per-kind post-import hooks for what the
reconciler converges: one hook asks for a pass with the import's warrant
(``Trigger.IMPORT``), inside the reconciler's hold that the round keeps over
its apply, so no periodic pass judges the imported rows half-applied.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence

from coffer.application.attention import AttentionService, AttentionSource, IgnoreStore
from coffer.application.audit_service import AuditService
from coffer.application.reconcile.attention_source import DriftAttentionSource
from coffer.application.reconcile.reconciler import Reconciler
from coffer.domain.reconcile import Outcome, PassReport, Trigger
from coffer.surfaces.http.reconcile_dependencies import set_attention_service, set_reconciler
from coffer.surfaces.http.sync_contributions import SyncContributions

_log = logging.getLogger(__name__)


class ReconcilerImportHook:
    """Implements ``application.sync.ports.PostImportHook``: after a sync
    import, one pass over every target, with the import's warrant."""

    kind = "reconcile"

    def __init__(self, reconciler: Reconciler) -> None:
        self._reconciler = reconciler

    async def reconcile(self) -> list[str]:
        return failures_of(await self._reconciler.run(trigger=Trigger.IMPORT))


def failures_of(report: PassReport) -> list[str]:
    """One line per item a pass could not bring in step, and per target that
    raised — what a sync round reports among its failures."""
    lines = [f"{f.target}: {f.error}" for f in report.failures]
    lines += [f"{r.change.id}: {r.error}" for r in report.results if r.outcome is Outcome.FAILED]
    return lines


def build_reconciler(audit: AuditService, sync: SyncContributions) -> Reconciler:
    """The one reconciler, registered for the routes and the sync round."""
    reconciler = Reconciler(audit=audit)
    set_reconciler(reconciler)
    sync.post_import_hooks.append(ReconcilerImportHook(reconciler))
    sync.apply_guard = reconciler.hold
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
    return asyncio.create_task(reconciler.serve(), name="reconciler")


__all__ = [
    "ReconcilerImportHook",
    "build_reconciler",
    "failures_of",
    "run_boot_pass",
    "start_reconciler",
    "wire_attention",
]
