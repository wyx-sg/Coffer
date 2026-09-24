"""Which channels this machine runs — the three gates, and only the gates.

``ChannelRuntime`` owns lifecycle: start an adapter, stop it, keep the
websocket connection in step. This module owns the question
it asks first, every tick — *which channels are mine to run?* — and the answer
has three parts, each a different kind of fact:

1. **enabled** — is this resource live at all, here.
2. **the machine binding** — is this channel's `runs_on` this machine (spec
   channels "Bind each channel to the one machine that runs it"). This one is about somebody else's
   machine, which is why it comes ahead of the third.
3. **routing** — does this channel name an agent it may actually drive (ADR
   per-agent-resource-scope, read inverted for this kind).

They live together because they are one predicate to the reconciler and three
separate arguments to a reader, and because the second one is new: a channel
travels between machines now, so the resource table is no longer a private list
and "enabled here" stopped being the whole answer.

The gate keeps a little memory (``Gate``), and it is memory about *reporting*
rather than about state: a channel bound elsewhere stays bound elsewhere, so
saying so every two seconds would bury the daemon log under a fact that is not
changing.

**This is also the one place an agent uid becomes an agent key.** See
``Routing``.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from coffer.application.channel.runtime_supervision import Desired
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope, is_active

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.resource_service import ResourceService

_logger = logging.getLogger(__name__)

#: Where an agent resource keeps the key the turn platform routes on. Read as a
#: raw string rather than through ``AgentConfig``: the channel kind may not
#: import the agent kind (the cross-kind import contract), and this needs no
#: judgement about the value anyway. A uid whose row carries no usable key
#: resolves to nothing, which is the right answer for an agent this vault
#: cannot route to.
_AGENT_KEY = "type"


@dataclass(frozen=True)
class Routing:
    """What the runtime stamps onto a started channel's binding.

    This is the ONE boundary where an agent **uid** becomes an agent **key**,
    and it is here because this is the only place the resource row and the
    running adapter meet. Above it — the channel's ``default_agent``, its
    ``scope``, every validator in ``kind.py`` — an agent is named by its uid,
    because those are references to an agent resource and a reference has to
    survive the owner renaming it. Below it — ``/agent``'s listing and card,
    the sticky ``preferred_agent`` column, ``conversation_spec``, the turn's own
    routing — an agent is named by the key the turn platform dispatches on,
    because that is the vocabulary the platform, and the user typing
    ``/agent codex``, actually speak.

    Translating once, here, is what makes a second vocabulary harmless. It was
    harmful when the two met in three places at once: each of them compared a
    scope written in one to a default written in the other, and each read a
    correctly-narrowed scope as excluding the channel's own agent. There is one
    crossing now, it runs one way, and nothing downstream of it can compare a
    uid to a key because nothing downstream of it has a uid.
    """

    #: The agent key the channel routes to by default.
    default_agent: str
    #: The channel's scope with every agent uid rewritten as that agent's key,
    #: or ``None`` when the channel may drive anything.
    agent_scope: Scope | None

    def to_json(self) -> dict[str, Any]:
        """The part of a binding the runtime diffs a running channel against."""
        return {
            "default_agent": self.default_agent,
            "scope": self.agent_scope.to_json() if self.agent_scope is not None else None,
        }


def _agent_keys_by_uid(agents: Iterable[Resource]) -> dict[str, str]:
    """Every registered agent's uid mapped to the key the turn platform uses."""
    out: dict[str, str] = {}
    for resource in agents:
        agent_key = resource.config.get(_AGENT_KEY)
        if isinstance(agent_key, str) and agent_key:
            out[resource.uid] = agent_key
    return out


def _scope_as_keys(scope: Scope | None, keys_by_uid: Mapping[str, str]) -> Scope | None:
    """``scope`` rewritten into agent keys, for the readers below the binding.

    A uid the registry does not know is dropped rather than carried through: it
    maps to no key, so it can admit no agent, and keeping it would only let it
    masquerade as one in an error message. Dropping NARROWS — an allow-list of
    one unknown agent becomes an empty one, which admits nothing — so this
    cannot widen a channel's reach, only close it. An unrestricted scope stays
    unrestricted; it is never turned into a list.
    """
    if scope is None or scope.agents is None:
        return None
    return Scope(agents=sorted({keys_by_uid[uid] for uid in scope.agents if uid in keys_by_uid}))


@dataclass
class Gate:
    """The three gates, plus this machine's identity and what it has reported.

    ``machine_id`` is resolved once and kept: it is derived from the host and
    cannot change while the daemon runs, and deriving it may shell out to
    ``ioreg``.

    ``None`` — no provider wired — means there is no machine to compare a
    binding against, so the binding gate is skipped and every enabled channel
    runs. That is a test convenience, not a fallback: the composition root
    always injects one, so the only runtime that can be ungated is one built by
    a test that never had a second machine to fight with.
    """

    machine_id_provider: Callable[[], Awaitable[str]] | None = None
    _machine_id: str | None = None
    #: The binding of each channel already reported as not this machine's.
    _foreign: dict[str, object] = field(default_factory=dict)
    #: What each channel the last pass found live routes to, keyed by name.
    #: Read back by the runtime, which stamps it onto the binding at start — so
    #: a scope edit reaches `/agent` within one tick rather than at the next
    #: daemon restart.
    routing: dict[str, Routing] = field(default_factory=dict)

    async def machine_id(self) -> str | None:
        """This machine's id, or ``None`` when no provider is wired."""
        if self.machine_id_provider is None:
            return None
        if self._machine_id is None:
            self._machine_id = await self.machine_id_provider()
        return self._machine_id

    async def wanted(self, resources: ResourceService) -> Desired:
        """Every channel this machine should be running, right now."""
        local = await self.machine_id()
        # The agent registry, read once per pass: an agent registered mid-tick
        # is picked up on the next one, two seconds later. It answers the only
        # question a uid cannot answer alone — which key the turn platform
        # dispatches this agent by (see ``Routing``).
        keys_by_uid = _agent_keys_by_uid(await resources.list(kind="agent"))
        live: Desired = {}
        routing: dict[str, Routing] = {}
        for r in await resources.list(kind="channel"):
            if not r.enabled:
                continue
            if not self._bound_here(r, local):
                continue
            route = self._routing(r, keys_by_uid)
            if route is None:
                continue
            live[r.name] = r
            routing[r.name] = route
        self.routing = routing
        return live

    def _bound_here(self, r: Resource, local: str | None) -> bool:
        """Whether this machine is the one the channel names.

        Two daemons answering one bot is the failure this prevents, and it is a
        failure no amount of later checking could undo — the platform has
        already been answered twice.

        Failing CLOSED covers all three of "not mine": another machine's id, an
        id no machine in the registry claims any more, and no id at all. None of
        them says "this machine", and starting on a guess is the one outcome
        that cannot be walked back. The management surface distinguishes them —
        it reports the binding and whether it names this machine — so a channel
        that is dark because it belongs elsewhere never looks like a channel
        that is dark because it crashed.
        """
        binding = r.config.get("runs_on")
        if local is None or binding == local:
            # Ours: forget any binding already reported, so a channel handed
            # away and later handed back reports the second departure too.
            self._foreign.pop(r.name, None)
            return True
        if self._foreign.get(r.name) != binding:
            self._foreign[r.name] = binding
            _logger.info(
                "channel.not_bound_here",
                extra={"channel": r.name, "runs_on": binding, "machine_id": local},
            )
        return False

    def _routing(self, r: Resource, keys_by_uid: Mapping[str, str]) -> Routing | None:
        """What this channel routes to, or ``None`` when it can route nowhere.

        Three ways a channel has no route, and all three end the same way: the
        adapter never starts, the management surface says the channel is not
        running, and no message is ever accepted only to be refused. That is
        the loud, early failure; the alternative is a bot that answers and then
        apologises, turn after turn.

        1. It names no agent at all. A ``default_agent`` is a reference to an
           agent resource and there is no value that could stand in for one, so
           a channel without it is bound to nobody.
        2. Its own scope excludes the agent it names. A channel's scope names
           the agents it may DRIVE (ADR per-agent-resource-scope), so a channel
           outside its own allow-list can drive nothing. Both write paths hold
           ``default_agent`` inside a non-empty scope (``on_update_config`` and
           ``validate_scope_for``), so the only case this normally reaches is
           the deliberate one — an empty allow-list, dormant, the owner
           switched the channel off — but it stays as written rather than
           narrowing to that check, as defence-in-depth for a row the scope-path
           validation never saw.
        3. The agent it names is not registered here. New with uids, and the
           honest reading of a reference that resolves to nothing: this vault
           has no such agent, so there is no key to route a turn by. It is also
           the ordinary state of a channel that arrived from another machine
           before that machine's agents did.
        """
        default_agent = r.config.get("default_agent")
        if not isinstance(default_agent, str) or not default_agent:
            self._not_started(r, None, "the channel names no default agent")
            return None
        if not is_active(r.scope, default_agent):
            self._not_started(r, default_agent, "its scope excludes its own default agent")
            return None
        agent_key = keys_by_uid.get(default_agent)
        if agent_key is None:
            self._not_started(r, default_agent, "its default agent is not registered here")
            return None
        return Routing(default_agent=agent_key, agent_scope=_scope_as_keys(r.scope, keys_by_uid))

    def _not_started(self, r: Resource, default_agent: str | None, reason: str) -> None:
        """Why a bot is quiet, in the record, without reconstructing it by hand."""
        _logger.info(
            "channel.not_started",
            extra={
                "channel": r.name,
                "default_agent": default_agent,
                "reason": reason,
                "scope": r.scope.to_json() if r.scope is not None else None,
            },
        )
