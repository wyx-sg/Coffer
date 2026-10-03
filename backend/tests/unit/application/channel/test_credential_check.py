"""Check credentials before they are saved (spec channels): the rule over a fake
probe — result shape, same-bot comparison, timeout, and that a failing stored
token never hides the new token's answer."""

from __future__ import annotations

import asyncio

import pytest

from coffer.application.channel.credential_check import (
    CredentialCheck,
    CredentialCheckRequest,
    CredentialProbeError,
    ProbedBot,
    StoredCredentials,
)


class _Probe:
    def __init__(self) -> None:
        self.telegram_bots: dict[str, ProbedBot | CredentialProbeError] = {}
        self.seatalk_calls: list[tuple[str, str]] = []
        self.hang = False

    async def telegram(self, bot_token: str) -> ProbedBot:
        if self.hang:
            await asyncio.sleep(5)
        result = self.telegram_bots[bot_token]
        if isinstance(result, CredentialProbeError):
            raise result
        return result

    async def seatalk(self, app_id: str, app_secret: str) -> ProbedBot:
        self.seatalk_calls.append((app_id, app_secret))
        if app_secret != "good":
            raise CredentialProbeError("rejected")
        return ProbedBot(bot_id=app_id)


class _Stored:
    def __init__(self, stored: StoredCredentials | None = None) -> None:
        self.stored = stored

    async def read(self, channel_uid: str) -> StoredCredentials | None:
        return self.stored


def _check(probe: _Probe, stored: StoredCredentials | None = None) -> CredentialCheck:
    return CredentialCheck(probe, _Stored(stored), timeout=0.2)


async def test_telegram_token_reports_the_bot_and_compares_nothing_without_a_channel() -> None:
    probe = _Probe()
    probe.telegram_bots["new"] = ProbedBot("7", "alexc_bot", "Alex Bot")
    result = await _check(probe).check(CredentialCheckRequest("telegram", bot_token=" new "))
    assert (result.ok, result.bot_handle, result.bot_name, result.same_bot) == (
        True,
        "alexc_bot",
        "Alex Bot",
        None,
    )


@pytest.mark.parametrize(("old_id", "same"), [("7", True), ("8", False)])
@pytest.mark.acceptance(spec="channels", scenario="a replacement says whether it is the same bot")
async def test_replacement_says_whether_it_is_the_stored_bot(old_id: str, same: bool) -> None:
    probe = _Probe()
    probe.telegram_bots["new"] = ProbedBot("7", "b")
    probe.telegram_bots["old"] = ProbedBot(old_id, "c")
    stored = StoredCredentials(platform="telegram", bot_token="old")
    result = await _check(probe, stored).check(
        CredentialCheckRequest("telegram", bot_token="new", channel_uid="u")
    )
    assert result.ok and result.same_bot is same


@pytest.mark.acceptance(spec="channels", scenario="a replacement says whether it is the same bot")
async def test_a_revoked_stored_token_leaves_same_bot_unknown_not_failed() -> None:
    probe = _Probe()
    probe.telegram_bots["new"] = ProbedBot("7", "b")
    probe.telegram_bots["old"] = CredentialProbeError("rejected")
    stored = StoredCredentials(platform="telegram", bot_token="old")
    result = await _check(probe, stored).check(
        CredentialCheckRequest("telegram", bot_token="new", channel_uid="u")
    )
    assert result.ok and result.same_bot is None


async def test_rejected_token_is_a_normal_answer_with_the_platforms_words() -> None:
    probe = _Probe()
    probe.telegram_bots["bad"] = CredentialProbeError("rejected", "Unauthorized")
    result = await _check(probe).check(CredentialCheckRequest("telegram", bot_token="bad"))
    assert (result.ok, result.reason, result.detail) == (False, "rejected", "Unauthorized")


async def test_missing_field_is_reported_without_calling_the_platform() -> None:
    probe = _Probe()
    assert (await _check(probe).check(CredentialCheckRequest("telegram"))).reason == "missing"
    seatalk = CredentialCheckRequest("seatalk", app_id="9", app_secret=None)
    assert (await _check(probe).check(seatalk)).reason == "missing"
    assert probe.seatalk_calls == []


async def test_seatalk_replacement_takes_the_app_id_from_the_stored_channel() -> None:
    probe = _Probe()
    stored = StoredCredentials(platform="seatalk", app_id="9402")
    result = await _check(probe, stored).check(
        CredentialCheckRequest("seatalk", app_secret="good", channel_uid="u")
    )
    assert probe.seatalk_calls == [("9402", "good")]
    assert result.ok and result.same_bot is True


async def test_seatalk_new_app_id_is_a_different_bot() -> None:
    stored = StoredCredentials(platform="seatalk", app_id="9402")
    result = await _check(_Probe(), stored).check(
        CredentialCheckRequest("seatalk", app_id="1111", app_secret="good", channel_uid="u")
    )
    assert result.ok and result.same_bot is False


async def test_a_channel_of_another_platform_is_not_compared() -> None:
    probe = _Probe()
    probe.telegram_bots["new"] = ProbedBot("7")
    stored = StoredCredentials(platform="seatalk", app_id="9402")
    result = await _check(probe, stored).check(
        CredentialCheckRequest("telegram", bot_token="new", channel_uid="u")
    )
    assert result.ok and result.same_bot is None


@pytest.mark.acceptance(
    spec="channels", scenario="a refused or unreachable platform is reported, not raised"
)
async def test_a_slow_platform_times_out() -> None:
    probe = _Probe()
    probe.hang = True
    result = await _check(probe).check(CredentialCheckRequest("telegram", bot_token="x"))
    assert (result.ok, result.reason) == (False, "timeout")
