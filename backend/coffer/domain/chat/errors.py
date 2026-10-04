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
    """A route names no such message in that conversation — a resend of anything
    but one of its user messages, or the files of anything but one of its
    replies; never there, or deleted with its conversation."""

    code = "MESSAGE_NOT_FOUND"

    def __init__(self, conversation_id: str, message_id: str) -> None:
        super().__init__(f"no such message {message_id!r} in conversation {conversation_id!r}")
        self.conversation_id = conversation_id
        self.message_id = message_id


class ReplyFileNotFound(CofferError):  # noqa: N818
    """A reply's changed-file diff was asked for under a path the reply did not
    record (spec chat "Record what each reply changed in each file")."""

    code = "REPLY_FILE_NOT_FOUND"

    def __init__(self, message_id: str, path: str) -> None:
        super().__init__(f"reply {message_id!r} recorded no changes to {path!r}")
        self.message_id = message_id
        self.path = path


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


class AttachmentUnavailable(CofferError):  # noqa: N818
    """A thread asked for the bytes of a file no message of that conversation
    references, or one the media sweep has since deleted (spec chat "Show a
    message's attachments in the thread"). The chip stays a plain chip."""

    code = "ATTACHMENT_UNAVAILABLE"

    def __init__(self, attachment_id: str) -> None:
        super().__init__(f"attachment not available: {attachment_id!r}")
        self.attachment_id = attachment_id


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
