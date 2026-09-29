"""Kind-agnostic vocabulary: whether an agent will run a hook Coffer installed.

Two kinds have to agree on it: the ``memory`` kind's delivery adapters read an
agent's trust record and answer with one of these values, and the ``agent``
kind's hooks listing reports it. Neither kind may import the other
(import-linter cross-kind contracts), so the values live here, in the
kind-agnostic domain, the way ``domain.connection`` holds the one string the
provider and chat kinds share.
"""

from __future__ import annotations

from enum import StrEnum


class HookTrust(StrEnum):
    """Whether the agent will actually run Coffer's installed hook.

    Codex runs a hook only after the user has reviewed it: it records trust
    against a hash of the hook's definition, so a new or changed hook is
    skipped — silently — until the user trusts it with ``/hooks``. Coffer never
    writes that trust itself (spec agent-registry/codex "Leave Codex's
    internal-state tables untouched"); it reads it and says so.
    """

    #: The agent has no review step (Claude Code).
    NOT_REQUIRED = "not_required"
    #: Reviewed and trusted for exactly this definition.
    TRUSTED = "trusted"
    #: Never reviewed.
    UNTRUSTED = "untrusted"
    #: Trusted once, for a different definition — every change to the
    #: command lands here until the user approves it again.
    MODIFIED = "modified"
    #: The user switched the hook off in the agent.
    DISABLED = "disabled"
    #: The agent's trust record could not be read.
    UNKNOWN = "unknown"


__all__ = ["HookTrust"]
