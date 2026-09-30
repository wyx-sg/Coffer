"""An approved key reaches the running proxy without a restart (spec
provider-switching "Push the proxy an approved key without a restart").

The whole daemon runs in-process over a throwaway ``HOME``; its supervisor is
attached to a real proxy app on a loopback port (the way it re-attaches to a
running proxy through ``proxy.json``), and the connection points at a fake
upstream that records the key each request carries. Nothing is restarted
between the key's rotation, its approval and the next request.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Callable, Iterator

import httpx
import pytest

from coffer.infrastructure.model_proxy.info import ProxyInfo
from coffer.surfaces.http.proxy_dependencies import get_proxy_facade
from tests.integration.model_proxy.conftest import CONTROL, Proxy
from tests.integration.model_proxy.harness import FakeUpstream, ServerThread, wait_for
from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon

BODY = b'{"model":"m1","max_tokens":8,"messages":[]}'


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


def _attach(d: BoundaryDaemon, proxy: Proxy) -> None:
    """Point the daemon's supervisor at ``proxy``, as a re-attach would."""
    # The facade's refresh is the wiring's own, so it leads to the supervisor.
    wiring = get_proxy_facade().refresh.__self__  # type: ignore[attr-defined]
    wiring.supervisor._info = ProxyInfo(
        port=proxy.server.port,
        pid=os.getpid(),
        started_at="2026-09-30T00:00:00Z",
        version="test",
        control_token=CONTROL,
    )


def _send(proxy: Proxy, token: str) -> httpx.Response:
    return proxy.client.post(
        "/anthropic/v1/messages",
        content=BODY,
        headers={"x-api-key": token, "anthropic-version": "2023-06-01"},
    )


def _keys(up: FakeUpstream) -> list[str | None]:
    return [r.header("x-api-key") for r in up.requests]


@pytest.mark.acceptance(
    spec="provider-switching", scenario="an approved key reaches the running proxy"
)
def test_an_approved_key_reaches_the_running_proxy(
    daemon: BoundaryDaemon,
    proxy: Proxy,
    upstreams: Callable[[], tuple[FakeUpstream, ServerThread]],
) -> None:
    d = daemon
    first_up, first = upstreams()
    second_up, second = upstreams()
    config_dir = d.home / ".claude"
    config_dir.mkdir(parents=True, exist_ok=True)
    agent = d.client.post(
        "/api/v1/agents",
        json={"type": "claude_code", "name": "claude-code", "config_dir": str(config_dir)},
    )
    assert agent.status_code == 201, agent.text
    agent_uid = agent.json()["uid"]
    created = d.client.post(
        "/api/v1/providers",
        json={
            "name": "gw",
            "protocol": "anthropic",
            "base_url": first.base,
            "secret_value": "sk-first-key",
        },
    )
    assert created.status_code == 201, created.text
    uid = created.json()["uid"]
    assert d.client.post(f"/api/v1/providers/{uid}/activate").status_code == 200
    _attach(d, proxy)
    # Minting the agent's token pushes the proxy its state before answering.
    token = d.client.get(f"/api/v1/proxy/tokens/{agent_uid}").json()["token"]

    assert _send(proxy, token).status_code == 200
    assert _keys(first_up) == ["sk-first-key"]

    # A new key for a key in use waits; the proxy keeps sending the old one.
    rotated = d.client.patch(f"/api/v1/providers/{uid}", json={"secret_value": "sk-second-key"})
    assert rotated.status_code == 200, rotated.text
    assert _send(proxy, token).status_code == 200
    assert _keys(first_up)[-1] == "sk-first-key"

    [replace] = [a for a in d.pending() if a["op"] == "replace_value"]
    d.approve(replace["id"])

    def sent_new_key() -> bool:
        _send(proxy, token)
        return _keys(first_up)[-1] == "sk-second-key"

    assert wait_for(sent_new_key, timeout=5.0), _keys(first_up)

    # A new base URL waits too: until approved the proxy holds no key for it,
    # and once approved the next request goes there with the key.
    moved = d.client.patch(f"/api/v1/providers/{uid}", json={"base_url": second.base})
    assert moved.status_code == 200, moved.text
    [bind] = [a for a in d.pending(destination_uid=uid) if second.base in (a["target"] or "")]
    assert wait_for(lambda: _send(proxy, token).status_code != 200, timeout=5.0)
    assert second_up.requests == []
    d.approve(bind["id"])

    def reached_second() -> bool:
        return _send(proxy, token).status_code == 200 and bool(second_up.requests)

    assert wait_for(reached_second, timeout=5.0)
    assert _keys(second_up)[-1] == "sk-second-key"
