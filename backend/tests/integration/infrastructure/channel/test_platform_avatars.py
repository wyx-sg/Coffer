"""Where each platform's picture of a person comes from (spec channels "Show
each paired person's platform picture"): Telegram's ``getUserProfilePhotos``
and SeaTalk's employee profile."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from coffer.domain.channel.errors import ChannelSendFailed
from coffer.infrastructure.channel import seatalk_avatar, telegram_avatar

_JPEG = b"\xff\xd8\xff\xe0jpeg"


def _client(routes: dict[str, httpx.Response], seen: list[httpx.Request]) -> httpx.AsyncClient:
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return routes.get(str(request.url), httpx.Response(404))

    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


async def test_telegram_downloads_the_newest_photos_smallest_size_that_fills_the_row() -> None:
    made: list[tuple[str, dict[str, Any]]] = []

    async def call(method: str, **params: Any) -> Any:
        made.append((method, params))
        if method == "getUserProfilePhotos":
            return {
                "total_count": 2,
                "photos": [
                    [
                        {"file_id": "big", "width": 640},
                        {"file_id": "small", "width": 160},
                        {"file_id": "tiny", "width": 80},
                    ]
                ],
            }
        return {"file_path": f"photos/{params['file_id']}.jpg"}

    seen: list[httpx.Request] = []
    client = _client(
        {"https://t/file/botX/photos/small.jpg": httpx.Response(200, content=_JPEG)}, seen
    )
    data = await telegram_avatar.fetch_avatar(client, call, "https://t/file/botX", "tg", "42")
    assert data == _JPEG
    assert made[0] == ("getUserProfilePhotos", {"user_id": "42", "limit": 1})
    assert made[1] == ("getFile", {"file_id": "small"})


async def test_telegram_person_without_photos_has_none() -> None:
    async def call(method: str, **params: Any) -> Any:
        return {"total_count": 0, "photos": []}

    client = _client({}, [])
    assert await telegram_avatar.fetch_avatar(client, call, "https://t/f", "tg", "42") is None


async def test_seatalk_reads_the_profile_and_downloads_without_the_app_token() -> None:
    asked: list[tuple[str, dict[str, Any]]] = []

    async def get(path: str, params: dict[str, Any], *, retries: int = 3) -> Any:
        asked.append((path, params))
        return {
            "code": 0,
            "employees": [{"employee_code": "e1", "avatar": "https://cdn.example/a.jpg"}],
        }

    seen: list[httpx.Request] = []
    client = _client({"https://cdn.example/a.jpg": httpx.Response(200, content=_JPEG)}, seen)
    assert await seatalk_avatar.fetch_avatar(get, client, "st", "e1") == _JPEG
    assert asked == [("/contacts/v2/profile", {"employee_code": "e1"})]
    assert "authorization" not in seen[0].headers


async def test_seatalk_profile_without_a_picture_has_none() -> None:
    async def get(path: str, params: dict[str, Any], *, retries: int = 3) -> Any:
        return {"code": 0, "employees": [{"employee_code": "e1", "avatar": ""}]}

    assert await seatalk_avatar.fetch_avatar(get, _client({}, []), "st", "e1") is None


async def test_seatalk_failed_download_raises() -> None:
    async def get(path: str, params: dict[str, Any], *, retries: int = 3) -> Any:
        return {"code": 0, "employees": [{"employee_code": "e1", "avatar": "https://cdn/x"}]}

    with pytest.raises(ChannelSendFailed):
        await seatalk_avatar.fetch_avatar(get, _client({}, []), "st", "e1")
