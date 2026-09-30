"""A chore Coffer hands to an agent instead of doing it itself.

Coffer is AI-native: a chore that depends on the machine — installing a tool,
setting something up, troubleshooting — is not run by the daemon but written
up as a prompt the person gives to their agent (spec skill-manager "Hand a
required command to an agent with a prompt"). Each feature supplies only its
facts; this module owns the shape and the rules every hand-off carries, so the
prompts read alike wherever they come from.

A hand-off is three parts, rendered in this order:

* ``task`` — one sentence saying what to do;
* ``facts`` — what the agent needs to know, one short line each;
* ``steps`` — how to go about it and how to confirm it worked, one sentence
  each, followed by the rules every hand-off carries (:data:`STANDING_RULES`).

The text is built server-side so the command line and the web UI hand over
the same words. It is plain text with no markup beyond a leading ``-`` on each
fact, because it is pasted into whichever agent the person uses.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Asking before anything elevated or system-wide.
ASK_BEFORE_SYSTEM_CHANGES = (
    "Check with me before running anything that needs sudo or changes system settings."
)
#: Credentials stay with the person.
NO_CREDENTIALS = (
    "If a login is needed, tell me how and I will log in myself; do not handle my credentials."
)

#: The rules every hand-off ends with, whatever the chore.
STANDING_RULES: tuple[str, ...] = (ASK_BEFORE_SYSTEM_CHANGES, NO_CREDENTIALS)


@dataclass(frozen=True)
class Handoff:
    """What a feature knows about a chore; :func:`render_handoff` writes it up."""

    task: str
    facts: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()


def render_handoff(handoff: Handoff) -> str:
    """The prompt text: the task, a blank line, the facts as ``-`` lines, a
    blank line, then the steps and the standing rules one per line."""
    parts = [handoff.task.strip()]
    facts = [f"- {fact.strip()}" for fact in handoff.facts if fact.strip()]
    if facts:
        parts.append("\n".join(facts))
    steps = [step.strip() for step in handoff.steps if step.strip()]
    steps.extend(rule for rule in STANDING_RULES if rule not in steps)
    parts.append("\n".join(steps))
    return "\n\n".join(parts)


__all__ = [
    "ASK_BEFORE_SYSTEM_CHANGES",
    "NO_CREDENTIALS",
    "STANDING_RULES",
    "Handoff",
    "render_handoff",
]
