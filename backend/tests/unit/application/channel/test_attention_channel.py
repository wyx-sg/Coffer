"""ChannelAttentionSource: enabled channels bound to this machine."""

from __future__ import annotations

import pytest

from coffer.application.attention import AttentionAction, Severity
from coffer.application.channel.attention import ChannelAttentionSource
from coffer.application.channel.inbound_status import InboundInfo
from coffer.application.channel.service import ChannelStatus, SecretApproval
from tests.unit.application._attention_fakes import FakeResources, resource


def _status(
    uid: str,
    *,
    running: bool = True,
    runs_here: bool = True,
    ws: tuple[str, str | None] | None = None,
    seatalk: bool = True,
    title: str | None = None,
    approval: str | None = None,
) -> ChannelStatus:
    inbound = (
        InboundInfo(websocket_state=ws[0] if ws else None, websocket_error=ws[1] if ws else None)
        if seatalk
        else None
    )
    return ChannelStatus(
        uid=uid,
        name=f"bot-{uid}",
        channel_type="seatalk" if seatalk else "telegram",
        enabled=True,
        running=running,
        pending_pairing=False,
        people=(),
        inbound=inbound,
        runs_here=runs_here,
        title=title,
        secret_approval=SecretApproval(state=approval, secret_ref="coffer://secret/x")
        if approval
        else None,
    )


class FakeChannels:
    def __init__(self, statuses: dict[str, ChannelStatus]) -> None:
        self.statuses = statuses
        self.asked: list[str] = []

    async def status(self, channel_uid: str) -> ChannelStatus:
        self.asked.append(channel_uid)
        return self.statuses[channel_uid]


def _source(*statuses: ChannelStatus, disabled: tuple[str, ...] = ()) -> ChannelAttentionSource:
    rows = [resource(s.uid, "channel", {}) for s in statuses]
    rows += [resource(uid, "channel", {}, enabled=False) for uid in disabled]
    return ChannelAttentionSource(
        resources=FakeResources(rows), channels=FakeChannels({s.uid: s for s in statuses})
    )


def _check(uid: str) -> AttentionAction:
    return AttentionAction(verb="check", method="GET", path=f"/api/v1/channels/{uid}/status")


async def test_connecting_websocket_is_a_reconnecting_warning() -> None:
    [item] = await _source(_status("c1", ws=("connecting", None), title="Team bot")).items()
    assert (item.kind, item.uid, item.title) == ("channel", "c1", "Team bot")
    assert item.reason_code == "channel_reconnecting"
    assert item.severity is Severity.WARNING
    assert item.action == _check("c1")
    assert item.since is None


@pytest.mark.parametrize("state", ["kicked", "error"])
async def test_a_down_websocket_is_an_error_carrying_the_recorded_text(state: str) -> None:
    [item] = await _source(_status("c1", ws=(state, "another   process\nholds it"))).items()
    assert item.reason_code == "channel_disconnected"
    assert item.severity is Severity.ERROR
    assert "another process holds it" in item.reason
    assert item.title == "bot-c1"
    assert item.action == _check("c1")


@pytest.mark.acceptance(
    spec="channels/seatalk", scenario="a missing sdk is handed to an agent on the Overview"
)
async def test_a_missing_sdk_carries_the_hand_off_and_a_command_free_reason() -> None:
    asked: list[str] = []

    def handoff(name: str) -> str:
        asked.append(name)
        return f"put the SDK in place for {name}"

    status = _status("c1", ws=("sdk_missing", "not found in /v"))
    source = ChannelAttentionSource(
        resources=FakeResources([resource("c1", "channel", {})]),
        channels=FakeChannels({"c1": status}),
        sdk_handoff=handoff,
    )
    [item] = await source.items()
    assert item.reason_code == "channel_sdk_missing"
    assert item.severity is Severity.ERROR
    assert item.handoff == "put the SDK in place for bot-c1"
    assert asked == ["bot-c1"]
    assert "coffer " not in item.reason and "/v" not in item.reason
    assert item.action == _check("c1")


async def test_a_missing_sdk_without_a_hand_off_source_still_reports() -> None:
    [item] = await _source(_status("c1", ws=("sdk_missing", "x"))).items()
    assert item.reason_code == "channel_sdk_missing"
    assert item.handoff is None


async def test_the_recorded_error_is_clipped() -> None:
    [item] = await _source(_status("c1", ws=("error", "x" * 500))).items()
    assert "x" * 199 in item.reason
    assert "x" * 200 not in item.reason
    assert item.reason.endswith("…")


async def test_a_stopped_adapter_with_no_websocket_state_is_not_running() -> None:
    [item] = await _source(_status("t1", running=False, seatalk=False)).items()
    assert item.reason_code == "channel_not_running"
    assert item.severity is Severity.ERROR
    assert item.action == _check("t1")


async def test_healthy_or_elsewhere_channels_report_nothing() -> None:
    source = _source(
        _status("ok", ws=("connected", None)),
        _status("tg", seatalk=False),
        _status("away", running=False, runs_here=False, ws=("error", "boom")),
    )
    assert await source.items() == []


async def test_disabled_channels_are_not_asked() -> None:
    source = _source(_status("on", ws=("connected", None)), disabled=("off",))
    assert await source.items() == []
    assert source._channels.asked == ["on"]  # type: ignore[attr-defined]


async def test_a_raising_status_propagates() -> None:
    class Broken(FakeChannels):
        async def status(self, channel_uid: str) -> ChannelStatus:
            raise RuntimeError("runtime gone")

    source = ChannelAttentionSource(
        resources=FakeResources([resource("c1", "channel", {})]), channels=Broken({})
    )
    with pytest.raises(RuntimeError, match="runtime gone"):
        await source.items()


def test_source_identity() -> None:
    source = _source()
    assert (source.name, source.feature) == ("channel", None)


@pytest.mark.parametrize(
    ("state", "phrase"), [("pending", "waits for your approval"), ("refused", "refused")]
)
async def test_a_secret_awaiting_approval_is_named_not_a_generic_stop(
    state: str, phrase: str
) -> None:
    [item] = await _source(_status("c1", running=False, approval=state)).items()
    assert item.reason_code == "channel_secret_approval"
    assert phrase in item.reason
    assert "Secrets page" in item.reason
