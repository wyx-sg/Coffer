"""Channel-specific Kind wiring used by the composition root."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from coffer.application.channel.agent_vocabulary import drives, scope_agent_keys
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
    types_by_name: Mapping[str, str] | None = None,
) -> None:
    """The channel's default agent must name a registered agent the channel
    may actually drive.

    A stale value (e.g. the withdrawn ``builtin``) would otherwise be
    accepted at create/edit and only fail at turn time, deep inside a chat —
    where the owner can't tell why the bot went silent. Reject it loudly here
    instead. Skip when the registry is empty (can't validate) so a misconfigured
    registry never blocks all channel writes.

    ``scope`` names the agents the channel MAY route to (ADR
    per-agent-resource-scope) — as resource NAMES, while ``default_agent`` is an
    agent KEY. ``types_by_name`` translates, and without it the scope half of
    the check is skipped rather than run in the wrong vocabulary: comparing the
    two directly rejected every correctly-narrowed scope and admitted only the
    agent key, which the reach picker then had to render as a name registered
    nowhere. An unrestricted scope (the
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
    if routable and types_by_name is not None and not drives(scope, default_agent, types_by_name):
        raise ValueError(
            f"default_agent '{default_agent}' is outside this channel's scope "
            f"({_scope_reads_as(scope, routable, types_by_name)})"
        )
    known = agent_keys()
    if known and default_agent not in known:
        raise ValueError(
            f"default_agent '{default_agent}' is not a registered agent "
            f"(known: {', '.join(sorted(known))})"
        )


def _scope_reads_as(
    scope: Scope | None, routable: list[str], types_by_name: Mapping[str, str]
) -> str:
    """How a rejected scope reads to the owner: the names, and what they drive.

    Both halves, because a scope names agent RESOURCES and the refusal is about
    agent KEYS, and printing only the names produced the one message nobody can
    act on: "scope (may drive: claude_code) excludes this channel\'s
    default_agent \'claude_code\'" — the same string on both sides of an
    exclusion. Saying what the names resolve to turns that into the sentence it
    always meant: this name drives no registered agent.
    """
    keys = scope_agent_keys(scope, types_by_name) or []
    names = ", ".join(sorted(routable))
    return f"may drive: {names} → {', '.join(keys) if keys else 'no registered agent'}"


def _make_scope_validator(
    agent_types: Callable[[], Awaitable[Mapping[str, str]]] | None,
) -> Callable[[Resource, Scope | None], Awaitable[None]] | None:
    """The scope write path's validator, with the translation it needs.

    Async because the name→key map is read off the resource service, and absent
    entirely when no reader is wired — the same convention ``on_update_config``
    already follows. A scope names agent RESOURCES and a ``default_agent`` is an
    agent KEY, so without the map there is no check to run, only a comparison
    between two vocabularies that reads every correct answer as wrong. The
    composition root always injects one.
    """
    if agent_types is None:
        return None

    async def _validate(resource: Resource, scope: Scope | None) -> None:
        _validate_channel_scope(resource, scope, await agent_types())

    return _validate


def _validate_channel_scope(
    resource: Resource, scope: Scope | None, types_by_name: Mapping[str, str]
) -> None:
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
    if not drives(scope, default_agent, types_by_name):
        raise ValueError(
            f"scope ({_scope_reads_as(scope, routable, types_by_name)}) excludes this "
            f"channel's default_agent '{default_agent}', which would leave it unable to "
            "drive anything. Add that agent to the scope, or change the channel's "
            "default_agent first."
        )


def _bound_elsewhere(config: dict[str, Any], local_machine_id: str | None) -> bool:
    """Whether this channel names a machine that is not this one.

    Such a channel is not this machine's to judge. Its adapter starts on the
    machine it names, its agents are that machine's agents, and the document
    reached this registry only because the vault converges — refusing it here
    would hold a perfectly good document out of the vault for failing a
    precondition it was never meant to satisfy.

    Unbound (``None``) is NOT elsewhere: an unbound channel is one nobody has
    placed yet, and it is validated like any other so that binding it here is a
    single click rather than a click and a rejection.
    """
    if local_machine_id is None:
        return False
    runs_on = config.get("runs_on")
    return isinstance(runs_on, str) and bool(runs_on) and runs_on != local_machine_id


def _make_validator(
    agent_keys: Callable[[], list[str]] | None,
    local_machine_id: str | None = None,
) -> Callable[[dict[str, Any]], None]:
    def _validate_channel_config(config: dict[str, Any]) -> None:
        """The default agent must name an agent registered on the machine that
        runs this channel — which is this one, or none of our business."""
        if agent_keys is not None and not _bound_elsewhere(config, local_machine_id):
            _validate_default_agent(config, agent_keys)

    return _validate_channel_config


def _make_update_validator(
    agent_keys: Callable[[], list[str]] | None,
    scope_of: Callable[[ResourceRef], Awaitable[Scope | None]] | None,
    local_machine_id: str | None = None,
    agent_types: Callable[[], Awaitable[Mapping[str, str]]] | None = None,
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
        if _bound_elsewhere(after, local_machine_id):
            # Including the edit that BINDS it elsewhere: handing a channel to
            # another machine must not be blocked by this machine's opinion of
            # an agent the other machine is the one to have.
            return
        scope = await scope_of(ref) if scope_of is not None else None
        types = await agent_types() if agent_types is not None else None
        try:
            _validate_default_agent(after, agent_keys, scope, types)
        except ValueError as e:
            raise ConfigValidationError(str(e)) from e

    return _validate_update


def make_channel_kind(
    on_delete: Callable[[ResourceRef], Awaitable[None]] | None = None,
    *,
    agent_keys: Callable[[], list[str]] | None = None,
    scope_of: Callable[[ResourceRef], Awaitable[Scope | None]] | None = None,
    agent_types: Callable[[], Awaitable[Mapping[str, str]]] | None = None,
    local_machine_id: str | None = None,
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
    (``validate_scope_for``), so the two paths cannot disagree: a channel's
    ``default_agent`` is inside its scope whichever of the two the user edits.
    ``agent_types`` is what both of them compare WITH — the registry's
    name→key map, because a scope names agent resources and a ``default_agent``
    names an agent key (``agent_vocabulary``). Each check is absent rather than
    wrong when its reader is not wired.

    ``local_machine_id`` is this machine's id (spec vault-sync "Identity is
    derived"). It buys exactly one thing: the agent checks above are skipped for
    a channel bound to a DIFFERENT machine. Those checks ask "will this channel
    be able to drive anything when it starts", and a channel this machine never
    starts has no answer to give — without the skip, a converged channel whose
    owner machine has an agent this one does not would be refused at the
    registry door every round, for a fault on nobody's machine.
    """
    return Kind(
        name="channel",
        display_name="Channel",
        config_schema=ChannelConfigModel,
        on_delete=on_delete,
        credential_ref_extractor=_channel_credential_ref_extractor,
        validate_config=_make_validator(agent_keys, local_machine_id),
        on_update_config=_make_update_validator(
            agent_keys, scope_of, local_machine_id, agent_types
        ),
        # The scope path's own pre-validation, the mirror of the check
        # ``on_update_config`` runs on the config path, so the invariant holds
        # no matter which of the two paths a write arrives on. It judges a
        # proposed scope against the channel's own stored ``default_agent`` —
        # and needs ``agent_types`` to do it, because the two are written in
        # different vocabularies (``agent_vocabulary``).
        validate_scope_for=_make_scope_validator(agent_types),
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
