"""`coffer daemon` subcommand group: start / stop / restart / status.

These work when the daemon is down, which is why they are on the command line
(spec resource-framework "Offer every management operation on the command line"). The port it
listens on is the one setting that works the same way: `coffer config set
daemon.port`."""

from __future__ import annotations

import json as _json
import os
import signal
import time
from pathlib import Path
from typing import Any

import typer

from coffer.infrastructure.daemon import bootstrap, port_alloc
from coffer.infrastructure.daemon.force_stop import GRACEFUL_STOP_SECONDS, stop_daemon_process
from coffer.infrastructure.daemon.orphan_sweep import other_daemons_of_our_vault
from coffer.infrastructure.daemon.pid_lock import pid_is_coffer_daemon
from coffer.infrastructure.daemon.spawn import spawn_detached_daemon
from coffer.infrastructure.vault.home import daemon_json_path
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli import _io
from coffer.surfaces.cli._options import ExitCode

app = typer.Typer(help="Daemon lifecycle")


START_TIMEOUT_SECONDS = 30.0


def _wait_until_serving(proc: Any, timeout: float = START_TIMEOUT_SECONDS) -> str:
    """Wait for the spawned daemon to answer its status call.

    Returns ``"serving"``, ``"exited"`` (the child ended first — it refused to
    start, e.g. git is too old) or
    ``"timeout"``. ``daemon.json`` is no evidence of either: the daemon
    publishes it before uvicorn and the lifespan run, and a file left by a
    crash is there before the child has done anything.
    """
    deadline = time.monotonic() + timeout
    while True:
        if bootstrap.live_daemon() is not None:
            return "serving"
        if proc.poll() is not None:
            return "exited"
        if time.monotonic() >= deadline:
            return "timeout"
        time.sleep(0.2)


def _wait_for_daemon_json_gone(path: Path, timeout: float = GRACEFUL_STOP_SECONDS) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not path.exists():
            return True
        time.sleep(0.1)
    return False


def _refuse_if_the_port_is_taken() -> None:
    """Diagnose a squatted port here, instead of after a boot timeout.

    Without this the user meets "daemon failed to start within 10s; check
    daemon.log" — true, but it hides the likeliest cause behind a file they
    then have to open. The daemon binds one port and refuses to move, so this
    applies to every start, not only to a start whose port the user chose.

    The check is the real bind, done once and immediately let go, because that
    is the probe that agrees with the daemon's own attempt where it matters
    most: a port in TIME_WAIT from the daemon this ``restart`` just stopped is
    bindable and must not be reported as a conflict, and a holder owned by
    another user is unidentifiable but still blocks. Closing a socket that
    never accepted anything leaves nothing behind.

    It can report "free" when the port is not, and only ever errs that way. Two
    windows do it: the ordinary TOCTOU gap between this close and the daemon's
    own bind, and — on Linux specifically — a daemon that is bound but has not
    yet called ``listen``, which ``SO_REUSEADDR`` lets a second socket bind
    straight through (the platform difference held sockets turn on; see
    ``port_alloc._new_socket``). Both are safe to lose. The spawn this
    function guards goes on to take the daemon spawn lock and re-probe
    liveness, so a missed conflict resolves as "daemon already running" rather
    than as two daemons. What is lost is this early, actionable message — never
    correctness — which is why the probe is allowed to be optimistic and must
    never be made pessimistic.

    Only the caller's ordering makes this correct: ``live_daemon()`` is probed
    first, so *our own* daemon holding the port stays the clean "already
    running" path rather than a conflict.
    """
    port = bootstrap.planned_port()
    if port is None:
        return  # the range override is in play; there is no one port to check
    try:
        sock = port_alloc.bind_fixed_socket(port, attempts=1)
    except port_alloc.PortInUse as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None
    sock.close()


def _start_daemon() -> None:
    """Body of ``start``, shared with ``restart``."""
    # Spec daemon "Manage the daemon from the command line": key off
    # live_daemon() (a real status probe), NOT mere file presence. A stale
    # daemon.json left by a crashed daemon must trigger a respawn, not a false
    # "already running".
    if bootstrap.live_daemon() is not None:
        typer.echo("daemon already running")
        raise typer.Exit(0)

    _refuse_if_the_port_is_taken()

    # The same detached spawn the shim and the CLI's auto-spawn use: stdio to
    # ~/.coffer/logs/daemon.log, so the daemon's own refusal is readable there.
    try:
        proc = spawn_detached_daemon()
    except OSError as exc:
        typer.echo(f"failed to spawn daemon: {exc}", err=True)
        raise typer.Exit(1) from None

    outcome = _wait_until_serving(proc)
    if outcome == "exited":
        typer.echo(f"daemon exited at startup (code {proc.returncode}); check daemon.log", err=True)
        raise typer.Exit(1)
    if outcome == "timeout":
        # Not killed: see _client.client_or_exit — a slow boot finishes, and a
        # stuck one gives up on the spawn lock by itself.
        typer.echo(
            f"daemon did not answer within {START_TIMEOUT_SECONDS:.0f}s; check daemon.log",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo(f"daemon started (pid={proc.pid})")
    # Started, but waiting for git (spec daemon "Wait in a setup state when git
    # is missing or too old"): say why now rather than at the next command.
    info = _cli_client.discover()
    setup = _cli_client.waiting_for_git(bootstrap.probe_status(info) if info else None)
    if setup is not None:
        _cli_client.print_waiting_for_git(setup)


@app.command("start")
def start() -> None:
    """Spawn the daemon as a detached background process."""
    _start_daemon()


def _stop_daemon(*, force: bool = False) -> bool:
    """Body of ``stop``, shared with ``restart``.

    Returns False when there was nothing to stop. The two callers differ only
    in what that means — an error for ``stop``, the normal case for
    ``restart`` — so the decision is theirs, not this helper's.

    ``force`` is ``restart``'s: a daemon that does not exit within the grace
    period is killed rather than reported, so the replacement can bind (spec
    daemon "Force out a wedged daemon on an explicit restart").
    """
    info = _cli_client.discover()
    if info is None:
        return False

    # Verify the recorded pid IS a coffer daemon before signalling it.
    # A crashed daemon's pid can be recycled onto an unrelated process; we must
    # not SIGTERM a stranger. If it isn't ours, the daemon.json is stale —
    # clean it up instead of killing whoever now holds that pid.
    if not pid_is_coffer_daemon(info.pid):
        daemon_json_path().unlink(missing_ok=True)
        typer.echo("daemon pid is not a coffer daemon; cleaned up stale daemon.json")
        return True

    if force:
        outcome = stop_daemon_process(info.pid)
        if outcome == "killed":
            bootstrap.release_for(info.pid)
            typer.echo(
                f"daemon (pid {info.pid}) did not exit within "
                f"{GRACEFUL_STOP_SECONDS:.0f}s and was killed"
            )
            return True
        if outcome != "not_ours":
            _wait_for_daemon_json_gone(daemon_json_path(), timeout=1.0)
            bootstrap.release_for(info.pid)
            typer.echo("daemon stopped")
            return True
        # A Coffer daemon, but not provably this vault's: never forced.

    try:
        os.kill(info.pid, signal.SIGTERM)
    except ProcessLookupError:
        # already gone; just clean up daemon.json
        daemon_json_path().unlink(missing_ok=True)
        typer.echo("daemon already exited; cleaned up stale daemon.json")
        return True

    if _wait_for_daemon_json_gone(daemon_json_path(), timeout=GRACEFUL_STOP_SECONDS):
        typer.echo("daemon stopped")
        return True
    typer.echo(
        f"daemon did not exit within {GRACEFUL_STOP_SECONDS:.0f}s; "
        "coffer daemon restart replaces it by force",
        err=True,
    )
    raise typer.Exit(1)


@app.command("stop")
def stop() -> None:
    """Send SIGTERM to the running daemon and wait for it to exit."""
    if not _stop_daemon():
        typer.echo("daemon not running", err=True)
        raise typer.Exit(0)


@app.command("restart")
def restart() -> None:
    """Stop the running daemon (if any) and start a fresh one.

    The way a changed setting — a fixed port above all — actually takes effect,
    since a running daemon owns its bound socket and cannot move without one.
    """
    _stop_daemon(force=True)
    _start_daemon()


@app.command("status")
def status(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
    show_tasks: bool = typer.Option(
        False, "--tasks", help="Also list the running background tasks, counted by name"
    ),
) -> None:
    """Show whether the daemon is running, and the passes it is running right now.

    Reports its version, port and pid, the event loop's lag (p99 and
    maximum over the last few minutes), how many background tasks are running
    and how many have crashed, and the long passes in flight (kind, target,
    start time), oldest first. --tasks adds the running tasks counted by name
    (reconciler, seatalk-ws, coffer-mcp-http-upstream, ...), largest first.

    Read-only: when no daemon is running it says so and exits 3 instead of
    starting one.

    \f
    3 is both this CLI's "daemon unreachable" code and the LSB ``status`` code
    for "not running". The passes in flight are ``GET /upkeep/runs`` (spec
    resource-framework "Report the passes in flight in one cross-kind read"),
    oldest first, carried under ``passes_in_flight`` in ``--json``.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    # Probe first: client_or_exit() alone would spawn a daemon, and a status
    # query must never change what it reports on.
    if not _cli_client.daemon_is_running():
        if output_json:
            typer.echo(_json.dumps({"status": "stopped"}))
        else:
            typer.echo("status:  not running")
        raise typer.Exit(int(ExitCode.DAEMON_UNREACHABLE))
    try:
        c, info = _cli_client.client_or_exit(allow_setup=True, as_json=output_json)
    except _cli_client.ClientUnavailable as e:
        _io.fail(e.code, e.message, e.exit_code, as_json=output_json, details=e.details)
    with c:
        r = c.get("/daemon/status")
        _cli_client.check(r, verbose=verbose, as_json=output_json)
        data = r.json()
        setup = _cli_client.waiting_for_git(data)
        runs: list[dict[str, Any]] = []
        # A daemon waiting for git runs no passes and refuses the route.
        if setup is None:
            r = c.get("/upkeep/runs")
            _cli_client.check(r, verbose=verbose, as_json=output_json)
            runs = r.json()["runs"]
    others = other_daemons_of_our_vault(info.pid)
    if output_json:
        typer.echo(
            _json.dumps(
                {
                    **data,
                    "port": info.port,
                    "pid": info.pid,
                    "passes_in_flight": runs,
                    "other_daemon_pids": others,
                }
            )
        )
        return
    typer.echo(f"status:  {data['status']}")
    typer.echo(f"version: {data['version']}")
    typer.echo(f"port:    {info.port}")
    typer.echo(f"pid:     {info.pid}")
    if others:
        # One daemon serves a vault; any other daemon process of this vault is
        # a start still booting or queued, or a stray (spec daemon "Keep
        # exactly one daemon per vault").
        typer.echo(f"other daemon processes for this vault: {', '.join(map(str, others))}")
    for line in _runtime_lines(data.get("runtime")):
        typer.echo(line)
    if show_tasks:
        for line in _task_lines(data.get("runtime")):
            typer.echo(line)
    if setup is not None:
        typer.echo("")
        _cli_client.print_waiting_for_git(setup)
        return
    typer.echo("")
    typer.echo("passes in flight:")
    if not runs:
        typer.echo("  no pass is running")
    for run in runs:
        typer.echo(f"  {run['kind']:<10} {run['name']}  (started {run['started_at']})")


def _task_lines(runtime: dict[str, Any] | None) -> list[str]:
    """The running tasks by name, largest count first."""
    counts: dict[str, int] = (runtime or {}).get("tasks_by_name") or {}
    if not counts:
        return []
    width = max(len(name) for name in counts)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [f"         {name:<{width}}  {count}" for name, count in ordered]


def _runtime_lines(runtime: dict[str, Any] | None) -> list[str]:
    """The loop-lag and task-crash lines, or none from a daemon that reports neither."""
    if not runtime:
        return []
    p99 = runtime.get("loop_lag_p99_ms")
    window = int(runtime.get("loop_lag_window_seconds") or 0)
    lag = (
        "no sample yet" if p99 is None else f"p99 {p99:g} ms, max {runtime['loop_lag_max_ms']:g} ms"
    )
    lines = [
        f"loop lag: {lag} (last {window}s)",
        f"tasks:   {runtime['tasks_running']} running, {runtime['task_crashes']} crashed",
    ]
    last = runtime.get("last_crash")
    if last:
        lines.append(f"         last crash: {last['task']} ({last['error']}) at {last['at']}")
    return lines
