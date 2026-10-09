"""Errors of reading the invocation log; surfaces map codes to statuses.

Spec mcp-gateway "Record invocations with redacted, bounded content".
"""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class InvocationNotFound(CofferError):  # noqa: N818
    """No call in the invocation log has this id (it never existed, or retention pruned it)."""

    code = "INVOCATION_NOT_FOUND"

    def __init__(self, invocation_id: int) -> None:
        super().__init__(f"no call with id {invocation_id} in the invocation log")
