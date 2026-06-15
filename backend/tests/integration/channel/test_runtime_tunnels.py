"""ChannelRuntime._reconcile_tunnels: managed-tunnel start/stop/retry.

Drives the reconcile step directly with a recording fake tunnel and a fake
materialize — no subprocess, no DB. TunnelController's real spawn lives in
test_tunnel_spawn.py.
"""

from __future__ import annotations

from typing import Any

from coffer.application.channel.runtime import ChannelRuntime


class _FakeTunnel:
    def __init__(self, *, fail: bool = False) -> None:
        self.started: dict[str, str] = {}
        self.stopped: list[str] = []
        self._active: set[str] = set()
        self._fail = fail

    def running(self, name: str) -> bool:
        return name in self._active

    def active(self) -> set[str]:
        return set(self._active)

    async def ensure_running(self, name: str, token: str) -> None:
        if self._fail:
            raise RuntimeError("cloudflared missing")
        self.started[name] = token
        self._active.add(name)

    async def ensure_stopped(self, name: str) -> None:
        self.stopped.append(name)
        self._active.discard(name)

    async def dispose(self) -> None:
        self._active.clear()


async def _materialize(refs: dict[str, str]) -> dict[str, str]:
    return {k: f"token::{v}" for k, v in refs.items()}


def _runtime(tunnel: Any, *, materialize: Any = _materialize) -> ChannelRuntime:
    # _reconcile_tunnels only touches tunnel/materialize/stop state, so the
    # adapter machinery can be left as None.
    return ChannelRuntime(
        resources=None,  # type: ignore[arg-type]
        adapter_factory=None,  # type: ignore[arg-type]
        processor=None,  # type: ignore[arg-type]
        pairing=None,  # type: ignore[arg-type]
        tunnel=tunnel,
        materialize=materialize,
    )


def _seatalk(token_ref: str | None) -> dict[str, object]:
    cfg: dict[str, object] = {"channel_type": "seatalk", "signing_secret_ref": "s"}
    if token_ref is not None:
        cfg["tunnel_token_ref"] = token_ref
    return cfg


async def test_starts_tunnel_for_managed_channel_with_materialized_token():
    tunnel = _FakeTunnel()
    rt = _runtime(tunnel)
    await rt._reconcile_tunnels({"st": (1, _seatalk("channel/st/tunnel-token"))})
    assert tunnel.started == {"st": "token::channel/st/tunnel-token"}
    assert tunnel.running("st") is True


async def test_skips_channel_without_token_ref():
    tunnel = _FakeTunnel()
    rt = _runtime(tunnel)
    await rt._reconcile_tunnels(
        {"st": (1, _seatalk(None)), "tg": (2, {"channel_type": "telegram"})}
    )
    assert tunnel.started == {}


async def test_stops_tunnel_when_token_ref_removed():
    tunnel = _FakeTunnel()
    rt = _runtime(tunnel)
    await rt._reconcile_tunnels({"st": (1, _seatalk("channel/st/tunnel-token"))})
    assert tunnel.running("st") is True
    # token-ref cleared (or channel disabled → absent from desired)
    await rt._reconcile_tunnels({"st": (1, _seatalk(None))})
    assert "st" in tunnel.stopped
    assert tunnel.running("st") is False


async def test_spawn_failure_is_latched_not_raised():
    tunnel = _FakeTunnel(fail=True)
    rt = _runtime(tunnel)
    # cloudflared missing → must not raise out of the reconcile tick
    await rt._reconcile_tunnels({"st": (1, _seatalk("channel/st/tunnel-token"))})
    assert tunnel.running("st") is False


async def test_materialize_failure_is_latched_not_raised():
    async def boom(refs: dict[str, str]) -> dict[str, str]:
        raise RuntimeError("store down")

    tunnel = _FakeTunnel()
    rt = _runtime(tunnel, materialize=boom)
    await rt._reconcile_tunnels({"st": (1, _seatalk("channel/st/tunnel-token"))})
    assert tunnel.started == {}
