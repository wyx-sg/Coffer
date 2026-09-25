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


class AttachmentTooLarge(CofferError):  # noqa: N818
    """An upload from the web composer is over the per-file ceiling; the message
    names the limit so the refusal is actionable (spec chat "Upload a file for a
    web message")."""

    code = "ATTACHMENT_TOO_LARGE"

    def __init__(self, size: int, limit: int) -> None:
        super().__init__(
            f"attachment is {size} bytes; the limit is {limit} bytes ({limit // (1024 * 1024)} MB)"
        )
        self.size = size
        self.limit = limit


class AttachmentTypeUnsupported(CofferError):  # noqa: N818
    """An upload whose type no agent can use from a turn (video, archives,
    executables, other binaries)."""

    code = "ATTACHMENT_TYPE_UNSUPPORTED"

    def __init__(self, filename: str, mime: str | None) -> None:
        super().__init__(
            f"unsupported attachment type for {filename!r} ({mime or 'unknown'}): "
            "attach an image, a document, audio, or a text file"
        )
        self.filename = filename


class AttachmentNotFound(CofferError):  # noqa: N818
    """A message names an attachment id no upload stored — never uploaded, or
    its file was pruned. Nothing is persisted or queued for that message."""

    code = "ATTACHMENT_NOT_FOUND"

    def __init__(self, attachment_id: str) -> None:
        super().__init__(f"attachment not found: {attachment_id!r}; upload the file again")
        self.attachment_id = attachment_id


class MessageNotFound(CofferError):  # noqa: N818
    """A resend names no user message of that conversation — never sent there,
    deleted with its conversation, or an assistant reply rather than a prompt."""

    code = "MESSAGE_NOT_FOUND"

    def __init__(self, conversation_id: str, message_id: str) -> None:
        super().__init__(f"no user message {message_id!r} in conversation {conversation_id!r}")
        self.conversation_id = conversation_id
        self.message_id = message_id


class AttachmentExpired(CofferError):  # noqa: N818
    """A message being sent again references a file that is no longer on disk —
    the 30-day media sweep deleted it. The resend is refused rather than sent
    without the file (spec chat "Show a failed turn as one inline banner with
    Retry")."""

    code = "ATTACHMENT_EXPIRED"

    def __init__(self, filename: str) -> None:
        super().__init__(
            f"attachment {filename!r} is no longer stored (uploads are kept for 30 days); "
            "attach it again"
        )
        self.filename = filename
