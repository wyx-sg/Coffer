"""Typed per-conversation agent provider config (spec chat "Record the agent on
each conversation").

The chat platform keeps a small per-conversation blob of provider-owned state:
the working directory a turn runs in, the upstream session id to ``--resume``,
an optional model override, and — for an agent that takes one as its own field
rather than as part of the model name — how hard that model should think. This
value object replaces the former untyped ``dict[str, Any]`` blob: the providers
validate raw input into it and the persistence layer serializes it to/from the
``conversations.agent_config`` JSON column.

Lives in the domain (a pure, dependency-free frozen dataclass) because both the
application-layer repo port and the infrastructure persistence/providers
reference it, and the layering forbids ``application`` importing ``infrastructure``.

Internal only: the HTTP ``agent_config`` request field stays an opaque object
(no wire-contract change). A provider projects that raw input into this typed
shape at ``init_conversation``; ``cwd`` is therefore optional here — a
conversation whose provider has not (yet) stored one is represented faithfully
rather than rejected at parse time, and ``build_adapter`` is what requires a cwd.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentConfig:
    """A conversation's provider-owned config: cwd, resume session, model, effort.

    ``effort`` is the agent's own reasoning-effort setting, kept beside the model
    rather than inside it because that is how the agent takes it: Codex's
    app-server has a separate ``effort`` field on a turn, and its own picker
    offers the two as one choice. Only an agent that reports efforts for a model
    (see ``AgentModel.efforts``) does anything with it; the others ignore it.
    """

    cwd: str | None = None
    session_id: str | None = None
    model: str | None = None
    effort: str | None = None

    def to_json(self) -> dict[str, Any]:
        """Serialize to the dict stored in the JSON column, omitting unset fields."""
        data: dict[str, Any] = {}
        if self.cwd is not None:
            data["cwd"] = self.cwd
        if self.session_id is not None:
            data["session_id"] = self.session_id
        if self.model is not None:
            data["model"] = self.model
        if self.effort is not None:
            data["effort"] = self.effort
        return data

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> AgentConfig:
        """Parse a stored blob, tolerating legacy/partial shapes.

        Non-string fields are dropped to ``None`` so a malformed blob degrades to
        an unconfigured config rather than raising.
        """

        def _str(value: Any) -> str | None:
            return value if isinstance(value, str) and value else None

        return cls(
            cwd=_str(raw.get("cwd")),
            session_id=_str(raw.get("session_id")),
            model=_str(raw.get("model")),
            effort=_str(raw.get("effort")),
        )


__all__ = ["AgentConfig"]
