"""Which channels this machine runs — the three gates, and only the gates.

``ChannelRuntime`` owns lifecycle: start an adapter, stop it, keep the
listener, the tunnel and the websocket in step. This module owns the question
it asks first, every tick — *which channels are mine to run?* — and the answer
has three parts, each a different kind of fact:

1. **enabled** — is this resource live at all, here.
2. **the machine binding** — is this channel's `runs_on` this machine (spec
   channels ``## Where a channel runs``). This one is about somebody else's
   machine, which is why it comes ahead of the third.
3. **scope** — may the channel drive its own default agent (ADR
   per-agent-resource-scope), read inverted for this kind.

They live together because they are one predicate to the reconciler and three
separate arguments to a reader, and because the second one is new: a channel
travels between machines now, so the resource table is no longer a private list
and "enabled here" stopped being the whole answer.

The gate keeps a little memory (``Gate``), and it is memory about *reporting*
rather than about state: a channel bound elsewhere stays bound elsewhere, so
saying so every two seconds would bury the daemon log under a fact that is not
changing.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from coffer.application.channel.agent_vocabulary import (
    agent_key_by_name,
    as_agent_keys,
    drives,
)
from coffer.application.channel.runtime_supervision import Desired
from coffer.domain.channel.config import DEFAULT_AGENT
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.resource_service import ResourceService

_logger = logging.getLogger(__name__)


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
    #: The scope of each channel the last pass found live, keyed by name, and
    #: rewritten into agent KEYS (``agent_vocabulary.as_agent_keys``) because
    #: that is the vocabulary every reader downstream of the binding speaks.
    #: Read back by the runtime, which stamps it onto the binding at start — so
    #: a scope edit reaches `/agent` within one tick rather than at the next
    #: daemon restart.
    scopes: dict[str, Scope | None] = field(default_factory=dict)

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
        # A scope names agents by RESOURCE NAME and a channel names its default
        # by AGENT KEY, so the gate needs the registry to compare them at all
        # (``agent_vocabulary``). Read once per pass: an agent registered mid-
        # tick is picked up on the next one, two seconds later.
        agent_keys = agent_key_by_name(await resources.list(kind="agent"))
        live: list[Resource] = []
        for r in await resources.list(kind="channel"):
            if not r.enabled:
                continue
            if not self._bound_here(r, local):
                continue
            if not self._may_drive(r, agent_keys):
                continue
            live.append(r)
        self.scopes = {r.name: as_agent_keys(r.scope, agent_keys) for r in live}
        return {r.name: (r.id, dict(r.config)) for r in live}

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

    def _may_drive(self, r: Resource, agent_keys: Mapping[str, str]) -> bool:
        """Whether the channel may drive its own default agent.

        A channel's scope names the agents it may DRIVE (ADR
        per-agent-resource-scope), so a channel whose own ``default_agent`` is
        outside it can drive nothing and does not run. That is the loud, early
        failure: the adapter never starts, the management surface says the
        channel is not running, and no message is ever accepted only to be
        refused.

        Both write paths hold ``default_agent`` inside a non-empty scope (the
        channel kind's ``on_update_config`` and ``validate_scope_for``), so the
        only case this can reach is the deliberate one: an empty allow-list,
        dormant, the owner switched the channel off. It stays as written rather
        than narrowing to that check, as defence-in-depth for a row that
        predates the scope-path validation and could still carry the
        inconsistent combination.

        ``agent_keys`` is the registry's name→key map: the scope answers in
        resource names and ``default_agent`` is an agent key, so without it
        this compared two vocabularies and read every correctly-narrowed scope
        as excluding the channel's own agent (``agent_vocabulary``).
        """
        # Read straight off the stored config rather than parsing it: a row this
        # cannot read is not one the adapter factory could start either.
        default_agent = str(r.config.get("default_agent") or DEFAULT_AGENT)
        if drives(r.scope, default_agent, agent_keys):
            return True
        # The scope and the agent it refused are both in the record, so the
        # reason a bot went quiet is readable without reconstructing the
        # comparison by hand.
        _logger.info(
            "channel.not_started",
            extra={
                "channel": r.name,
                "default_agent": default_agent,
                "scope": r.scope.to_json() if r.scope is not None else None,
            },
        )
        return False
