"""SeaTalkWebSocketConnector + controller, driven by the fake SDK.

Real threads and a real event loop — the whole point of this module is the
boundary between them — with the fake ``seatalk_oapi_sdk`` standing in for a
package that cannot be installed in CI. The fake mirrors the real one's calling
order (handler inline on the listen thread, ack straight after it returns, kick
handler then ``KickError`` out of ``listen()``), so these tests pin the behaviour
that matters in production.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from typing import Any

import pytest

from coffer.infrastructure.channel.seatalk_sdk import SeaTalkSdkMissingError
from coffer.infrastructure.channel.seatalk_ws import SeaTalkWebSocketConnector
from coffer.infrastructure.channel.seatalk_ws_controller import SeaTalkWebSocketController

from .conftest import wait_until
from .fake_seatalk_sdk import (
    FakeSeaTalkSdk,
    build_fake_sdk,
    deliver,
    drop,
    envelope,
    hold,
    kick,
)


@pytest.fixture
def sdk() -> Iterator[FakeSeaTalkSdk]:
    handle = build_fake_sdk()
    handle.plan.append(hold())
    yield handle


class _Recorder:
    """Stands in for ChannelService.ingest_event."""

    def __init__(self, *, fail: bool = False) -> None:
        self.received: list[tuple[str, dict[str, Any]]] = []
        self._fail = fail

    async def __call__(self, name: str, payload: dict[str, Any]) -> None:
        if self._fail:
            raise RuntimeError("ingest blew up")
        self.received.append((name, payload))


def _connector(
    sdk: FakeSeaTalkSdk,
    ingest: Any,
    **kwargs: Any,
) -> SeaTalkWebSocketConnector:
    return SeaTalkWebSocketConnector(
        "st",
        "app-1",
        "app-secret",
        ingest=ingest,
        loader=lambda: sdk.module,
        # A real ladder would make this suite sleep for a minute; the shape is
        # what is under test, not the wall-clock values.
        backoff_initial=0.01,
        backoff_max=0.04,
        kick_backoff=60.0,
        join_timeout=2.0,
        **kwargs,
    )


@pytest.mark.acceptance(
    spec="channels", scenario="a websocket channel receives an event with no public url"
)
async def test_an_event_on_the_socket_reaches_ingest(sdk: FakeSeaTalkSdk) -> None:
    body = envelope()
    sdk.plan[:] = [deliver(body), hold()]
    ingest = _Recorder()
    connector = _connector(sdk, ingest)
    await connector.start()
    try:
        await wait_until(lambda: ingest.received, message="no event reached ingest")
        name, payload = ingest.received[0]
        assert name == "st"
        # The raw envelope, unchanged: the adapter seam is transport-agnostic, so
        # nothing on this path parses or reshapes the event.
        assert payload == body
        assert connector.state() == ("connected", None)
        # The register handshake used the app's own credentials — no signing
        # secret and no public URL are involved anywhere in this flow.
        assert sdk.connects == [("app-1", "app-secret")]
    finally:
        await connector.stop()


async def test_the_dispatcher_acks_the_event_the_handler_did_not_block_on(
    sdk: FakeSeaTalkSdk,
) -> None:
    """Our handler must return immediately: the SDK acks as soon as it does."""
    sdk.plan[:] = [deliver(envelope(), callback_id="cb-42"), hold()]
    ingest = _Recorder()
    connector = _connector(sdk, ingest)
    await connector.start()
    try:
        await wait_until(lambda: sdk.acks, message="the event was never acked")
        assert sdk.acks == ["cb-42"]
    finally:
        await connector.stop()


async def test_the_sdks_printing_handlers_are_silenced(sdk: FakeSeaTalkSdk) -> None:
    """The SDK defaults two handlers to ``print()`` — they must not survive.

    Its default envelope handler dumps every frame's full JSON, message bodies
    and all, and its invalid-frame handler prints the raw payload. The daemon's
    stdout is its log file, so leaving either in place would write every private
    message the owner receives into ~/.coffer/logs.
    """
    sdk.plan[:] = [hold()]
    connector = _connector(sdk, _Recorder())
    await connector.start()
    try:
        await wait_until(lambda: sdk.connections == 1, message="never connected")
        dispatcher = sdk.dispatchers[-1]
        assert dispatcher.envelope_handler is None
        # The invalid-frame one is replaced rather than dropped, so a bad frame
        # is still reported — just without its contents.
        assert dispatcher.invalid_frame_handler is not None
        assert dispatcher.invalid_frame_handler.__name__ != "_printing_invalid_frame_handler"
    finally:
        await connector.stop()


async def test_an_invalid_frame_is_reported_without_its_contents(
    sdk: FakeSeaTalkSdk, caplog: pytest.LogCaptureFixture
) -> None:
    sdk.plan[:] = [hold()]
    connector = _connector(sdk, _Recorder())
    with caplog.at_level(logging.WARNING):
        await connector.start()
        try:
            await wait_until(lambda: sdk.connections == 1, message="never connected")
            handler = sdk.dispatchers[-1].invalid_frame_handler
            assert handler is not None
            handler(b'{"text": "a private message"}', ValueError("bad json"))
            records = [r for r in caplog.records if "invalid_frame" in r.message]
            assert records, "a bad frame was swallowed"
            assert "a private message" not in str(records[0].__dict__)
        finally:
            await connector.stop()


async def test_an_ingest_failure_is_logged_and_does_not_drop_the_connection(
    sdk: FakeSeaTalkSdk, caplog: pytest.LogCaptureFixture
) -> None:
    sdk.plan[:] = [deliver(envelope()), hold()]
    connector = _connector(sdk, _Recorder(fail=True))
    with caplog.at_level(logging.ERROR):
        await connector.start()
        try:
            await wait_until(
                lambda: any("ingest_failed" in r.message for r in caplog.records),
                message="a failed ingest was swallowed silently",
            )
            # The socket is untouched: the failure was ours, not the platform's.
            assert connector.state()[0] == "connected"
        finally:
            await connector.stop()


async def test_an_event_without_a_data_dict_is_ignored(sdk: FakeSeaTalkSdk) -> None:
    def _bad(client: Any) -> None:
        client.dispatcher.event_handler(object())  # no .data at all
        client.block_until_closed()

    sdk.plan[:] = [_bad, hold()]
    ingest = _Recorder()
    connector = _connector(sdk, ingest)
    await connector.start()
    try:
        await wait_until(lambda: connector.state()[0] == "connected", message="never connected")
        await asyncio.sleep(0.05)
        assert ingest.received == []
        # Nothing raised into the dispatcher, so the connection is still up.
        assert connector.state()[0] == "connected"
    finally:
        await connector.stop()


@pytest.mark.acceptance(
    spec="channels",
    scenario="the websocket connection backs off when another process takes it over",
)
async def test_a_kick_backs_off_a_flat_sixty_seconds(sdk: FakeSeaTalkSdk) -> None:
    sdk.plan[:] = [kick("another connection registered")]
    connector = _connector(sdk, _Recorder())
    await connector.start()
    try:
        await wait_until(lambda: connector.backoffs, message="never backed off")
        assert connector.backoffs == [60.0]
        state, detail = connector.state()
        assert state == "kicked"
        assert detail is not None
        # The owner has to be able to tell this apart from a network fault.
        assert "another process" in detail
        assert "another connection registered" in detail
    finally:
        await connector.stop()


async def test_a_dropped_socket_reconnects_with_a_growing_backoff(sdk: FakeSeaTalkSdk) -> None:
    sdk.plan[:] = [drop("read failed")]
    connector = _connector(sdk, _Recorder())
    await connector.start()
    try:
        await wait_until(lambda: len(connector.backoffs) >= 3, message="did not retry three times")
        assert connector.backoffs[:3] == [0.01, 0.02, 0.04]
        assert sdk.connections >= 3  # every retry is a fresh register handshake
        state, detail = connector.state()
        assert state == "error"
        assert detail is not None and "read failed" in detail
    finally:
        await connector.stop()


async def test_a_recovered_socket_reports_connected_again(sdk: FakeSeaTalkSdk) -> None:
    """``state()`` must not flatter: connected only while the socket is up."""
    sdk.plan[:] = [drop("first attempt failed"), hold()]
    connector = _connector(sdk, _Recorder())
    await connector.start()
    try:
        await wait_until(lambda: connector.state()[0] == "connected", message="never recovered")
        assert connector.state() == ("connected", None)
    finally:
        await connector.stop()


@pytest.mark.acceptance(
    spec="channels", scenario="a websocket channel without the sdk says what is missing"
)
async def test_without_the_sdk_the_state_says_what_is_missing() -> None:
    missing = build_fake_sdk()

    def _loader() -> Any:
        raise SeaTalkSdkMissingError(
            "SeaTalk's WebSocket SDK (seatalk_oapi_sdk) is not installed; unpack it into "
            "/tmp/vendor — see https://open.seatalk.io/docs/WebSocket-Event-Callback"
        )

    connector = _connector(missing, _Recorder())
    connector._loader = _loader  # type: ignore[assignment]
    await connector.start()
    try:
        await wait_until(
            lambda: connector.state()[0] == "sdk_missing", message="never reported sdk_missing"
        )
        state, detail = connector.state()
        assert state == "sdk_missing"
        assert detail is not None
        assert "seatalk_oapi_sdk" in detail
        assert "/tmp/vendor" in detail  # the directory it looked in
        # It keeps trying, so dropping the SDK in needs no daemon restart.
        await wait_until(lambda: connector.backoffs, message="stopped retrying")
        assert missing.connections == 0  # nothing was ever dialled
    finally:
        await connector.stop()


async def test_stop_joins_the_listen_thread_and_closes_the_client(sdk: FakeSeaTalkSdk) -> None:
    connector = _connector(sdk, _Recorder())
    await connector.start()
    await wait_until(lambda: sdk.listen_threads, message="listen never started")
    thread = sdk.listen_threads[0]
    assert thread.is_alive()

    await connector.stop()

    assert thread.is_alive() is False  # the blocking worker really stopped
    assert sdk.closes >= 1  # and the socket was closed, not abandoned
    assert connector.supervising is False


async def test_stop_is_idempotent(sdk: FakeSeaTalkSdk) -> None:
    connector = _connector(sdk, _Recorder())
    await connector.start()
    await connector.stop()
    await connector.stop()
    assert connector.supervising is False


async def test_start_twice_supervises_one_connection(sdk: FakeSeaTalkSdk) -> None:
    connector = _connector(sdk, _Recorder())
    await connector.start()
    try:
        await wait_until(lambda: sdk.connections == 1, message="never connected")
        await connector.start()
        await asyncio.sleep(0.05)
        assert sdk.connections == 1
    finally:
        await connector.stop()


# ---------------------------------------------------------------------------
# The controller
# ---------------------------------------------------------------------------


def _controller(sdk: FakeSeaTalkSdk, ingest: Any) -> SeaTalkWebSocketController:
    def factory(name: str, app_id: str, app_secret: str, *, ingest: Any) -> Any:
        return _connector(sdk, ingest)

    return SeaTalkWebSocketController(ingest=ingest, connector_factory=factory)


async def test_controller_starts_stops_and_reports_one_connection_per_channel(
    sdk: FakeSeaTalkSdk,
) -> None:
    controller = _controller(sdk, _Recorder())
    try:
        await controller.ensure_running("st", "app-1", "app-secret")
        assert controller.running("st") is True
        assert controller.active() == {"st"}
        await wait_until(
            lambda: controller.state("st") == ("connected", None), message="never connected"
        )
        assert controller.state("other") is None  # a channel with no connector

        await controller.ensure_stopped("st")
        assert controller.running("st") is False
        assert controller.active() == set()
        assert controller.state("st") is None
    finally:
        await controller.dispose()


async def test_controller_ensure_running_is_idempotent_but_respawns_on_new_credentials(
    sdk: FakeSeaTalkSdk,
) -> None:
    controller = _controller(sdk, _Recorder())
    try:
        await controller.ensure_running("st", "app-1", "app-secret")
        await wait_until(lambda: sdk.connections == 1, message="never connected")
        await controller.ensure_running("st", "app-1", "app-secret")
        await asyncio.sleep(0.05)
        assert sdk.connections == 1  # same credentials: nothing restarted

        # A rotated secret must reconnect — the old socket authenticated with the
        # old one and would keep running on it otherwise.
        await controller.ensure_running("st", "app-1", "rotated-secret")
        await wait_until(lambda: sdk.connections == 2, message="rotation did not reconnect")
    finally:
        await controller.dispose()


async def test_controller_dispose_stops_every_channel(sdk: FakeSeaTalkSdk) -> None:
    controller = _controller(sdk, _Recorder())
    await controller.ensure_running("st", "app-1", "app-secret")
    await controller.ensure_running("st2", "app-2", "app-secret-2")
    await wait_until(lambda: sdk.connections == 2, message="both never connected")

    await controller.dispose()

    assert controller.active() == set()
    assert all(t.is_alive() is False for t in sdk.listen_threads)


async def test_controller_ensure_stopped_on_an_unknown_channel_is_a_no_op(
    sdk: FakeSeaTalkSdk,
) -> None:
    controller = _controller(sdk, _Recorder())
    await controller.ensure_stopped("never-started")
    assert controller.active() == set()
