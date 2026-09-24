"""make_channel_kind: Kind wiring + credential-ref extraction."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from coffer.application.channel.kind import make_channel_kind
from coffer.domain.channel.config import ChannelConfigModel
from coffer.domain.errors import ConfigValidationError
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope

_NOW = datetime(2026, 9, 13, tzinfo=UTC)

#: The registry as the kind reads it: agent UIDS on the left, the labels a
#: refusal is written in on the right. Both a scope and a ``default_agent``
#: name the LEFT column now, so the map decides nothing — it is here so a
#: rejection says "codex" instead of a UUID, and so "is anything registered
#: under this uid at all" has an answer.
_CLAUDE = "uid-of-claude-code"
_CODEX = "uid-of-codex"
_AGENTS = {_CLAUDE: "claude-code", _CODEX: "codex"}


async def _agent_names() -> dict[str, str]:
    return _AGENTS


def test_kind_named_channel_with_config_schema():
    kind = make_channel_kind()
    assert kind.name == "channel"
    assert kind.display_name == "Channel"
    assert kind.config_schema is ChannelConfigModel


def test_generic_create_allowed_defaults_true():
    assert make_channel_kind().generic_create_allowed is True


def test_on_delete_defaults_none_and_is_passed_through():
    assert make_channel_kind().on_delete is None

    async def evict(resource: Resource) -> None:  # pragma: no cover - never awaited
        pass

    assert make_channel_kind(on_delete=evict).on_delete is evict


def test_extractor_pulls_telegram_bot_token_ref():
    extractor = make_channel_kind().credential_ref_extractor
    assert extractor is not None
    refs = extractor({"channel_type": "telegram", "bot_token_ref": "channel/tg/bot-token"})
    assert refs == {"bot_token_ref": "channel/tg/bot-token"}


def test_extractor_pulls_the_seatalk_app_secret_ref_only():
    """A webhook-era key a document may still carry is not a ref to probe:
    nothing reads it, so nothing must be made to exist for it."""
    extractor = make_channel_kind().credential_ref_extractor
    assert extractor is not None
    refs = extractor(
        {
            "channel_type": "seatalk",
            "app_id": "app-123",
            "app_secret_ref": "channel/st/app-secret",
            "signing_secret_ref": "channel/st/signing-secret",
            "tunnel_token_ref": "channel/st/tunnel-token",
        }
    )
    assert refs == {"app_secret_ref": "channel/st/app-secret"}


def test_extractor_skips_missing_empty_and_non_string_values():
    extractor = make_channel_kind().credential_ref_extractor
    assert extractor is not None
    refs = extractor(
        {
            "channel_type": "telegram",
            "bot_token_ref": "",  # empty: skipped
            "app_secret_ref": 123,  # non-string: skipped
        }
    )
    assert refs == {}
    assert extractor({}) == {}


# -- default_agent validation at REGISTRATION ---------------------------------
# Every check this kind makes is about ANOTHER resource — does this uid name a
# registered agent, does this channel's scope admit it — and only the resource
# table can answer that, from a coroutine. So ``validate_config`` is async here,
# which it did not have to be while ``default_agent`` held an agent key an
# in-memory registry could answer for.


def _create_validate(config: dict, agent_names=_agent_names, local_machine_id=None):
    validator = make_channel_kind(
        agent_names=agent_names, local_machine_id=local_machine_id
    ).validate_config
    assert validator is not None
    result = validator(config)
    assert result is not None  # async: ResourceService awaits it
    asyncio.run(result)


def test_create_accepts_a_registered_default_agent():
    _create_validate({"channel_type": "telegram", "default_agent": _CODEX})


@pytest.mark.acceptance(
    spec="channels", scenario="a channel bound to an agent that does not exist is refused"
)
def test_create_rejects_a_default_agent_naming_no_registered_agent():
    # Without this a channel can be CREATED bound to an agent that does not
    # exist, and the only symptom is a bot that never answers.
    with pytest.raises(ValueError, match="not a registered agent"):
        _create_validate({"channel_type": "telegram", "default_agent": "uid-of-nothing"})


def test_create_accepts_a_channel_that_names_no_agent_yet():
    _create_validate({"channel_type": "telegram"})


def test_create_skips_a_channel_bound_to_another_machine():
    # Its agents are that machine's business; refusing the document here would
    # hold it out of the vault for a fault on nobody's machine.
    _create_validate(
        {"channel_type": "telegram", "default_agent": "uid-of-nothing", "runs_on": "other"},
        local_machine_id="mine",
    )


def test_create_skips_when_registry_empty():
    async def _none() -> dict[str, str]:
        return {}

    _create_validate({"channel_type": "telegram", "default_agent": "uid-of-nothing"}, _none)


# -- default_agent validation on UPDATE ---------------------------------------


def _update_validate(config: dict, agent_names=_agent_names, scope=None):
    hook = make_channel_kind(agent_names=agent_names).on_update_config
    assert hook is not None
    resource = _channel({"channel_type": "telegram"}, scope=scope)
    # Async because it reads the registry for the labels a refusal needs;
    # ResourceService awaits an awaitable hook result.
    asyncio.run(hook(resource, config))


def test_update_accepts_registered_default_agent():
    _update_validate({"channel_type": "telegram", "default_agent": _CODEX})


def test_update_rejects_unregistered_default_agent():
    with pytest.raises(ConfigValidationError, match="not a registered agent"):
        _update_validate({"channel_type": "telegram", "default_agent": "uid-of-nothing"})


def test_the_unregistered_refusal_lists_the_agents_by_label():
    # The uid it refused is unprintable to a person; the ones it knows are not.
    with pytest.raises(ConfigValidationError, match="claude-code, codex"):
        _update_validate({"channel_type": "telegram", "default_agent": "uid-of-nothing"})


def test_the_update_hook_is_always_wired():
    # Not "absent rather than wrong" any more. Both sides of every comparison
    # are agent uids, so the check needs nothing injected to be correct — the
    # registry is consulted only to write the refusal.
    assert make_channel_kind().on_update_config is not None


def test_update_skips_when_registry_empty():
    # An empty registry can't say what is registered; never block all channel
    # writes over it.
    async def _none() -> dict[str, str]:
        return {}

    _update_validate({"channel_type": "telegram", "default_agent": "uid-of-nothing"}, _none)


def test_update_skips_when_default_agent_absent():
    # A channel bound to no agent: nothing to check, and the runtime is what
    # refuses to start it.
    _update_validate({"channel_type": "telegram"})


# -- per-agent scope (ADR per-agent-resource-scope) ----------------------------------------------
# Read the other way round from every other kind: a channel is an inbound
# surface no agent consumes, so its scope names the agents the channel may
# DRIVE. ``default_agent`` is held inside it on every write path; the `/agent`
# narrowing is covered in test_agent_routing.py.


def test_channel_kind_declares_scope():
    assert make_channel_kind().supports_scope is True


def test_channel_kind_has_no_starting_scope():
    # Unlike ``provider``, a new channel is unscoped — every agent — so
    # nothing changes for a channel created before scope reached this kind.
    assert make_channel_kind().default_scope is None


@pytest.mark.acceptance(
    spec="channels",
    scenario="a channel may only route to the agents in its scope",
)
def test_update_rejects_default_agent_outside_scope():
    with pytest.raises(ConfigValidationError, match="outside this channel's scope"):
        _update_validate(
            {"channel_type": "telegram", "default_agent": _CLAUDE},
            scope=Scope(agents=[_CODEX]),
        )


def test_update_accepts_default_agent_inside_scope():
    _update_validate(
        {"channel_type": "telegram", "default_agent": _CODEX}, scope=Scope(agents=[_CODEX])
    )


def test_update_unscoped_channel_admits_every_registered_agent():
    # scope None is the pre-scope behaviour and must stay untouched.
    _update_validate({"channel_type": "telegram", "default_agent": _CLAUDE}, scope=None)


@pytest.mark.acceptance(
    spec="channels",
    scenario="edit a dormant channel's configuration",
)
def test_update_on_a_dormant_channel_is_allowed():
    # ``scope == []`` means the channel is OFF, the same as for every other
    # kind — it must not also mean frozen, or a channel the owner deliberately
    # switched off could never have its bot token corrected.
    _update_validate({"channel_type": "telegram", "default_agent": _CLAUDE}, scope=Scope(agents=[]))


# -- the same invariant on the SCOPE write path (``validate_scope_for``) -------
# The config path holds an edited ``default_agent`` inside the scope; this holds
# an edited scope around the ``default_agent``. Both exist so the inconsistent
# state — a channel scoped away from the agent it drives — cannot be stored at
# all, whichever path the write arrives on.


def _channel(config: dict, *, scope: Scope | None = None) -> Resource:
    return Resource(
        id=1,
        uid="uid-of-the-channel",
        kind="channel",
        name="tg",
        description=None,
        config=config,
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
        scope=scope,
    )


def _validate_scope(scope, config=None, agent_names=_agent_names):
    hook = make_channel_kind(agent_names=agent_names).validate_scope_for
    assert hook is not None
    resource = _channel(config if config is not None else {"channel_type": "telegram"})
    # Async because the labels for a refusal are read off the registry;
    # ResourceService awaits an awaitable hook result.
    asyncio.run(hook(resource, scope))


def test_the_scope_hook_is_always_wired():
    # It used to be absent whenever its name→key map was not injected, because
    # without the map it compared two vocabularies and read every correct
    # answer as wrong. A uid compares to a uid with nothing injected, so the
    # invariant now holds on every runtime — including one a test builds.
    assert make_channel_kind().validate_scope_for is not None
    assert make_channel_kind(agent_names=_agent_names).validate_scope_for is not None


@pytest.mark.acceptance(
    spec="channels",
    scenario="reject narrowing a channel's scope past its default agent",
)
def test_scope_narrowed_past_the_default_agent_is_rejected():
    with pytest.raises(ValueError, match="unable to drive anything"):
        _validate_scope(
            Scope(agents=[_CODEX]), {"channel_type": "telegram", "default_agent": _CLAUDE}
        )


def test_the_refusal_names_both_sides_in_labels():
    # Both sides, so the owner can see the two ways out of it — and both as
    # labels, because one list of uids is not a sentence anybody can act on.
    with pytest.raises(ValueError, match=r"may drive: codex.*default_agent 'claude-code'"):
        _validate_scope(
            Scope(agents=[_CODEX]), {"channel_type": "telegram", "default_agent": _CLAUDE}
        )


def test_a_scope_entry_naming_no_registered_agent_prints_as_itself():
    # There is no label to print for a uid the registry does not know, and the
    # uid IS the whole of what the row says. Printing it bare beats inventing.
    with pytest.raises(ValueError, match="uid-of-a-deleted-agent"):
        _validate_scope(
            Scope(agents=["uid-of-a-deleted-agent"]),
            {"channel_type": "telegram", "default_agent": _CLAUDE},
        )


def test_scope_containing_the_default_agent_is_accepted():
    _validate_scope(
        Scope(agents=[_CLAUDE, _CODEX]), {"channel_type": "telegram", "default_agent": _CLAUDE}
    )


def test_the_invariant_holds_with_no_registry_wired():
    # The check itself needs nothing injected: uid against uid. Only the
    # wording of the refusal degrades, to the uids themselves.
    hook = make_channel_kind().validate_scope_for
    assert hook is not None
    resource = _channel({"channel_type": "telegram", "default_agent": _CLAUDE})
    with pytest.raises(ValueError, match=_CLAUDE):
        asyncio.run(hook(resource, Scope(agents=[_CODEX])))


def test_a_channel_naming_no_agent_has_nothing_for_a_scope_to_exclude():
    _validate_scope(Scope(agents=[_CODEX]), {"channel_type": "telegram"})


@pytest.mark.acceptance(
    spec="channels",
    scenario="a channel scoped to no agent is dormant",
)
def test_the_dormant_scope_is_always_accepted():
    _validate_scope(Scope(agents=[]), {"channel_type": "telegram", "default_agent": _CLAUDE})


def test_clearing_the_scope_is_always_accepted():
    _validate_scope(None, {"channel_type": "telegram", "default_agent": _CLAUDE})
