"""Fixtures: a live proxy app, fake upstreams, and a state builder."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from coffer.domain.model_proxy.state import (
    CONTROL_TOKEN_HEADER,
    ProxyAgent,
    ProxyMember,
    ProxyRoute,
    ProxyState,
    UpstreamAuth,
    token_digest,
)
from coffer.domain.usage.records import Wire
from coffer.infrastructure.model_proxy.app import ModelProxyApp
from coffer.infrastructure.model_proxy.spool import UsageSpool
from tests.integration.model_proxy.harness import FakeUpstream, ServerThread, wait_for

CONTROL = "control-token-for-tests"
CLAUDE_TOKEN = "local-claude-token-" + "a" * 40
CODEX_TOKEN = "local-codex-token-" + "b" * 40


def member(
    up: ServerThread | str,
    uid: str,
    *,
    auth: UpstreamAuth = UpstreamAuth.ANTHROPIC,
    key: str | None = None,
    local: bool = False,
) -> ProxyMember:
    root = up if isinstance(up, str) else up.base
    return ProxyMember(
        connection_uid=uid,
        connection_name=f"conn {uid}",
        upstream_root=root,
        auth=auth,
        key=key if key is not None or auth is UpstreamAuth.NONE else f"sk-real-{uid}",
        local=local,
    )


def state(
    anthropic: ProxyMember | None = None,
    openai: ProxyMember | None = None,
    *,
    revision: int = 1,
    claude_token: str = CLAUDE_TOKEN,
    served: list[str] | None = None,
    fallback: str | None = None,
    tiers: dict[str, str] | None = None,
) -> ProxyState:
    routes = []
    if anthropic is not None:
        routes.append(
            ProxyRoute(
                agent_uid="agent-claude",
                wire=Wire.ANTHROPIC,
                member=anthropic,
                served_models=served or [],
                fallback_model=fallback,
                tier_fallbacks=tiers or {},
            )
        )
    if openai is not None:
        routes.append(
            ProxyRoute(
                agent_uid="agent-codex",
                wire=Wire.OPENAI,
                member=openai,
                served_models=served or [],
                fallback_model=fallback,
                tier_fallbacks=tiers or {},
            )
        )
    return ProxyState(
        revision=revision,
        agents=[
            ProxyAgent(
                agent_uid="agent-claude",
                agent_type="claude-code",
                token_sha256=token_digest(claude_token),
            ),
            ProxyAgent(
                agent_uid="agent-codex", agent_type="codex", token_sha256=token_digest(CODEX_TOKEN)
            ),
        ],
        routes=routes,
    )


@dataclass
class Proxy:
    app: ModelProxyApp
    server: ServerThread
    client: httpx.Client
    spool_dir: Path

    @property
    def base(self) -> str:
        return self.server.base

    def push(self, st: ProxyState) -> None:
        r = self.client.put(
            "/_coffer/state", content=st.model_dump_json(), headers={CONTROL_TOKEN_HEADER: CONTROL}
        )
        assert r.status_code == 200, r.text

    def records(self, count: int, timeout: float = 5.0) -> list[dict[str, object]]:
        """Wait for ``count`` finalized records and return them in order."""

        def _read() -> list[dict[str, object]]:
            out: list[dict[str, object]] = []
            for f in sorted(self.spool_dir.glob("*.jsonl")):
                out += [json.loads(line) for line in f.read_text().splitlines() if line]
            return out

        wait_for(lambda: len(_read()) >= count, timeout)
        return _read()


@pytest.fixture
def upstreams() -> Iterator[Callable[[], tuple[FakeUpstream, ServerThread]]]:
    started: list[ServerThread] = []

    def _make() -> tuple[FakeUpstream, ServerThread]:
        up = FakeUpstream()
        server = ServerThread(up, lifespan="off").__enter__()
        started.append(server)
        return up, server

    yield _make
    for server in started:
        server.__exit__()


@pytest.fixture
def proxy(tmp_path: Path) -> Iterator[Proxy]:
    spool_dir = tmp_path / "spool"
    drained: list[bool] = []
    app = ModelProxyApp(
        control_token=CONTROL,
        version="test",
        started_at="2026-09-30T00:00:00Z",
        spool=UsageSpool(spool_dir, max_age=0.05),
        on_drained=lambda: drained.append(True),
    )
    app.drained = drained  # type: ignore[attr-defined]
    with (
        ServerThread(app) as server,
        httpx.Client(base_url=server.base, trust_env=False, timeout=30) as client,
    ):
        yield Proxy(app, server, client, spool_dir)


def claude_headers(token: str = CLAUDE_TOKEN, **extra: str) -> dict[str, str]:
    return {
        "x-api-key": token,
        "authorization": f"Bearer {token}",
        "anthropic-version": "2023-06-01",
        **extra,
    }
