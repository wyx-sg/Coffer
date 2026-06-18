"""Chat-platform domain errors (spec 008-agent-chat).

Split out of ``coffer.domain.errors`` for the file-size limit; that module
re-exports everything here, so ``from coffer.domain.errors import
ConversationNotFound`` keeps working everywhere.
"""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class ConversationNotFound(CofferError):  # noqa: N818
    code = "CONVERSATION_NOT_FOUND"

    def __init__(self, conversation_id: str) -> None:
        super().__init__(f"conversation not found: {conversation_id!r}")
        self.conversation_id = conversation_id


class ModelNotFound(CofferError):  # noqa: N818
    code = "MODEL_NOT_FOUND"

    def __init__(self, model_id: str) -> None:
        super().__init__(f"model config not found: {model_id!r}")
        self.model_id = model_id


class ModelRejected(CofferError):  # noqa: N818
    """``ModelConfig`` failed validation. ``reason``: missing_credential |
    missing_base_url | duplicate_name | empty_display_name."""

    code = "MODEL_REJECTED"

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class NoModelConfigured(CofferError):  # noqa: N818
    """Raised when a chat turn is started but no model has been configured."""

    code = "NO_MODEL_CONFIGURED"

    def __init__(self) -> None:
        msg = "no model is configured; register at least one model under Settings → Models"
        super().__init__(msg)


class TurnInProgress(CofferError):  # noqa: N818
    """Raised when a second message is sent to a conversation with an active turn."""

    code = "TURN_IN_PROGRESS"

    def __init__(self, conversation_id: str) -> None:
        super().__init__(
            f"conversation {conversation_id!r} already has a turn in progress; "
            "wait for it to complete before sending another message"
        )
        self.conversation_id = conversation_id


class UnknownAgent(CofferError):  # noqa: N818
    """Raised when a conversation names an ``agent_key`` no provider is registered for."""

    code = "UNKNOWN_AGENT"

    def __init__(self, agent_key: str) -> None:
        super().__init__(f"unknown agent: {agent_key!r}; no agent provider is registered for it")
        self.agent_key = agent_key


class AgentConfigRejected(CofferError):  # noqa: N818
    """Agent provider rejected its ``agent_config`` at conversation creation.
    ``reason`` is a short machine token (e.g. ``"model_not_found"``)."""

    code = "AGENT_CONFIG_REJECTED"

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
