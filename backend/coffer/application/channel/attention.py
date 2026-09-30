"""What about the channels needs a person (the Overview list).

Asked only of enabled channels bound to this machine — a channel another
machine runs is not this daemon's to report on:

- ``channel_reconnecting`` — its SeaTalk websocket is (re)connecting;
- ``channel_sdk_missing`` — SeaTalk's WebSocket SDK is not where the daemon
  loads it from; the item carries the hand-off that puts it there
  (``sdk_handoff``), and its reason names no command;
- ``channel_disconnected`` — the websocket was kicked by another connection or
  failed; the reason carries the recorded error text;
- ``channel_not_running`` — the adapter is not running and no websocket state
  explains why (a Telegram adapter whose start failed).

Extension point: nothing records a bot token the platform *rejected* today —
it surfaces only as one of the websocket errors above, or as an adapter that
did not start. A source for it needs that signal recorded first.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from coffer.application.attention import AttentionAction, AttentionItem, Severity
from coffer.application.channel.service import ChannelStatus
from coffer.domain.resource import Resource

KIND = "channel"
#: The websocket's recorded error is shown verbatim, cut to a readable length.
_ERROR_MAX = 200
_DISCONNECTED = frozenset({"kicked", "error"})


class ChannelListPort(Protocol):
    async def list(
        self, kind: str | None = None, enabled: bool | None = None
    ) -> Sequence[Resource]: ...


class ChannelStatusPort(Protocol):
    async def status(self, channel_uid: str) -> ChannelStatus: ...


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _ERROR_MAX else text[: _ERROR_MAX - 1] + "…"


class ChannelAttentionSource:
    name = "channel"
    feature: str | None = None

    def __init__(
        self,
        *,
        resources: ChannelListPort,
        channels: ChannelStatusPort,
        sdk_handoff: Callable[[str], str] | None = None,
    ) -> None:
        self._resources = resources
        self._channels = channels
        #: A channel's name → the prompt that puts the SeaTalk SDK in place.
        self._sdk_handoff = sdk_handoff

    async def items(self) -> Sequence[AttentionItem]:
        out: list[AttentionItem] = []
        for resource in await self._resources.list(kind=KIND, enabled=True):
            item = self._item(await self._channels.status(resource.uid))
            if item is not None:
                out.append(item)
        return out

    def _item(self, status: ChannelStatus) -> AttentionItem | None:
        if not status.enabled or not status.runs_here:
            return None
        ws_state = status.inbound.websocket_state if status.inbound is not None else None
        ws_error = status.inbound.websocket_error if status.inbound is not None else None
        handoff: str | None = None
        if ws_state == "sdk_missing":
            code, severity = "channel_sdk_missing", Severity.ERROR
            reason = "SeaTalk's WebSocket SDK is not on this machine, so it receives nothing."
            handoff = self._sdk_handoff(status.name) if self._sdk_handoff else None
        elif ws_state == "connecting":
            code, severity = "channel_reconnecting", Severity.WARNING
            reason = "Its connection to the platform is being re-established."
        elif ws_state in _DISCONNECTED:
            code, severity = "channel_disconnected", Severity.ERROR
            reason = "Its connection to the platform is down"
            reason += f": {_clip(ws_error)}" if ws_error else "."
        elif ws_state is None and not status.running:
            code, severity = "channel_not_running", Severity.ERROR
            reason = "It is enabled for this machine but is not running."
        else:
            return None
        return AttentionItem(
            kind=KIND,
            uid=status.uid,
            title=status.title or status.name,
            reason_code=code,
            reason=reason,
            severity=severity,
            action=AttentionAction(
                verb="check", method="GET", path=f"/api/v1/channels/{status.uid}/status"
            ),
            handoff=handoff,
        )


__all__ = ["ChannelAttentionSource", "ChannelListPort", "ChannelStatusPort"]
