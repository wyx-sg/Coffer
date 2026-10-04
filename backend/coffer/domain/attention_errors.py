"""Errors of the cross-kind attention list (the Overview's "needs you")."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class AttentionNotIgnorable(CofferError):  # noqa: N818
    """The key names no item in the list right now, so there is nothing to ignore."""

    code = "ATTENTION_NOT_IGNORABLE"

    def __init__(self, key: str) -> None:
        super().__init__(f"no attention item {key!r} to ignore")
        self.key = key


__all__ = ["AttentionNotIgnorable"]
