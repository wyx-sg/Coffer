"""Telegram's status-message live surface against the Bot API's own text cap.

A plain ``sendMessage`` / ``editMessageText`` carries at most 4096 characters.
The turn renderer clips its preview to the adapter's ``max_message_chars``,
which is the RICH-message budget (32000) when rich messages are on — so the
status message itself must hold the line, or a long reply kills the surface
and leaves the scaffolding behind (spec channels/telegram "Use a deleted status
message as the live scaffolding").
"""

from __future__ import annotations

from typing import Any

from coffer.infrastructure.channel.live_text import TelegramLiveText

_BOT_API_TEXT_LIMIT = 4096


class _BotApi:
    """Records calls and refuses a text over the Bot API limit, as Telegram does."""

    def __init__(self, *, fail_edits: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._fail_edits = fail_edits

    async def __call__(self, method: str, **params: Any) -> dict[str, Any]:
        self.calls.append((method, params))
        text = params.get("text")
        if isinstance(text, str) and len(text) > _BOT_API_TEXT_LIMIT:
            raise RuntimeError("Bad Request: message is too long")
        if method == "editMessageText" and self._fail_edits:
            raise RuntimeError("Bad Request: message can't be edited")
        return {"message_id": 101}

    def texts(self, method: str) -> list[str]:
        return [p["text"] for m, p in self.calls if m == method]

    def deletes(self) -> list[dict[str, Any]]:
        return [p for m, p in self.calls if m == "deleteMessage"]


def _ticking() -> Any:
    box = [0.0]

    def now() -> float:
        box[0] += 2.0  # past Telegram's 1.5 s buffer on every read
        return box[0]

    return now


async def test_a_long_preview_is_clipped_to_the_bot_api_limit() -> None:
    api = _BotApi()
    live = TelegramLiveText(api, "-100", now=_ticking())
    long_reply = "word " * 2000  # 10000 chars, well inside the 32000 rich budget

    await live.update("Thinking…")
    await live.update(long_reply)
    leftover = await live.close(long_reply)

    edits = api.texts("editMessageText")
    assert len(edits) == 1
    assert len(edits[0]) == _BOT_API_TEXT_LIMIT
    assert edits[0].startswith("…")  # the tail — the newest words — is what shows
    assert edits[0].endswith(long_reply.strip()[-100:])
    # The surface stayed alive, so the scaffolding is deleted and the whole
    # reply is handed back to be sent properly.
    assert api.deletes() == [{"chat_id": "-100", "message_id": "101"}]
    assert leftover == long_reply


async def test_a_status_message_is_deleted_even_after_a_later_edit_failed() -> None:
    api = _BotApi(fail_edits=True)
    live = TelegramLiveText(api, "-100", now=_ticking())

    await live.update("Thinking…")  # opens the status message
    await live.update("Thinking… and more")  # refused: the surface goes dead
    await live.update("never sent")
    leftover = await live.close("the final reply")

    assert api.texts("editMessageText") == ["Thinking… and more"]
    assert api.deletes() == [{"chat_id": "-100", "message_id": "101"}]
    assert leftover == "the final reply"
    # Closing again touches nothing: the scaffolding is already gone.
    await live.close("the final reply")
    assert len(api.deletes()) == 1
