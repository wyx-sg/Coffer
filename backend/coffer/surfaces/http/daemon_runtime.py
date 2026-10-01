"""The ``runtime`` block of ``GET /api/v1/daemon/status``: loop lag and task crashes.

Read from the daemon's one loop-lag probe and one task supervisor
(``application.runtime``); split out of ``daemon_routes`` for the file-size cap.
"""

from __future__ import annotations

from coffer.application.runtime.loop_lag import probe
from coffer.application.runtime.supervisor import tasks
from coffer.surfaces.http.daemon_schemas import RuntimeHealthOut, TaskCrashOut


def runtime_health() -> RuntimeHealthOut:
    """What the probe and the supervisor report right now."""
    lag = probe().snapshot()
    stats = tasks().stats()
    last = stats.last_crash
    return RuntimeHealthOut(
        loop_lag_p99_ms=lag.p99_ms,
        loop_lag_max_ms=lag.max_ms,
        loop_lag_samples=lag.samples,
        loop_lag_window_seconds=lag.window_seconds,
        tasks_running=stats.running,
        task_crashes=stats.crashes,
        last_crash=(
            TaskCrashOut(task=last.task, error=last.error, at=last.at, restarting=last.restarting)
            if last is not None
            else None
        ),
    )
