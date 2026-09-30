"""How a git remote can fail, by what a person can do about it."""

from __future__ import annotations

from enum import StrEnum

from coffer.domain.error_base import CofferError


class RemoteProblem(StrEnum):
    UNREACHABLE = "unreachable"
    AUTH_FAILED = "auth_failed"
    PUSH_REJECTED = "push_rejected"
    OTHER = "other"


class RemoteFailed(CofferError):  # noqa: N818
    """The remote could not be reached, refused the credential, or refused
    the push. ``problem`` says which; ``detail`` is git's redacted stderr."""

    code = "SYNC_REMOTE_FAILED"

    def __init__(self, problem: RemoteProblem, detail: str) -> None:
        self.problem = problem
        self.detail = detail
        super().__init__(detail)


__all__ = ["RemoteFailed", "RemoteProblem"]
