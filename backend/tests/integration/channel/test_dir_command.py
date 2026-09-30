"""`/dir` switches the working directory, within the channel's allow-list only
(spec channels "Choose the working directory from chat")."""

from __future__ import annotations

from pathlib import Path

import pytest

from coffer.application.channel.dir_switch import NO_DIRECTORIES

from .conftest import ChannelEnv, FakeChannelAdapter, Resource, inbound, tap_event


async def _channel(
    env: ChannelEnv, directories: list[str], *, buttons: bool = False
) -> tuple[Resource, FakeChannelAdapter]:
    resource = await env.register_channel("tg")
    adapter = env.bind(
        resource,
        FakeChannelAdapter(supports_buttons=buttons, supports_card_update=buttons),
        directories=directories,
    )
    await env.pair(resource, "owner")
    return resource, adapter


def _dirs(tmp_path: Path) -> tuple[str, str]:
    app, lib = tmp_path / "src" / "app", tmp_path / "src" / "lib"
    (app / "sub").mkdir(parents=True)
    lib.mkdir(parents=True)
    return str(app), str(lib)


async def _sticky_cwd(env: ChannelEnv, resource: Resource) -> str | None:
    row = await env.threads.get(resource.id, "owner", "")
    return row.preferred_cwd if row is not None else None


@pytest.mark.acceptance(
    spec="channels", scenario="/dir switches to an allowed directory in a fresh conversation"
)
async def test_dir_switches_to_an_allowed_directory_in_a_fresh_conversation(
    env: ChannelEnv, tmp_path: Path
) -> None:
    app, lib = _dirs(tmp_path)
    resource, adapter = await _channel(env, [app, lib])
    await env.processor.on_message(inbound("tg", "owner", "/new"))
    before = await env.active_conversation(resource)

    # By basename…
    await env.processor.on_message(inbound("tg", "owner", "/dir lib"))

    assert await _sticky_cwd(env, resource) == lib
    fresh = await env.active_conversation(resource)
    assert fresh not in (None, before)
    assert env.provider.last_agent_config == {"cwd": lib}
    assert adapter.texts()[-1] == (
        f"📁 Now in {lib} — started a fresh conversation (the previous one is in /resume)."
    )
    # …and by a path under an allowed one.
    await env.processor.on_message(inbound("tg", "owner", f"/dir {app}/sub"))
    assert await _sticky_cwd(env, resource) == f"{app}/sub"
    # /new keeps it.
    await env.processor.on_message(inbound("tg", "owner", "/new"))
    assert env.provider.last_agent_config == {"cwd": f"{app}/sub"}
    assert adapter.texts()[-1].endswith(f" · {app}/sub")


@pytest.mark.acceptance(spec="channels", scenario="/dir refuses a directory outside the allow-list")
async def test_dir_refuses_a_directory_outside_the_allow_list(
    env: ChannelEnv, tmp_path: Path
) -> None:
    app, lib = _dirs(tmp_path)
    resource, adapter = await _channel(env, [app, lib])

    await env.processor.on_message(inbound("tg", "owner", f"/dir {tmp_path}"))
    await env.processor.on_message(inbound("tg", "owner", f"/dir {app}/../../../"))

    for text in adapter.texts():
        assert "is not an allowed directory" in text
        assert f"Allowed: {app}, {lib}" in text
    assert await _sticky_cwd(env, resource) is None
    assert await env.active_conversation(resource) is None


async def test_an_allowed_directory_that_does_not_exist_is_refused(
    env: ChannelEnv, tmp_path: Path
) -> None:
    gone = str(tmp_path / "gone")
    resource, adapter = await _channel(env, [gone])

    await env.processor.on_message(inbound("tg", "owner", "/dir gone"))

    assert adapter.texts() == [f"⚠️ {gone} is not an existing directory."]
    assert await _sticky_cwd(env, resource) is None


async def test_an_empty_allow_list_says_how_to_add_one(env: ChannelEnv) -> None:
    _resource, adapter = await _channel(env, [])

    await env.processor.on_message(inbound("tg", "owner", "/dir /tmp"))

    assert adapter.texts() == [NO_DIRECTORIES]


async def test_bare_dir_offers_the_allow_list_and_a_tap_switches(
    env: ChannelEnv, tmp_path: Path
) -> None:
    app, lib = _dirs(tmp_path)
    resource, adapter = await _channel(env, [app, lib], buttons=True)

    await env.processor.on_message(inbound("tg", "owner", "/dir"))

    [(_chat, text, buttons)] = adapter.cards
    assert text.startswith("Current: Default directory\n")
    assert [(b.label, b.value) for b in buttons] == [
        (app, "dir:0"),
        (lib, "dir:1"),
        ("Default ✓", "dir:default"),
    ]

    await env.processor.on_callback(tap_event("tg", "owner", "dir:1", platform_message_id="c-1"))

    assert await _sticky_cwd(env, resource) == lib
    _chat, _mid, _text, buttons, _title = adapter.card_updates[-1]
    assert [b.value for b in buttons if b.selected] == ["dir:1"]

    await env.processor.on_callback(tap_event("tg", "owner", "dir:default"))
    assert await _sticky_cwd(env, resource) is None
    await env.processor.on_callback(tap_event("tg", "owner", "dir:9"))
    assert "no longer allowed" in adapter.texts()[-1]


async def test_bare_dir_without_buttons_lists_them(env: ChannelEnv, tmp_path: Path) -> None:
    app, lib = _dirs(tmp_path)
    _resource, adapter = await _channel(env, [app, lib])

    await env.processor.on_message(inbound("tg", "owner", "/dir"))

    assert adapter.texts() == [
        f"📁 Working directory: Default directory\nAllowed:\n1. {app}\n2. {lib}\n"
        "Send /dir <path|name> or /dir default."
    ]
