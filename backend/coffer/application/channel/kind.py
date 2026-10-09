"""Channel-specific Kind wiring used by the composition root."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import Any

from coffer.domain.channel.config import ChannelConfigModel
from coffer.domain.errors import ConfigValidationError
from coffer.domain.resource import Kind, Resource
from coffer.domain.scope import Scope, is_active
from coffer.domain.vault.layout import StorageClass

_REF_FIELDS = ("bot_token_ref", "app_secret_ref")

#: What the composition root injects to turn agent uids back into something a
#: person can read: every registered agent resource's ``uid`` mapped to its
#: ``name``. It decides nothing — the checks below compare uid to uid — it only
#: writes the refusals, so an owner is told "codex" and not a bare UUID.
AgentNames = Callable[[], Awaitable[Mapping[str, str]]]


def _channel_secret_ref_extractor(config: dict[str, Any]) -> dict[str, str]:
    """Every `*_ref` field is a secret ref to probe before registration."""
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

    A switched-off channel stays editable: it still has to accept a corrected
    bot token or app secret ref, and nothing here looks at ``enabled``.

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
    if scope is not None and scope.agents and not is_active(scope, default_agent):
        raise ValueError(
            f"default_agent '{_label(default_agent, agent_names)}' is outside this "
            f"channel's scope (may drive: {_scope_reads_as(scope.agents, agent_names)})"
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

    An unrestricted scope (every agent) is always allowed; an empty one never
    reaches here (``validate_scope`` refuses it first). Only a narrowing has to
    name the default agent. The message names
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


def _make_create_validator(
    agent_names: AgentNames | None,
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
        names = await agent_names() if agent_names is not None else {}
        _validate_default_agent(config, None, names)

    return _validate_create


def _make_update_validator(
    agent_names: AgentNames | None,
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
) -> Kind:
    """Construct the `channel` Kind.

    ``on_delete`` is injected by the composition root: it evicts the channel
    from the runtime (stopping its adapter and, for SeaTalk, closing its
    websocket connection) before the row — and, as a follower
    of the resource's lifecycle, the peer pairings document — is removed.
    Channel config holds only secret refs, so no audit redaction is needed.

    ``agent_names`` (also injected by the composition root) maps every
    registered agent's uid to its name. It is the only reader this kind still
    needs, and it decides nothing: a channel's ``default_agent`` and its scope
    are both agent uids (ADR identity-is-the-uid-inside-the-file), so the
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

    A channel is machine-local (ADR channels-are-machine-local-resources): its
    file is under ``local/`` like an agent's, never committed, never synced, so
    the agents its ``default_agent`` and scope name are always this machine's.
    """
    return Kind(
        free_name=True,
        name="channel",
        display_name="Channel",
        config_schema=ChannelConfigModel,
        # A bot identity tolerates one consumer, and everything a channel names
        # — its agents, its directories, its pairings — is this machine's, so
        # it is filed under ``local/`` and never travels
        # (ADR channels-are-machine-local-resources).
        storage=StorageClass.LOCAL,
        on_delete=on_delete,
        secret_ref_extractor=_channel_secret_ref_extractor,
        # Registration and edit run the same check from the two ends of a
        # channel's life, so a ``default_agent`` naming no registered agent is
        # refused wherever it is written rather than only failing at start time.
        validate_config=_make_create_validator(agent_names),
        on_update_config=_make_update_validator(agent_names),
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
        # drive**. Two enforcement seams: `/new <agent>` lists and accepts
        # only agents inside the scope, and ``default_agent`` is held inside it
        # on every write path — config (``on_update_config``) and scope
        # (``validate_scope_for``) alike. A channel that should drive nothing is
        # switched off, not scoped to nobody; an empty allow-list is refused.
        supports_scope=True,
    )
