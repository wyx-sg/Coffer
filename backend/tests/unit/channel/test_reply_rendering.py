"""What each transport does with a reply's structure (spec channels "Shape a
reply for what the chat can show"): Telegram collapses ``## Details``, and a
reply cut into several messages numbers its continuations."""

from __future__ import annotations

from typing import Any

import pytest

from coffer.infrastructure.channel.seatalk_live import SeaTalkLiveText
from coffer.infrastructure.channel.seatalk_send import send_text_pieces
from coffer.infrastructure.channel.telegram_features import Feature
from coffer.infrastructure.channel.telegram_send import send_text_chunks

_REPLY = "Deploy is green.\n\n## Details\n\n- built in 3m\n- 412 tests passed"


class _Api:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, method: str, **params: Any) -> dict[str, Any]:
        self.calls.append((method, params))
        return {"message_id": len(self.calls)}


@pytest.mark.acceptance(spec="channels/telegram", scenario="a details section arrives collapsed")
async def test_telegram_rich_collapses_details_into_a_details_block() -> None:
    api = _Api()
    await send_text_chunks(api, "1", _REPLY, limit=4000, rich=Feature("rich_messages"))
    [(method, params)] = api.calls
    assert method == "sendRichMessage"
    assert params["rich_message"]["markdown"] == (
        "Deploy is green.\n\n<details><summary>Details</summary>\n\n"
        "- built in 3m\n- 412 tests passed\n\n</details>"
    )


async def test_telegram_html_collapses_details_into_an_expandable_quote() -> None:
    api = _Api()
    await send_text_chunks(api, "1", _REPLY, limit=4000)
    texts = [p["text"] for m, p in api.calls if m == "sendMessage"]
    assert texts[0] == "Deploy is green."
    assert texts[1].startswith("(2/2)\n<b>Details</b>\n<blockquote expandable>")
    assert texts[1].endswith("</blockquote>")


class _SeaTalk:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.sends: list[str] = []

    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self.posts.append((path, body))
        return {"stream_id": "s1"}

    async def send(self, chat_id: str, message: dict[str, Any], thread: str, kind: str) -> Any:
        self.sends.append(message["text"]["content"])
        return {"message_id": f"m{len(self.sends)}"}


@pytest.mark.acceptance(
    spec="channels/seatalk", scenario="continuations after the stream are numbered"
)
async def test_the_seatalk_stream_sends_its_own_numbered_remainder() -> None:
    fake = _SeaTalk()
    live = SeaTalkLiveText(fake.post, "e1", send=fake.send, char_limit=3000, byte_limit=3000)
    await live.update("⏳ Working · 1s")
    reply = "\n\n".join([("a" * 1500), ("b" * 1500), ("c" * 2500), ("d" * 2500)])

    assert await live.close(reply) == ""
    assert len(fake.sends) >= 1
    total = len(fake.sends) + 1
    for i, text in enumerate(fake.sends, start=2):
        assert text.startswith(f"({i}/{total})\n")


async def test_seatalk_numbers_a_chunked_ordinary_send() -> None:
    fake = _SeaTalk()
    text = "\n\n".join(["x" * 30] * 3)
    await send_text_pieces(fake.send, "e1", text, char_limit=40, byte_limit=4000)
    assert fake.sends[0] == "x" * 30
    assert fake.sends[1].startswith("(2/3)\n") and fake.sends[2].startswith("(3/3)\n")
