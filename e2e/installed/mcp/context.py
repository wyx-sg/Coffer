"""What every MCP case shares: the run, the wire, the fixtures and their ledgers."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from e2e.installed._common.recorder import CaseRecorder
from e2e.installed._common.run import Run
from e2e.installed.mcp.wire import Wire

UPSTREAM = Path(__file__).with_name("upstream.py")
#: Every stdio fixture runs under the runner's own interpreter, which has the MCP SDK.
PYTHON = sys.executable


@dataclass
class Ctx:
    run: Run
    wire: Wire
    canary: str
    servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: Ports of the runner's own HTTP fixtures, by tag.
    http: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def rec(self) -> CaseRecorder:
        return self.run.recorder

    @property
    def ledger_dir(self) -> Path:
        return self.run.fixture_dir

    def ledger(self, tag: str) -> Path:
        return self.ledger_dir / f"{tag}.jsonl"

    # --- fixtures ---------------------------------------------------------------

    def stdio(
        self,
        tag: str,
        mode: str = "basic",
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> dict[str, Any]:
        """A stdio transport the target spawns: this suite's fixture under ``tag``."""
        transport: dict[str, Any] = {
            "type": "stdio",
            "command": PYTHON,
            "args": [
                str(UPSTREAM),
                "--tag",
                tag,
                "--mode",
                mode,
                "--ledger",
                str(self.ledger(tag)),
            ],
            "env": dict(env or {}),
        }
        if cwd is not None:
            transport["cwd"] = str(cwd)
        return transport

    async def start_http(self, tag: str, *, stateful: bool = False) -> dict[str, int]:
        """Start one of the runner's own HTTP fixtures; returns its two ports."""
        ready = self.run.fixture_dir / f"{tag}.ready"
        command = [PYTHON, str(UPSTREAM), "--transport", "http", "--tag", tag]
        command += ["--ledger", str(self.ledger(tag)), "--ready", str(ready)]
        if stateful:
            command.append("--stateful")
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/"),
            "QA_CANARY_EXPECTED": self.canary,
        }
        proc = self.run.processes.spawn(
            command, tag, self.run.out / f"{tag}.log", env=env, cwd=self.run.out
        )
        for _ in range(150):
            if ready.exists() and ready.read_text():
                break
            if proc.poll() is not None:
                raise RuntimeError(f"HTTP fixture {tag} exited with {proc.returncode}")
            await asyncio.sleep(0.1)
        ports: dict[str, int] = json.loads(ready.read_text())
        self.http[tag] = ports
        return ports

    async def register(self, name: str, transport: dict[str, Any], **config: Any) -> dict[str, Any]:
        reply = await self.run.api.register_server(name, transport, **config)
        if reply.status != 201:
            raise RuntimeError(f"registering {name}: HTTP {reply.status} {reply.body}")
        self.servers[name] = reply.json
        return reply.json

    def uid(self, name: str) -> str:
        return str(self.servers[name]["uid"])

    async def capabilities(self, name: str, want: str = "echo") -> list[str]:
        """The server's tool keys once discovery has seen ``want`` (spawns it once)."""
        path = f"/api/v1/resources/mcp_server/{self.uid(name)}/capabilities"
        keys: list[str] = []
        for _ in range(30):
            reply = await self.run.client.request("GET", path, timeout=30)
            keys = [str(t.get("original_name")) for t in reply.json.get("tools", [])]
            if want in keys:
                break
            await asyncio.sleep(0.5)
        return keys

    async def expose(self, name: str, tools: list[str], mode: str) -> int:
        """Set the tools' exposure. The route knows a server's tools from the list
        discovery saved, which can land a moment after a live capabilities read,
        so a 404 is retried for a few seconds."""
        path = f"/api/v1/resources/mcp_server/{self.uid(name)}/tools/exposure"
        for _ in range(40):
            reply = await self.run.client.request("PATCH", path, {"tools": tools, "mode": mode})
            if reply.status != 404:
                break
            await asyncio.sleep(0.25)
        return reply.status

    async def toggle(self, name: str, tool: str, enabled: bool) -> int:
        verb = "enable" if enabled else "disable"
        path = f"/api/v1/resources/mcp_server/{self.uid(name)}/capabilities/tool/{verb}"
        reply = await self.run.client.request("POST", path, {"capability_key": tool})
        return reply.status

    async def invocations(self, name: str, status: str | None = None) -> dict[str, Any]:
        query = "?limit=50" + (f"&status={status}" if status else "")
        path = f"/api/v1/resources/mcp_server/{self.uid(name)}/invocations{query}"
        return (await self.run.client.request("GET", path)).json

    # --- ledgers ----------------------------------------------------------------

    def events(self, tag: str, event: str | None = None, name: str | None = None) -> list[dict]:
        path = self.ledger(tag)
        if not path.exists():
            return []
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        return [
            r
            for r in rows
            if (event is None or r.get("event") == event)
            and (name is None or r.get("name") == name)
        ]

    def count(self, tag: str, event: str = "start", name: str | None = None) -> int:
        return len(self.events(tag, event, name))

    def note_pids(self, tag: str) -> set[int]:
        """Remember every child the target spawned for ``tag``: it must be gone at the end."""
        pids = {int(r["pid"]) for r in self.events(tag, "process-start")}
        self.run.fixture_pids.update(pids)
        return pids

    async def wait_count(
        self,
        tag: str,
        target: int,
        event: str = "start",
        name: str | None = None,
        timeout: float = 10,
    ) -> int:
        deadline = asyncio.get_running_loop().time() + timeout
        while (
            self.count(tag, event, name) < target and asyncio.get_running_loop().time() < deadline
        ):
            await asyncio.sleep(0.05)
        return self.count(tag, event, name)


async def phase(ctx: Ctx, area: str, body: Callable[[Ctx], Awaitable[None]]) -> None:
    """Run one area's cases; an exception there is that area's FAIL, not the run's end."""
    ctx.rec.area = area
    try:
        await body(ctx)
    except Exception as exc:
        trace = ctx.run.out / f"harness-{area}.txt"
        trace.write_text(ctx.run.redactor.text(traceback.format_exc()))
        ctx.rec.record(
            f"{area}.harness",
            f"the {area} cases ran to their end",
            expected="no exception in the case code",
            actual={"error": f"{type(exc).__name__}: {exc}", "trace": trace.name},
            ok=False,
        )
