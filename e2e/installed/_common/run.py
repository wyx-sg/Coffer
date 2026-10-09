"""One suite run against the target: open, guard, clean up, verify, report.

``main`` is the whole lifecycle a suite plugs its cases into:

1. ``--out`` is checked (outside the repo, empty) before anything else.
2. The target is read from ``daemon.json`` and must answer ``ready``.
3. The sync guard runs before any write.
4. Every name the suite will create is reserved (refused if one exists).
5. The suite runs.
6. In ``finally``: created objects are deleted, owned processes stopped, and
   three cleanup cases are recorded — no ``qa-`` object left, no fixture
   process left (by this run's marker), the target daemon still the same
   process.

Exit codes: 0 every case passed or was reported BLOCKED/N/A, 1 a case failed,
2 a guard refused the run (nothing was written to the target).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from e2e.installed._common.coffer_api import CofferApi
from e2e.installed._common.http import DaemonClient
from e2e.installed._common.journal import ResourceJournal
from e2e.installed._common.processes import OwnedProcesses, processes_with_marker, wait_gone
from e2e.installed._common.recorder import CaseRecorder
from e2e.installed._common.redact import Redactor
from e2e.installed._common.sync_guard import check_sync_guard
from e2e.installed._common.target import (
    RefusedError,
    Target,
    add_common_arguments,
    checked_out_dir,
    read_target,
)


@dataclass
class Run:
    suite: str
    args: argparse.Namespace
    out: Path
    target: Target
    status: dict[str, Any]
    redactor: Redactor
    client: DaemonClient
    journal: ResourceJournal
    api: CofferApi
    recorder: CaseRecorder
    processes: OwnedProcesses = field(default_factory=OwnedProcesses)
    #: Child pids a suite expects gone once its resources are deleted.
    fixture_pids: set[int] = field(default_factory=set)
    header: dict[str, Any] = field(default_factory=dict)

    @property
    def fixture_dir(self) -> Path:
        """Where a suite keeps its fixtures' files (ledgers, ready files).

        Every fixture names a path under it on its command line, which makes
        :attr:`marker` match this run's fixtures and nothing else — not even
        the ``make`` or runner process, whose command lines name only ``--out``.
        """
        path = self.out / "fixtures"
        path.mkdir(exist_ok=True)
        return path

    @property
    def marker(self) -> str:
        return str(self.fixture_dir) + "/"

    def write_json(self, name: str, value: Any) -> Path:
        path = self.out / name
        path.write_text(json.dumps(self.redactor.value(value), indent=2, default=str))
        return path


Suite = Callable[[Run], Awaitable[None]]


def parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    add_common_arguments(p)
    return p


async def _open(args: argparse.Namespace, suite: str) -> Run:
    out = checked_out_dir(args.out)
    redactor = Redactor()
    target = read_target(args)
    redactor.add(target.token)
    client = DaemonClient(target, redactor, out / "transcript.jsonl")
    reply = await client.request("GET", "/api/v1/daemon/status")
    if reply.status != 200 or reply.json.get("status") != "ready":
        await client.aclose()
        raise RefusedError(
            f"target daemon on port {target.port} is not ready (HTTP {reply.status})"
        )
    if reply.json.get("pid") != target.pid:
        await client.aclose()
        raise RefusedError("daemon.json names another process than the one answering its port")
    journal = ResourceJournal(out)
    run = Run(
        suite=suite,
        args=args,
        out=out,
        target=target,
        status=reply.json,
        redactor=redactor,
        client=client,
        journal=journal,
        api=CofferApi(client, journal),
        recorder=CaseRecorder(out, redactor, suite),
    )
    run.write_json(
        "target.json",
        {
            "target": target.describe(reply.json),
            "runner": {
                "python": sys.version,
                "executable": sys.executable,
                "platform": platform.platform(),
                "started_at": datetime.now(UTC).isoformat(),
            },
        },
    )
    return run


async def _finish(run: Run) -> None:
    rec = run.recorder
    rec.area = "cleanup"
    failed = await run.journal.cleanup()
    leftovers = await run.api.qa_leftovers()
    run.journal.leftovers = leftovers
    run.journal.write()
    ours = {e.name for e in run.journal.entries}
    remaining = sorted(set(leftovers["mcp_servers"] + leftovers["secrets"]) & ours)
    rec.record(
        "cleanup.resources",
        "every qa- object this run created is gone",
        expected="each created object deleted (204/404) and none listed afterwards",
        actual={
            "created": len(run.journal.entries),
            "failed_deletes": [f"{e.kind} {e.name}: {e.error}" for e in failed],
            "still_listed": remaining,
            "other_qa_objects_untouched": sorted(
                set(leftovers["mcp_servers"] + leftovers["secrets"]) - ours
            ),
        },
        ok=not failed and not remaining,
    )
    owned = await run.processes.stop_all()
    gone_by_pid = await wait_gone(run.fixture_pids, 15)
    survivors: list[dict[str, Any]] = []
    for _ in range(30):
        survivors = processes_with_marker(run.marker)
        if not survivors:
            break
        await asyncio.sleep(0.5)
    rec.record(
        "cleanup.processes",
        "no fixture process outlives its resource",
        expected="every upstream child the target spawned for this run, and every process "
        "the runner started, has exited",
        actual={
            "owned": owned,
            "fixture_pids_seen": sorted(run.fixture_pids),
            "still_alive_by_pid": gone_by_pid,
            "still_alive_by_marker": survivors,
        },
        ok=not gone_by_pid and not survivors,
    )
    reply = await run.client.request("GET", "/api/v1/daemon/status")
    rec.record(
        "cleanup.daemon",
        "the target daemon is the same process, untouched",
        expected="status ready with the pid and start time the run began with",
        actual={
            "http": reply.status,
            "pid": reply.json.get("pid"),
            "started_at": reply.json.get("started_at"),
        },
        ok=reply.status == 200
        and reply.json.get("pid") == run.target.pid
        and reply.json.get("started_at") == run.status.get("started_at"),
    )


def main(
    description: str,
    suite_name: str,
    reserve: Iterable[tuple[str, str]],
    suite: Suite,
    argv: list[str] | None = None,
) -> int:
    args = parser(description).parse_args(argv)
    return asyncio.run(_main(args, suite_name, list(reserve), suite))


async def _main(
    args: argparse.Namespace, suite_name: str, reserve: list[tuple[str, str]], suite: Suite
) -> int:
    try:
        run = await _open(args, suite_name)
    except RefusedError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    refused: RefusedError | None = None
    started = False
    try:
        guard = await check_sync_guard(run.client, args.allow_sync_remote)
        run.write_json("guard.json", guard)
        await run.journal.reserve(reserve, run.api.exists)
        run.header["sync guard"] = json.dumps(guard)
        started = True
        await suite(run)
    except RefusedError as exc:
        refused = exc
    except Exception as exc:  # a harness bug still cleans up and reports
        run.recorder.area = "harness"
        run.recorder.record(
            "harness",
            "the suite ran to its end",
            expected="no exception escapes the suite",
            actual={"error": f"{type(exc).__name__}: {exc}"},
            ok=False,
        )
    finally:
        if started:
            await _finish(run)
        else:
            await run.processes.stop_all()
            await run.journal.cleanup()
        await run.client.aclose()
    if refused is not None:
        run.write_json("refused.json", {"refused": str(refused), "details": refused.details})
        print(f"REFUSED: {refused}", file=sys.stderr)
        return 2
    header = {
        "target": f"{run.target.base_url} pid {run.target.pid} version {run.status.get('version')}",
        "out": str(run.out),
        **run.header,
    }
    run.recorder.write(header)
    counts = run.recorder.counts()
    print(f"RESULT {json.dumps(counts)} → {run.out / 'summary.md'}", flush=True)
    return run.recorder.exit_code()
