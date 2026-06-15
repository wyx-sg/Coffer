"""Channel-specific Kind wiring used by the composition root."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from coffer.application.channel.conversation_spec import validate_workspaces
from coffer.domain.channel.config import ChannelConfigModel
from coffer.domain.resource import Kind, ResourceRef

_REF_FIELDS = ("bot_token_ref", "app_secret_ref", "signing_secret_ref")


def _channel_credential_ref_extractor(config: dict[str, Any]) -> dict[str, str]:
    """Every `*_ref` field is a credential ref to probe before registration."""
    refs: dict[str, str] = {}
    for field in _REF_FIELDS:
        value = config.get(field)
        if isinstance(value, str) and value:
            refs[field] = value
    return refs


def _validate_default_agent(config: dict[str, Any], agent_keys: Callable[[], list[str]]) -> None:
    """The channel's default agent must name a registered agent.

    A stale value (e.g. the pre-ADR-024 ``builtin``) would otherwise be
    accepted at create/edit and only fail at turn time, deep inside a chat —
    where the owner can't tell why the bot went silent. Reject it loudly here
    instead. Skip when the registry is empty (can't validate) so a misconfigured
    registry never blocks all channel writes.
    """
    default_agent = config.get("default_agent")
    if not isinstance(default_agent, str) or not default_agent:
        return
    known = agent_keys()
    if known and default_agent not in known:
        raise ValueError(
            f"default_agent '{default_agent}' is not a registered agent "
            f"(known: {', '.join(sorted(known))})"
        )


def _make_validator(
    agent_keys: Callable[[], list[str]] | None,
) -> Callable[[dict[str, Any]], None]:
    def _validate_channel_config(config: dict[str, Any]) -> None:
        """Workspace directories must exist on disk at registration (the cwd
        allowlist is only useful if its entries are real), and the default
        agent must name a registered agent."""
        workspaces = [(w["name"], w["path"]) for w in config.get("workspaces", [])]
        validate_workspaces(workspaces, default=config.get("default_workspace"))
        if agent_keys is not None:
            _validate_default_agent(config, agent_keys)

    return _validate_channel_config


def make_channel_kind(
    on_delete: Callable[[ResourceRef], Awaitable[None]] | None = None,
    *,
    agent_keys: Callable[[], list[str]] | None = None,
) -> Kind:
    """Construct the `channel` Kind.

    ``on_delete`` is injected by the composition root: it evicts the channel
    from the runtime (stopping its adapter and, when it was the last SeaTalk
    channel, the callback listener) before the row — and, via FK cascade, the
    peer binding — is removed. Channel config holds only credential refs, so
    no audit redaction is needed.

    ``agent_keys`` (also injected by the composition root) lists the currently
    registered agent keys; when provided, a channel's ``default_agent`` is
    validated against it at create/edit so an unknown agent is rejected up front
    rather than failing silently on the first turn.
    """
    return Kind(
        name="channel",
        display_name="Channel",
        config_schema=ChannelConfigModel,
        on_delete=on_delete,
        credential_ref_extractor=_channel_credential_ref_extractor,
        validate_config=_make_validator(agent_keys),
    )
