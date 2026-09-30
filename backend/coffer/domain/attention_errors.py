"""Errors of the cross-kind attention list (the Overview's "needs you")."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class AttentionNotIgnorable(CofferError):  # noqa: N818
    """The key names no item that can be ignored right now: nothing is listed
    under it, or what is listed is broken rather than informational."""

    code = "ATTENTION_NOT_IGNORABLE"

    def __init__(self, key: str) -> None:
        super().__init__(f"no informational attention item {key!r} to ignore")
        self.key = key


__all__ = ["AttentionNotIgnorable"]
