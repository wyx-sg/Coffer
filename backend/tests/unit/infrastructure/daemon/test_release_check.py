"""The release lookup behind ``coffer update`` and the daemon's check (spec
daemon "Check the installed binaries for a new release")."""

from __future__ import annotations

import pytest

from coffer.infrastructure.daemon.release_check import (
    Release,
    ReleaseCheck,
    is_newer,
    parse_release,
    version_key,
)


def test_versions_compare_as_semver_with_a_pre_release_first() -> None:
    assert is_newer("0.10.0", "0.9.9")
    assert is_newer("v1.0.0", "1.0.0-rc.1")
    assert not is_newer("1.0.0", "1.0.0")
    assert not is_newer("garbage", "0.1.0")
    assert version_key("1.2") is None


def test_a_release_answer_is_read_and_a_pre_release_refused() -> None:
    release = parse_release(
        {
            "tag_name": "v0.4.0",
            "body": " notes \n",
            "published_at": "2026-10-01T00:00:00Z",
            "html_url": "https://example/r",
        }
    )
    assert release == Release(
        "0.4.0", "v0.4.0", "notes", "2026-10-01T00:00:00Z", "https://example/r"
    )
    with pytest.raises(ValueError):
        parse_release({"tag_name": "v0.4.0", "prerelease": True})
    with pytest.raises(ValueError):
        parse_release({"tag_name": "nightly"})


async def test_a_failed_check_keeps_the_last_result() -> None:
    answers: list[Release | Exception] = [
        Release("0.4.0", "v0.4.0", "", None, "u"),
        RuntimeError("offline"),
    ]

    async def fetch() -> Release:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    check = ReleaseCheck(running="0.3.0", applies=True, fetch=fetch, pinned_off=lambda: False)
    assert await check.check_now() is True
    first = check.checked_at
    assert await check.check_now() is False
    assert check.available() is not None and check.available().version == "0.4.0"  # type: ignore[union-attr]
    assert check.checked_at == first
    assert check.last_error is not None and "offline" in check.last_error


async def test_an_older_or_equal_release_is_not_offered() -> None:
    async def fetch() -> Release:
        return Release("0.3.0", "v0.3.0", "", None, "u")

    check = ReleaseCheck(running="0.3.0", applies=True, fetch=fetch, pinned_off=lambda: False)
    await check.check_now()
    assert check.available() is None
