"""The reasoning levels Claude Code can be run at, read from the runtime that
runs it.

Same discipline as ``claude_binary_models``: Coffer writes no list down. The
levels are the ``EffortLevel`` alias in the installed Claude Agent SDK — the
same package ``claude_sdk_agent`` drives a turn with, and the one that turns a
chosen level into the CLI's ``--effort`` flag — so the menu and the thing that
consumes it cannot disagree, and an SDK release that adds a level reaches the
picker without an edit here.

WHY EVERY ENTRY GETS THE SAME SET, unlike Codex. Codex reports
``supportedReasoningEfforts`` per model because its protocol takes the level per
turn against a named model. Claude's SDK takes ``effort`` as an option on the
session, not on the model, and documents its own per-model degradation
(``xhigh`` falls back to ``high`` where the model cannot do it). There is
therefore no per-model menu to read — the honest answer for every Claude Code
entry is the same one.

WHY NO DEFAULT IS NAMED. ``ClaudeAgentOptions.effort`` defaults to ``None``,
which means "whatever the CLI decides"; the CLI does not tell us what that is.
The SDK's prose calls ``high`` the default, but prose is not a machine-readable
fact and a picker that names the wrong default is worse than one that names
none — so ``default_effort`` stays ``None`` and the picker simply offers
"the agent's own".

WHAT THIS COSTS WHEN IT BREAKS. An SDK without the alias (an older pin, a
vendored stub) yields an empty tuple: every Claude Code model then reports no
levels, the pickers hide themselves, and turns run exactly as they did before
this existed. It cannot return wrong data and it cannot fail a lookup.
"""

from __future__ import annotations

import functools
import logging
from typing import get_args

_log = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def claude_effort_levels() -> tuple[str, ...]:
    """The levels in the SDK's own order, or ``()`` when it names none.

    Cached because it is read once per model on every catalogue render and the
    answer cannot change without restarting the daemon that imported the SDK.
    """
    try:
        from claude_agent_sdk import EffortLevel
    except Exception:
        # An SDK that predates the field, or a partial install. Not an error:
        # the agent simply offers no level, which is where Coffer started.
        _log.debug("agent.claude_effort.unavailable", exc_info=True)
        return ()
    return tuple(level for level in get_args(EffortLevel) if isinstance(level, str) and level)


__all__ = ["claude_effort_levels"]
