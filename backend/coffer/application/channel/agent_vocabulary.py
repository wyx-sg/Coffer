"""Translating between the two names an agent has (spec channels FR-013).

A channel's ``default_agent`` is a turn-platform **agent key** — ``claude_code``,
``codex`` — because that is what the turn platform routes on
(``conversation_spec`` hands it straight to the registry) and what ``/agent``
offers. A resource ``scope`` is a list of **registry names** — ``claude-code``
— because that is what an agent resource is called, and what the reach picker
shows.

They are different vocabularies for the same thing, and three places used to
compare them directly: the config write path, the scope write path, and the
runtime's own gate. Every one of them read a correctly-narrowed scope as
excluding the channel's default agent. The user-visible shape of the bug was
worse than a refusal: narrowing a channel's reach to ``claude-code`` — the only
name the picker offers — was rejected, and the only value that passed was the
agent key, which the picker then had to render as a name registered nowhere.

So the comparison happens in ONE vocabulary, and this is where the other one
is translated in. Agent keys win: they are what the runtime actually routes on,
and a channel that names an agent key no registry name maps to is a channel
that will not run whatever the scope says.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from coffer.domain.resource import Resource
from coffer.domain.scope import Scope

#: Where an agent resource keeps its type — the agent key the turn platform
#: routes on. Read as a raw string rather than through ``AgentConfig``: the
#: channel kind may not import the agent kind (the cross-kind import contract),
#: and this needs no judgement about the value anyway. A key no provider is
#: registered under matches nothing, which is the right answer for a row this
#: vault cannot route to.
_TYPE = "type"


def agent_key_by_name(agents: Iterable[Resource]) -> dict[str, str]:
    """Every registered agent's resource NAME mapped to its agent KEY.

    The one place the translation is built, so the write paths and the runtime
    gate cannot end up disagreeing about what a scope admits.
    """
    out: dict[str, str] = {}
    for resource in agents:
        agent_key = resource.config.get(_TYPE)
        if isinstance(agent_key, str) and agent_key:
            out[resource.name] = agent_key
    return out


def scope_agent_keys(scope: Scope | None, types_by_name: Mapping[str, str]) -> list[str] | None:
    """The agent KEYS a scope admits, or ``None`` when it admits every agent.

    A name the registry does not know is dropped rather than passed through:
    it maps to no agent key, so it can admit no agent, and keeping it would
    only let it masquerade as one in an error message.
    """
    if scope is None or scope.agents is None:
        return None
    return sorted({types_by_name[name] for name in scope.agents if name in types_by_name})


def as_agent_keys(scope: Scope | None, types_by_name: Mapping[str, str]) -> Scope | None:
    """``scope`` rewritten into agent keys, for a reader that speaks only those.

    The channel runtime stamps a channel's scope onto its binding, and
    everything downstream of the binding — the ``/agent`` listing, the ``/agent``
    card, the validation of a chosen key, the turn's own routing — asks about an
    agent KEY. Translating once, here, is why none of them has to know that a
    scope was written in another vocabulary.
    """
    keys = scope_agent_keys(scope, types_by_name)
    return None if keys is None else Scope(agents=keys)


def drives(scope: Scope | None, agent_key: str, types_by_name: Mapping[str, str]) -> bool:
    """Whether a channel carrying ``scope`` may drive ``agent_key``.

    The channel-shaped reading of :func:`coffer.domain.scope.is_active`: an
    unrestricted scope drives anything, and a restricted one drives what it
    names — once what it names is read in the same vocabulary as the question.
    """
    keys = scope_agent_keys(scope, types_by_name)
    return keys is None or agent_key in keys


__all__ = ["agent_key_by_name", "as_agent_keys", "drives", "scope_agent_keys"]
