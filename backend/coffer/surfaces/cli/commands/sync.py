"""``coffer sync`` — the Sync page: remote, rounds, machines and conflicts.

Spec vault-sync. A round runs in the daemon; ``sync run`` waits for the one it
starts, and ``sync wait`` waits for a round already running (a scheduled one,
or one another surface started) and prints how it ended. The master key's
commands are ``coffer secret key-*``: the key is the secret store's.
"""

from __future__ import annotations

import time

import typer

from coffer.domain.sync.stops import Answer
from coffer.surfaces.cli import _io
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli._route_command import Q, RouteCommand, mount
from coffer.surfaces.cli.groups import group
from coffer.surfaces.cli.registry import maps

_UI = "Sync · "
_PATH = (Q("path", "A path under the vault"),)
#: The answers ``POST /sync/stop/files/answer`` accepts, from the domain's enum.
ANSWERS = " | ".join(a.value for a in Answer)

SPECS = [
    RouteCommand(
        "sync status",
        "GET",
        "/sync/status",
        _UI + "status",
        "The remote, the last and next round, what waits, and what needs you.",
    ),
    RouteCommand(
        "sync run",
        "POST",
        "/sync/run",
        _UI + "Sync now",
        "Run one round now and print how it ended (waits for it).",
    ),
    RouteCommand(
        "sync continue",
        "POST",
        "/sync/continue",
        _UI + "Continue",
        "Continue a round that stopped for you.",
    ),
    RouteCommand(
        "sync runs",
        "GET",
        "/sync/runs",
        _UI + "History",
        "Every round this machine ran, newest first.",
        query=(Q("limit", kind=int), Q("cursor")),
    ),
    RouteCommand(
        "sync run-diff",
        "GET",
        "/sync/runs/{run_id}/diff",
        _UI + "a round · a file's diff",
        "What a round changed in one file.",
        query=(*_PATH, Q("side")),
    ),
    RouteCommand(
        "sync rollback-plan",
        "GET",
        "/sync/runs/{run_id}/rollback-plan",
        _UI + "a round · Roll back (review)",
        "What rolling a round back would change.",
    ),
    RouteCommand(
        "sync rollback",
        "POST",
        "/sync/runs/{run_id}/rollback",
        _UI + "a round · Roll back",
        "Roll a round back.",
    ),
    RouteCommand(
        "sync remote set",
        "PUT",
        "/sync/remote",
        _UI + "Set up · remote",
        "Set the remote. Body: url, branch, secret_ref, include_secret, enabled, interval_seconds.",
        body=True,
        pending=True,
    ),
    RouteCommand(
        "sync remote check",
        "POST",
        "/sync/remote/check",
        _UI + "Set up · Check",
        "Check a remote before saving it. Body: url, branch, secret_ref.",
        body=True,
    ),
    RouteCommand(
        "sync remote delete",
        "DELETE",
        "/sync/remote",
        _UI + "Stop syncing",
        "Forget the remote (the local vault stays).",
    ),
    RouteCommand(
        "sync remote restore",
        "POST",
        "/sync/remote/restore",
        _UI + "Restore from the remote",
        "Rebuild the remote from this machine's vault.",
    ),
    RouteCommand(
        "sync join-preview",
        "GET",
        "/sync/join/preview",
        _UI + "Join · review",
        "What joining the remote's vault would change here.",
    ),
    RouteCommand("sync join", "POST", "/sync/join", _UI + "Join", "Join the remote's vault."),
    RouteCommand(
        "sync join-choices",
        "GET",
        "/sync/join-choices",
        _UI + "Join · choices",
        "Files where this machine and the remote differ on joining.",
    ),
    RouteCommand(
        "sync join-choose",
        "POST",
        "/sync/join-choices",
        _UI + "Join · choose",
        "Choose a side per file. Body: choices.",
        body=True,
    ),
    RouteCommand(
        "sync join-discard",
        "POST",
        "/sync/join-choices/discard",
        _UI + "Join · discard this machine's file",
        "Body: path.",
        body=True,
    ),
    RouteCommand(
        "sync join-handoff",
        "POST",
        "/sync/join-choices/handoff",
        _UI + "Join · Ask an agent",
        "The prompt that hands the choices to an agent. Body: paths, agent.",
        body=True,
    ),
    RouteCommand(
        "sync stop",
        "GET",
        "/sync/stop",
        _UI + "a round that stopped",
        "Why the round stopped and what it asks.",
    ),
    RouteCommand(
        "sync file-versions",
        "GET",
        "/sync/stop/files/versions",
        _UI + "a conflicting file's versions",
        "Both versions of a file.",
        query=_PATH,
    ),
    RouteCommand(
        "sync file-answer",
        "POST",
        "/sync/stop/files/answer",
        _UI + "a conflicting file · keep one",
        f"Answer for one file. Body: path, answer ({ANSWERS}); edited keeps the "
        "copy you resolved in your editor.",
        body=True,
    ),
    RouteCommand(
        "sync file-discard",
        "POST",
        "/sync/stop/files/discard",
        _UI + "a conflicting file · discard mine",
        "Body: path.",
        body=True,
    ),
    RouteCommand(
        "sync stop-handoff",
        "POST",
        "/sync/stop/handoff",
        _UI + "Ask an agent to resolve",
        "The prompt that hands resolving to an agent. Body: paths, agent.",
        body=True,
    ),
    RouteCommand(
        "sync hold-diff",
        "GET",
        "/sync/hold/diff",
        _UI + "a held change · diff",
        "A change held for confirmation, one file.",
        query=_PATH,
    ),
    RouteCommand(
        "sync hold-confirm",
        "POST",
        "/sync/hold/confirm",
        _UI + "held · Apply",
        "Apply the held changes.",
    ),
    RouteCommand(
        "sync hold-restore",
        "POST",
        "/sync/hold/restore",
        _UI + "held · Restore",
        "Put back what the held round would delete.",
    ),
    RouteCommand(
        "sync pending-diff",
        "GET",
        "/sync/pending/diff",
        _UI + "waiting · diff",
        "A local change waiting to be pushed, one file.",
        query=_PATH,
    ),
    RouteCommand(
        "sync plaintext-context",
        "GET",
        "/sync/plaintext/context",
        _UI + "a plaintext secret · where",
        "The lines around a plaintext secret.",
        query=(*_PATH, Q("line", kind=int)),
    ),
    RouteCommand(
        "sync push-anyway",
        "POST",
        "/sync/plaintext/push-anyway",
        _UI + "a plaintext secret · Push anyway",
        "Push although a file holds plaintext.",
    ),
    RouteCommand(
        "sync machines", "GET", "/sync/machines", _UI + "Machines", "Every machine in the vault."
    ),
    RouteCommand(
        "sync machine rename",
        "PATCH",
        "/sync/machines/self",
        _UI + "Machines · rename",
        "Rename this machine. Body: name.",
        body=True,
    ),
    RouteCommand(
        "sync machine retire",
        "DELETE",
        "/sync/machines/{machine_id}",
        _UI + "Machines · Retire",
        "Retire a machine.",
    ),
    RouteCommand(
        "sync machine restore",
        "POST",
        "/sync/machines/{machine_id}/restore",
        _UI + "Machines · Restore",
        "Bring a retired machine back.",
    ),
    RouteCommand(
        "sync vault-move",
        "POST",
        "/sync/vault/move",
        _UI + "Move the vault",
        "Move the vault's files out of a synchronised folder. Body: to.",
        body=True,
    ),
]

mount(SPECS)

syncs = group("sync")


@syncs.command("wait")
@maps("sync wait", ("GET", "/sync/status"), ui=_UI + "a round in progress")
def wait(
    timeout: float = typer.Option(600.0, "--timeout", help="Seconds to wait"),
    as_json: bool = _io.json_option(),
) -> None:
    """Wait for the round now running to end and print the status (exit 13 on timeout)."""
    deadline = time.monotonic() + timeout
    while True:
        status = _io.call("GET", "/sync/status", as_json=as_json)
        if not status.get("running_since"):
            _io.emit(status, as_json=as_json)
            return
        if time.monotonic() >= deadline:
            _io.fail(
                "CLI_WAIT_TIMEOUT",
                f"a round is still running after {timeout:g}s",
                ExitCode.WAIT_TIMEOUT,
                as_json=as_json,
            )
        time.sleep(1.0)
