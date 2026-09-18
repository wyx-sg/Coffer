"""ChannelRuntime._reconcile_websockets: hold/drop/retry per channel (spec channels/seatalk FR-004).

Drives the reconcile step directly with the recording stub controller and a fake
materialize — no SDK, no socket, no DB. The real connector's threading lives in
test_seatalk_ws.py; what is under test here is which channels are wanted and
which credentials reach them.
"""

from __future__ import annotations

from typing import Any

from coffer.application.channel.runtime import ChannelRuntime

from .conftest import StubWebSocketController, channel_row

#: The uid ``channel_row`` mints for the channel named "st". The controllers
#: are keyed by uid, not by name (``runtime_supervision``).
_ST = "uid-of-st"


async def _materialize(refs: dict[str, str]) -> dict[str, str]:
    return {k: f"secret::{v}" for k, v in refs.items()}


def _runtime(websockets: Any, *, materialize: Any = _materialize) -> ChannelRuntime:
    # _reconcile_websockets only touches the controller, materialize and stop
    # state, so the adapter machinery can be left as None.
    return ChannelRuntime(
        resources=None,  # type: ignore[arg-type]
        adapter_factory=None,  # type: ignore[arg-type]
        processor=None,  # type: ignore[arg-type]
        pairing=None,  # type: ignore[arg-type]
        websockets=websockets,
        materialize=materialize,
    )


def _seatalk(delivery: str, *, app_id: str = "app-1") -> dict[str, object]:
    cfg: dict[str, object] = {
        "channel_type": "seatalk",
        "app_id": app_id,
        "app_secret_ref": "channel/st/app-secret",
        "delivery": delivery,
    }
    if delivery == "webhook":
        cfg["signing_secret_ref"] = "channel/st/sign"
    return cfg


async def test_holds_a_connection_for_a_websocket_channel_with_materialized_secret():
    ws = StubWebSocketController()
    rt = _runtime(ws)
    await rt._reconcile_websockets({"st": channel_row("st", _seatalk("websocket"))})
    assert ws.started == {_ST: ("app-1", "secret::channel/st/app-secret")}
    assert ws.running(_ST) is True


async def test_skips_webhook_and_telegram_channels():
    ws = StubWebSocketController()
    rt = _runtime(ws)
    await rt._reconcile_websockets(
        {
            "st": channel_row("st", _seatalk("webhook")),
            "tg": channel_row(
                "tg", {"channel_type": "telegram", "bot_token_ref": "channel/tg/bot"}, id=2
            ),
        }
    )
    assert ws.started == {}


async def test_a_seatalk_config_without_delivery_is_a_webhook_channel():
    """No migration restates the stored reality, so the absent key must mean
    webhook here exactly as it does in the domain model."""
    ws = StubWebSocketController()
    rt = _runtime(ws)
    await rt._reconcile_websockets(
        {"st": channel_row("st", {"channel_type": "seatalk", "app_id": "a", "app_secret_ref": "r"})}
    )
    assert ws.started == {}


async def test_stops_the_connection_when_the_channel_switches_back_to_webhook():
    ws = StubWebSocketController()
    rt = _runtime(ws)
    await rt._reconcile_websockets({"st": channel_row("st", _seatalk("websocket"))})
    assert ws.running(_ST) is True
    await rt._reconcile_websockets({"st": channel_row("st", _seatalk("webhook"))})
    assert _ST in ws.stopped
    assert ws.running(_ST) is False


async def test_stops_the_connection_when_the_channel_is_disabled_or_deleted():
    ws = StubWebSocketController()
    rt = _runtime(ws)
    await rt._reconcile_websockets({"st": channel_row("st", _seatalk("websocket"))})
    await rt._reconcile_websockets({})  # disabled → absent from desired
    assert ws.running(_ST) is False


async def test_a_steady_state_does_not_touch_the_credential_store_again():
    calls: list[dict[str, str]] = []

    async def counting(refs: dict[str, str]) -> dict[str, str]:
        calls.append(dict(refs))
        return {k: f"secret::{v}" for k, v in refs.items()}

    ws = StubWebSocketController()
    rt = _runtime(ws, materialize=counting)
    desired = {"st": channel_row("st", _seatalk("websocket"))}
    await rt._reconcile_websockets(desired)
    await rt._reconcile_websockets(desired)
    await rt._reconcile_websockets(desired)
    assert len(calls) == 1


async def test_a_changed_app_id_reconnects():
    ws = StubWebSocketController()
    rt = _runtime(ws)
    await rt._reconcile_websockets({"st": channel_row("st", _seatalk("websocket"))})
    await rt._reconcile_websockets({"st": channel_row("st", _seatalk("websocket", app_id="app-2"))})
    assert ws.started == {_ST: ("app-2", "secret::channel/st/app-secret")}


async def test_start_failure_is_latched_not_raised():
    ws = StubWebSocketController(fail=True)
    rt = _runtime(ws)
    # e.g. the SDK is missing — must not raise out of the reconcile tick.
    await rt._reconcile_websockets({"st": channel_row("st", _seatalk("websocket"))})
    assert ws.running(_ST) is False


async def test_materialize_failure_is_latched_not_raised():
    async def boom(refs: dict[str, str]) -> dict[str, str]:
        raise RuntimeError("store down")

    ws = StubWebSocketController()
    rt = _runtime(ws, materialize=boom)
    await rt._reconcile_websockets({"st": channel_row("st", _seatalk("websocket"))})
    assert ws.started == {}


async def test_no_controller_wired_is_a_no_op():
    rt = _runtime(None)
    await rt._reconcile_websockets({"st": channel_row("st", _seatalk("websocket"))})
    assert rt.websocket_state(_ST) is None


async def test_websocket_state_passes_the_controller_answer_through():
    ws = StubWebSocketController()
    rt = _runtime(ws)
    await rt._reconcile_websockets({"st": channel_row("st", _seatalk("websocket"))})
    assert rt.websocket_state(_ST) == ("connecting", None)
    ws.set_state(_ST, "kicked", "another process holds it")
    assert rt.websocket_state(_ST) == ("kicked", "another process holds it")
    assert rt.websocket_state("unknown") is None
