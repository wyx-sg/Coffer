"""Channel-specific Kind wiring used by the composition root."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import Any

from coffer.domain.channel.config import ChannelConfigModel
from coffer.domain.errors import ConfigValidationError
from coffer.domain.resource import Kind, Resource
from coffer.domain.scope import Scope, is_active

_REF_FIELDS = ("bot_token_ref", "app_secret_ref", "signing_secret_ref", "tunnel_token_ref")

#: What the composition root injects to turn agent uids back into something a
#: person can read: every registered agent resource's ``uid`` mapped to its
#: ``name``. It decides nothing — the checks below compare uid to uid — it only
#: writes the refusals, so an owner is told "codex" and not a bare UUID.
AgentNames = Callable[[], Awaitable[Mapping[str, str]]]


def _channel_credential_ref_extractor(config: dict[str, Any]) -> dict[str, str]:
    """Every `*_ref` field is a credential ref to probe before registration."""
    refs: dict[str, str] = {}
    for field in _REF_FIELDS:
        value = config.get(field)
        if isinstance(value, str) and value:
            refs[field] = value
    return refs


def _default_agent_of(config: Mapping[str, Any]) -> str | None:
    """The uid of the agent a channel drives, straight off a raw config dict.

    Read raw rather than parsed because every caller here already holds a dict,
    and a row this cannot read is not one the adapter factory could start
    either. ``None`` is a channel bound to no agent: there is no fallback value
    to substitute, since a uid is minted per vault and no constant can name one.
    """
    value = config.get("default_agent")
    return value if isinstance(value, str) and value else None


def _label(uid: str, agent_names: Mapping[str, str]) -> str:
    """How one agent uid reads to the owner: its label, or the uid itself.

    A uid the registry does not know has no label to print, and printing it
    bare is the honest answer — that uid IS the whole of what the channel says
    about the agent it wants.
    """
    return agent_names.get(uid, uid)


def _scope_reads_as(routable: Iterable[str], agent_names: Mapping[str, str]) -> str:
    """How a rejected scope reads to the owner: the agents it names.

    One list, not two. While a scope held agent resource NAMES and a
    ``default_agent`` held an agent KEY, this had to print both the names and
    what they resolved to, or the refusal came out as the one message nobody
    could act on — the same string on both sides of an exclusion. Both sides
    are uids now, so there is one list and it is the list of labels.
    """
    return ", ".join(sorted(_label(uid, agent_names) for uid in routable))


def _validate_default_agent(
    config: Mapping[str, Any],
    scope: Scope | None,
    agent_names: Mapping[str, str],
) -> None:
    """The channel's default agent must name a registered agent the channel
    may actually drive.

    A stale value (an agent the owner deleted) would otherwise be accepted at
    edit time and only fail at turn time, deep inside a chat — where the owner
    can't tell why the bot went silent. Reject it loudly here instead. Skip the
    registration half when the registry is empty (can't validate) so a
    misconfigured registry never blocks all channel writes.

    ``scope`` names the agents the channel MAY route to (ADR
    per-agent-resource-scope) and ``default_agent`` names the one it routes to
    by default. Both are agent uids, so the comparison is
    :func:`~coffer.domain.scope.is_active` and nothing else — no map, no
    translation, no second vocabulary to get the direction of wrong in. An
    unrestricted scope (the create-time state, and any channel the owner never
    narrowed) admits every registered agent, so this is the behaviour the check
    always had. A NON-EMPTY one rejects a default outside it here rather than
    letting the channel start and then refuse every turn.

    An empty scope is deliberately NOT a rejection: it is the vault-wide
    meaning of dormant — this channel is off — and "off" must not also mean
    "frozen". A channel the owner switched off still has to accept a corrected
    bot token or tunnel token, so an edit to a dormant channel passes through
    untouched and the row simply stays dormant.

    A channel with NO default agent is likewise not a rejection: it is bound to
    nobody, which the runtime reads as "do not start", so there is nothing here
    for a scope to exclude.
    """
    default_agent = _default_agent_of(config)
    if default_agent is None:
        return
    if agent_names and default_agent not in agent_names:
        raise ValueError(
            f"default_agent '{default_agent}' is not a registered agent "
            f"(known: {', '.join(sorted(agent_names.values()))})"
        )
    routable = scope.agents if scope is not None else None
    if routable and not is_active(scope, default_agent):
        raise ValueError(
            f"default_agent '{_label(default_agent, agent_names)}' is outside this "
            f"channel's scope (may drive: {_scope_reads_as(routable, agent_names)})"
        )


def _make_scope_validator(
    agent_names: AgentNames | None,
) -> Callable[[Resource, Scope | None], Awaitable[None]]:
    """The scope write path's validator (``validate_scope_for``).

    ``_validate_default_agent`` holds an edited ``default_agent`` inside the
    channel's scope; this holds an edited scope around the channel's
    ``default_agent``. Without it the invariant was enforced on one path only,
    and narrowing a reach past the default agent was accepted silently — the
    runtime then refused to start the adapter and the owner's bot went dead with
    nothing but a log line to say why.

    It is ALWAYS wired now, which it could not be while the two sides were
    written in different vocabularies: back then a validator with no name→key
    map to compare through read every correct answer as wrong, so the whole
    check had to be absent rather than wrong whenever the reader was missing.
    A uid compares to a uid with nothing injected, so the invariant holds on
    every runtime — including the ones a test builds. ``agent_names`` is
    consulted only after the refusal is already decided, to write it in labels.

    An unrestricted scope (every agent) and an empty one (dormant — the channel
    is off, the universal meaning of an empty allow-list) are always allowed.
    Only a non-empty narrowing has to name the default agent. The message names
    both sides so the owner can see the two ways out: widen the scope, or
    change the default agent first.
    """

    async def _validate(resource: Resource, scope: Scope | None) -> None:
        routable = scope.agents if scope is not None else None
        if not routable:
            return
        # Read the same way the runtime's gate reads it, so the two cannot
        # disagree about which agent a channel drives.
        default_agent = _default_agent_of(resource.config)
        if default_agent is None or is_active(scope, default_agent):
            return
        names = await agent_names() if agent_names is not None else {}
        raise ValueError(
            f"scope (may drive: {_scope_reads_as(routable, names)}) excludes this "
            f"channel's default_agent '{_label(default_agent, names)}', which would "
            "leave it unable to drive anything. Add that agent to the scope, or "
            "change the channel's default_agent first."
        )

    return _validate


def _bound_elsewhere(config: Mapping[str, Any], local_machine_id: str | None) -> bool:
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


def _make_create_validator(
    agent_names: AgentNames | None,
    local_machine_id: str | None = None,
) -> Callable[[dict[str, Any]], Awaitable[None]]:
    """Registration-time validation (``validate_config``).

    The same question ``on_update_config`` asks, asked at the other end of the
    channel's life: does this ``default_agent`` name an agent this vault has,
    and — vacuously at create, where there is no scope yet — one this channel
    may drive. Without it a channel can be CREATED bound to an agent that does
    not exist and fails only at start time, in the daemon log, with the bot
    simply never answering.

    It is async, which ``validate_config`` did not used to be. That is the whole
    cost of the uid: while ``default_agent`` held an agent key, "is this
    registered" was answerable from an in-memory registry, and a uid is only
    answerable from the resource table. ``ResourceService.register`` awaits an
    awaitable result, as it does for every other hook.

    A brand-new channel has no scope — the row does not exist yet — so ``None``
    is passed for it. That is not a weaker check than the edit path's: an
    unscoped channel may drive every registered agent, which is precisely what a
    channel at create time is.
    """

    async def _validate_create(config: dict[str, Any]) -> None:
        if _bound_elsewhere(config, local_machine_id):
            # A channel handed straight to another machine names that machine's
            # agents, which are none of this registry's business — the same skip
            # the edit path makes, for the same reason.
            return
        names = await agent_names() if agent_names is not None else {}
        _validate_default_agent(config, None, names)

    return _validate_create


def _make_update_validator(
    agent_names: AgentNames | None,
    local_machine_id: str | None = None,
) -> Callable[[Resource, dict[str, Any]], Awaitable[None]]:
    """Update-time validation hook (``on_update_config``).

    An edit that re-binds the channel to an agent it may not drive, or to one
    that is not registered at all, would still pass shape validation and only
    fail (silently) at the next turn. So it is validated here, converting the
    resolver's ``ValueError`` into the ``ConfigValidationError`` the resource
    service surfaces to the caller.

    Unlike ``validate_config``, this hook is handed the resource being edited,
    so the channel's own scope comes with it — ``resource.scope``. It used to
    be handed a bare identifier and a separately-injected reader to look that
    scope up with; the hook's new signature makes the reader redundant and it
    is gone. It stays async because the labels for a refusal are read off the
    registry, and ``ResourceService`` already awaits an awaitable hook result.
    """

    async def _validate_update(resource: Resource, after: dict[str, Any]) -> None:
        if _bound_elsewhere(after, local_machine_id):
            # Including the edit that BINDS it elsewhere: handing a channel to
            # another machine must not be blocked by this machine's opinion of
            # an agent the other machine is the one to have.
            return
        names = await agent_names() if agent_names is not None else {}
        try:
            _validate_default_agent(after, resource.scope, names)
        except ValueError as e:
            raise ConfigValidationError(str(e)) from e

    return _validate_update


def make_channel_kind(
    on_delete: Callable[[Resource], Awaitable[None]] | None = None,
    *,
    agent_names: AgentNames | None = None,
    local_machine_id: str | None = None,
) -> Kind:
    """Construct the `channel` Kind.

    ``on_delete`` is injected by the composition root: it evicts the channel
    from the runtime (stopping its adapter and, when it was the last SeaTalk
    channel, the callback listener) before the row — and, via FK cascade, the
    peer binding — is removed. Channel config holds only credential refs, so
    no audit redaction is needed.

    ``agent_names`` (also injected by the composition root) maps every
    registered agent's uid to its name. It is the only reader this kind still
    needs, and it decides nothing: a channel's ``default_agent`` and its scope
    are both agent uids (ADR resource-identity-is-an-immutable-uid), so the
    checks compare them directly. What the map buys is a refusal an owner can
    act on — labels instead of UUIDs — plus the one question a uid cannot
    answer by itself: whether any agent is registered under it at all.

    Three injections became one. The kind used to take the registry's agent
    KEYS to check a ``default_agent`` against, a name→key map to compare a
    scope through, and a reader to fetch the edited channel's scope with. The
    first two existed because an agent answered to two names and this kind was
    where they met; the third because the update hook was handed an identifier
    instead of the row. All three are gone.

    Both write paths consult it and both are async, including
    ``validate_config``, which was synchronous while ``default_agent`` held an
    agent key an in-memory registry could answer for. A uid is only answerable
    from the resource table.

    The scope write path carries the same invariant from the other side
    (``validate_scope_for``), so the two paths cannot disagree: a channel's
    ``default_agent`` is inside its scope whichever of the two the user edits.

    ``local_machine_id`` is this machine's id (spec vault-sync "Derive machine
    identity from the host"). It buys exactly one thing: the agent checks above
    are skipped for a channel bound to a DIFFERENT machine. Those checks ask
    "will this channel be able to drive anything when it starts", and a channel
    this machine never starts has no answer to give — without the skip, a
    converged channel whose owner machine has an agent this one does not would
    be refused at the registry door every round, for a fault on nobody's
    machine.
    """
    return Kind(
        name="channel",
        display_name="Channel",
        config_schema=ChannelConfigModel,
        on_delete=on_delete,
        credential_ref_extractor=_channel_credential_ref_extractor,
        # Registration and edit run the same check from the two ends of a
        # channel's life, so a ``default_agent`` naming no registered agent is
        # refused wherever it is written rather than only failing at start time.
        validate_config=_make_create_validator(agent_names, local_machine_id),
        on_update_config=_make_update_validator(agent_names, local_machine_id),
        # The scope path's own pre-validation, the mirror of the check
        # ``on_update_config`` runs on the config path, so the invariant holds
        # no matter which of the two paths a write arrives on. It judges a
        # proposed scope against the channel's own stored ``default_agent``,
        # uid against uid.
        validate_scope_for=_make_scope_validator(agent_names),
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
