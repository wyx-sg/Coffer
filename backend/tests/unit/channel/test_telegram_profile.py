"""Start-up introspection and self-description (spec channels "Probe platform
capabilities and latch off rejected ones", "Register the bot's command menu and
profile from one roster"; spec channels/telegram "Register command menus per
chat scope and language")."""

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

    def menus(self) -> dict[tuple[str, str], dict[str, str]]:
        """``(scope type or "default", language or "") -> {command: description}``."""
        out: dict[tuple[str, str], dict[str, str]] = {}
        for name, params in self.made:
            if name != "setMyCommands":
                continue
            key = (
                (params.get("scope") or {}).get("type", "default"),
                params.get("language_code", ""),
            )
            assert key not in out, f"{key} registered twice"
            out[key] = {c["command"]: c["description"] for c in params["commands"]}
        return out


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
    # as a problem (spec channels/telegram "Report privacy mode that defeats
    # the group configuration"), so it stays None rather than defaulting to
    # False.
    assert (await probe_identity(_Calls({"getMe": {"id": 1}}))).reads_all_group_messages is None


@pytest.mark.asyncio
async def test_a_failed_get_me_degrades_to_an_empty_identity() -> None:
    identity = await probe_identity(_Calls(fails=frozenset({"getMe"})))
    assert identity == BotIdentity()


@pytest.mark.asyncio
async def test_a_non_dict_get_me_degrades_to_an_empty_identity() -> None:
    assert await probe_identity(_Calls({"getMe": "nonsense"})) == BotIdentity()


# -- register_profile ---------------------------------------------------------


_PRIVATE = {"new", "stop", "model", "dir", "status", "resume", "thread", "del", "help"}
_GROUP = {"new", "stop", "del", "help"}


@pytest.mark.acceptance(
    spec="channels/telegram",
    scenario="private chats get every command and groups the group set, in English and Chinese",
)
@pytest.mark.asyncio
async def test_menus_are_registered_per_scope_and_language() -> None:
    call = _Calls({"getMyDescription": {"description": "x"}})
    await register_profile(call)
    menus = call.menus()
    # Spelled out rather than read from the roster, so a wrong roster fails here.
    assert set(menus) == {
        (scope, lang)
        for scope in ("default", "all_private_chats", "all_group_chats")
        for lang in ("", "zh")
    }
    for lang in ("", "zh"):
        assert set(menus[("all_private_chats", lang)]) == _PRIVATE
        assert set(menus[("default", lang)]) == _PRIVATE
        assert set(menus[("all_group_chats", lang)]) == _GROUP
    # /start is what the start button sends — typed, never listed.
    assert all("start" not in menu for menu in menus.values())
    assert menus[("all_private_chats", "")]["help"] == "Commands"
    assert menus[("all_private_chats", "zh")]["help"] == "命令列表"
    assert call.params_for("setChatMenuButton")["menu_button"] == {"type": "commands"}


@pytest.mark.asyncio
async def test_asker_only_commands_stay_ephemeral_in_every_menu() -> None:
    call = _Calls({"getMyDescription": {"description": "x"}})
    await register_profile(call)
    for name, params in call.made:
        if name == "setMyCommands":
            flags = {c["command"]: c["is_ephemeral"] for c in params["commands"]}
            assert flags["help"] is True and flags["new"] is False


@pytest.mark.asyncio
async def test_an_empty_description_is_filled() -> None:
    call = _Calls({"getMyDescription": {"description": ""}, "getMyShortDescription": {}})
    await register_profile(call)
    description = call.params_for("setMyDescription")["description"]
    assert "Coffer" in description and "/new" in description and "/agent" not in description
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
