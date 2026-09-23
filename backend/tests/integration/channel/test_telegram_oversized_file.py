"""A Telegram file known to be over the bot download cap is noted once and never requested.

Integration tier: the download path runs against an httpx mock transport, which
the unit tier's purity gate does not allow.
"""

from __future__ import annotations

from typing import Any

import pytest

#: Over the Bot API's 20 MB download cap.
_TOO_BIG = 25 * 1024 * 1024


@pytest.mark.acceptance(
    spec="channels/telegram", scenario="an oversized file is reported once and never requested"
)
async def test_an_oversized_file_gets_one_note_and_no_getfile(tmp_path) -> None:
    import httpx

    from coffer.infrastructure.channel.telegram_media import download_attachments

    calls: list[tuple[str, dict[str, Any]]] = []

    async def call(method: str, **params: Any) -> Any:
        calls.append((method, params))
        raise AssertionError("getFile must not be called for a file over the cap")

    message = {
        "caption": "have a look",
        "document": {"file_id": "huge", "file_name": "dump.sql", "file_size": _TOO_BIG},
    }
    async with httpx.AsyncClient() as client:
        fetched = await download_attachments(
            client, call, "https://files.invalid", tmp_path, "tg", message
        )
    assert calls == []
    assert fetched.attachments == ()
    assert len(fetched.notes) == 1
    assert "dump.sql" in fetched.notes[0] and "20 MB" in fetched.notes[0]
