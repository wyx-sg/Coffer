"""The ``runtime`` block of ``GET /api/v1/daemon/status``: loop lag, tasks, workers.

Read from the daemon's one loop-lag probe, task supervisor and worker registry
(``application.runtime``); split out of ``daemon_routes`` for the file-size cap.
"""

from __future__ import annotations

from coffer.application.runtime.loop_lag import probe
from coffer.application.runtime.supervisor import tasks
from coffer.application.runtime.workers import workers
from coffer.surfaces.http.daemon_schemas import RuntimeHealthOut, TaskCrashOut, WorkerOut


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
        tasks_by_name=tasks().running_by_name(),
        task_crashes=stats.crashes,
        last_crash=(
            TaskCrashOut(task=last.task, error=last.error, at=last.at, restarting=last.restarting)
            if last is not None
            else None
        ),
        workers=[
            WorkerOut(
                name=w.name,
                mode=w.mode.value,
                state=w.state,
                runs=w.runs,
                failures=w.failures,
                last_started_at=w.last_started_at,
                last_duration_ms=w.last_duration_ms,
                last_ok=w.last_ok,
                next_run_at=w.next_run_at,
            )
            for w in workers().snapshot()
        ],
    )
