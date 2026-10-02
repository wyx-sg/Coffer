"""The secret boundary's contribution to the Overview's "needs you" list.

Spec secret "Turn the protection off only through the desktop app": while the
approval requirement is off, a secret goes to any new destination without
asking, which is something a person who switched it off a while ago should be
told is still the case. The item's action is the call that turns it back on,
which needs no approval — it only narrows.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence

from coffer.application.attention import AttentionAction, AttentionItem, Severity

KIND = "secret"
REASON_CODE = "secret_approval_off"


class SecretAttentionSource:
    name = "secret"
    feature: str | None = None

    def __init__(self, protections_on: Callable[[], bool]) -> None:
        self._protections_on = protections_on

    async def items(self) -> Sequence[AttentionItem]:
        if await asyncio.to_thread(self._protections_on):
            return []
        return [
            AttentionItem(
                kind=KIND,
                uid=None,
                title="Secret approval",
                reason_code=REASON_CODE,
                reason=(
                    "Secret approval is off: a secret can be sent to a new destination "
                    "without asking."
                ),
                severity=Severity.WARNING,
                action=AttentionAction(
                    verb="turn_on",
                    method="PUT",
                    path="/api/v1/settings/secret-boundary",
                    body={"require_approval": True},
                ),
            )
        ]


__all__ = ["SecretAttentionSource"]
