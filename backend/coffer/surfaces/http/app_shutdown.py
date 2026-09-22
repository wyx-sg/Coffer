"""How the daemon takes itself apart, in the order that makes it safe.

Split out of ``app._lifespan``, which was doing two jobs in one function: build
everything, then — forty lines later, after a ``yield`` — stop everything. The
two halves share nothing but the objects handed over here, and the teardown is
the half whose ORDER is load-bearing, so it is worth reading on its own.

Three rules the order encodes:

* **Stop what starts work before stopping what work needs.** The advance
  worker is first because it is the one worker that starts agent turns; the
  channel adapters are next for the same reason.
* **Cancel the reconciler before disposing it.** An in-flight tick would
  otherwise resurrect the adapters ``dispose()`` just stopped.
* **Every step is best-effort.** A dead component must not abort the teardown
  of the ones after it — a daemon that fails to close its database because a
  channel adapter raised is a daemon that leaves a lock behind.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from coffer.surfaces.http import daemon_routes
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.curation_wiring import stop_curation_worker
from coffer.surfaces.http.mcp.protocol_routes import shutdown_all_sessions
from coffer.surfaces.http.memory_wiring import stop_aggregate_worker, stop_distil_worker
from coffer.surfaces.http.sync_wiring import stop_converge_worker
from coffer.surfaces.http.transcript_warm_wiring import stop_transcript_warm_worker
from coffer.surfaces.http.workflow_wiring import stop_advance_worker

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Running:
    """What the daemon has running, as the teardown needs to reach it.

    Deliberately not typed against every wiring module's own result classes:
    this is the composition root's own bookkeeping, and importing nine result
    types to name them here would make the layering fence ugly for no reader's
    benefit. What each field IS, is documented where it is built.
    """

    workers: Any
    workflow: Any
    channel_runtime: Any
    channel_runtime_task: asyncio.Task[None]
    reaper_task: asyncio.Task[Any]
    kinds: Any
    chat: Any
    engine: AsyncEngine


async def best_effort(step: str, awaitable: Any) -> None:
    """Await ``awaitable``, logging and swallowing whatever it raises.

    Shutdown is a sequence of independent obligations; one failing must not
    cost the rest. The step's name is logged so a silent swallow is still a
    thing somebody can find.
    """
    try:
        await awaitable
    except (Exception, asyncio.CancelledError):
        _logger.exception("shutdown.step_failed", extra={"step": step})


async def shutdown(running: Running) -> None:
    """Stop everything, in the order above."""
    daemon_routes.set_daemon_phase("draining")
    running.workers.retention_worker.stop()
    # First — it is the one worker that starts agent turns.
    await stop_advance_worker(running.workflow.worker)
    await stop_converge_worker(running.workers.converge_worker)
    await stop_curation_worker(running.workers.curation_task)
    await stop_distil_worker(running.workers.distil_task)
    await stop_aggregate_worker(running.workers.aggregate_task)
    await stop_transcript_warm_worker(running.workers.warm_worker, running.workers.warm_task)

    # Channel adapters next, so no new turns start mid-teardown. Cancel the
    # reconciler BEFORE dispose() so an in-flight tick cannot resurrect what
    # dispose() just stopped.
    running.channel_runtime.stop()
    running.channel_runtime_task.cancel()
    await best_effort(
        "channel_runtime", asyncio.wait_for(running.channel_runtime_task, timeout=2.0)
    )
    await best_effort("channel_runtime.dispose", running.channel_runtime.dispose())

    # The retention worker was asked to stop above; give it a grace period to
    # finish an in-flight prune, then cancel it.
    try:
        await asyncio.wait_for(running.workers.retention_task, timeout=2.0)
    except TimeoutError:
        _logger.warning("shutdown.retention_worker.grace_expired; cancelling")
        running.workers.retention_task.cancel()
    except asyncio.CancelledError:
        _logger.debug("shutdown.retention_worker.cancelled")
        running.workers.retention_task.cancel()

    running.reaper_task.cancel()
    await best_effort("mcp_session_reaper", running.reaper_task)
    # Drain the buffered invocation writer before tearing down sessions.
    await best_effort("invocation_repo", running.kinds.mcp.invocation_repo.stop())
    # The built-in agent's chat gateway session first (best-effort); its
    # on_dispose callback removes its entry from session_supervisors.
    await best_effort("chat_gateway_session", running.chat.gateway_session.dispose())
    # Dispose MCP supervisors (best-effort). The process-wide supervisor is IN
    # this registry now — it has to be, or the kind's delete and rename hooks
    # cannot reach the upstreams it holds — so the loop covers it and the
    # separate call it used to get would only dispose it twice.
    for session_id, sup in list(running.kinds.mcp.session_supervisors.items()):
        await best_effort(f"session_supervisor[{session_id}]", sup.dispose())
    running.kinds.mcp.session_supervisors.clear()
    # Close per-/mcp/-session state in the protocol routes.
    await best_effort("mcp_sessions", shutdown_all_sessions())
    # The knowledge service holds no long-lived handles (the directory is
    # session-maker-bound + lazy), so only the shared engine needs disposal.
    await running.engine.dispose()
    set_active_token(None)
