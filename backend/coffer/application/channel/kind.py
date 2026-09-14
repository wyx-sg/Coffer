"""Channel-specific Kind wiring used by the composition root."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from coffer.domain.channel.config import DEFAULT_AGENT, ChannelConfigModel
from coffer.domain.errors import ConfigValidationError
from coffer.domain.resource import Kind, Resource, ResourceRef
from coffer.domain.scope import Scope

_REF_FIELDS = ("bot_token_ref", "app_secret_ref", "signing_secret_ref", "tunnel_token_ref")


def _channel_credential_ref_extractor(config: dict[str, Any]) -> dict[str, str]:
    """Every `*_ref` field is a credential ref to probe before registration."""
    refs: dict[str, str] = {}
    for field in _REF_FIELDS:
        value = config.get(field)
        if isinstance(value, str) and value:
            refs[field] = value
    return refs


def _validate_default_agent(
    config: dict[str, Any],
    agent_keys: Callable[[], list[str]],
    scope: Scope | None = None,
) -> None:
    """The channel's default agent must name a registered agent the channel
    may actually drive.

    A stale value (e.g. the withdrawn ``builtin``) would otherwise be
    accepted at create/edit and only fail at turn time, deep inside a chat —
    where the owner can't tell why the bot went silent. Reject it loudly here
    instead. Skip when the registry is empty (can't validate) so a misconfigured
    registry never blocks all channel writes.

    ``scope`` is the channel's scope — it names the agents the channel MAY
    route to (ADR per-agent-resource-scope). An unrestricted scope (the
    create-time state, and any channel the owner never narrowed) admits every
    registered agent, so this is the behaviour the check always had. A
    NON-EMPTY one rejects a default outside it here rather than letting the
    channel start and then refuse every turn.

    An empty scope is deliberately NOT a rejection: it is the vault-wide
    meaning of dormant — this channel is off — and "off" must not also mean
    "frozen". A channel the owner switched off still has to accept a corrected
    bot token or tunnel token, so an edit to a dormant channel passes through
    untouched and the row simply stays dormant.
    """
    default_agent = config.get("default_agent")
    if not isinstance(default_agent, str) or not default_agent:
        return
    routable = scope.agents if scope is not None else None
    if routable and default_agent not in routable:
        raise ValueError(
            f"default_agent '{default_agent}' is outside this channel's scope "
            f"(may route to: {', '.join(sorted(routable))})"
        )
    known = agent_keys()
    if known and default_agent not in known:
        raise ValueError(
            f"default_agent '{default_agent}' is not a registered agent "
            f"(known: {', '.join(sorted(known))})"
        )


def _validate_channel_scope(resource: Resource, scope: Scope | None) -> None:
    """The other half of the same invariant, on the scope write path.

    ``_validate_default_agent`` holds an edited ``default_agent`` inside the
    channel's scope; this holds an edited scope around the channel's
    ``default_agent``. Without it the invariant was enforced on one path only,
    and narrowing a reach past the default agent was accepted silently — the
    runtime then refused to start the adapter and the owner's bot went dead with
    nothing but a log line to say why (``Kind.validate_scope_for``).

    An unrestricted scope (every agent) and an empty one (dormant — the channel
    is off, the universal meaning of an empty allow-list) are always allowed.
    Only a non-empty narrowing has to name the default agent. The message names
    both sides so the owner can see the two ways out: widen the scope, or
    change the default agent first.
    """
    routable = scope.agents if scope is not None else None
    if not routable:
        return
    # Read the same way the runtime's gate reads it, so the two cannot disagree
    # about which agent a channel with no explicit default drives.
    default_agent = str(resource.config.get("default_agent") or DEFAULT_AGENT)
    if default_agent not in routable:
        raise ValueError(
            f"scope (may drive: {', '.join(sorted(routable))}) excludes this channel's "
            f"default_agent '{default_agent}', which would leave it unable to drive "
            "anything. Add that agent to the scope, or change the channel's "
            "default_agent first."
        )


def _make_validator(
    agent_keys: Callable[[], list[str]] | None,
) -> Callable[[dict[str, Any]], None]:
    def _validate_channel_config(config: dict[str, Any]) -> None:
        """The default agent must name a registered agent."""
        if agent_keys is not None:
            _validate_default_agent(config, agent_keys)

    return _validate_channel_config


def _make_update_validator(
    agent_keys: Callable[[], list[str]] | None,
    scope_of: Callable[[ResourceRef], Awaitable[Scope | None]] | None,
) -> Callable[[ResourceRef, dict[str, Any], dict[str, Any]], Awaitable[None]] | None:
    """Update-time validation hook (``on_update_config``).

    An edit that re-binds the channel to an unknown ``default_agent`` would
    still pass shape validation and only fail (silently) at the next turn. So
    when an ``agent_keys`` provider is injected we also validate
    ``default_agent`` here, converting the resolver's ``ValueError`` into the
    ``ConfigValidationError`` the resource service surfaces to the caller.
    Returns ``None`` when no provider is injected (no hook wired — backward
    compatible).

    Unlike ``validate_config``, this hook knows WHICH channel is being edited,
    so it can also read that channel's scope (``scope_of``, injected by the
    composition root) and hold the edit to it. It is async for exactly that
    reason — the scope lives in the resource row — and ``ResourceService``
    already awaits an awaitable hook result.
    """
    if agent_keys is None:
        return None

    async def _validate_update(
        ref: ResourceRef, _before: dict[str, Any], after: dict[str, Any]
    ) -> None:
        scope = await scope_of(ref) if scope_of is not None else None
        try:
            _validate_default_agent(after, agent_keys, scope)
        except ValueError as e:
            raise ConfigValidationError(str(e)) from e

    return _validate_update


def make_channel_kind(
    on_delete: Callable[[ResourceRef], Awaitable[None]] | None = None,
    *,
    agent_keys: Callable[[], list[str]] | None = None,
    scope_of: Callable[[ResourceRef], Awaitable[Scope | None]] | None = None,
) -> Kind:
    """Construct the `channel` Kind.

    ``on_delete`` is injected by the composition root: it evicts the channel
    from the runtime (stopping its adapter and, when it was the last SeaTalk
    channel, the callback listener) before the row — and, via FK cascade, the
    peer binding — is removed. Channel config holds only credential refs, so
    no audit redaction is needed.

    ``agent_keys`` (also injected by the composition root) lists the currently
    registered agent keys; when provided, a channel's ``default_agent`` is
    validated against it at BOTH create (``validate_config``) and edit
    (``on_update_config``) so an unknown agent is rejected up front rather than
    failing silently on the first turn. ``scope_of`` reads the channel's own
    per-agent scope, so the edit path also holds ``default_agent`` inside the
    agents this channel may drive; create needs no such reader (a brand-new
    channel is unscoped).

    The scope write path carries the same invariant from the other side
    (``validate_scope_for``), and needs nothing injected at all, so the two
    paths cannot disagree: a channel's ``default_agent`` is inside its scope
    whichever of the two the user edits.
    """
    return Kind(
        name="channel",
        display_name="Channel",
        config_schema=ChannelConfigModel,
        on_delete=on_delete,
        credential_ref_extractor=_channel_credential_ref_extractor,
        validate_config=_make_validator(agent_keys),
        on_update_config=_make_update_validator(agent_keys, scope_of),
        # The scope path's own pre-validation, the mirror of the check
        # ``on_update_config`` runs on the config path. Needs nothing injected —
        # it judges a proposed scope against the channel's own stored
        # ``default_agent`` — so it is always wired, and the invariant holds no
        # matter which of the two paths a write arrives on.
        validate_scope_for=_validate_channel_scope,
        # Per-agent scope, read the other way round from every other kind
        # (ADR per-agent-resource-scope). Elsewhere scope names the agents a resource is
        # DELIVERED to; a channel is not consumed by an agent at all — it is an
        # inbound surface — so its scope names **the agents this channel may
        # drive**. Two enforcement seams: `/agent` lists, offers and accepts
        # only agents inside the scope, and ``default_agent`` is held inside it
        # on every write path — config (``on_update_config``) and scope
        # (``validate_scope_for``) alike. An empty allow-list is dormant: the
        # channel routes to no agent, so the runtime does not start its adapter
        # at all rather than letting it accept turns it would have to refuse one
        # by one. Dormant is off, never frozen — its config stays editable, so
        # neither validator judges an empty allow-list.
        supports_scope=True,
    )
