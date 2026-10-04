"""Chat-platform domain errors (the turn platform, spec chat).

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


class QuestionClosed(CofferError):  # noqa: N818
    """An answer to a question that is no longer waiting — already answered
    (the first answer wins), cancelled, or gone with its turn (spec chat "Pause a
    turn on a question for the owner")."""

    code = "QUESTION_CLOSED"

    def __init__(self, question_id: str) -> None:
        super().__init__(
            f"question {question_id!r} is not waiting for an answer any more "
            "(it was answered, or its turn ended)"
        )
        self.question_id = question_id


class QuestionAnswerInvalid(CofferError):  # noqa: N818
    """An answer that does not fit its question: an unknown option, several
    options on a single-choice question, or nothing at all."""

    code = "QUESTION_ANSWER_INVALID"

    def __init__(self, reason: str) -> None:
        super().__init__(f"invalid answer: {reason}")
        self.reason = reason
