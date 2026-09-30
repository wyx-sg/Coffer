"""Vault files that need a person: hand edits validation refused
(spec vault-storage "Keep the last valid version when a hand edit is invalid").

Such a file is still on disk as the person left it, uncommitted; everything
reads the last valid version at ``HEAD`` until it is fixed. The item names the
file and the first reason; the action opens the file's problems.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.application.attention import AttentionAction, AttentionItem, Severity
from coffer.application.vault.ports import VaultWriterPort

KIND = "vault"


class VaultAttentionSource:
    name = "vault"
    feature: str | None = None

    def __init__(self, writer: VaultWriterPort) -> None:
        self._writer = writer

    async def items(self) -> Sequence[AttentionItem]:
        out: list[AttentionItem] = []
        for path, findings in sorted(self._writer.problems().items()):
            first = findings[0]
            out.append(
                AttentionItem(
                    kind=KIND,
                    uid=first.uid,
                    title=path,
                    reason_code=f"vault_{first.code.value}",
                    reason=f"{first.message} The last valid version stays in effect.",
                    severity=Severity.ERROR,
                    action=AttentionAction(
                        verb="review", method="GET", path="/api/v1/vault/problems"
                    ),
                )
            )
        return out


__all__ = ["VaultAttentionSource"]
