"""The real ``coffer-seatalk-bridge`` process, end to end.

Each test starts the bridge exactly as the daemon does — the unfrozen form,
``python -m coffer.infrastructure.channel.seatalk_bridge`` with the allow-listed
environment — against a file-based fake ``seatalk_oapi_sdk`` written into a tmp
vendor directory. What is pinned is the boundary itself: events cross it, the
SDK never enters this process, and the app secret never appears in the
bridge's argv or environment.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from coffer.infrastructure.channel.seatalk_bridge.protocol import BridgeConfig
from coffer.infrastructure.channel.seatalk_bridge_process import (
    BridgeUnavailableError,
    SubprocessBridge,
    bridge_command,
    bridge_environment,
)
from coffer.infrastructure.channel.seatalk_ws import SeaTalkWebSocketConnector

from .conftest import wait_until
from .fake_seatalk_sdk import envelope, write_fake_sdk_package

_PACKAGE = "seatalk_oapi_sdk"
_SECRET = "app-secret-value-7f3a"


class _Recorder:
    def __init__(self) -> None:
        self.received: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, name: str, payload: dict[str, Any]) -> None:
        self.received.append((name, payload))


def _connector(vendor: Path, ingest: Any, *, secret: str = _SECRET) -> SeaTalkWebSocketConnector:
    return SeaTalkWebSocketConnector(
        "st",
        "app-1",
        secret,
        ingest=ingest,
        sdk_directory=lambda: vendor,
        backoff_initial=0.05,
        backoff_max=0.2,
        kick_backoff=60.0,
    )


def _assert_daemon_untouched(vendor: Path) -> None:
    assert _PACKAGE not in sys.modules, "the SDK was imported into the daemon"
    assert str(vendor) not in sys.path, "the vendor dir landed on the daemon's sys.path"


@pytest.mark.acceptance(
    spec="channels/seatalk", scenario="a websocket channel receives an event with no public url"
)
async def test_an_event_crosses_the_bridge_and_the_sdk_never_enters_the_daemon(
    tmp_path: Path,
) -> None:
    vendor = tmp_path / "vendor"
    body = envelope()
    record = tmp_path / "record.json"
    write_fake_sdk_package(vendor, script={"events": [body]}, record=record)
    ingest = _Recorder()
    connector = _connector(vendor, ingest)
    await connector.start()
    try:
        await wait_until(lambda: ingest.received, timeout=20.0, message="no event crossed")
        assert ingest.received[0] == ("st", body)
        await wait_until(
            lambda: connector.state() == ("connected", None), message="never reported connected"
        )
    finally:
        await connector.stop()
    _assert_daemon_untouched(vendor)

    # The secret reached the SDK over stdin, and nowhere a process listing or a
    # child process could see it.
    seen = json.loads(record.read_text())
    assert not any(_SECRET in arg for arg in seen["argv"])
    assert not any(_SECRET in value for value in seen["env"].values())
    assert not any(name.startswith("COFFER_") for name in seen["env"])
    # Inside the bridge the vendor dir comes last, after everything it could shadow.
    assert seen["path"][-1] == str(vendor)


@pytest.mark.acceptance(
    spec="channels/seatalk", scenario="a websocket channel without the sdk says what is missing"
)
async def test_without_the_sdk_the_bridge_reports_sdk_missing(tmp_path: Path) -> None:
    vendor = tmp_path / "vendor"  # never created
    connector = _connector(vendor, _Recorder())
    await connector.start()
    try:
        await wait_until(
            lambda: connector.state()[0] == "sdk_missing",
            timeout=20.0,
            message="never reported sdk_missing",
        )
        detail = connector.state()[1] or ""
        assert _PACKAGE in detail and str(vendor) in detail
        # Dropping the SDK in needs no restart: the next attempt finds it.
        write_fake_sdk_package(vendor)
        await wait_until(
            lambda: connector.state()[0] == "connected", timeout=20.0, message="never recovered"
        )
    finally:
        await connector.stop()
    _assert_daemon_untouched(vendor)


async def test_a_refusal_is_rejected_and_its_secret_scrubbed(tmp_path: Path) -> None:
    vendor = tmp_path / "vendor"
    write_fake_sdk_package(vendor)
    connector = _connector(vendor, _Recorder(), secret="bad-secret-1234")
    await connector.start()
    try:
        await wait_until(
            lambda: connector.state()[0] == "rejected", timeout=20.0, message="never rejected"
        )
        detail = connector.state()[1] or ""
        assert detail.startswith("RegisterError: ")
        assert "invalid app secret" in detail
        assert "bad-secret-1234" not in detail
    finally:
        await connector.stop()


async def test_a_kick_is_classified_by_the_reported_class_name(tmp_path: Path) -> None:
    vendor = tmp_path / "vendor"
    write_fake_sdk_package(vendor, script={"kick": "taken over elsewhere"})
    connector = _connector(vendor, _Recorder())
    await connector.start()
    try:
        await wait_until(lambda: connector.backoffs, timeout=20.0, message="never backed off")
        assert connector.backoffs == [60.0]
        state, detail = connector.state()
        assert state == "kicked"
        assert detail is not None and "taken over elsewhere" in detail
    finally:
        await connector.stop()


async def test_stray_sdk_prints_do_not_corrupt_the_protocol(tmp_path: Path) -> None:
    """The fake prints on import and on listen; neither may reach the pipe."""
    vendor = tmp_path / "vendor"
    write_fake_sdk_package(vendor, script={"invalid_frame": True})
    bridge = await SubprocessBridge.spawn(BridgeConfig("app-1", _SECRET, str(vendor)))
    kinds: list[str] = []
    try:
        while (message := await bridge.receive()) is not None:
            kinds.append(message["type"])
            if message["type"] == "invalid_frame":
                assert message["bytes"] == len(b"secret body")
                assert "secret body" not in json.dumps(message)
                break
    finally:
        await bridge.close()
    assert kinds == ["loaded", "connected", "invalid_frame"]


async def test_closing_stdin_stops_the_bridge(tmp_path: Path) -> None:
    vendor = tmp_path / "vendor"
    write_fake_sdk_package(vendor)
    bridge = await SubprocessBridge.spawn(BridgeConfig("app-1", _SECRET, str(vendor)))
    assert (await bridge.receive() or {}).get("type") == "loaded"
    assert (await bridge.receive() or {}).get("type") == "connected"
    await bridge.close()
    assert bridge.exit_detail().startswith("exit code 0")


def test_the_spawn_carries_no_secret_and_no_coffer_settings() -> None:
    env = bridge_environment(
        {
            "PATH": "/usr/bin",
            "HOME": "/home/me",
            "LC_ALL": "en_US.UTF-8",
            "HTTPS_PROXY": "http://proxy:3128",
            "COFFER_SEATALK_SDK_DIR": "/v",
            "COFFER_MASTER_KEY": "nope",
            "AWS_SECRET_ACCESS_KEY": "nope",
        },
        frozen=True,
    )
    assert env == {
        "PATH": "/usr/bin",
        "HOME": "/home/me",
        "LC_ALL": "en_US.UTF-8",
        "HTTPS_PROXY": "http://proxy:3128",
    }
    # Unfrozen, the module must import from this checkout.
    dev = bridge_environment({"PATH": "/usr/bin"}, frozen=False)
    assert Path(dev["PYTHONPATH"].split(":")[0], "coffer").is_dir()
    assert bridge_command(frozen=False)[1:] == [
        "-m",
        "coffer.infrastructure.channel.seatalk_bridge",
    ]


def test_a_frozen_build_without_the_bridge_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "executable", str(tmp_path / "coffer-daemon"))
    with pytest.raises(BridgeUnavailableError, match="coffer-seatalk-bridge is missing"):
        bridge_command(frozen=True)
    (tmp_path / "coffer-seatalk-bridge").write_text("")
    assert bridge_command(frozen=True) == [str(tmp_path / "coffer-seatalk-bridge")]
