"""Start-up introspection and self-description (FR-059 / FR-065)."""

from __future__ import annotations

from typing import Any

import pytest

from coffer.infrastructure.channel.telegram_profile import (
    BotIdentity,
    probe_identity,
    register_profile,
)


class _Calls:
    """A recording stand-in for the adapter's ``_call``: canned results per
    method, and any method named in ``fails`` raises instead."""

    def __init__(
        self, results: dict[str, Any] | None = None, fails: frozenset[str] = frozenset()
    ) -> None:
        self.results = results or {}
        self.fails = fails
        self.made: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, method: str, **params: Any) -> Any:
        self.made.append((method, params))
        if method in self.fails:
            raise RuntimeError(f"{method} refused")
        return self.results.get(method)

    def params_for(self, method: str) -> dict[str, Any]:
        for name, params in self.made:
            if name == method:
                return params
        raise AssertionError(f"{method} was never called")

    def methods(self) -> list[str]:
        return [name for name, _ in self.made]


# -- probe_identity -----------------------------------------------------------


@pytest.mark.asyncio
async def test_identity_is_read_from_get_me() -> None:
    call = _Calls({"getMe": {"id": 42, "username": "mybot", "can_read_all_group_messages": True}})
    assert await probe_identity(call) == BotIdentity(
        bot_id=42, username="mybot", reads_all_group_messages=True
    )


@pytest.mark.asyncio
async def test_privacy_mode_on_is_reported_as_cannot_read() -> None:
    call = _Calls({"getMe": {"id": 42, "username": "b", "can_read_all_group_messages": False}})
    assert (await probe_identity(call)).reads_all_group_messages is False


@pytest.mark.asyncio
async def test_missing_privacy_field_stays_unknown() -> None:
    # An older Bot API server omits the field; unknown must never be reported
    # as a problem (FR-060), so it stays None rather than defaulting to False.
    assert (await probe_identity(_Calls({"getMe": {"id": 1}}))).reads_all_group_messages is None


@pytest.mark.asyncio
async def test_a_failed_get_me_degrades_to_an_empty_identity() -> None:
    identity = await probe_identity(_Calls(fails=frozenset({"getMe"})))
    assert identity == BotIdentity()


@pytest.mark.asyncio
async def test_a_non_dict_get_me_degrades_to_an_empty_identity() -> None:
    assert await probe_identity(_Calls({"getMe": "nonsense"})) == BotIdentity()


# -- register_profile ---------------------------------------------------------


@pytest.mark.asyncio
async def test_command_menu_and_menu_button_are_registered() -> None:
    call = _Calls({"getMyDescription": {"description": "x"}})
    await register_profile(call)
    registered = {entry["command"] for entry in call.params_for("setMyCommands")["commands"]}
    assert {"new", "agent", "model", "stop", "status", "help"} <= registered
    assert call.params_for("setChatMenuButton")["menu_button"] == {"type": "commands"}


@pytest.mark.asyncio
async def test_an_empty_description_is_filled() -> None:
    call = _Calls({"getMyDescription": {"description": ""}, "getMyShortDescription": {}})
    await register_profile(call)
    assert "Coffer" in call.params_for("setMyDescription")["description"]
    assert len(call.params_for("setMyShortDescription")["short_description"]) <= 120


@pytest.mark.asyncio
async def test_an_owner_written_description_is_left_alone() -> None:
    call = _Calls(
        {
            "getMyDescription": {"description": "My own bot, hands off"},
            "getMyShortDescription": {"short_description": "mine"},
        }
    )
    await register_profile(call)
    assert "setMyDescription" not in call.methods()
    assert "setMyShortDescription" not in call.methods()


@pytest.mark.asyncio
async def test_profile_is_untouched_when_it_cannot_be_read() -> None:
    # Not knowing whether copy exists must not license overwriting it.
    call = _Calls(fails=frozenset({"getMyDescription", "getMyShortDescription"}))
    await register_profile(call)
    assert "setMyDescription" not in call.methods()


@pytest.mark.asyncio
async def test_a_refused_menu_registration_does_not_raise() -> None:
    # A bot that cannot describe itself still serves turns.
    call = _Calls({"getMyDescription": {"description": "x"}}, fails=frozenset({"setMyCommands"}))
    await register_profile(call)
    assert "setChatMenuButton" in call.methods()
